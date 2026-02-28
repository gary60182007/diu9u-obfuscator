"""
Runtime-trace the VM to map opcodes to operations.
Hook the VM executor to log each opcode and its register effects.
Instead of parsing the minified source, we trace execution directly.
"""
import sys, time, json, re
sys.path.insert(0, '.')

with open(r'unobfuscator\pending crack\bloxburg_script.lua', 'r', encoding='utf-8', errors='replace') as f:
    source = f.read()

exec(open('run_luraph_test.py').read().split("print('Reading source...')")[0])
source = preprocess_luau(source)
from unobfuscator.utils.lua_runtime import LuaRuntimeWrapper, LuaRuntimeError

modified = source

# Strategy: Hook r[56] (the VM executor factory) to wrap each created executor
# The executor function is: r[56] = function(C, W) ... end
# where C = proto data table, W = upvalues
# It returns a closure J that IS the executor

# Find the zy function that assigns r[56]
# Pattern: zy=function(z,r)(r)[56]=function(C,W) ...
zy_pat = re.compile(r'zy=function\((\w+),(\w+)\)')
zy_m = zy_pat.search(modified)
zy_pos = zy_m.start()
zy_z, zy_r = zy_m.group(1), zy_m.group(2)
print(f"zy function at pos {zy_pos}, params: z={zy_z}, r={zy_r}")

# Find r[56] = function(C, W) inside zy
r56_pat = re.compile(r'\(' + zy_r + r'\)\[(?:56|0[xX]38|0[bB]111000)\]\s*=\s*function\((\w+),(\w+)\)')
r56_m = r56_pat.search(modified, zy_pos)
r56_C, r56_W = r56_m.group(1), r56_m.group(2)
print(f"r[56] = function({r56_C}, {r56_W}) at pos {r56_m.start()}")

# Now inject a wrapper around r[56] AFTER zy assigns it
# Find the end of zy function
# zy_end should be at the end; marker

# Instead, wrap d9 to hook r[56] after it's been set
d9_pat = re.compile(r'(d9=function\((\w+),(\w+),(\w+),(\w+)\))')
d9_m = d9_pat.search(modified)
d9_C = d9_m.group(4)

# Inject trace hook: wrap r[56] to log opcode, register effects for first N instructions
inject = f"""do
local _st={d9_C}
local _orig56=_st[56]
_G._op_log={{}}
_G._op_count2=0
_G._max_log=50000
_st[56]=function(_C,_W)
  local _exec=_orig56(_C,_W)
  local _opcodes=_C[4]
  local _nregs=_C[10]
  return function(...)
    if _G._op_count2>=_G._max_log then return _exec(...) end
    local _pid=(_G._cur_pid or 0)
    local _before={{}}
    local _result={{_exec(...)}}
    return unpack(_result)
  end
end
end;"""

# Actually, tracing inside the executor is harder because we can't easily hook the while loop.
# Better approach: trace at the PROTOTYPE level - log which protos are called and with what args.
# Or: instrument the opcode dispatch by modifying the source.

# Even better: Just trace which handlers are reached for each opcode value.
# Since the executor uses T=Y[y] and then dispatches, I can find all the leaf handlers
# and add logging there.

# Simplest practical approach: extract what each opcode does from the static handler analysis,
# supplemented by runtime observation of register changes.

# Let me use a different strategy: for each opcode in our extracted data,
# find what operation it corresponds to by looking at the surrounding instructions
# and constant references.

# Actually, the SIMPLEST approach: map opcodes by their operand patterns and frequency
# to standard Lua 5.1 opcodes, then verify with runtime tracing.

# Load the proto data
with open('all_protos_data.json', 'r', encoding='utf-8') as f:
    all_protos = json.load(f)

with open('c2_full_data.json', 'r', encoding='utf-8') as f:
    c2_data = json.load(f)

# Build a comprehensive opcode profile for each opcode:
# - frequency
# - operand patterns (which of A,B,C,K are used)
# - surrounding opcodes
# - associated constant types
from collections import defaultdict

opcode_profiles = defaultdict(lambda: {
    'count': 0,
    'patterns': defaultdict(int),
    'has_c2': 0,
    'c2_types': defaultdict(int),
    'a_vals': [],
    'b_vals': [],
    'c_vals': [],
    'prev_ops': defaultdict(int),
    'next_ops': defaultdict(int),
})

