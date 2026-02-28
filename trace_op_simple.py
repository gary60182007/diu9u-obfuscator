"""
Simple opcode trace - just log T and operands, verify variable names in scope.
"""
import sys, time, json, re
sys.path.insert(0, '.')

with open(r'unobfuscator\pending crack\bloxburg_script.lua', 'r', encoding='utf-8', errors='replace') as f:
    source = f.read()

exec(open('run_luraph_test.py').read().split("print('Reading source...')")[0])
source = preprocess_luau(source)
from unobfuscator.utils.lua_runtime import LuaRuntimeWrapper, LuaRuntimeError

modified = source

# Find the i==3 executor's 'local T=Y[y]'
unpack_pat = re.compile(r'local\s+Q,i,O,a,q,D,Y,Z,w,m,J\s*=\s*C\[')
um = unpack_pat.search(modified)

# The i==3 executor is the SECOND Y[...] pattern (first is i==4's k=Y[L])
t_fetch_all = list(re.finditer(r'local\s+(\w+)\s*=\s*Y\[(\w+)\]', modified[um.start():um.start()+50000]))
print(f"Y[] fetch patterns found:")
for m2 in t_fetch_all:
    print(f"  var={m2.group(1)}, idx={m2.group(2)} at offset +{m2.start()}")

# Use the second one (T=Y[y]) for the i==3 executor
t_m = t_fetch_all[1]
t_global_pos = um.start() + t_m.start()
semi = modified.find(';', t_global_pos + len(t_m.group(0)))

# Show context around the injection point to verify variable names
ctx_before = modified[t_global_pos-300:t_global_pos]
print(f"\n300 chars BEFORE 'local T=Y[y]':")
print(ctx_before[-300:])

# Extract the function signature and locals before the while loop
# Search backwards for 'function(' from the injection point
func_region = modified[t_global_pos-2000:t_global_pos]
func_matches = list(re.finditer(r'function\(([^)]*)\)', func_region))
if func_matches:
    last = func_matches[-1]
    print(f"\nNearest function signature: function({last.group(1)})")
    
    # Show locals defined between function and while loop
    between = func_region[last.start():]
    local_defs = re.findall(r'local\s+([^=;]+?)=', between)
    print(f"Locals defined: {local_defs[:10]}")

# Now inject a VERY simple trace - just count and verify variable access
inject = (
    'if not _G._t2 then _G._t2={};_G._t2n=0 end;'
    'if _G._t2n<300 and not _G._t2[T] then '
    '_G._t2[T]=tostring(T)..";"'
    '..tostring(type(D))..";"'
    '..tostring(type(a))..";"'
    '..tostring(type(Z))..";"'
    '..tostring(type(q))..";"'
    '..tostring(type(w))..";"'
    '..tostring(type(m))..";"'  
    '..tostring(D and D[y] or "?")..";"'
    '..tostring(a and a[y] or "?")..";"'
    '..tostring(Z and Z[y] or "?");'
    '_G._t2n=_G._t2n+1 end;'
)
modified = modified[:semi+1] + inject + modified[semi+1:]
print(f"\nInjected simple trace at pos {semi+1}")

# Suppress entry
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
runtime.lua.execute("_G._pn=0;_G._t2={};_G._t2n=0")
modified = runtime.suppress_vm_errors(modified)

print("Executing...")
t0 = time.time()
try:
    runtime.execute(modified)
except LuaRuntimeError as e:
    print(f"Stopped after {time.time()-t0:.1f}s: {str(e)[:200]}")

runtime.lua.execute("_G._op_count=0;_G._op_limit=10000000000")

# Extract results
runtime.lua.execute("""
local _p = {}
for k, v in pairs(_G._t2 or {}) do
    table.insert(_p, v)
end
table.sort(_p)
_G._t2out = table.concat(_p, "\\n")
""")
out = str(runtime.lua.eval('_G._t2out') or '')
count = runtime.lua.eval('_G._t2n')
print(f"\nTrace entries: {count}")
print(f"Output length: {len(out)}")

if out:
    lines = out.strip().split('\n')
    print(f"\nFirst 50 entries (T;type(D);type(a);type(Z);type(q);type(w);type(m);D[y];a[y];Z[y]):")
    for line in sorted(lines, key=lambda x: int(x.split(';')[0]) if x.split(';')[0].isdigit() else 0)[:50]:
        parts = line.split(';')
        if len(parts) >= 10:
            t_val = parts[0]
            types = parts[1:7]
            vals = parts[7:10]
            print(f"  T={t_val:>4s}  types={','.join(types):>40s}  D[y]={vals[0]:>5s} a[y]={vals[1]:>5s} Z[y]={vals[2]:>5s}")
else:
    print("No output - checking for errors...")
    # Try to check if the injection caused any issues
    err = runtime.lua.eval('_G._last_error')
    if err:
        print(f"Error: {err}")
