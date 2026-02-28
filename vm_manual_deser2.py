"""
Manual deserialization attempt #2.
Start at r[10]=94736 (the value after full init), not 94773.
Also try different offsets systematically.
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
runtime.lua.execute("_G._protos = {}; _G._saved = {}")

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
print(f"r[10] after VM: {li('_G._r[10]')}")

# Test reading a varint at different offsets
print(f"\n=== Testing varint reader at different offsets ===")
for test_off in [94736, 94737, 94773, 94774]:
    runtime.lua.execute(f"""
    _G._op_count = 0
    _G._r[10] = {test_off}
    local ok, v = pcall(_G._r[46])
    _G._tv = ok and v or nil
    _G._tr10 = _G._r[10]
    _G._tok = ok
    """)
    ok = ls("tostring(_G._tok)")
    v = li("_G._tv")
    r10a = li("_G._tr10")
    print(f"  offset {test_off}: ok={ok} varint={v} r[10]after={r10a} consumed={r10a-test_off if r10a else '?'}")

# Test readu8 at key offsets
print(f"\n=== Testing readu8 (r[39]) at different offsets ===")
for test_off in [94736, 94737, 94773, 94774, 94775]:
    runtime.lua.execute(f"""
    _G._op_count = 0
    _G._r[10] = {test_off}
    local ok, v = pcall(_G._r[39])
    _G._tv = ok and v or nil
    _G._tr10 = _G._r[10]
    """)
    v = li("_G._tv")
    r10a = li("_G._tr10")
    print(f"  offset {test_off}: u8={v} (0x{v:02x}) r[10]after={r10a}")

# Now let's understand: the lazy deserializer W starts with r[10] at 94736
# But wait - who set r[10] = 94736? Let me check if the sub-buffer read
# is done before lF or as part of lF

# Actually, let me trace the entire z:q flow to understand when r[10] gets set
# The key question: does any method between z:zy and W() set r[10]?

# Let me check what r[10] is used for. Maybe it's not the buffer offset at all
# during the init phase. Let me see if r[10] changes when I call r[39]
print(f"\n=== Verifying r[10] is buffer offset ===")
runtime.lua.execute(f"""
_G._op_count = 0
_G._r[10] = 0
local v1 = _G._r[39]()
_G._v1 = v1
_G._r10_1 = _G._r[10]
local v2 = _G._r[39]()
_G._v2 = v2  
_G._r10_2 = _G._r[10]
""")
v1 = li("_G._v1")
r10_1 = li("_G._r10_1")
v2 = li("_G._v2")
r10_2 = li("_G._r10_2")
print(f"  After 1st readu8: val={v1}, r[10]={r10_1}")
print(f"  After 2nd readu8: val={v2}, r[10]={r10_2}")

# Check buffer bytes at offset 0
with open(r'unobfuscator\cracked script\buffer_1_1064652.bin', 'rb') as f:
    buf_data = f.read()
print(f"  Buffer[0]={buf_data[0]:02x}, Buffer[1]={buf_data[1]:02x}")
print(f"  Match: v1==Buffer[0]? {v1==buf_data[0]}, v2==Buffer[1]? {v2==buf_data[1]}")

# Now try the full deserializer chain starting at 94736
print(f"\n{'='*70}")
print("Full deserializer chain starting at r[10]=94736")
print(f"{'='*70}")

# First check: does the lazy deserializer read the sub-buffer?
# Or is the sub-buffer handled separately?
# Let me try calling z:lF at 94736 vs 94773

for start_off in [94736, 94773]:
    print(f"\n--- Starting at r[10]={start_off} ---")
    runtime.lua.execute(f"""
    _G._op_count = 0
    _G._r[10] = {start_off}
    _G._r[12] = nil
    _G._r[42] = nil
    _G._r[57] = {{}}
    
    local ok, W, r_nil, C = pcall(function()
        return _G._z.lF(_G._z, nil, nil, nil, _G._r)
    end)
    _G._lf_ok = ok
    _G._lf_r10 = _G._r[10]
    if ok then
        _G._lf_W = W
        _G._lf_C = C
        _G._lf_Wtype = type(W)
    else
        _G._lf_err = tostring(W)
    end
    """)
    ok = ls("tostring(_G._lf_ok)")
    r10_after = li("_G._lf_r10")
    if str(ok) == 'true':
        W_type = ls("_G._lf_Wtype")
        C = li("_G._lf_C")
        consumed = r10_after - start_off if r10_after else 0
        print(f"  lF OK: W type={W_type}, C={C}, r[10]={r10_after}, consumed={consumed}")
        
        # Check what W is (it should be meaningful for the next steps)
        if str(W_type) == 'table':
            runtime.lua.execute("""
            _G._W_info = ''
            for k, v in pairs(_G._lf_W) do
                _G._W_info = _G._W_info .. tostring(k) .. ':' .. type(v) .. ' '
            end
            """)
            print(f"  W contents: {ls('_G._W_info')}")
        elif str(W_type) == 'number':
            print(f"  W value: {li('_G._lf_W')}")
        
        r42 = ls("type(_G._r[42])")
        print(f"  r[42]={r42}")
    else:
        print(f"  lF ERROR: {ls('_G._lf_err')[:200]}")

# Since r[10]=94736 didn't give sub-buffer, let me check:
# Maybe the sub-buffer is read by a different function, not lF
# Let me try r[54] (sub-buffer reader) at 94736
print(f"\n=== Testing r[54] (sub-buffer reader) at 94736 ===")
runtime.lua.execute("""
_G._op_count = 0
_G._r[10] = 94736
local ok, v = pcall(_G._r[54])
_G._sb_ok = ok
_G._sb_r10 = _G._r[10]
if ok then
    _G._sb_type = type(v)
    if type(v) == 'userdata' or type(v) == 'table' then
        _G._sb_info = tostring(v)
    elseif type(v) == 'number' then
        _G._sb_info = tostring(v)
    else
        _G._sb_info = type(v) .. '=' .. tostring(v)
    end
