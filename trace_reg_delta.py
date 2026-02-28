"""
Trace register deltas per opcode using next-iteration capture.
At start of each iteration, the register state reflects what the PREVIOUS
instruction wrote. By saving before-types and comparing with after-types,
we can determine which registers each opcode modifies.
"""
import sys, time, json, re
sys.path.insert(0, '.')

with open(r'unobfuscator\pending crack\bloxburg_script.lua', 'r', encoding='utf-8', errors='replace') as f:
    source = f.read()

exec(open('run_luraph_test.py').read().split("print('Reading source...')")[0])
from unobfuscator.utils.lua_runtime import LuaRuntimeWrapper, LuaRuntimeError

modified = source

# Find 'local T=Y[y]' in the i==3 executor
unpack_pat = re.compile(r'local\s+Q,i,O,a,q,D,Y,Z,w,m,J\s*=\s*C\[')
um = unpack_pat.search(modified)
t_fetches = list(re.finditer(r'local\s+(\w+)\s*=\s*Y\[(\w+)\]', modified[um.start():um.start()+50000]))
i3_fetch = t_fetches[1]  # T=Y[y]
t_global = um.start() + i3_fetch.start()
semi = modified.find(';', t_global + len(i3_fetch.group(0)))

# Lean injection: capture before-types, then on NEXT iteration compare with after-types
# Use single-char type abbreviations to minimize string ops
inject = (
    'do local _p=_G._p;'
    'if _p and not _G._od[_p[1]]then '
    'local _d,_a,_z=_p[2],_p[3],_p[4];'
    '_G._od[_p[1]]=_p[5]..(_p[6])..(_p[7])..">"'
    '..string.sub(type(s[_d]),1,3)'
    '..string.sub(type(s[_a]),1,3)'
    '..string.sub(type(s[_z]),1,3);'
    '_G._on=_G._on+1;if _G._on>=300 then _G._p=nil end;'
    'end;'
    'if _G._on<300 then '
    'local _d=D[y]or 0;local _a=a[y]or 0;local _z=Z[y]or 0;'
    '_G._p={T,_d,_a,_z,'
    'string.sub(type(s[_d]),1,3),'
    'string.sub(type(s[_a]),1,3),'
    'string.sub(type(s[_z]),1,3)};'
    'end;end;'
)
modified = modified[:semi+1] + inject + modified[semi+1:]

# Suppress entry point
pat = re.compile(
    r'(\)\[(?:\d+|0[xXbBoO][0-9a-fA-F_]+)\]=function\()'
    r'([A-Za-z_]\w*)' r',' r'([A-Za-z_]\w*)' r'\)'
    r'(local\s+[A-Za-z_]\w*(?:,[A-Za-z_]\w*){9,}=)'
    r'(\2\[)'
)
m2 = pat.search(modified)
if m2:
    p1 = m2.group(2)
    full_match = m2.group(0)
    lp = full_match.index('local')
    hook = f'if {p1}==nil then return function(...)return end end;'
    modified = modified[:m2.start()] + full_match[:lp] + hook + full_match[lp:] + modified[m2.end():]

modified = preprocess_luau(modified)
runtime = LuaRuntimeWrapper(op_limit=15_000_000_000, timeout=600)
runtime._init_runtime()
runtime.lua.execute("_G._od={};_G._on=0;_G._p=nil")
modified = runtime.suppress_vm_errors(modified)

print("Executing with register delta trace...")
t0 = time.time()
try:
    runtime.execute(modified)
except LuaRuntimeError as e:
    print(f"Stopped after {time.time()-t0:.1f}s: {str(e)[:200]}")

runtime.lua.execute("_G._op_count=0;_G._op_limit=10000000000")

# Extract
runtime.lua.execute("""
local _out = {}
for _op, _delta in pairs(_G._od or {}) do
    table.insert(_out, tostring(math.floor(_op)) .. ":" .. tostring(_delta))
end
table.sort(_out)
_G._delta_result = table.concat(_out, "\\n")
""")

result = str(runtime.lua.eval('_G._delta_result') or '')
count = runtime.lua.eval('_G._on') or 0
print(f"\nDeltas captured: {count}")

# Also get the operand trace
runtime.lua.execute("""
local _out2 = {}
for _op, _v in pairs(_G._os or {}) do
    if type(_v) == "table" then
        local _p = {}
        for _i = 1, #_v do table.insert(_p, tostring(_v[_i])) end
        table.insert(_out2, tostring(math.floor(_op)) .. ":" .. table.concat(_p, ","))
    end
end
table.sort(_out2)
_G._os_result = table.concat(_out2, "\\n")
""")
os_result = str(runtime.lua.eval('_G._os_result') or '')

# Parse delta results
delta_data = {}
if result:
    for line in result.strip().split('\n'):
        if ':' not in line: continue
        op_str, delta = line.split(':', 1)
        try: op = int(op_str)
        except: continue
        delta_data[op] = delta

