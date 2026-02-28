"""
Trace the full deserialization chain with corrected parameter mapping.
_9=function(z,r,C,W,Q,i,O): r=state_table, C=w(loop_idx), Q=count
"""
import sys, time, json, re
sys.path.insert(0, '.')

with open(r'unobfuscator\pending crack\bloxburg_script.lua', 'r', encoding='utf-8', errors='replace') as f:
    source = f.read()

exec(open('run_luraph_test.py').read().split("print('Reading source...')")[0])
source = preprocess_luau(source)

from unobfuscator.utils.lua_runtime import LuaRuntimeWrapper, LuaRuntimeError

modified = source

# === Inject in _9 ===
_9_pat = re.compile(r'(_9=function\((\w+),(\w+),(\w+),(\w+),(\w+),(\w+),(\w+)\))')
_9_m = _9_pat.search(modified)
z_p, r_p, C_p, W_p, Q_p, i_p, O_p = [_9_m.group(j) for j in range(2, 9)]
print(f"_9: z={z_p} r(state)={r_p} C(w)={C_p} W={W_p} Q(count)={Q_p} i={i_p} O={O_p}")

inject = (
    f'do local _n=(_G._9_n or 0)+1;_G._9_n=_n;'
    f'_G._9_trace[_n]={C_p}.."|"..'
    f'tostring({r_p}[10]).."|"..tostring({Q_p}) end;'
)
modified = modified[:_9_m.end()] + inject + modified[_9_m.end():]

# === Inject in P9 ===
P9_pat = re.compile(r'(P9=function\((\w+),(\w+),(\w+),(\w+)\))')
P9_m = P9_pat.search(modified)
if P9_m:
    P9_z, P9_r, P9_C, P9_W = [P9_m.group(j) for j in range(2, 6)]
    print(f"P9: z={P9_z} r={P9_r} C={P9_C} W={P9_W}")
    inject_P9 = (
        f'_G._P9_calls=(_G._P9_calls or 0)+1;'
        f'_G._P9_r10={P9_C}[10];'
    )
    modified = modified[:P9_m.end()] + inject_P9 + modified[P9_m.end():]

# === Inject in d9 ===
d9_pat = re.compile(r'(d9=function\((\w+),(\w+),(\w+),(\w+)\))')
d9_m = d9_pat.search(modified)
if d9_m:
    d9_z, d9_r, d9_C, d9_W = [d9_m.group(j) for j in range(2, 6)]
    print(f"d9: z={d9_z} r={d9_r} C={d9_C} W={d9_W}")
    inject_d9 = (
        f'_G._d9_calls=(_G._d9_calls or 0)+1;'
        f'_G._d9_r10={d9_C}[10];'
    )
    modified = modified[:d9_m.end()] + inject_d9 + modified[d9_m.end():]

# === Inject in m9 ===
m9_pat = re.compile(r'(m9=function\((\w+),(\w+),(\w+),(\w+)\))')
m9_m = m9_pat.search(modified)
if m9_m:
    m9_z, m9_r, m9_C, m9_W = [m9_m.group(j) for j in range(2, 6)]
    print(f"m9: z={m9_z} r={m9_r} C={m9_C} W={m9_W}")
    inject_m9 = (
        f'_G._m9_calls=(_G._m9_calls or 0)+1;'
        f'_G._m9_r10={m9_C}[10];'
    )
    modified = modified[:m9_m.end()] + inject_m9 + modified[m9_m.end():]

