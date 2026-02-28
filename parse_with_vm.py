import sys, time, json, re
sys.path.insert(0, '.')

with open(r'unobfuscator\pending crack\bloxburg_script.lua', 'r', encoding='utf-8', errors='replace') as f:
    source = f.read()

exec(open('run_luraph_test.py').read().split("print('Reading source...')")[0])
source = preprocess_luau(source)

from unobfuscator.utils.lua_runtime import LuaRuntimeWrapper, LuaRuntimeError

runtime = LuaRuntimeWrapper(op_limit=5_000_000_000, timeout=180.0)
runtime._init_runtime()

runtime.lua.execute("_G._state_r = nil; _G._protos = {}")

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

# Capture state table
r49_pattern = re.compile(r'(\w)\[0X31\]\s*=\s*function\(\)')
r49_match = r49_pattern.search(modified)
if r49_match:
    r_var = r49_match.group(1)
    insert_pos = r49_match.start()
    capture_code = f'_G._state_r={r_var};'
    modified = modified[:insert_pos] + capture_code + modified[insert_pos:]
    print(f"State capture injected (r_var={r_var})")

modified = runtime.suppress_vm_errors(modified)

print("Executing VM init...")
t0 = time.time()
try:
    runtime.execute(modified)
    print(f"Completed in {time.time()-t0:.1f}s")
except LuaRuntimeError as e:
    print(f"Error after {time.time()-t0:.1f}s: {str(e)[:200]}")

has_r = runtime.lua.eval("_G._state_r ~= nil")
print(f"State table captured: {has_r}")
if not has_r:
    print("FAILED: State table not captured")
    sys.exit(1)

def lua_int(expr):
    v = runtime.lua.eval(f"tonumber({expr})")
    return int(v) if v is not None else 0

def lua_val(expr):
    return runtime.lua.eval(expr)

# Get current offset (end of init data)
init_end = lua_int("_G._state_r[10]")
print(f"Init end offset: {init_end}")

# Map reader functions
# r[39] = readu8, r[40] = readu16, r[43] = readu32
# r[46] = varint, r[50] = readf64, r[54] = read sub-buffer
# r[44] = readi32, r[49] = readf32

# Now systematically parse the script data section
# Set offset to start of script data
SCRIPT_START = 94736

print(f"\n=== Parsing script data from offset {SCRIPT_START} ===")

# First, understand the varint encoding
print("\nVarint encoding test:")
for test_off in [94736, 94852, 94876]:
    runtime.lua.execute(f"_G._state_r[10] = {test_off}")
    v = lua_int("_G._state_r[46]()")
    new_off = lua_int("_G._state_r[10]")
    consumed = new_off - test_off
    print(f"  offset {test_off}: varint={v} (consumed {consumed} bytes)")

# Read the deserialization sequence from the VM init trace
# to understand the format. The init reads prototypes using a specific
# sequence of reader calls. Let me replicate that for the script data.

# From analyzing the VM code:
# The main deserialization loop reads prototypes:
# 1. Read number of prototypes (varint)
# 2. For each prototype:
#    a. Read instruction count (varint)
#    b. Read instructions
#    c. Read constant count (varint)
#    d. Read constants
#    e. Read sub-prototypes count (varint)
#    f. Read sub-prototypes recursively

# But first, let me just sequentially read varints and see the pattern
print(f"\n=== Sequential varint reads from script data ===")
runtime.lua.execute(f"_G._state_r[10] = {SCRIPT_START}")

varints = []
for i in range(200):
    try:
        off_before = lua_int("_G._state_r[10]")
        v = lua_int("_G._state_r[46]()")
        off_after = lua_int("_G._state_r[10]")
        consumed = off_after - off_before
        varints.append((off_before, v, consumed))
    except Exception as e:
        print(f"  Read {i} failed at offset {off_before}: {str(e)[:80]}")
        break

print(f"Read {len(varints)} varints")
for i, (off, v, c) in enumerate(varints[:50]):
    print(f"  [{i:3d}] offset={off:7d} varint={v:10d} ({c} bytes)")