# Load frequency data
with open('all_protos_data.json', 'r') as f:
    all_protos = json.load(f)
op_freq = {}
for p in all_protos:
    for op in p.get('C4', []):
        if op is not None:
            op_freq[op] = op_freq.get(op, 0) + 1

# Classify based on deltas
print(f"\n{'Op':>4} {'Freq':>6} {'Delta (before>after)':>30} {'Classification':>30}")
print('-' * 80)

opcode_semantics = {}
for op in sorted(delta_data.keys()):
    delta = delta_data[op]
    freq = op_freq.get(op, 0)
    
    # Parse delta: "befD befA befZ > aftD aftA aftZ"
    # Each is 3-char type prefix: nil, num, str, tab, fun, boo, use
    parts = delta.split('>')
    if len(parts) != 2:
        cls = f'PARSE_ERR({delta})'
    else:
        before = parts[0]
        after = parts[1]
        # Each part is 9 chars: 3 type prefixes (D, a, Z)
        bD = before[0:3]
        bA = before[3:6]
        bZ = before[6:9]
        aD = after[0:3]
        aA = after[3:6]
        aZ = after[6:9]
        
        # Determine what changed
        d_changed = bD != aD
        a_changed = bA != aA
        z_changed = bZ != aZ
        
        changes = []
        if d_changed: changes.append(f'D:{bD}->{aD}')
        if a_changed: changes.append(f'A:{bA}->{aA}')
        if z_changed: changes.append(f'Z:{bZ}->{aZ}')
        
        if not changes:
            # No register changes at operand positions
            # Could be JMP, TEST, RETURN, SETTABLE, SETUPVAL, SETGLOBAL
            cls = 'NO_REG_CHANGE'
        elif len(changes) == 1:
            ch = changes[0]
            if 'D:' in ch:
                new_type = aD
                if new_type == 'nil': cls = 'LOADNIL'
                elif new_type == 'num': cls = 'ARITH/LOADK/LEN'
                elif new_type == 'str': cls = 'CONCAT/LOADK_STR'
                elif new_type == 'tab': cls = 'NEWTABLE/GETTABLE(t)'
                elif new_type == 'fun': cls = 'CLOSURE/GETGLOBAL(f)'
                elif new_type == 'boo': cls = 'CMP_STORE/LOADBOOL'
                elif new_type == 'use': cls = 'GETTABLE(udata)'
                else: cls = f'WRITE_D({new_type})'
            elif 'A:' in ch:
                new_type = aA
                if new_type == 'nil': cls = 'LOADNIL_A'
                elif new_type == 'num': cls = 'ARITH_A/LOADK_A'
                elif new_type == 'str': cls = 'CONCAT_A/LOADK_A_STR'
                elif new_type == 'tab': cls = 'NEWTABLE_A'
                elif new_type == 'fun': cls = 'CLOSURE_A/GETGLOBAL_A'
                elif new_type == 'boo': cls = 'CMP_A/LOADBOOL_A'
                elif new_type == 'use': cls = 'GETTABLE_A(udata)'
                else: cls = f'WRITE_A({new_type})'
            elif 'Z:' in ch:
                new_type = aZ
                if new_type == 'num': cls = 'ARITH_Z/LOADK_Z'
                elif new_type == 'str': cls = 'CONCAT_Z'
                elif new_type == 'fun': cls = 'GETGLOBAL_Z(f)'
                elif new_type == 'tab': cls = 'NEWTABLE_Z'
                elif new_type == 'boo': cls = 'CMP_Z'
                else: cls = f'WRITE_Z({new_type})'
            else:
                cls = f'SINGLE_CHANGE({ch})'
        else:
            # Multiple changes
            types = [c.split('->')[1] for c in changes]
            regs = [c.split(':')[0] for c in changes]
            cls = f'MULTI({"+".join(r+"="+t for r,t in zip(regs,types))})'
        
        opcode_semantics[op] = {
            'before': {'D': bD, 'A': bA, 'Z': bZ},
            'after': {'D': aD, 'A': aA, 'Z': aZ},
            'changes': changes,
            'classification': cls
        }
    
    print(f"{op:4d} {freq:6d} {delta:>30s} {cls:>30s}")

# Save
with open('opcode_deltas.json', 'w') as f:
    json.dump(opcode_semantics, f, indent=1, sort_keys=True, default=str)
print(f"\nSaved to opcode_deltas.json")

# Summary by classification
from collections import Counter
cls_counts = Counter()
for data in opcode_semantics.values():
    cls_counts[data.get('classification', 'UNKNOWN')] += 1

print(f"\nClassification summary:")
for cls, cnt in cls_counts.most_common():
    print(f"  {cls:>35s}: {cnt}")
