"""
Inject diagnostics inside q9 (which calls ZF for each string).
Also inject inside lF to see what varint it reads and the buffer offset.
This tells us:
1. What r[10] is when lF/q9 are called
2. What Q (string count) is
3. Whether ZF is called at all
"""
import sys, time, json, re
sys.path.insert(0, '.')

with open(r'unobfuscator\pending crack\bloxburg_script.lua', 'r', encoding='utf-8', errors='replace') as f:
    source = f.read()

exec(open('run_luraph_test.py').read().split("print('Reading source...')")[0])
source = preprocess_luau(source)

from unobfuscator.utils.lua_runtime import LuaRuntimeWrapper, LuaRuntimeError

# Find q9 and inject logging at its start
# q9=function(z,r,C,W,Q)local i;for O=0B1,Q do...
# After preprocessing: q9=function(z,r,C,W,Q)local i;for O=1,Q do...
q9_pat = re.compile(r'q9=function\((\w+),(\w+),(\w+),(\w+),(\w+)\)(local \w+;)')
q9_m = q9_pat.search(source)
if q9_m:
    print(f"Found q9 at pos {q9_m.start()}")
    z_p, r_p, C_p, W_p, Q_p = q9_m.group(1,2,3,4,5)
    local_decl = q9_m.group(6)
    print(f"  Params: z={z_p}, r={r_p}, C={C_p}, W={W_p}, Q={Q_p}")
    
    # Inject after the local declaration
    inject_q9 = (
        f'if not _G._q9_log then _G._q9_log={{}} end;'
        f'table.insert(_G._q9_log,{{'
        f'Q={Q_p},'
        f'r10=type({W_p})=="table" and {W_p}[10] or -1,'
        f'r57_type=type(type({W_p})=="table" and {W_p}[57] or nil),'
        f'call_num=#_G._q9_log+1'
        f'}});'
    )
    
    insert_pos = q9_m.end()
    modified = source[:insert_pos] + inject_q9 + source[insert_pos:]
    print("q9 injection done")
else:
    print("ERROR: q9 not found!")
    modified = source

# Find lF and inject logging
# lF=function(z,r,C,W,Q)local i;(Q)[12]=({});C=nil;W=nil;for O=...
lf_pat = re.compile(r'lF=function\((\w+),(\w+),(\w+),(\w+),(\w+)\)(local \w+;)')
lf_m = lf_pat.search(modified)
if lf_m:
    print(f"Found lF at pos {lf_m.start()}")
    z_p, r_p, C_p, W_p, Q_p = lf_m.group(1,2,3,4,5)
    print(f"  Params: z={z_p}, r={r_p}, C={C_p}, W={W_p}, Q={Q_p}")
    
    inject_lf = (
        f'if not _G._lF_log then _G._lF_log={{}} end;'
        f'table.insert(_G._lF_log,{{'
        f'r10=type({Q_p})=="table" and {Q_p}[10] or -1,'
        f'Q_type=type({Q_p}),'
        f'call_num=#_G._lF_log+1'
        f'}});'
    )
    
    insert_pos = lf_m.end()
    modified = modified[:insert_pos] + inject_lf + modified[insert_pos:]
    print("lF injection done")

# Find ZF and inject logging
# ZF stores result in r[57][C] — inject to count ZF calls
zf_pat = re.compile(r'ZF=function\((\w+),(\w+),(\w+),(\w+)\)')
zf_m = zf_pat.search(modified)
if zf_m:
    print(f"Found ZF at pos {zf_m.start()}")
    z_p, r_p, C_p, W_p = zf_m.group(1,2,3,4)
    print(f"  Params: z={z_p}, r={r_p}, C={C_p}, W={W_p}")
    
    # Find the closing ')' of the function parameters
    func_body_start = modified.index(')', zf_m.end()) + 1
    
    inject_zf = (
        f'if not _G._zf_count then _G._zf_count=0 end;'
        f'_G._zf_count=_G._zf_count+1;'
        f'if _G._zf_count<=5 then '
        f'if not _G._zf_log then _G._zf_log={{}} end;'
        f'table.insert(_G._zf_log,{{'
        f'r10=type({r_p})=="table" and {r_p}[10] or -1,'
        f'C={C_p},'
        f'W_type=type({W_p}),'
        f'call_num=_G._zf_count'
        f'}}) end;'
    )
    
    modified = modified[:func_body_start] + inject_zf + modified[func_body_start:]
    print("ZF injection done")

