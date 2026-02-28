"""
Combined opcode trace: operands + register types + delta detection.
Uses the proven fast-trace pattern with enhanced data capture.
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
i3_fetch = t_fetches[1]
t_global = um.start() + i3_fetch.start()
semi = modified.find(';', t_global + len(i3_fetch.group(0)))

# Two-phase injection:
# Phase 1: Record "after" state from previous instruction + "before" for current
# Uses _G._pT (prev opcode), _G._pR (prev operand regs), _G._pB (prev before-types)
inject = (
    'do '
    'local _pT=_G._pT;'
    'if _pT and not _G._od[_pT]then '
    'local _pd=_G._pR[1];local _pa=_G._pR[2];local _pz=_G._pR[3];'
    '_G._od[_pT]={_G._pB[1],_G._pB[2],_G._pB[3],'
    'type(s[_pd]),type(s[_pa]),type(s[_pz]),'
    '_pd,_pa,_pz,'
    'type(_G._pQ),type(_G._pW),type(_G._pM)};'
    '_G._odn=_G._odn+1;'
    'end;'
    'if _G._odn<300 then '
    'local _cd=D[y]or 0;local _ca=a[y]or 0;local _cz=Z[y]or 0;'
    '_G._pT=T;_G._pR={_cd,_ca,_cz};'
    '_G._pB={type(s[_cd]),type(s[_ca]),type(s[_cz])};'
    '_G._pQ=q and q[y];_G._pW=w and w[y];_G._pM=m and m[y];'
    'else _G._pT=nil;end;'
    'end;'
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
runtime.lua.execute("_G._od={};_G._odn=0;_G._pT=nil;_G._pR={0,0,0};_G._pB={'nil','nil','nil'};_G._pQ=nil;_G._pW=nil;_G._pM=nil")
modified = runtime.suppress_vm_errors(modified)

print("Executing combined trace...")
t0 = time.time()
try:
    runtime.execute(modified)
except LuaRuntimeError as e:
    print(f"Stopped after {time.time()-t0:.1f}s: {str(e)[:200]}")

runtime.lua.execute("_G._op_count=0;_G._op_limit=10000000000")

# Extract - with proper type checking
runtime.lua.execute("""
local _out = {}
for _op, _v in pairs(_G._od or {}) do
    if type(_op) == "number" and type(_v) == "table" then
        local _parts = {}
        for _i = 1, #_v do
            table.insert(_parts, tostring(_v[_i] or "nil"))
        end
        table.insert(_out, string.format("%d", _op) .. ":" .. table.concat(_parts, "|"))
    end
