"""
Fast runtime opcode trace - capture operands for each unique opcode.
Uses minimal overhead: just one table lookup + early exit per instruction.
"""
import sys, time, json, re
sys.path.insert(0, '.')

with open(r'unobfuscator\pending crack\bloxburg_script.lua', 'r', encoding='utf-8', errors='replace') as f:
    source = f.read()

exec(open('run_luraph_test.py').read().split("print('Reading source...')")[0])
source = preprocess_luau(source)
from unobfuscator.utils.lua_runtime import LuaRuntimeWrapper, LuaRuntimeError

modified = source

# Find 'local T=Y[y]' in the i==3 executor
unpack_pat = re.compile(r'local\s+Q,i,O,a,q,D,Y,Z,w,m,J\s*=\s*C\[')
um = unpack_pat.search(modified)
t_fetches = list(re.finditer(r'local\s+(\w+)\s*=\s*Y\[(\w+)\]', modified[um.start():um.start()+50000]))
i3_fetch = t_fetches[1]  # T=Y[y]
t_global = um.start() + i3_fetch.start()
semi = modified.find(';', t_global + len(i3_fetch.group(0)))

# Inject FAST trace - just flag seen opcodes and capture operands as numbers
# This adds minimal overhead: one table lookup per instruction
inject = (
    'if not _G._os then _G._os={} end;'
    'if not _G._os[T] then '
    '_G._os[T]={D[y] or 0,a[y] or 0,Z[y] or 0,'
    'type(q)=="table" and type(q[y])or"x",'
    'type(w)=="table" and type(w[y])or"x",'
    'type(m)=="table" and type(m[y])or"x"};end;'
)

modified = modified[:semi+1] + inject + modified[semi+1:]

# Also inject AFTER the dispatch to capture what the handler DID
# Find the 'y=y+1' or 'y+=1' at the end of the while loop
# Actually, we need to capture register writes. Let me use a different approach.
# Instead, inject a "before" snapshot via metatable proxy on the register table.

# Actually, the simplest approach: just capture the operands and their types.
# Combined with the static handler analysis, this should be enough.

# BUT ALSO: let me capture what type each operand register holds BEFORE execution
# This helps distinguish MOVE vs LOADK vs GETTABLE etc.

# Better injection: capture register values at operand positions
inject2 = (
    'if not _G._os then _G._os={} end;'
    'if not _G._os[T] then '
    'local _d=D[y]or 0;local _a=a[y]or 0;local _z=Z[y]or 0;'
    'local _qt=q and q[y];local _wt=w and w[y];local _mt=m and m[y];'
    '_G._os[T]={'
    '_d,_a,_z,'  # operand indices
    'type(_qt),type(_wt),type(_mt),'  # sparse operand types
    'type(s[_d]),type(s[_a]),type(s[_z]),'  # register types at operand positions
    '_qt and(type(_qt)=="number"and _qt or(type(_qt)=="string"and"S"or(type(_qt)=="table"and"T"or"?")))or"N",'  # q value summary
    '_wt and(type(_wt)=="number"and _wt or"?")or"N",'  # w value summary
    '_mt and(type(_mt)=="number"and _mt or"?")or"N"'  # m value summary
    '};end;'
)

# Use the better injection
modified2 = source  # start fresh
modified2 = modified2[:semi+1] + inject2 + modified2[semi+1:]

# Suppress entry point
pat = re.compile(
    r'(\)\[(?:\d+|0[xXbBoO][0-9a-fA-F_]+)\]=function\()'
    r'([A-Za-z_]\w*)' r',' r'([A-Za-z_]\w*)' r'\)'
    r'(local\s+[A-Za-z_]\w*(?:,[A-Za-z_]\w*){9,}=)'
    r'(\2\[)'
)
m2 = pat.search(modified2)
if m2:
    p1 = m2.group(2)
    full_match = m2.group(0)
    lp = full_match.index('local')
    hook = f'if {p1}==nil then return function(...)return end end;'
    modified2 = modified2[:m2.start()] + full_match[:lp] + hook + full_match[lp:] + modified2[m2.end():]

