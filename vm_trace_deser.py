"""
Trace the FULL deserialization chain after the constant table.
Log what each _9 iteration does and what C[58] (prototype deserializer) reads.
"""
import sys, time, json, re
sys.path.insert(0, '.')

with open(r'unobfuscator\pending crack\bloxburg_script.lua', 'r', encoding='utf-8', errors='replace') as f:
    source = f.read()

exec(open('run_luraph_test.py').read().split("print('Reading source...')")[0])
source = preprocess_luau(source)

from unobfuscator.utils.lua_runtime import LuaRuntimeWrapper, LuaRuntimeError

modified = source

# Inject tracing in key functions:
# 1. _9: log which branch (q9/P9/d9/m9) is taken and r[10] before/after
# 2. t9: log what it does
# 3. C[58]: log prototype deserialization

# Find _9 function
_9_pat = re.compile(r'(_9=function\((\w+),(\w+),(\w+),(\w+),(\w+),(\w+),(\w+)\))')
_9_m = _9_pat.search(modified)
if _9_m:
    z_p, r_p, C_p, W_p, Q_p, i_p, O_p = [_9_m.group(j) for j in range(2, 9)]
    print(f"_9 params: z={z_p}, r={r_p}, C={C_p}, W={W_p}, Q={Q_p}, i={i_p}, O={O_p}")
    
    inject = (
        f'do local _n=(_G._9_n or 0)+1;_G._9_n=_n;'
        f'local _e={{w={C_p},r10={Q_p}[10],Q={Q_p} and type({Q_p})=="table" and "tbl" or tostring({Q_p})}};'
        f'_G._9_trace[_n]=_e end;'
    )
    modified = modified[:_9_m.end()] + inject + modified[_9_m.end():]
    print("_9 tracing injected")

# Find t9 function  
t9_pat = re.compile(r'(t9=function\((\w+),(\w+),(\w+),(\w+),(\w+)\))')
t9_m = t9_pat.search(modified)
if t9_m:
    t9_params = [t9_m.group(j) for j in range(2, 7)]
    print(f"t9 params: {t9_params}")
    
    inject_t9 = (
        f'_G._t9_called=(_G._t9_called or 0)+1;'
        f'_G._t9_r10={t9_params[0]}[10];'
    )
    modified = modified[:t9_m.end()] + inject_t9 + modified[t9_m.end():]
    print("t9 tracing injected")

# Find P9 function
P9_pat = re.compile(r'(P9=function\((\w+),(\w+),(\w+),(\w+)\))')
P9_m = P9_pat.search(modified)
if P9_m:
    P9_params = [P9_m.group(j) for j in range(2, 6)]
    print(f"P9 params: {P9_params}")
    inject_P9 = (
        f'_G._P9_calls=(_G._P9_calls or 0)+1;'
        f'_G._P9_r10={P9_params[1]}[10];'
    )
    modified = modified[:P9_m.end()] + inject_P9 + modified[P9_m.end():]

# Find d9 function
d9_pat = re.compile(r'(d9=function\((\w+),(\w+),(\w+),(\w+)\))')
d9_m = d9_pat.search(modified)
if d9_m:
    d9_params = [d9_m.group(j) for j in range(2, 6)]
    print(f"d9 params: {d9_params}")
    inject_d9 = (
        f'_G._d9_calls=(_G._d9_calls or 0)+1;'
        f'_G._d9_r10={d9_params[2]}[10];'
    )
    modified = modified[:d9_m.end()] + inject_d9 + modified[d9_m.end():]

# Find m9 function
m9_pat = re.compile(r'(m9=function\((\w+),(\w+),(\w+),(\w+)\))')
m9_m = m9_pat.search(modified)
if m9_m:
    m9_params = [m9_m.group(j) for j in range(2, 6)]
    print(f"m9 params: {m9_params}")
    inject_m9 = (
        f'_G._m9_calls=(_G._m9_calls or 0)+1;'
        f'_G._m9_r10={m9_params[2]}[10];'
    )
    modified = modified[:m9_m.end()] + inject_m9 + modified[m9_m.end():]

# Find I9 function (the one that clears r[57])
I9_pat = re.compile(r'(I9=function\((\w+),(\w+),(\w+)\))')
I9_m = I9_pat.search(modified)
if I9_m:
    I9_params = [I9_m.group(j) for j in range(2, 5)]
    print(f"I9 params: {I9_params}")
    inject_I9 = (
        f'_G._I9_called=true;'
        f'_G._I9_r10={I9_params[1]}[10];'
    )
    modified = modified[:I9_m.end()] + inject_I9 + modified[I9_m.end():]

# Find F9 function (if it exists)
F9_pat = re.compile(r'(F9=function\((\w+),(\w+),(\w+)\))')
F9_m = F9_pat.search(modified)
if F9_m:
    print(f"F9 found")

# Inject in q9 to capture string dump + post-constants state
q9_start = modified.find('q9=function(')
q9_params = re.search(r'q9=function\((\w+),(\w+),(\w+),(\w+),(\w+)\)', modified[q9_start:])
W_var = q9_params.group(4)
C_var = q9_params.group(3)
inject_marker = re.search(r'end;end;(' + re.escape(C_var) + r'=\(' + re.escape(W_var) + r'\[)', modified[q9_start:])
inject_pos = q9_start + inject_marker.start() + len('end;end;')

dump_code = (
    f'_G._q9_end_r10={W_var}[10];'
)
modified = modified[:inject_pos] + dump_code + modified[inject_pos:]

