"""
Trace register writes per opcode using a __newindex proxy on the register table.
This tells us EXACTLY what each opcode writes to which register.
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

# APPROACH: Inject TWO things:
# 1. Right after s=r[0x18](Q), wrap s with a proxy that logs writes
# 2. Before the dispatch (after local T=Y[y]), save current T and clear write log
# 3. After the dispatch (before next iteration), record the writes for T

# Find where s is created: local y,s,X,P,L=1,r[0X18](Q),(0B1)
# This is inside the function(...)
region = modified[t_global-500:t_global]
s_create = re.search(r'local\s+y,s,(\w+),(\w+),(\w+)\s*=\s*1,r\[0[xX]18\]\(Q\)', region)
if s_create:
    print(f"Found s creation: {s_create.group(0)[:80]}")
    s_create_global = t_global - 500 + s_create.end()
else:
    print("s creation not found, searching broader...")
    region = modified[t_global-1000:t_global]
    s_create = re.search(r'local\s+y,s,\w+,\w+,\w+\s*=\s*1,r\[0[xX]18\]\(Q\)', region)
    s_create_global = t_global - 1000 + s_create.end()

# Find the semicolon after s creation
s_semi = modified.find(';', s_create_global)

# Inject proxy wrapper after s is created
# The proxy uses rawset/rawget to avoid recursion
proxy_inject = (
    'if not _G._rw then _G._rw={};_G._rwT=0;_G._rwN=0 end;'
    'local _rs=s;'
    's=setmetatable({},{__newindex=function(_,_k,_v)'
    'rawset(_rs,_k,_v);'
    'if _G._rwT>0 and _G._rwN<500 then '
    'local _e=_G._rw[_G._rwT];'
    'if not _e then _e={n=0,w={}};_G._rw[_G._rwT]=_e end;'
    'if _e.n<3 then '
    '_e.n=_e.n+1;_e.w[_e.n]={_k,type(_v)};'
    '_G._rwN=_G._rwN+1 '
    'end end end,'
    '__index=_rs,'
    '__len=function()return #_rs end});'
)
modified = modified[:s_semi+1] + proxy_inject + modified[s_semi+1:]

# Recalculate positions after injection
offset = len(proxy_inject)
t_global += offset
semi = modified.find(';', t_global + len(i3_fetch.group(0)))

# Inject before dispatch: save T for proxy logging
pre_dispatch = '_G._rwT=T;'
modified = modified[:semi+1] + pre_dispatch + modified[semi+1:]

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
runtime.lua.execute("_G._rw={};_G._rwT=0;_G._rwN=0")
modified = runtime.suppress_vm_errors(modified)

print("Executing with register write proxy...")
t0 = time.time()
try:
    runtime.execute(modified)
except LuaRuntimeError as e:
    print(f"Stopped after {time.time()-t0:.1f}s: {str(e)[:300]}")

# Extract results
runtime.lua.execute("""
local _out = {}
for _op, _data in pairs(_G._rw or {}) do
    if type(_data) == "table" and _data.w then
        local _parts = {}
        for _i = 1, _data.n do
            local _w = _data.w[_i]
            if _w then
                table.insert(_parts, tostring(_w[1]) .. "=" .. tostring(_w[2]))
            end
        end
        table.insert(_out, tostring(math.floor(_op)) .. ":" .. table.concat(_parts, ","))
    end
end
table.sort(_out)
_G._rw_result = table.concat(_out, "\\n")
""")

result = str(runtime.lua.eval('_G._rw_result') or '')
rw_count = runtime.lua.eval('_G._rwN') or 0
print(f"\nRegister writes captured: {rw_count}")
print(f"Result length: {len(result)}")

# Parse and display
if result:
    rw_data = {}
    for line in result.strip().split('\n'):
        if ':' not in line: continue
        op_str, writes_str = line.split(':', 1)
        try: op = int(op_str)
        except: continue
        writes = []
        for w in writes_str.split(','):
            if '=' in w:
                reg, typ = w.split('=', 1)
                writes.append((reg, typ))
        rw_data[op] = writes
    
    # Load frequency data
    with open('all_protos_data.json', 'r') as f:
        all_protos = json.load(f)
    op_freq = {}
    for p in all_protos:
        for op in p.get('C4', []):
            if op is not None:
                op_freq[op] = op_freq.get(op, 0) + 1
    
    # Load runtime trace for operand info
    try:
        with open('opcode_trace_fast.json', 'r') as f:
            rt = json.load(f)
    except: rt = {}
    
    print(f"\n{'Op':>4} {'Freq':>6} {'Writes':>50} {'Operand Info':>40}")
    print('-' * 110)
    for op in sorted(rw_data.keys()):
        writes = rw_data[op]
        freq = op_freq.get(op, 0)
        w_str = ', '.join(f'r[{r}]={t}' for r, t in writes)
        
        rt_info = rt.get(str(op), {})
        q_t = rt_info.get('q_type', '-')
        w_t = rt_info.get('w_type', '-')
        m_t = rt_info.get('m_type', '-')
        op_info = f"q={q_t} w={w_t} m={m_t}"
        
        print(f"{op:4d} {freq:6d} {w_str:>50s} {op_info:>40s}")
    
    # Classify based on write patterns
    print(f"\n{'='*90}")
    print("CLASSIFICATION BASED ON REGISTER WRITES")
    print(f"{'='*90}")
    
    for op in sorted(rw_data.keys()):
        writes = rw_data[op]
        rt_info = rt.get(str(op), {})
        q_t = rt_info.get('q_type', 'nil')
        
        if not writes:
            cls = 'NO_WRITES (JMP/TEST/RETURN)'
        elif len(writes) == 1:
            reg, typ = writes[0]
            if typ == 'nil':
                cls = 'LOADNIL'
            elif typ == 'boolean':
                cls = 'LOADBOOL/CMP_STORE'
            elif typ == 'number':
                if q_t == 'number':
                    cls = 'LOADK/ARITH_K'
                else:
                    cls = 'ARITH/LEN/MOVE(num)'
            elif typ == 'string':
                if q_t == 'string':
                    cls = 'LOADK_STR'
                else:
                    cls = 'CONCAT/GETTABLE(str)'
            elif typ == 'table':
                cls = 'NEWTABLE/GETTABLE(tbl)'
            elif typ == 'function':
                cls = 'CLOSURE/GETGLOBAL(fn)'
            elif typ == 'userdata':
                cls = 'GETTABLE(userdata)'
            else:
                cls = f'WRITE_{typ}'
        elif len(writes) == 2:
            types = [t for _, t in writes]
            if all(t == 'nil' for t in types):
                cls = 'LOADNIL_RANGE'
            elif 'function' in types and 'table' in types:
                cls = 'SELF'
            elif 'function' in types:
                cls = 'CALL_MULTI'
            else:
                cls = f'MULTI_WRITE({",".join(types)})'
        else:
            cls = f'MULTI_WRITE({len(writes)})'
        
        freq = op_freq.get(op, 0)
        print(f"  Op {op:4d} ({freq:5d}x): {cls}")
    
    with open('opcode_reg_writes.json', 'w') as f:
        json.dump({str(k): v for k, v in rw_data.items()}, f, indent=1, sort_keys=True)
    print(f"\nSaved to opcode_reg_writes.json")