modified2 = preprocess_luau(modified2)
runtime = LuaRuntimeWrapper(op_limit=15_000_000_000, timeout=600)
runtime._init_runtime()
runtime.lua.execute("_G._os={}")
modified2 = runtime.suppress_vm_errors(modified2)

print("Executing with fast trace...")
t0 = time.time()
try:
    runtime.execute(modified2)
except LuaRuntimeError as e:
    print(f"Stopped after {time.time()-t0:.1f}s: {str(e)[:200]}")

runtime.lua.execute("_G._op_count=0;_G._op_limit=10000000000")

# Extract trace data
runtime.lua.execute("""
local _out = {}
for _op, _v in pairs(_G._os or {}) do
    if type(_v) == "table" then
        local _parts = {}
        for _i = 1, #_v do
            table.insert(_parts, tostring(_v[_i]))
        end
        table.insert(_out, tostring(math.floor(_op)) .. ":" .. table.concat(_parts, ","))
    end
end
table.sort(_out)
_G._trace_result = table.concat(_out, "\\n")
""")

result = str(runtime.lua.eval('_G._trace_result') or '')
print(f"\nTrace result ({len(result)} chars):")

# Parse results
op_data = {}
if result:
    for line in result.strip().split('\n'):
        if ':' not in line: continue
        op_str, vals_str = line.split(':', 1)
        try:
            op = int(op_str)
        except: continue
        vals = vals_str.split(',')
        if len(vals) >= 12:
            op_data[op] = {
                'D': int(vals[0]) if vals[0].lstrip('-').isdigit() else 0,
                'a': int(vals[1]) if vals[1].lstrip('-').isdigit() else 0,
                'Z': int(vals[2]) if vals[2].lstrip('-').isdigit() else 0,
                'q_type': vals[3],
                'w_type': vals[4],
                'm_type': vals[5],
                'sD_type': vals[6],
                'sa_type': vals[7],
                'sZ_type': vals[8],
                'q_val': vals[9],
                'w_val': vals[10],
                'm_val': vals[11],
            }
        elif len(vals) >= 6:
            op_data[op] = {
                'D': int(vals[0]) if vals[0].lstrip('-').isdigit() else 0,
                'a': int(vals[1]) if vals[1].lstrip('-').isdigit() else 0,
                'Z': int(vals[2]) if vals[2].lstrip('-').isdigit() else 0,
                'q_type': vals[3] if len(vals) > 3 else '?',
                'w_type': vals[4] if len(vals) > 4 else '?',
                'm_type': vals[5] if len(vals) > 5 else '?',
            }

print(f"\nOpcodes traced: {len(op_data)}")

# Display results sorted by opcode
print(f"\n{'Op':>4} {'D':>4} {'a':>4} {'Z':>4} {'q_t':>8} {'w_t':>8} {'m_t':>8} {'sD_t':>8} {'sa_t':>8} {'sZ_t':>8} {'q_v':>8} {'w_v':>8} {'m_v':>8}")
print('-' * 110)
for op in sorted(op_data.keys()):
    d = op_data[op]
    print(f"{op:4d} {d.get('D',0):4d} {d.get('a',0):4d} {d.get('Z',0):4d} "
          f"{d.get('q_type','?'):>8s} {d.get('w_type','?'):>8s} {d.get('m_type','?'):>8s} "
          f"{d.get('sD_type','?'):>8s} {d.get('sa_type','?'):>8s} {d.get('sZ_type','?'):>8s} "
          f"{d.get('q_val','?'):>8s} {d.get('w_val','?'):>8s} {d.get('m_val','?'):>8s}")

# Save
with open('opcode_trace_fast.json', 'w') as f:
    json.dump(op_data, f, indent=1, sort_keys=True, default=str)
print(f"\nSaved to opcode_trace_fast.json")