else
    _G._sb_info = tostring(v)
end
""")
sb_ok = ls("tostring(_G._sb_ok)")
sb_r10 = li("_G._sb_r10")
print(f"  ok={sb_ok}, r[10]={sb_r10}, info={ls('_G._sb_info')}")

# Try also r[47] which reads f64 values (sub-buffer contains f64s!)
print(f"\n=== Testing r[47] (f64 reader?) at 94737 ===")
# The sub-buffer starts at 94737 (after varint 36)
# It contains 36 bytes = 4.5 f64 values (or 9 f32 values)
# From raw data: e88fd77d60cf3f50... looks like f64 little-endian
import struct
for i in range(4):
    off = 94737 + i * 8
    val = struct.unpack_from('<d', buf_data, off)[0]
    print(f"  f64 at {off}: {val}")

# Also check: is the sub-buffer a key/seed table?
# Let me read it as f64 array using r[47]
print(f"\n=== Reading sub-buffer as f64 via r[47] ===")
runtime.lua.execute("""
_G._op_count = 0
_G._r[10] = 94737
_G._f64_vals = {}
for i = 1, 4 do
    local ok, v = pcall(_G._r[47])
    if ok then
        table.insert(_G._f64_vals, v)
    else
        table.insert(_G._f64_vals, 'ERR:' .. tostring(v))
        break
    end
end
_G._r10_after_f64 = _G._r[10]
""")
r10_af64 = li("_G._r10_after_f64")
print(f"  r[10] after 4 f64 reads: {r10_af64}")
for i in range(1, 5):
    v = ls(f"tostring(_G._f64_vals[{i}])")
    print(f"  f64[{i}]: {v}")

# Now the big test: manually call the FULL lazy deserializer chain
# using the correct flow from the W function in F9
print(f"\n{'='*70}")
print("Full lazy deserializer W() simulation")
print(f"{'='*70}")

# Set r[10] to 94736 (where the VM left it after init)
runtime.lua.execute("""
_G._op_count = 0
_G._r[10] = 94736
_G._r[12] = nil
_G._r[42] = nil
_G._r[57] = {}