# Now let me try the sub-buffer reader (r[54])
# It reads a length (varint) then copies that many bytes
print(f"\n=== Testing r[54] (sub-buffer reader) ===")
runtime.lua.execute(f"_G._state_r[10] = {SCRIPT_START}")
try:
    # Read the sub-buffer
    sub_result = runtime.lua.eval("_G._state_r[54]()")
    new_off = lua_int("_G._state_r[10]")
    print(f"r[54]() consumed {new_off - SCRIPT_START} bytes, offset now at {new_off}")
    
    # Read the sub-buffer contents
    sub_len = lua_int("buffer.len(_G._last_sub or buffer.create(0))")
    print(f"Sub-buffer length: {sub_len}")
    
    # Store the sub-buffer for inspection
    runtime.lua.execute("""
    local r = _G._state_r
    r[10] = """ + str(SCRIPT_START) + """
    local sub = r[54]()
    _G._last_sub = sub
    _G._sub_len = buffer.len(sub)
    """)
    sub_len = lua_int("_G._sub_len")
    print(f"Sub-buffer size: {sub_len} bytes")
    
    # Read first few bytes of sub-buffer
    sub_bytes = []
    for i in range(min(sub_len, 100)):
        b = lua_int(f"buffer.readu8(_G._last_sub, {i})")
        sub_bytes.append(b)
    print(f"First {len(sub_bytes)} bytes: {bytes(sub_bytes).hex()}")
    
    # Try parsing as f64 values
    import struct
    raw = bytes(sub_bytes)
    n_floats = len(raw) // 8
    print(f"\nAs f64 values ({n_floats} doubles):")
    for i in range(n_floats):
        v = struct.unpack_from('<d', raw, i*8)[0]
        if 0 < abs(v) < 1e10 and v == v:
            print(f"  float[{i}] = {v}")

except Exception as e:
    print(f"r[54]() error: {str(e)[:200]}")

# After the sub-buffer, continue reading
new_off = lua_int("_G._state_r[10]")
print(f"\n=== Continuing reads after sub-buffer (offset {new_off}) ===")

# Read more varints
varints2 = []
for i in range(100):
    try:
        off_before = lua_int("_G._state_r[10]")
        v = lua_int("_G._state_r[46]()")
        off_after = lua_int("_G._state_r[10]")
        consumed = off_after - off_before
        varints2.append((off_before, v, consumed))
    except Exception as e:
        print(f"  Read {i} failed: {str(e)[:80]}")
        break

for i, (off, v, c) in enumerate(varints2[:50]):
    print(f"  [{i:3d}] offset={off:7d} varint={v:10d} ({c} bytes)")

# Now try calling the FULL deserialization function 
# r[50] was identified as the main reader function that dispatches
print(f"\n=== Testing r[50] (main deserialization reader) ===")
runtime.lua.execute(f"_G._state_r[10] = {SCRIPT_START + 37}")  # after sub-buffer
try:
    result = lua_val("_G._state_r[50]()")
    new_off = lua_int("_G._state_r[10]")
    print(f"r[50]() = {result} (type: {type(result).__name__})")
    print(f"Consumed: {new_off - SCRIPT_START - 37} bytes")
except Exception as e:
    print(f"r[50]() error: {str(e)[:200]}")

# Try r[45] (reads 8 bytes as integer)
runtime.lua.execute(f"_G._state_r[10] = {SCRIPT_START + 37}")
try:
    result = lua_val("_G._state_r[45]()")
    new_off = lua_int("_G._state_r[10]")
    print(f"r[45]() = {result} (type: {type(result).__name__})")
    print(f"Consumed: {new_off - SCRIPT_START - 37} bytes")
except Exception as e:
    print(f"r[45]() error: {str(e)[:200]}")

# Summary
print(f"\n=== Reader function mapping ===")
reader_map = {
    39: "readu8 (1 byte)",
    40: "readu16 (2 bytes)",
    43: "readu32 (4 bytes)",
    44: "readi32 (4 bytes)",
    46: "varint (1-2 bytes)",
    49: "readf32 (4 bytes)",
    50: "readf64 (8 bytes)",
    54: "sub-buffer (varint len + data)",
}
for idx, desc in sorted(reader_map.items()):
    print(f"  r[{idx}] = {desc}")
