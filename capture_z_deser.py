import sys, time, json, re
sys.path.insert(0, '.')

with open(r'unobfuscator\pending crack\bloxburg_script.lua', 'r', encoding='utf-8', errors='replace') as f:
    source = f.read()

exec(open('run_luraph_test.py').read().split("print('Reading source...')")[0])
source = preprocess_luau(source)

from unobfuscator.utils.lua_runtime import LuaRuntimeWrapper, LuaRuntimeError

runtime = LuaRuntimeWrapper(op_limit=2_000_000_000, timeout=120.0)
runtime._init_runtime()

runtime.lua.execute("_G._protos = {}; _G._z_obj = nil; _G._state_r = nil")

# Find closure factory pattern
pattern = re.compile(
    r'(\)\[(?:\d+|0[xXbBoO][0-9a-fA-F_]+)\]=function\()'
    r'([A-Za-z_]\w*)'
    r','
    r'([A-Za-z_]\w*)'
    r'\)'
    r'(local\s+[A-Za-z_]\w*(?:,[A-Za-z_]\w*){9,}=)'
    r'(\2\[)'
)
m = pattern.search(source)
p1 = m.group(2)
full_match = m.group(0)
local_pos = full_match.index('local')
prefix = full_match[:local_pos]
suffix = full_match[local_pos:]

hook_code = (
    f'if {p1}==nil then return function(...)return end end;'
    f'do local _p={{}};for _i=1,11 do _p[_i]={p1}[_i] end;'
    f'_p.id=#_G._protos+1;table.insert(_G._protos,_p) end;'
)
replacement = prefix + hook_code + suffix
modified = source[:m.start()] + replacement + source[m.end():]

# Capture state table r right when reader functions are defined
r49_pattern = re.compile(r'(\w)\[0X31\]\s*=\s*function\(\)')
r49_match = r49_pattern.search(modified)
if r49_match:
    r_var = r49_match.group(1)
    insert_pos = r49_match.start()
    capture_code = f'_G._state_r={r_var};'
    modified = modified[:insert_pos] + capture_code + modified[insert_pos:]

# Capture the z object (return value)
# The script starts with 'return({...'
# Replace 'return(' with '_G._z_obj=(' at the very beginning
if modified.startswith('return('):
    modified = '_G._z_obj=' + modified[len('return'):]
    modified += ';return _G._z_obj'

modified = runtime.suppress_vm_errors(modified)

print("Executing VM init...")
t0 = time.time()
try:
    runtime.execute(modified)
    print(f"Completed in {time.time()-t0:.1f}s")
except LuaRuntimeError as e:
    print(f"Error after {time.time()-t0:.1f}s: {str(e)[:200]}")

def lua_int(expr):
    v = runtime.lua.eval(f"tonumber({expr})")
    return int(v) if v is not None else 0

def lua_str(expr):
    v = runtime.lua.eval(f"tostring({expr})")
    return str(v) if v else ''

# Check captures
has_z = runtime.lua.eval("_G._z_obj ~= nil")
has_r = runtime.lua.eval("_G._state_r ~= nil")
print(f"z object captured: {has_z}")
print(f"r state captured: {has_r}")
print(f"Prototypes captured: {lua_int('#_G._protos')}")

if has_z:
    # List all methods/fields on z
    z_fields = runtime.lua.eval("""
    (function()
        local result = {}
        for k, v in pairs(_G._z_obj) do
            result[#result+1] = {key=tostring(k), typ=type(v)}
        end
        return result
    end)()
    """)
    
    n = lua_int("#" + "z_fields" if False else "0")
    # Get count properly
    field_count = 0
    z_methods = []
    z_tables = []
    z_other = []
    for i in range(1, 200):
        try:
            k = str(runtime.lua.eval(f"_G._z_obj_fields and _G._z_obj_fields[{i}] and _G._z_obj_fields[{i}].key"))
            if k == 'None' or k == 'nil':
                break
        except:
            break
    
    # Better approach: iterate in Lua
    runtime.lua.execute("""
    _G._z_fields = {}
    _G._z_funcs = {}
    _G._z_tables = {}
    for k, v in pairs(_G._z_obj) do
        table.insert(_G._z_fields, tostring(k) .. "=" .. type(v))
        if type(v) == "function" then
            table.insert(_G._z_funcs, tostring(k))
        elseif type(v) == "table" then
            table.insert(_G._z_tables, tostring(k))
        end
    end
    table.sort(_G._z_funcs)
    table.sort(_G._z_tables)
    """)
    
    nf = lua_int("#_G._z_funcs")
    nt = lua_int("#_G._z_tables")
    print(f"\nz object: {lua_int('#_G._z_fields')} fields ({nf} functions, {nt} tables)")
    
    print("\nz methods (functions):")
    for i in range(1, nf + 1):
        name = lua_str(f"_G._z_funcs[{i}]")
        print(f"  z.{name}")
    
    print("\nz tables:")
    for i in range(1, nt + 1):
        name = lua_str(f"_G._z_tables[{i}]")
        # Get table size
        sz = lua_int(f"#(_G._z_obj['{name}'] or {{}})")
        print(f"  z.{name} (#{sz})")