# Track C[58] calls (prototype deserializer)
# C[58] is assigned like: C[58]=function(...)... or (C)[58]=function(...)
c58_pat = re.compile(r'(\[(?:58|0[xXbB][0-9a-fA-F_]+)\]\s*=\s*function\((\w+),(\w+)\))')
# Search in the ret block
ret_start = modified.index('return({')
c58_matches = list(c58_pat.finditer(modified, ret_start))
print(f"\nC[58] pattern matches: {len(c58_matches)}")
for m in c58_matches:
    print(f"  pos={m.start()}: {repr(m.group(0)[:60])}")

# If we find C[58], inject a call counter
if c58_matches:
    cm = c58_matches[0]
    inject_c58 = (
        f'_G._c58_calls=(_G._c58_calls or 0)+1;'
        f'if _G._c58_calls<=200 then '
        f'_G._c58_trace[_G._c58_calls]='
        f'{{n=_G._c58_calls,r10={cm.group(3)}[10]}} end;'
    )
    modified = modified[:cm.end()] + inject_c58 + modified[cm.end():]
    print("C[58] tracing injected")

# Proto capture hook
pat = re.compile(
    r'(\)\[(?:\d+|0[xXbBoO][0-9a-fA-F_]+)\]=function\()'
    r'([A-Za-z_]\w*)' r',' r'([A-Za-z_]\w*)' r'\)'
    r'(local\s+[A-Za-z_]\w*(?:,[A-Za-z_]\w*){9,}=)'
    r'(\2\[)'
)
m = pat.search(modified)
if m:
    p1 = m.group(2)
    full_match = m.group(0)
    lp = full_match.index('local')
    hook = (
        f'if {p1}==nil then return function(...)return end end;'
        f'do local _p={{}};for _i=1,11 do _p[_i]={p1}[_i] end;'
        f'_p.id=#_G._protos+1;table.insert(_G._protos,_p) end;'
    )
    modified = modified[:m.start()] + full_match[:lp] + hook + full_match[lp:] + modified[m.end():]

runtime = LuaRuntimeWrapper(op_limit=15_000_000_000, timeout=600)
runtime._init_runtime()
runtime.lua.execute("""
_G._protos = {}
_G._9_trace = {}
_G._9_n = 0
_G._c58_trace = {}
_G._c58_calls = 0
_G._P9_calls = 0
_G._d9_calls = 0
_G._m9_calls = 0
_G._t9_called = 0
""")

modified = runtime.suppress_vm_errors(modified)

print("\nExecuting VM...")
t0 = time.time()
try:
    runtime.execute(modified)
except LuaRuntimeError as e:
    elapsed = time.time() - t0
    print(f"Stopped after {elapsed:.1f}s: {str(e)[:100]}")

runtime.lua.execute("_G._op_count = 0; _G._op_limit = 10000000000")

def li(expr):
    v = runtime.lua.eval(f"tonumber({expr})")
    return int(v) if v is not None else None

def ls(expr):
    v = runtime.lua.eval(expr)
    return str(v) if v is not None else None

print(f"\n=== Deserialization trace ===")
print(f"_9 calls: {li('_G._9_n')}")
print(f"P9 calls: {li('_G._P9_calls')}")
print(f"d9 calls: {li('_G._d9_calls')}")
print(f"m9 calls: {li('_G._m9_calls')}")
print(f"t9 called: {li('_G._t9_called')}")
print(f"I9 called: {ls('tostring(_G._I9_called)')}")
print(f"C[58] calls: {li('_G._c58_calls')}")
print(f"q9 end r10: {li('_G._q9_end_r10')}")
print(f"t9 r10: {li('_G._t9_r10')}")
print(f"I9 r10: {li('_G._I9_r10')}")
print(f"Protos captured: {li('#_G._protos')}")

# Show _9 trace
n_9 = li('_G._9_n') or 0
print(f"\n=== _9 trace ({n_9} calls) ===")
for i in range(1, min(n_9 + 1, 20)):
    runtime.lua.execute(f"""
    local e = _G._9_trace[{i}]
    if e then
        _G._tmp = e.w .. '|' .. tostring(e.r10) .. '|' .. tostring(e.Q)
    else
        _G._tmp = 'nil'
    end
    """)
    print(f"  [{i}] {ls('_G._tmp')}")

# Show C[58] trace
n_c58 = li('_G._c58_calls') or 0
print(f"\n=== C[58] trace ({n_c58} calls, first 30) ===")
for i in range(1, min(n_c58 + 1, 31)):
    runtime.lua.execute(f"""
    local e = _G._c58_trace[{i}]
    if e then
        _G._tmp = e.n .. '|' .. tostring(e.r10)
    else
        _G._tmp = 'nil'
    end
    """)
    print(f"  [{i}] {ls('_G._tmp')}")

# Show buffer around key offsets
with open(r'unobfuscator\cracked script\buffer_1_1064652.bin', 'rb') as f:
    buf = f.read()

print(f"\n=== Buffer around key offsets ===")
for name, offset in [
    ('q9_end (4303)', 4303),
    ('post_varint (4306)', 4306),
    ('4306+20', 4326),
]:
    if offset < len(buf):
        data = buf[offset:offset+20]
        print(f"  {name}: {' '.join(f'{b:02x}' for b in data)}")

# P9 r10
print(f"\nP9 r10: {li('_G._P9_r10')}")
print(f"d9 r10: {li('_G._d9_r10')}")
print(f"m9 r10: {li('_G._m9_r10')}")