-- Step 1: Call lF
local W, r_nil, C = _G._z.lF(_G._z, nil, nil, nil, _G._r)
_G._step1_W = W
_G._step1_C = C
_G._step1_r10 = _G._r[10]
_G._step1_W_type = type(W)
""")
print(f"Step 1 (lF): W type={ls('_G._step1_W_type')}, C={li('_G._step1_C')}, r[10]={li('_G._step1_r10')}")

# Step 2: _9 loop
runtime.lua.execute("""
_G._op_count = 0
local W = _G._step1_W  -- D from lF
local Y = nil           -- r from lF (nil)
local q = _G._step1_C  -- C from lF
local Z = nil

for w = 30, 530, 117 do
    local a
    a, Y, Z = _G._z._9(_G._z, _G._r, w, Y, q, Z, W)
    _G.__9_last_a = a
    _G.__9_last_w = w
    if a == 62586 then
        -- continue
    elseif a == -1 then
        _G.__9_err = 'returned -1 at w=' .. w
        break
    else
        _G.__9_unknown_a = a
    end
end

_G.__9_Y = Y
_G.__9_Z = Z
_G.__9_r10 = _G._r[10]
_G.__9_Z_type = type(Z)
_G.__9_Y_type = type(Y)
""")
print(f"Step 2 (_9): Z type={ls('_G.__9_Z_type')}, Y type={ls('_G.__9_Y_type')}, r[10]={li('_G.__9_r10')}")
print(f"  last a={li('_G.__9_last_a')}, last w={li('_G.__9_last_w')}")
if ls("_G.__9_err"):
    print(f"  Error: {ls('_G.__9_err')}")
if li("_G.__9_unknown_a"):
    print(f"  Unknown a: {li('_G.__9_unknown_a')}")

# Step 3: t9 (first call, builds string table?)
runtime.lua.execute("""
_G._op_count = 0
local ok, result = pcall(function()
    return _G._z.t9(_G._z, _G._r, _G.__9_Z, _G._step1_W, _G._step1_C)
end)
_G._t9_1_ok = ok
_G._t9_1_r10 = _G._r[10]
if ok then
    _G._t9_1_result = result
    _G._t9_1_type = type(result)
else
    _G._t9_1_err = tostring(result)
end
""")
t9_ok = ls("tostring(_G._t9_1_ok)")
print(f"Step 3 (t9 #1): ok={t9_ok}, r[10]={li('_G._t9_1_r10')}")
if str(t9_ok) == 'true':
    print(f"  result type={ls('_G._t9_1_type')}")
else:
    print(f"  error: {ls('_G._t9_1_err')[:200]}")

# Check r[57]
runtime.lua.execute("""
_G._str_count57 = 0
if type(_G._r[57]) == 'table' then
    for k, v in pairs(_G._r[57]) do
        _G._str_count57 = _G._str_count57 + 1
    end
end
""")
print(f"  r[57] entries: {li('_G._str_count57')}")

# Step 4: I9
runtime.lua.execute("""
_G._op_count = 0
pcall(function() _G._z.I9(_G._z, _G._r) end)
""")

# Step 5: t9 second call
runtime.lua.execute("""
_G._op_count = 0
local ok, result = pcall(function()
    return _G._z.t9(_G._z, _G._r, _G.__9_Z, _G._step1_W, _G._t9_1_result or _G._step1_C)
end)
_G._t9_2_ok = ok
_G._t9_2_r10 = _G._r[10]
if ok then
    _G._t9_2_type = type(result)
else
    _G._t9_2_err = tostring(result)
end
""")
print(f"Step 5 (t9 #2): ok={ls('tostring(_G._t9_2_ok)')}, r[10]={li('_G._t9_2_r10')}")

# Final r[57] check
runtime.lua.execute("""
_G._final_str_count = 0
_G._final_str_samples = {}
if type(_G._r[57]) == 'table' then
    for k, v in pairs(_G._r[57]) do
        _G._final_str_count = _G._final_str_count + 1
        if _G._final_str_count <= 30 then
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
            end
            table.insert(_G._final_str_samples, info)
        end
    end
end
""")
final_count = li("_G._final_str_count")
print(f"\nFinal r[57]: {final_count} entries")
n = li("#_G._final_str_samples") or 0
for i in range(1, n + 1):
    print(f"  {ls(f'_G._final_str_samples[{i}]')}")
