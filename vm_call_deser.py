"""
Use the VM's own reader functions to deserialize.
Key insight: F9 sets C[58] where C = r table, so r[58] = prototype deserializer.
Also F9 defines W (lazy deserializer) that is called by C9.
We need to call the deserialization chain in the right order.
"""
import sys, time, json, re, struct
sys.path.insert(0, '.')

with open(r'unobfuscator\pending crack\bloxburg_script.lua', 'r', encoding='utf-8', errors='replace') as f:
    source = f.read()

exec(open('run_luraph_test.py').read().split("print('Reading source...')")[0])
source = preprocess_luau(source)

from unobfuscator.utils.lua_runtime import LuaRuntimeWrapper, LuaRuntimeError

runtime = LuaRuntimeWrapper(op_limit=2_000_000_000, timeout=120)
runtime._init_runtime()
runtime.lua.execute("_G._protos = {}; _G._saved = {}")

# Inject r table capture after z:zy(r) + proto capture hook
pat = re.compile(
    r'(\)\[(?:\d+|0[xXbBoO][0-9a-fA-F_]+)\]=function\()'
    r'([A-Za-z_]\w*)' r',' r'([A-Za-z_]\w*)' r'\)'
    r'(local\s+[A-Za-z_]\w*(?:,[A-Za-z_]\w*){9,}=)'
    r'(\2\[)'
)
m = pat.search(source)
p1 = m.group(2)
full_match = m.group(0)
lp = full_match.index('local')
hook = (
    f'if {p1}==nil then return function(...)return end end;'
    f'do local _p={{}};for _i=1,11 do _p[_i]={p1}[_i] end;'
    f'_p.id=#_G._protos+1;table.insert(_G._protos,_p) end;'
)
modified = source[:m.start()] + full_match[:lp] + hook + full_match[lp:] + source[m.end():]

zy_matches = list(re.finditer(r':zy\((\w+)\)', modified))
zm = zy_matches[0]
r_arg = zm.group(1)
semi_pos = modified.index(';', zm.end())
capture = f';_G._r={r_arg};_G._saved.done=true'
modified = modified[:semi_pos+1] + capture + modified[semi_pos+1:]

modified = runtime.suppress_vm_errors(modified)

print("Executing...")
t0 = time.time()
try:
    runtime.execute(modified)
except LuaRuntimeError as e:
    print(f"Stopped after {time.time()-t0:.1f}s")

def li(expr):
    v = runtime.lua.eval(f"tonumber({expr})")
    return int(v) if v is not None else None

def ls(expr):
    v = runtime.lua.eval(expr)
    return str(v) if v is not None else None

runtime.lua.execute("_G._op_count = 0; _G._op_limit = 10000000000")

print(f"State captured: {ls('tostring(_G._saved.done)')}")

# Enumerate ALL r table entries
print("\n=== r table contents ===")
runtime.lua.execute("""
_G._r_info = {}
for k = 1, 200 do
    local v = _G._r[k]
    if v ~= nil then
        local t = type(v)
        local info = t
        if t == 'number' then info = t .. '=' .. tostring(v)
        elseif t == 'table' then
            local count = 0
            for _ in pairs(v) do count = count + 1 end
            info = t .. '(' .. count .. ' entries)'
        elseif t == 'boolean' then info = tostring(v)
        end
        table.insert(_G._r_info, k .. ':' .. info)
    end
end
""")
n_info = li("#_G._r_info") or 0
for i in range(1, n_info + 1):
    print(f"  {ls(f'_G._r_info[{i}]')}")

# Check specifically for r[58] (should be C[58] = prototype deserializer from F9)
r58_type = ls("type(_G._r[58])")
print(f"\nr[58] type: {r58_type}")

# Check r[57] - should be string table
r57_type = ls("type(_G._r[57])")
print(f"r[57] type: {r57_type}")

