"""
Debug why lF doesn't read from buffer when called manually.
Instrument r[46] and z.fF to trace exact call flow.
"""
import sys, time, json, re
sys.path.insert(0, '.')

with open(r'unobfuscator\pending crack\bloxburg_script.lua', 'r', encoding='utf-8', errors='replace') as f:
    source = f.read()

exec(open('run_luraph_test.py').read().split("print('Reading source...')")[0])
source = preprocess_luau(source)

from unobfuscator.utils.lua_runtime import LuaRuntimeWrapper, LuaRuntimeError

runtime = LuaRuntimeWrapper(op_limit=2_000_000_000, timeout=120)
runtime._init_runtime()
runtime.lua.execute("_G._protos = {}")

modified = source
zy_matches = list(re.finditer(r':zy\((\w+)\)', modified))
zm = zy_matches[0]
r_arg = zm.group(1)
semi_pos = modified.index(';', zm.end())
i = zm.start() - 1
while i >= 0 and (modified[i].isalnum() or modified[i] == '_'):
    i -= 1
z_var = modified[i+1:zm.start()]
capture = f';_G._r={r_arg};_G._z={z_var}'
modified = modified[:semi_pos+1] + capture + modified[semi_pos+1:]

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

modified = runtime.suppress_vm_errors(modified)

print("Executing VM...")
t0 = time.time()
try:
    runtime.execute(modified)
except LuaRuntimeError as e:
    print(f"Stopped after {time.time()-t0:.1f}s")

runtime.lua.execute("_G._op_count = 0; _G._op_limit = 10000000000")

def li(expr):
    v = runtime.lua.eval(f"tonumber({expr})")
    return int(v) if v is not None else None

def ls(expr):
    v = runtime.lua.eval(expr)
    return str(v) if v is not None else None

print(f"z: {ls('type(_G._z)')}, r: {ls('type(_G._r)')}")

# Extract oF function to understand what it does
runtime.lua.execute("""
_G._oF_src = 'NOT FOUND'
if type(_G._z.oF) == 'function' then
    _G._oF_src = 'function found'
end
""")
print(f"z.oF: {ls('_G._oF_src')}")

# Step 1: Wrap r[46] and z.fF to trace calls
runtime.lua.execute("""
_G._trace = {}
_G._op_count = 0

-- Wrap r[46] (varint reader)
local _orig_r46 = _G._r[46]
_G._r[46] = function(...)
    local r10_before = _G._r[10]
    local result = _orig_r46(...)
    local r10_after = _G._r[10]
    table.insert(_G._trace, 'r46: r10=' .. r10_before .. '->' .. r10_after .. ' val=' .. tostring(result))
    return result
end

-- Wrap r[39] (readu8)
local _orig_r39 = _G._r[39]
_G._r[39] = function(...)
    local r10_before = _G._r[10]
    local result = _orig_r39(...)
    local r10_after = _G._r[10]
    table.insert(_G._trace, 'r39: r10=' .. r10_before .. '->' .. r10_after .. ' val=' .. tostring(result))
    return result
end

-- Wrap z.fF
local _orig_fF = _G._z.fF
_G._z.fF = function(z, r, C, W, Q)
    table.insert(_G._trace, 'fF called: C=' .. tostring(C) .. ' W=' .. type(W) .. ' Q=' .. tostring(Q))
    local i, w = _orig_fF(z, r, C, W, Q)
    table.insert(_G._trace, 'fF returned: i=' .. tostring(i) .. ' W type=' .. type(w))
    return i, w
end

-- Wrap z.oF
local _orig_oF = _G._z.oF
if _orig_oF then
    _G._z.oF = function(z, W, r)
        table.insert(_G._trace, 'oF called: W=' .. type(W) .. ' r=' .. type(r))
        local result = _orig_oF(z, W, r)
        table.insert(_G._trace, 'oF returned: ' .. type(result))
        return result
    end
end

-- Now call lF with r[10] = 94736
_G._r[10] = 94736
_G._r[57] = {}

local ok, W, r_nil, C = pcall(function()
    return _G._z.lF(_G._z, nil, nil, nil, _G._r)
end)

_G._lf_ok = ok
_G._lf_r10 = _G._r[10]
if ok then
    _G._lf_W_type = type(W)
    _G._lf_C = C
else
    _G._lf_err = tostring(W)
end
""")

ok = ls("tostring(_G._lf_ok)")
r10_after = li("_G._lf_r10")
print(f"\nlF ok={ok}, r[10]={r10_after}")
if str(ok) == 'true':
    print(f"  W type={ls('_G._lf_W_type')}, C={li('_G._lf_C')}")
else:
    print(f"  Error: {ls('_G._lf_err')}")

# Print trace
trace_n = li("#_G._trace") or 0
print(f"\nTrace ({trace_n} entries):")
for i in range(1, trace_n + 1):
    print(f"  {ls(f'_G._trace[{i}]')}")

# Also check: what does r[57] look like now?
r57_type = ls("type(_G._r[57])")
if str(r57_type) == 'table':
    runtime.lua.execute("""
    _G._r57_count = 0
    for k, v in pairs(_G._r[57]) do
        _G._r57_count = _G._r57_count + 1
    end
    """)
    print(f"r[57]: {li('_G._r57_count')} entries")