for p in all_protos:
    pid = str(p['id'])
    opcodes = p.get('C4', [])
    c7 = p.get('C7', [])
    c8 = p.get('C8', [])
    c9 = p.get('C9', [])
    p_c2 = c2_data.get(pid, {})
    
    for i, op in enumerate(opcodes):
        if op is None:
            continue
        prof = opcode_profiles[op]
        prof['count'] += 1
        
        a = c7[i] if i < len(c7) else 0
        b = c8[i] if i < len(c8) else 0
        c = c9[i] if i < len(c9) else 0
        has_k = str(i+1) in p_c2
        
        pat = f"{'A' if a else '_'}{'B' if b else '_'}{'C' if c else '_'}{'K' if has_k else '_'}"
        prof['patterns'][pat] += 1
        
        if has_k:
            prof['has_c2'] += 1
            entry = p_c2[str(i+1)]
            if entry.startswith('n:'):
                prof['c2_types']['number'] += 1
            elif entry.startswith('s:'):
                prof['c2_types']['string'] += 1
            elif entry.startswith('t:'):
                prof['c2_types']['table'] += 1
            else:
                prof['c2_types']['other'] += 1
        
        if prof['count'] <= 100:
            if a: prof['a_vals'].append(a)
            if b: prof['b_vals'].append(b)
            if c: prof['c_vals'].append(c)
        
        if i > 0 and opcodes[i-1] is not None:
            prof['prev_ops'][opcodes[i-1]] += 1
        if i < len(opcodes)-1 and opcodes[i+1] is not None:
            prof['next_ops'][opcodes[i+1]] += 1

# Now try to classify each opcode based on the handler analysis + profiles
# Load the handler analysis from the static extraction
handler_map = {}

# From the extract_i3_dispatch.py output, manually map the identified handlers
# These are opcodes where we could see the operation in the handler body
static_handlers = {
    # GETGLOBAL variants (s[reg] = <global>)
    312: 'GETGLOBAL_collectgarbage', 34: 'GETGLOBAL_tostring',
    69: 'GETGLOBAL_select', 91: 'GETGLOBAL_loadstring',
    96: 'GETGLOBAL_pcall', 41: 'GETGLOBAL_debug',
    9: 'GETGLOBAL_getrenv', 139: 'GETGLOBAL_writefile',
    157: 'GETGLOBAL_coroutine', 154: 'GETGLOBAL_Vector2',
    160: 'GETGLOBAL_ColorSequence', 144: 'GETGLOBAL_readfile',
    
    # Operations
    116: 'CONCAT_RR',  # s[a[y]] = s[D[y]]..s[Z[y]]
    89: 'LT_JMP',      # if s[a[y]] < s[Z[y]] then y=D[y]
    79: 'NE_JMP',       # if s[D[y]] ~= s[Z[y]] then y=a[y]
    267: 'TEST_FALSE',  # if not s[Z[y]] then y=D[y]
    109: 'LE_IMM_JMP',  # if not(s[a[y]]<=m[y]) then y=Z[y]
    129: 'SETUPVAL',    # r[4][D[y]] = s[Z[y]]
    124: 'LT_IMM',      # s[Z[y]] = s[D[y]] < w[y]
    321: 'CALL_VAR',    # s[H] = s[H](r[29](X,s,H+1))
    277: 'CALL_MULTI',  # complex call
    282: 'CALL_VARARG2',
    250: 'GETUPVAL_T',  # H=W[a[y]]; s[Z[y]]=H[2][H[1]][s[D[y]]]
    300: 'RETURN_NIL',
    287: 'ARITH_FUNC',  # s[Z[y]] = r[37](s[D[y]], s[a[y]])
    305: 'GETGLOBAL_bit',
    66: 'GETUPVAL_U',   # s[Z[y]] = N[U]
    101: 'GT',          # s[Z[y]] = s[a[y]] > s[D[y]]
    270: 'NE_IMM',      # s[a[y]] = m[y] ~= q[y]
    76: 'ARITH_FUNC2',  # s[Z[y]] = r[37](s[D[y]], w[y])
    51: 'ASSIGN_W',     # F=Z[y]; k=W; K=D[y]  
    71: 'SETUPVAL_TABLE', # W[Z[y]][s[D[y]]] = w[y]
    39: 'TABLE_MOVE',   # table.move variant
}

# Classify all opcodes
print(f"{'Op':>4} {'Count':>6} {'Pattern':>10} {'K%':>5} {'C2Type':>10} {'Classification':>25}")
print('-' * 75)

by_count = sorted(opcode_profiles.items(), key=lambda x: x[1]['count'], reverse=True)
for op, prof in by_count[:60]:
    count = prof['count']
    top_pat = max(prof['patterns'].items(), key=lambda x: x[1])[0] if prof['patterns'] else '????'
    k_pct = prof['has_c2'] / count * 100 if count > 0 else 0
    c2_top = max(prof['c2_types'].items(), key=lambda x: x[1])[0] if prof['c2_types'] else '-'
    
    classification = static_handlers.get(op, '')
    
    if not classification:
        # Heuristic classification based on patterns
        if k_pct > 90 and c2_top == 'string':
            classification = 'CONST_STRING'
        elif k_pct > 90 and c2_top == 'number':
            classification = 'CONST_NUMBER'
        elif k_pct > 90:
            classification = 'CONST_LOAD'
        elif top_pat == 'A___':
            classification = 'REG_ONLY_A'
        elif top_pat == '_B__':
            classification = 'REG_ONLY_B'
        elif top_pat == '__C_':
            classification = 'REG_ONLY_C'  
        elif top_pat == 'ABC_':
            classification = 'THREE_REG'
        elif top_pat == '_BC_':
            classification = 'TWO_REG_BC'
        elif top_pat == 'AB__':
            classification = 'TWO_REG_AB'
        elif top_pat == 'A_C_':
            classification = 'TWO_REG_AC'
        elif top_pat == 'ABCK':
            classification = 'THREE_REG_K'
        elif top_pat == 'A_CK':
            classification = 'TWO_REG_AK'
        elif top_pat == '_BCK':
            classification = 'TWO_REG_BK'
    
    print(f"{op:4d} {count:6d} {top_pat:>10} {k_pct:5.1f} {c2_top:>10} {classification:>25}")