if str(r57_type) == 'table':
    r57_len = li("#_G._r[57]") or 0
    print(f"r[57] length: {r57_len}")
    # Show first entries
    runtime.lua.execute("""
    _G._r57_info = {}
    for k, v in pairs(_G._r[57]) do
        local info = tostring(k) .. ':' .. type(v)
        if type(v) == 'string' then
            info = info .. '=' .. string.sub(v, 1, 50)
        elseif type(v) == 'number' then
            info = info .. '=' .. tostring(v)
        end
        table.insert(_G._r57_info, info)
        if #_G._r57_info > 50 then break end
    end
    """)
    n57 = li("#_G._r57_info") or 0
    for i in range(1, n57 + 1):
        print(f"  r[57]: {ls(f'_G._r57_info[{i}]')}")

# Also check the z object (VM class) for attributes
print("\n=== z object attributes ===")
runtime.lua.execute("""
_G._z_info = {}
-- The z object is the return table. We captured _G._r which is the r param.
-- To access z, we need the z param from one of the methods.
-- Actually, the z methods are defined as methods on the return table.
-- The return table is what :q() is called on.
-- We don't have a direct reference to z, but z.D, z.T, z.M are used.
""")

# Check what r[24] does (z.T)
print("\n=== Testing r[24] (z.T) ===")
r24_type = ls("type(_G._r[24])")
print(f"r[24] type: {r24_type}")
if str(r24_type) == 'function':
    # r[24] is called with a number arg in UF: O[24](q) where q = varint - 96207
    # Let's test it with different inputs
    for test_val in [0, 1, 10, 100, 1000]:
        try:
            runtime.lua.execute(f"_G._op_count = 0; _G._t24 = _G._r[24]({test_val})")
            v = ls("tostring(_G._t24)")
            t = ls("type(_G._t24)")
            print(f"  r[24]({test_val}) = {v} (type={t})")
        except Exception as e:
            print(f"  r[24]({test_val}) ERROR: {e}")

# Check r[43] (readu8 wrapper? or another function?)
print("\n=== Testing r[43] ===")
r43_type = ls("type(_G._r[43])")
print(f"r[43] type: {r43_type}")

# Set r[10] to script data start and try calling r[58]
print("\n=== Attempting to call r[58] (prototype deserializer) ===")
if str(r58_type) == 'function':
    # Set offset to after the init section
    runtime.lua.execute(f"_G._r[10] = 94736; _G._op_count = 0")
    try:
        runtime.lua.execute("""
        _G._op_count = 0
        local ok, result = pcall(_G._r[58])
        _G._deser_ok = ok
        _G._deser_result = result
        _G._deser_type = type(result)
        _G._deser_r10 = _G._r[10]
        """)
        ok = ls("tostring(_G._deser_ok)")
        rtype = ls("_G._deser_type")
        r10 = li("_G._deser_r10")
        print(f"  ok={ok}, result type={rtype}, r[10] after={r10}")
        
        if str(ok) == 'true' and str(rtype) == 'table':
            # The result should be a prototype table!
            runtime.lua.execute("""
            _G._proto_info = {}
            for k = 1, 11 do
                local v = _G._deser_result[k]
                if v ~= nil then
                    local t = type(v)
                    local info = tostring(k) .. ':' .. t
                    if t == 'number' then info = info .. '=' .. tostring(v)
                    elseif t == 'table' then
                        local c = 0
                        for _ in pairs(v) do c = c + 1 end
                        info = info .. '(' .. c .. ' entries)'
                    end
                    table.insert(_G._proto_info, info)
                end
            end
            """)
            n_pi = li("#_G._proto_info") or 0
            print(f"  Proto fields ({n_pi}):")
            for i in range(1, n_pi + 1):
                print(f"    {ls(f'_G._proto_info[{i}]')}")
        elif str(ok) == 'false':
            err = ls("tostring(_G._deser_result)")
            print(f"  Error: {err[:200]}")
    except Exception as e:
        print(f"  Exception: {e}")
else:
    print(f"  r[58] is {r58_type}, not a function - F9 hasn't executed yet")
    print("  F9 runs AFTER z:zy, so r[58] is set during z:q execution")
    print("  But our capture is after z:zy which is inside z:q's Jy call")
    print("  F9 is called AFTER Jy in z:q, so r[58] might not be set yet")
    
# Check buffer offset
print(f"\n=== Buffer state ===")
print(f"r[10] = {li('_G._r[10]')}")
print(f"Buffer len = {li('buffer.len(_G._r[33])')}")