# Now try calling lF with wrapped r[46] at offset 94773
print(f"\n{'='*70}")
print("Testing at offset 94773")
print(f"{'='*70}")
runtime.lua.execute("""
_G._trace = {}
_G._op_count = 0
_G._r[10] = 94773
_G._r[57] = {}

local ok, W, r_nil, C = pcall(function()
    return _G._z.lF(_G._z, nil, nil, nil, _G._r)
end)

_G._lf2_ok = ok
_G._lf2_r10 = _G._r[10]
if ok then
    _G._lf2_W_type = type(W)
    _G._lf2_C = C
else
    _G._lf2_err = tostring(W)
end
""")
ok2 = ls("tostring(_G._lf2_ok)")
r10_2 = li("_G._lf2_r10")
print(f"lF ok={ok2}, r[10]={r10_2}")
if str(ok2) == 'true':
    print(f"  W type={ls('_G._lf2_W_type')}, C={li('_G._lf2_C')}")
else:
    print(f"  Error: {ls('_G._lf2_err')}")

trace_n2 = li("#_G._trace") or 0
print(f"\nTrace ({trace_n2} entries):")
for i in range(1, trace_n2 + 1):
    print(f"  {ls(f'_G._trace[{i}]')}")

# Now let's also check: can we call the full lazy deserializer W by calling
# C[58] and then W? These are defined by F9.
# Since F9 hasn't run, C[58] is nil. But maybe we can call F9 manually.
print(f"\n{'='*70}")
print("Checking if we can call F9 manually")
print(f"{'='*70}")
print(f"r[58] type: {ls('type(_G._r[58])')}")
print(f"z.F9 type: {ls('type(_G._z.F9)')}")

# F9 needs: z:F9(Q,r,O,q,a,i) where Q,r,O,q,a,i are from z:q
# C parameter of F9 = r_table
# Let's try calling F9 with the r table
runtime.lua.execute("""
_G._op_count = 0
_G._r[10] = 94736
_G._r[57] = {}

-- F9 signature: F9=function(z,r,C,W,Q,i,O) where C is the r_table
-- From z:q: i,O,a,q = z:F9(Q,r,O,q,a,i)
-- The params map to F9(z, Q_param, r_table, O_param, q_param, a_param, i_param)
-- F9 uses C (3rd param) to set C[58] = ... and C[46]() for varints
-- So C = r_table

local ok, err = pcall(function()
    local O, W, i, Q = _G._z.F9(_G._z, nil, _G._r, nil, nil, nil, nil)
    _G._f9_O = O
    _G._f9_W_type = type(W)
    _G._f9_i_type = type(i)
    _G._f9_Q_type = type(Q)
end)
_G._f9_ok = ok
if not ok then
    _G._f9_err = tostring(err)
end
""")

f9_ok = ls("tostring(_G._f9_ok)")
print(f"F9 ok={f9_ok}")
if str(f9_ok) == 'true':
    print(f"  O={li('_G._f9_O')}")
    print(f"  W type={ls('_G._f9_W_type')}")
    print(f"  i type={ls('_G._f9_i_type')}")
    print(f"  Q type={ls('_G._f9_Q_type')}")
    print(f"  r[58] type: {ls('type(_G._r[58])')}")
else:
    print(f"  Error: {ls('_G._f9_err')[:200]}")

# If F9 works, try calling W (the lazy deserializer)
if str(f9_ok) == 'true':
    runtime.lua.execute("""
    _G._op_count = 0
    _G._r[10] = 94736
    _G._r[57] = {}
    _G._trace = {}
    
    local W = _G._f9_W_type == 'function' and _G._z.F9 -- won't work, need actual W
    -- Actually, if F9 set C[58] = function, we can call it
    if type(_G._r[58]) == 'function' then
        local ok, result = pcall(_G._r[58])
        _G._r58_ok = ok
        if ok then
            _G._r58_result_type = type(result)
        else
            _G._r58_err = tostring(result)
        end
    end
    """)
    r58_type = ls("type(_G._r[58])")
    print(f"\nAfter F9: r[58] type={r58_type}")
    if str(r58_type) == 'function':
        r58_ok = ls("tostring(_G._r58_ok)")
        print(f"  r[58]() ok={r58_ok}")
        if str(r58_ok) == 'true':
            print(f"  result type={ls('_G._r58_result_type')}")
            # Check r[57]
            runtime.lua.execute("""
            _G._final_count = 0
            _G._final_samples = {}
            for k, v in pairs(_G._r[57]) do
                _G._final_count = _G._final_count + 1
                if _G._final_count <= 50 then
                    local info = tostring(k) .. ':' .. type(v)
                    if type(v) == 'string' then
                        local safe = ''
                        for i = 1, math.min(#v, 60) do
                            local b = string.byte(v, i)
                            if b >= 32 and b <= 126 then
                                safe = safe .. string.char(b)
                            else
                                safe = safe .. '.'
                            end
                        end
                        info = info .. '=' .. safe
                    elseif type(v) == 'table' then
                        local c = 0
                        for _ in pairs(v) do c = c + 1 end
                        info = info .. ' (tbl ' .. c .. ')'
                        if v[1] and type(v[1]) == 'string' then
                            local safe = ''
                            for i = 1, math.min(#v[1], 60) do
                                local b = string.byte(v[1], i)
                                if b >= 32 and b <= 126 then
                                    safe = safe .. string.char(b)
                                else
                                    safe = safe .. '.'
                                end
                            end
                            info = info .. '=' .. safe
                        end
                    end
                    table.insert(_G._final_samples, info)
                end
            end
            """)
            fc = li("_G._final_count")
            print(f"  r[57] entries: {fc}")
            for i in range(1, min((li("#_G._final_samples") or 0) + 1, 51)):
                print(f"    {ls(f'_G._final_samples[{i}]')}")
        else:
            print(f"  r[58]() error: {ls('_G._r58_err')[:200]}")