# === Inject in t9 ===
t9_pat = re.compile(r'(t9=function\((\w+),(\w+),(\w+),(\w+),(\w+)\))')
t9_m = t9_pat.search(modified)
if t9_m:
    t9_params = [t9_m.group(j) for j in range(2, 7)]
    print(f"t9 params: {t9_params}")
    # t9(z,z,r,C,W) — z is shadowed by 2nd param!
    # The shadowed z is actually the state table? Let me check
    # t9=function(z,z,r,C,W) — first z=self, second z=shadowed=state_table
    # t9 body: if C then if z[45]==z[35]... z[4][2]=z[57]... z[4][3]=r
    # z here is the shadowed 2nd param (state table)
    # r is the 3rd param
    # So z[10] = state_table[10]
    inject_t9 = (
        f'_G._t9_called=(_G._t9_called or 0)+1;'
        f'_G._t9_r10={t9_params[1]}[10];'
    )
    modified = modified[:t9_m.end()] + inject_t9 + modified[t9_m.end():]

# === Inject in I9 ===
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

# === Find and inject C[58] ===
# C[58] might be written as C[0x3a] or C[0B111010] or C[58]
# Search more broadly in the return block
ret_start = modified.index('return({')
# Look for )[NUMBER]=function( patterns
proto_deser_pat = re.compile(r'\)\[(\d+|0[xXbBoO][0-9a-fA-F_]+)\]\s*=\s*function\((\w+),(\w+)\)')
proto_matches = list(proto_deser_pat.finditer(modified, ret_start))
print(f"\nPrototype deserializer candidates: {len(proto_matches)}")
for m in proto_matches[:10]:
    idx_str = m.group(1)
    try:
        idx = int(idx_str.replace('_', ''), 0)
    except:
        idx = idx_str
    print(f"  idx={idx} (raw={idx_str}), params=({m.group(2)},{m.group(3)}), pos={m.start()}")
    # Show context
    ctx = modified[m.start():m.start()+100]
    print(f"    {repr(ctx[:80])}")

# === Inject in q9 for r10 tracking ===
q9_start = modified.find('q9=function(')
q9_params = re.search(r'q9=function\((\w+),(\w+),(\w+),(\w+),(\w+)\)', modified[q9_start:])
W_var = q9_params.group(4)
C_var = q9_params.group(3)
inject_marker = re.search(r'end;end;(' + re.escape(C_var) + r'=\(' + re.escape(W_var) + r'\[)', modified[q9_start:])
inject_pos = q9_start + inject_marker.start() + len('end;end;')
dump_code = f'_G._q9_end_r10={W_var}[10];'
modified = modified[:inject_pos] + dump_code + modified[inject_pos:]

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
    print(f"Stopped after {elapsed:.1f}s: {str(e)[:200]}")

runtime.lua.execute("_G._op_count = 0; _G._op_limit = 10000000000")

def li(expr):
    v = runtime.lua.eval(f"tonumber({expr})")
    return int(v) if v is not None else None

def ls(expr):
    v = runtime.lua.eval(expr)
    return str(v) if v is not None else None

print(f"\n=== Deserialization Summary ===")
print(f"_9 calls: {li('_G._9_n')}")
print(f"P9 calls: {li('_G._P9_calls')}")
print(f"d9 calls: {li('_G._d9_calls')}")
print(f"m9 calls: {li('_G._m9_calls')}")
print(f"t9 called: {li('_G._t9_called')}")
print(f"I9 called: {ls('tostring(_G._I9_called)')}")
print(f"q9 end r10: {li('_G._q9_end_r10')}")
print(f"P9 r10: {li('_G._P9_r10')}")
print(f"d9 r10: {li('_G._d9_r10')}")
print(f"m9 r10: {li('_G._m9_r10')}")
print(f"t9 r10: {li('_G._t9_r10')}")
print(f"I9 r10: {li('_G._I9_r10')}")
print(f"Protos: {li('#_G._protos')}")

n_9 = li('_G._9_n') or 0
print(f"\n=== _9 trace ({n_9} calls) ===")
for i in range(1, min(n_9 + 1, 20)):
    val = ls(f"_G._9_trace[{i}]")
    if val and val != 'None':
        parts = val.split('|')
        print(f"  [{i}] w={parts[0]}, r10={parts[1]}, Q={parts[2]}")
