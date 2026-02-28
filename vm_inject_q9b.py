"""
Inject simple diagnostics inside q9, lF, fF, oF using only simple global assignments.
"""
import sys, time, json, re
sys.path.insert(0, '.')

with open(r'unobfuscator\pending crack\bloxburg_script.lua', 'r', encoding='utf-8', errors='replace') as f:
    source = f.read()

exec(open('run_luraph_test.py').read().split("print('Reading source...')")[0])
source = preprocess_luau(source)

from unobfuscator.utils.lua_runtime import LuaRuntimeWrapper, LuaRuntimeError

modified = source

# 1. Inject in lF: log r[10] when called
# lF=function(z,r,C,W,Q)local i;(Q)[12]=...
lf_pat = re.compile(r'(lF=function\(\w+,\w+,\w+,\w+,(\w+)\)local \w+;)')
lf_m = lf_pat.search(modified)
if lf_m:
    Q_p = lf_m.group(2)
    inject = (
        f'_G._lf_calls=(_G._lf_calls or 0)+1;'
        f'_G._lf_r10={Q_p}[10];'
    )
    modified = modified[:lf_m.end()] + inject + modified[lf_m.end():]
    print(f"lF injected (Q_param={Q_p})")

# 2. Inject in fF: log C and Q values
# fF=function(z,r,C,W,Q)if C<=...
ff_pat = re.compile(r'(fF=function\(\w+,(\w+),(\w+),\w+,(\w+)\))')
ff_m = ff_pat.search(modified)
if ff_m:
    r_p, C_p, Q_p = ff_m.group(2), ff_m.group(3), ff_m.group(4)
    inject = (
        f'_G._ff_calls=(_G._ff_calls or 0)+1;'
        f'_G._ff_C={C_p};'
        f'_G._ff_Q={Q_p};'
        f'_G._ff_r10={r_p}[10];'
    )
    modified = modified[:ff_m.end()] + inject + modified[ff_m.end():]
    print(f"fF injected (r={r_p}, C={C_p}, Q={Q_p})")

# 3. Inject in oF: log r[10] before read
# oF=function(z,z,r)z=(r[39]()~=0);return z;
of_pat = re.compile(r'(oF=function\(\w+,\w+,(\w+)\))')
of_m = of_pat.search(modified)
if of_m:
    r_p = of_m.group(2)
    inject = (
        f'_G._of_calls=(_G._of_calls or 0)+1;'
        f'_G._of_r10={r_p}[10];'
    )
    modified = modified[:of_m.end()] + inject + modified[of_m.end():]
    print(f"oF injected (r={r_p})")

# 4. Inject in q9: log Q (string count) and r[10]
# q9=function(z,r,C,W,Q)local i;for O=1,Q do...
q9_pat = re.compile(r'(q9=function\(\w+,\w+,\w+,(\w+),(\w+)\)local \w+;)')
q9_m = q9_pat.search(modified)
if q9_m:
    W_p, Q_p = q9_m.group(2), q9_m.group(3)
    inject = (
        f'_G._q9_calls=(_G._q9_calls or 0)+1;'
        f'_G._q9_Q={Q_p};'
        f'_G._q9_r10={W_p}[10];'
    )
    modified = modified[:q9_m.end()] + inject + modified[q9_m.end():]
    print(f"q9 injected (W={W_p}, Q={Q_p})")

# 5. Inject in ZF: count calls and log first few
# ZF=function(z,r,C,W)local Q,i,O,a=...
zf_pat = re.compile(r'(ZF=function\(\w+,(\w+),(\w+),(\w+)\))')
zf_m = zf_pat.search(modified)
if zf_m:
    r_p, C_p, W_p = zf_m.group(2), zf_m.group(3), zf_m.group(4)
    inject = (
        f'_G._zf_calls=(_G._zf_calls or 0)+1;'
        f'if _G._zf_calls<=3 then '
        f'_G._zf_r10={r_p}[10];'
        f'_G._zf_C={C_p};'
        f'end;'
    )
    modified = modified[:zf_m.end()] + inject + modified[zf_m.end():]
    print(f"ZF injected (r={r_p}, C={C_p})")

# 6. Inject string dump at W's return point  
# D>4 then return q; (inside W function in F9)
return_q_pat = re.compile(r'(D>(?:0[xXbBoO][0-9a-fA-F_]+|\d+)\s*then\s*)(return\s+q\s*;)')
w_def = re.search(r'W=\(function\(\)local\s+\w+,q,', modified)
if w_def:
    rq_matches = list(return_q_pat.finditer(modified, w_def.start()))
    if rq_matches:
        target = rq_matches[0]
        dump = (
            '_G._w_done=true;'
            '_G._w_r10=C[10];'
            '_G._w_r57_type=type(C[57]);'
            'if type(C[57])=="table" then '
            '_G._w_r57_n=0;'
            'for _k in pairs(C[57]) do _G._w_r57_n=_G._w_r57_n+1 end '
            'end;'
        )
        modified = (
            modified[:target.start()] +
            target.group(1) + dump + target.group(2) +
            modified[target.end():]
        )
        print("W return dump injected")

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
_G._lf_calls = 0
_G._ff_calls = 0
_G._of_calls = 0
_G._q9_calls = 0
_G._zf_calls = 0
_G._w_done = false
""")

modified = runtime.suppress_vm_errors(modified)

print("\nExecuting VM (15B ops, 600s)...")
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

print(f"\n=== Diagnostics ===")
print(f"lF calls: {li('_G._lf_calls')}, r10 at call: {li('_G._lf_r10')}")
print(f"fF calls: {li('_G._ff_calls')}, C: {li('_G._ff_C')}, Q: {li('_G._ff_Q')}, r10: {li('_G._ff_r10')}")
print(f"oF calls: {li('_G._of_calls')}, r10: {li('_G._of_r10')}")
print(f"q9 calls: {li('_G._q9_calls')}, Q: {li('_G._q9_Q')}, r10: {li('_G._q9_r10')}")
print(f"ZF calls: {li('_G._zf_calls')}, r10: {li('_G._zf_r10')}, C: {li('_G._zf_C')}")
print(f"W done: {ls('tostring(_G._w_done)')}")
print(f"  W r10: {li('_G._w_r10')}")
print(f"  W r57 type: {ls('_G._w_r57_type')}")
print(f"  W r57 count: {li('_G._w_r57_n')}")
print(f"Protos: {li('#_G._protos')}")