# Save the full profile data
output = {}
for op, prof in opcode_profiles.items():
    output[op] = {
        'count': prof['count'],
        'patterns': dict(prof['patterns']),
        'has_c2': prof['has_c2'],
        'c2_types': dict(prof['c2_types']),
        'classification': static_handlers.get(op, ''),
    }

with open('opcode_profiles.json', 'w') as f:
    json.dump(output, f, indent=1, sort_keys=True)
print(f"\nSaved to opcode_profiles.json")

# Cross-reference with the known Lua 5.1 opcodes
# Standard Lua 5.1 has 38 opcodes:
lua51_ops = {
    'MOVE': 'AB', 'LOADK': 'ABx', 'LOADBOOL': 'ABC', 'LOADNIL': 'AB',
    'GETUPVAL': 'AB', 'GETGLOBAL': 'ABx', 'GETTABLE': 'ABC',
    'SETGLOBAL': 'ABx', 'SETUPVAL': 'AB', 'SETTABLE': 'ABC',
    'NEWTABLE': 'ABC', 'SELF': 'ABC',
    'ADD': 'ABC', 'SUB': 'ABC', 'MUL': 'ABC', 'DIV': 'ABC',
    'MOD': 'ABC', 'POW': 'ABC', 'UNM': 'AB', 'NOT': 'AB',
    'LEN': 'AB', 'CONCAT': 'ABC',
    'JMP': 'sBx', 'EQ': 'ABC', 'LT': 'ABC', 'LE': 'ABC',
    'TEST': 'AC', 'TESTSET': 'ABC',
    'CALL': 'ABC', 'TAILCALL': 'ABC', 'RETURN': 'AB',
    'FORLOOP': 'AsBx', 'FORPREP': 'AsBx',
    'TFORLOOP': 'AC', 'SETLIST': 'ABC',
    'CLOSE': 'A', 'CLOSURE': 'ABx', 'VARARG': 'AB',
}

print(f"\nStandard Lua 5.1 has {len(lua51_ops)} opcodes")
print(f"Luraph VM has {len(opcode_profiles)} unique opcodes")
print(f"Ratio: {len(opcode_profiles)/len(lua51_ops):.1f}x")
print(f"This suggests heavy super-instruction / specialized opcode usage")

# Identify likely Lua 5.1 opcode equivalents
print(f"\n{'='*80}")
print(f"LIKELY LUA 5.1 OPCODE MAPPING")
print(f"{'='*80}")

# The most common opcode (117, 22.7%) is likely MOVE or a common register op
# Second most (232, 13.2%) with ABCK pattern is likely GETTABLE or LOADK
# Third (194, 8.9%) with _BC_ is likely a two-operand op

for op, prof in sorted(by_count[:30], key=lambda x: -x[1]['count']):
    count = prof['count']
    top_pat = max(prof['patterns'].items(), key=lambda x: x[1])[0]
    
    candidates = []
    if top_pat == 'A___':
        candidates = ['MOVE', 'LOADNIL', 'CLOSE', 'JMP']
    elif top_pat == 'ABCK':
        k_type = max(prof['c2_types'].items(), key=lambda x: x[1])[0] if prof['c2_types'] else '-'
        if k_type == 'string':
            candidates = ['GETTABLE_K', 'SETTABLE_K', 'GETGLOBAL']
        elif k_type == 'number':
            candidates = ['LOADK', 'ARITH_K']
        else:
            candidates = ['GETTABLE', 'SETTABLE', 'LOADK']
    elif top_pat == '_BC_':
        candidates = ['SETTABLE', 'SETGLOBAL', 'TEST']
    elif top_pat == 'ABC_':
        candidates = ['ADD', 'SUB', 'MUL', 'DIV', 'GETTABLE', 'CALL', 'SELF']
    elif top_pat == 'AB__':
        candidates = ['MOVE', 'GETUPVAL', 'UNM', 'NOT', 'LEN']
    elif top_pat == '_B__':
        candidates = ['RETURN', 'JMP', 'CLOSE']
    elif top_pat == 'A_C_':
        candidates = ['TEST', 'TESTSET', 'TFORLOOP']
    elif top_pat == '__C_':
        candidates = ['JMP_TARGET', 'SETLIST']
    
    cand_str = ', '.join(candidates[:4]) if candidates else '?'
    print(f"  op {op:4d} ({count:5d}x) pat={top_pat}: likely {cand_str}")
