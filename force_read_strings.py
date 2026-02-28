import sys, time, json, re
sys.path.insert(0, '.')

with open(r'unobfuscator\pending crack\bloxburg_script.lua', 'r', encoding='utf-8', errors='replace') as f:
    source = f.read()

exec(open('run_luraph_test.py').read().split("print('Reading source...')")[0])
source = preprocess_luau(source)

from unobfuscator.utils.lua_runtime import LuaRuntimeWrapper, LuaRuntimeError

runtime = LuaRuntimeWrapper(op_limit=2_000_000_000, timeout=120.0)
runtime._init_runtime()

# Hook to capture the r state table
runtime.lua.execute("""
_G._state_r = nil
_G._protos = {}
""")

# Find closure factory and inject hooks
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

# Capture r table on first prototype creation
hook_code = (
    f'if {p1}==nil then return function(...)return end end;'
    f'do local _p={{}};for _i=1,11 do _p[_i]={p1}[_i] end;'
    f'_p.id=#_G._protos+1;table.insert(_G._protos,_p) end;'
)
replacement = prefix + hook_code + suffix
modified = source[:m.start()] + replacement + source[m.end():]

# Also capture the r state table
# The r table is used before the closure factory
# Find where r is initialized - look for the function that receives r as upvalue
# The init function calls r[56] = function(C,W)
# We need to find where r is the closure's environment

# Instead of modifying source, let's capture r via the Lua return value
# The script returns a table. That table IS the z/class object.
# The z object's methods receive r as a parameter.
# We need to capture r from within those methods.

# Simpler approach: look for where specific r[] values are set
# and inject a capture hook there
# The Ky function sets r[49] = function()...r[22](r[33], r[10])...end
# At that point, r is fully initialized. Let me hook r[49].

# Find r[49] or r[0x31] assignment in the modified source
r49_pattern = re.compile(r'(\w)\[0X31\]\s*=\s*function\(\)')
r49_match = r49_pattern.search(modified)
if r49_match:
    r_var = r49_match.group(1)
    insert_pos = r49_match.start()
    capture_code = f'_G._state_r={r_var};'
    modified = modified[:insert_pos] + capture_code + modified[insert_pos:]
    print(f"Injected state capture before r[49] def (r_var={r_var})")
else:
    # Try alternate patterns
    for pat in [r'(\w)\[(?:49|0[xX]31)\]\s*=\s*function']:
        m2 = re.search(pat, modified)
        if m2:
            r_var = m2.group(1)
            insert_pos = m2.start()
            capture_code = f'_G._state_r={r_var};'
            modified = modified[:insert_pos] + capture_code + modified[insert_pos:]
            print(f"Injected state capture (pattern: {pat}, r_var={r_var})")
            break

modified = runtime.suppress_vm_errors(modified)

print("Executing...")
t0 = time.time()
try:
    runtime.execute(modified)
    print(f"Completed in {time.time()-t0:.1f}s")
except LuaRuntimeError as e:
    print(f"Error after {time.time()-t0:.1f}s: {str(e)[:200]}")

# Check if we captured the state table
has_r = runtime.lua.eval("_G._state_r ~= nil")
print(f"\nState table captured: {has_r}")