if has_r:
    # Check key r entries
    print(f"\n=== State table r ===")
    for idx in [10, 22, 23, 31, 33, 36, 39, 40, 43, 44, 45, 46, 49, 50, 54]:
        t = lua_str(f"type(_G._state_r[{idx}])")
        if t == 'function':
            print(f"  r[{idx}] = function")
        elif t == 'userdata':
            print(f"  r[{idx}] = buffer (len={lua_int(f'buffer.len(_G._state_r[{idx}])')})")
        elif t == 'table':
            print(f"  r[{idx}] = table (#{lua_int(f'#_G._state_r[{idx}]')})")
        elif t == 'number':
            print(f"  r[{idx}] = {lua_int(f'_G._state_r[{idx}]')}")
        elif t == 'nil':
            print(f"  r[{idx}] = nil")
        else:
            print(f"  r[{idx}] = {t}")

    # Try to use reader functions - set r[10] first
    print(f"\n=== Testing reader functions ===")
    runtime.lua.execute("_G._state_r[10] = 94736")
    r10_check = lua_int("_G._state_r[10]")
    print(f"Set r[10] = 94736, read back: {r10_check}")
    
    if r10_check == 94736:
        # Test varint reader r[46]
        for fn_idx in [39, 46, 40, 43, 44, 50]:
            try:
                runtime.lua.execute("_G._state_r[10] = 94736")
                result = runtime.lua.eval(f"_G._state_r[{fn_idx}]()")
                new_off = lua_int("_G._state_r[10]")
                consumed = new_off - 94736
                if result is not None:
                    val = str(result)[:50]
                    print(f"  r[{fn_idx}]() at 94736: {val} (consumed {consumed} bytes, new_off={new_off})")
                else:
                    print(f"  r[{fn_idx}]() at 94736: nil")
            except Exception as e:
                print(f"  r[{fn_idx}]() ERROR: {str(e)[:100]}")
        
        # If varint works, read the sub-buffer then sequential varints
        print(f"\n=== Reading sub-buffer + sequential data ===")
        runtime.lua.execute("_G._state_r[10] = 94736")
        
        # Read sub-buffer length (varint)
        sub_len = lua_int("_G._state_r[46]()")
        print(f"Sub-buffer length: {sub_len}")
        off_after_len = lua_int("_G._state_r[10]")
        print(f"Offset after length read: {off_after_len}")
        
        # Skip sub-buffer data
        runtime.lua.execute(f"_G._state_r[10] = _G._state_r[10] + {sub_len}")
        off_after_sub = lua_int("_G._state_r[10]")
        print(f"Offset after sub-buffer: {off_after_sub}")
        
        # Now read sequential varints to understand the format
        print(f"\nSequential varints from offset {off_after_sub}:")
        varints = []
        for i in range(300):
            try:
                off = lua_int("_G._state_r[10]")
                v = lua_int("_G._state_r[46]()")
                new_off = lua_int("_G._state_r[10]")
                consumed = new_off - off
                varints.append((off, v, consumed))
            except Exception as e:
                print(f"  Varint {i} failed: {str(e)[:80]}")
                break
        
        print(f"Read {len(varints)} varints")
        for i, (off, v, c) in enumerate(varints[:100]):
            print(f"  [{i:3d}] off={off:7d} val={v:8d} ({c}B)")

        # Now try to detect the structure
        # Look for patterns: large value followed by many small values = instruction array
        print(f"\n=== Pattern detection ===")
        vals = [v for _, v, _ in varints]
        
        # Find potential instruction counts (values followed by that many more values)
        for i in range(min(20, len(vals))):
            count = vals[i]
            if 10 < count < 5000:
                # Check if we have enough values after this
                remaining = len(vals) - i - 1
                if remaining >= count:
                    # Possible instruction count at index i
                    subset = vals[i+1:i+1+min(count, 20)]
                    avg = sum(subset) / len(subset)
                    max_v = max(subset)
                    print(f"  val[{i}]={count}: next {min(count,20)} vals avg={avg:.1f} max={max_v}")
    else:
        print("WARNING: r[10] was not properly set (state table may be corrupted)")
        # Try direct buffer reads instead
        print("\nFalling back to direct buffer reads...")
        runtime.lua.execute("_G._state_r[10] = 94736")
        try:
            b = lua_int("buffer.readu8(_G._state_r[33], 94736)")
            print(f"  buffer.readu8(buf, 94736) = {b} (0x{b:02X})")
            b2 = lua_int("buffer.readu8(_G._state_r[33], 94737)")
            print(f"  buffer.readu8(buf, 94737) = {b2} (0x{b2:02X})")
        except Exception as e:
            print(f"  Direct read error: {str(e)[:100]}")