# Also inject inside oF to see if it reads from buffer
of_pat = re.compile(r'oF=function\((\w+),(\w+),(\w+)\)')
of_m = of_pat.search(modified)
if of_m:
    print(f"Found oF at pos {of_m.start()}")
    z_p, z2_p, r_p = of_m.group(1,2,3)
    func_body_start = modified.index(')', of_m.end()) + 1
    inject_of = (
        f'if not _G._oF_log then _G._oF_log={{}} end;'
        f'table.insert(_G._oF_log,{{'
        f'r10=type({r_p})=="table" and {r_p}[10] or -1,'
        f'r_type=type({r_p})'
        f'}});'
    )
    modified = modified[:func_body_start] + inject_of + modified[func_body_start:]
    print("oF injection done")

# Inject inside fF too
ff_pat = re.compile(r'fF=function\((\w+),(\w+),(\w+),(\w+),(\w+)\)')
ff_m = ff_pat.search(modified)
if ff_m:
    print(f"Found fF at pos {ff_m.start()}")
    z_p, r_p, C_p, W_p, Q_p = ff_m.group(1,2,3,4,5)
    func_body_start = modified.index(')', ff_m.end()) + 1
    inject_ff = (
        f'if not _G._fF_log then _G._fF_log={{}} end;'
        f'table.insert(_G._fF_log,{{'
        f'C={C_p},'
        f'Q=type({Q_p})=="number" and {Q_p} or -99999,'
        f'r10=type({r_p})=="table" and {r_p}[10] or -1,'
        f'r_type=type({r_p})'
        f'}});'
    )
    modified = modified[:func_body_start] + inject_ff + modified[func_body_start:]
    print("fF injection done")

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
_G._q9_log = {}
_G._lF_log = {}
_G._zf_log = {}
_G._zf_count = 0
_G._oF_log = {}
_G._fF_log = {}
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

# Print diagnostics
print(f"\n=== lF calls: {li('#_G._lF_log')} ===")
n = li('#_G._lF_log') or 0
for i in range(1, min(n+1, 11)):
    runtime.lua.execute(f"_G._t = _G._lF_log[{i}]")
    print(f"  [{i}] r10={li('_G._t.r10')}, Q_type={ls('_G._t.Q_type')}, call_num={li('_G._t.call_num')}")

print(f"\n=== fF calls: {li('#_G._fF_log')} ===")
n = li('#_G._fF_log') or 0
for i in range(1, min(n+1, 11)):
    runtime.lua.execute(f"_G._t = _G._fF_log[{i}]")
    print(f"  [{i}] C={li('_G._t.C')}, Q={li('_G._t.Q')}, r10={li('_G._t.r10')}, r_type={ls('_G._t.r_type')}")

print(f"\n=== oF calls: {li('#_G._oF_log')} ===")
n = li('#_G._oF_log') or 0
for i in range(1, min(n+1, 11)):
    runtime.lua.execute(f"_G._t = _G._oF_log[{i}]")
    print(f"  [{i}] r10={li('_G._t.r10')}, r_type={ls('_G._t.r_type')}")

print(f"\n=== q9 calls: {li('#_G._q9_log')} ===")
n = li('#_G._q9_log') or 0
for i in range(1, min(n+1, 11)):
    runtime.lua.execute(f"_G._t = _G._q9_log[{i}]")
    print(f"  [{i}] Q={li('_G._t.Q')}, r10={li('_G._t.r10')}, r57_type={ls('_G._t.r57_type')}, call_num={li('_G._t.call_num')}")

print(f"\n=== ZF calls: {li('_G._zf_count')} ===")
n = li('#_G._zf_log') or 0
for i in range(1, min(n+1, 11)):
    runtime.lua.execute(f"_G._t = _G._zf_log[{i}]")
    print(f"  [{i}] r10={li('_G._t.r10')}, C={li('_G._t.C')}, W_type={ls('_G._t.W_type')}, call_num={li('_G._t.call_num')}")

print(f"\nProtos captured: {li('#_G._protos')}")