if has_r:
    # Examine the state table
    r10 = runtime.lua.eval("_G._state_r[10]")
    print(f"r[10] (current offset): {r10}")
    
    # Check which r[] entries are functions
    func_entries = runtime.lua.eval("""
    (function()
        local result = {}
        local r = _G._state_r
        for i = 0, 60 do
            if type(r[i]) == "function" then
                result[#result+1] = i
            end
        end
        return result
    end)()
    """)
    
    func_list = []
    for i in range(1, 100):
        try:
            idx = int(func_entries[i])
            func_list.append(idx)
        except:
            break
    print(f"Function entries in r[]: {func_list}")
    
    # Check r[33] (buffer)
    buf_exists = runtime.lua.eval("type(_G._state_r[33])")
    print(f"r[33] type: {buf_exists}")
    
    buf_len = runtime.lua.eval("buffer.len(_G._state_r[33])")
    print(f"r[33] buffer length: {buf_len}")
    
    # Check r[31] (char table)
    r31_type = runtime.lua.eval("type(_G._state_r[31])")
    print(f"r[31] type: {r31_type}")
    if str(r31_type) == 'table':
        r31_len = runtime.lua.eval("#_G._state_r[31]")
        print(f"r[31] length: {r31_len}")
        # Sample entries
        for i in [0, 65, 66, 97, 98, 48]:
            try:
                v = runtime.lua.eval(f"_G._state_r[31][{i}]")
                print(f"  r[31][{i}] = {repr(str(v))}")
            except:
                pass
    
    # Now try to read strings from the unread buffer section
    # Set r[10] to start of script data and try calling reader functions
    print(f"\n=== Attempting to read script data section ===")
    
    # Save current offset
    old_offset = int(runtime.lua.eval("_G._state_r[10] or 0"))
    print(f"Current r[10]: {old_offset}")
    
    # Try r[50] (which is r[0x32]) - readstring function
    # Try r[45] - variable-length read
    # Try r[46] - another read function
    # Try r[49] - read 4 bytes
    
    # First, let's see what functions are available and test them
    print(f"\nTesting reader functions at current offset:")
    for fn_idx in func_list:
        try:
            # Reset offset to a known position in the script data
            runtime.lua.execute(f"_G._state_r[10] = 94736")
            result = runtime.lua.eval(f"_G._state_r[{fn_idx}]()")
            result_type = type(result).__name__
            if result is not None:
                if isinstance(result, (int, float)):
                    print(f"  r[{fn_idx}]() = {result} ({result_type})")
                elif isinstance(result, str):
                    print(f"  r[{fn_idx}]() = {repr(result[:50])} ({result_type}, len={len(result)})")
                else:
                    print(f"  r[{fn_idx}]() = {result} ({result_type})")
            else:
                print(f"  r[{fn_idx}]() = nil")
            # Check new offset
            new_off = int(runtime.lua.eval("_G._state_r[10] or 0"))
            if new_off != 94736:
                print(f"    offset advanced to {new_off} (consumed {new_off - 94736} bytes)")
        except Exception as e:
            err = str(e)[:100]
            print(f"  r[{fn_idx}]() ERROR: {err}")
    
    # Now try to read strings by calling the readstring-like function
    # with different offsets into the script data
    print(f"\n=== Trying to read strings at various offsets ===")
    
    # The 0x9E tag positions in the script data (sub-buffer offsets from parse)
    # First 0x9E at sub-buffer pos 103+12 = 115 → buffer offset 94736+115 = 94851
    test_offsets = [94840, 94848, 94851, 94852, 94866, 94876, 94894]
    
    for off in test_offsets:
        runtime.lua.execute(f"_G._state_r[10] = {off}")
        # Try each reader function
        for fn_idx in func_list:
            try:
                runtime.lua.execute(f"_G._state_r[10] = {off}")
                result = runtime.lua.eval(f"_G._state_r[{fn_idx}]()")
                new_off = int(runtime.lua.eval("_G._state_r[10] or 0"))
                consumed = new_off - off
                if result is not None and consumed > 0:
                    if isinstance(result, str) and len(result) >= 2:
                        is_print = all(32 <= ord(c) < 127 for c in result)
                        print(f"  offset={off} r[{fn_idx}]() = {repr(result[:60])} (len={len(result)}, consumed={consumed} bytes, printable={is_print})")
                    elif isinstance(result, (int, float)):
                        if consumed > 0 and consumed < 20:
                            print(f"  offset={off} r[{fn_idx}]() = {result} (consumed={consumed} bytes)")
            except:
                pass

    # Restore original offset
    if old_offset:
        runtime.lua.execute(f"_G._state_r[10] = {old_offset}")

else:
    print("Could not capture state table. Trying alternative approach...")
    # Try to find r via global references
    has_r2 = runtime.lua.eval("type(_G._state_r)")
    print(f"_G._state_r type: {has_r2}")