end
table.sort(_out)
_G._combined_result = table.concat(_out, "\\n")
""")

result = str(runtime.lua.eval('_G._combined_result') or '')
count = runtime.lua.eval('_G._odn') or 0
elapsed = time.time() - t0
print(f"\nCompleted in {elapsed:.1f}s, captured {count} opcodes")

# Parse
op_deltas = {}
if result:
    for line in result.strip().split('\n'):
        if ':' not in line: continue
        op_str, data_str = line.split(':', 1)
        try: op = int(op_str)
        except: continue
        parts = data_str.split('|')
        if len(parts) >= 12:
            op_deltas[op] = {
                'before_D': parts[0], 'before_A': parts[1], 'before_Z': parts[2],
                'after_D': parts[3], 'after_A': parts[4], 'after_Z': parts[5],
                'reg_D': int(parts[6]) if parts[6].lstrip('-').isdigit() else 0,
                'reg_A': int(parts[7]) if parts[7].lstrip('-').isdigit() else 0,
                'reg_Z': int(parts[8]) if parts[8].lstrip('-').isdigit() else 0,
                'q_type': parts[9], 'w_type': parts[10], 'm_type': parts[11],
            }

# Load frequencies
with open('all_protos_data.json', 'r') as f:
    all_protos = json.load(f)
op_freq = {}
for p in all_protos:
    for op in p.get('C4', []):
        if op is not None: op_freq[op] = op_freq.get(op, 0) + 1

# Classify
print(f"\n{'Op':>4} {'Freq':>6} {'bD':>5} {'bA':>5} {'bZ':>5} {'aD':>5} {'aA':>5} {'aZ':>5} {'rD':>3} {'rA':>3} {'rZ':>3} {'q':>6} {'w':>6} {'m':>6} {'Classification':>25}")
print('-' * 120)

classifications = {}
for op in sorted(op_deltas.keys()):
    d = op_deltas[op]
    bD, bA, bZ = d['before_D'][:3], d['before_A'][:3], d['before_Z'][:3]
    aD, aA, aZ = d['after_D'][:3], d['after_A'][:3], d['after_Z'][:3]
    rD, rA, rZ = d['reg_D'], d['reg_A'], d['reg_Z']
    qt, wt, mt = d['q_type'][:3], d['w_type'][:3], d['m_type'][:3]
    
    # Detect changes
    d_ch = bD != aD
    a_ch = bA != aA
    z_ch = bZ != aZ
    
    # Classify
    cls = 'UNKNOWN'
    
    if not d_ch and not a_ch and not z_ch:
        # No change at operand positions - could be JMP, TEST, SETTABLE, SETUPVAL, RETURN
        if qt[:3] == 'str':
            cls = 'SETTABLE_K/SETGLOBAL'
        elif qt[:3] == 'num':
            cls = 'SETTABLE_K(n)/SETGLOBAL'
        else:
            cls = 'JMP/TEST/RETURN/SET*'
    elif d_ch and not a_ch and not z_ch:
        # Only D changed
        at = aD[:3]
        if at == 'num':
            if qt[:3] == 'num': cls = 'LOADK(n)->D'
            elif qt[:3] == 'str': cls = 'LEN/ARITH->D'
            else: cls = 'ARITH/MOVE(n)->D'
        elif at == 'str':
            if qt[:3] == 'str': cls = 'LOADK(s)->D'
            else: cls = 'CONCAT/GT(s)->D'
        elif at == 'fun': cls = 'GETGLOBAL(f)/CLOSURE->D'
        elif at == 'tab': cls = 'NEWTABLE/GETTBL(t)->D'
        elif at == 'boo': cls = 'CMP_STORE/LOADBOOL->D'
        elif at == 'nil': cls = 'LOADNIL->D'
        elif at == 'use': cls = 'GETTBL(udata)->D'
        else: cls = f'WRITE_D({at})'
    elif a_ch and not d_ch and not z_ch:
        at = aA[:3]
        if at == 'num':
            if qt[:3] == 'num': cls = 'LOADK(n)->A'
            else: cls = 'ARITH/MOVE(n)->A'
        elif at == 'str':
            if qt[:3] == 'str': cls = 'LOADK(s)->A'
            else: cls = 'CONCAT->A'
        elif at == 'fun': cls = 'GETGLOBAL(f)/CLOSURE->A'
        elif at == 'tab': cls = 'NEWTABLE/GETTBL(t)->A'
        elif at == 'boo': cls = 'CMP_STORE/LOADBOOL->A'
        elif at == 'nil': cls = 'LOADNIL->A'
        elif at == 'use': cls = 'GETTBL(udata)->A'
        else: cls = f'WRITE_A({at})'
    elif z_ch and not d_ch and not a_ch:
        at = aZ[:3]
        if at == 'num': cls = 'ARITH/LOADK(n)->Z'
        elif at == 'str': cls = 'CONCAT/LOADK(s)->Z'
        elif at == 'fun': cls = 'GETGLOBAL(f)->Z'
        elif at == 'tab': cls = 'NEWTABLE->Z'
        elif at == 'boo': cls = 'CMP_STORE->Z'
        else: cls = f'WRITE_Z({at})'
    else:
        # Multiple changes
        changed = []
        if d_ch: changed.append(f'D:{aD[:3]}')
        if a_ch: changed.append(f'A:{aA[:3]}')
        if z_ch: changed.append(f'Z:{aZ[:3]}')
        cls = f'MULTI({"+".join(changed)})'
    
    classifications[op] = cls
    freq = op_freq.get(op, 0)
    print(f"{op:4d} {freq:6d} {bD:>5s} {bA:>5s} {bZ:>5s} {aD:>5s} {aA:>5s} {aZ:>5s} {rD:3d} {rA:3d} {rZ:3d} {qt:>6s} {wt:>6s} {mt:>6s} {cls:>25s}")

# Summary
from collections import Counter
cls_counts = Counter(classifications.values())
print(f"\n{'='*60}")
print(f"CLASSIFICATION SUMMARY ({len(classifications)} opcodes)")
print(f"{'='*60}")
for cls, cnt in cls_counts.most_common():
    ops = sorted(op for op, c in classifications.items() if c == cls)
    ops_str = ', '.join(str(o) for o in ops[:10])
    if len(ops) > 10: ops_str += f' +{len(ops)-10}'
    total_freq = sum(op_freq.get(o, 0) for o in ops)
    print(f"  {cls:>30s}: {cnt:3d} ops, {total_freq:6d} inst | {ops_str}")

# Save combined data
with open('opcode_combined.json', 'w') as f:
    json.dump({
        'deltas': {str(k): v for k, v in op_deltas.items()},
        'classifications': {str(k): v for k, v in classifications.items()},
    }, f, indent=1, sort_keys=True, default=str)
print(f"\nSaved to opcode_combined.json")
