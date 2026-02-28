import sys, time, json, re, struct
sys.path.insert(0, '.')

with open(r'unobfuscator\pending crack\bloxburg_script.lua', 'r', encoding='utf-8', errors='replace') as f:
    source = f.read()

exec(open('run_luraph_test.py').read().split("print('Reading source...')")[0])
source = preprocess_luau(source)

from unobfuscator.utils.lua_runtime import LuaRuntimeWrapper, LuaRuntimeError

runtime = LuaRuntimeWrapper(op_limit=2_000_000_000, timeout=120.0)
runtime._init_runtime()

runtime.lua.execute("_G._protos = {}; _G._state_r = nil")

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

# Capture r state table - inject at r[49] definition
r49_pattern = re.compile(r'(\w)\[0X31\]\s*=\s*function\(\)')
r49_match = r49_pattern.search(modified)
if r49_match:
    r_var = r49_match.group(1)
    insert_pos = r49_match.start()
    capture_code = f'_G._state_r={r_var};'
    modified = modified[:insert_pos] + capture_code + modified[insert_pos:]
    print(f"State capture injected (r_var={r_var})")

modified = runtime.suppress_vm_errors(modified)

print("Executing...")
t0 = time.time()
try:
    runtime.execute(modified)
    print(f"Completed in {time.time()-t0:.1f}s")
except LuaRuntimeError as e:
    print(f"Error after {time.time()-t0:.1f}s: {str(e)[:200]}")

has_r = runtime.lua.eval("_G._state_r ~= nil")
print(f"State table captured: {has_r}")

if not has_r:
    print("FAILED")
    sys.exit(1)

def li(expr):
    v = runtime.lua.eval(f"tonumber({expr})")
    return int(v) if v is not None else None

# Verify reader functions work
runtime.lua.execute("_G._state_r[10] = 94736")
test = li("_G._state_r[46]()")
new_off = li("_G._state_r[10]")
print(f"r[46]() at 94736 = {test}, new offset = {new_off}")

if new_off != 94737:
    print(f"Reader functions corrupted (offset should be 94737, got {new_off})")
    sys.exit(1)

print("Reader functions working!")

# Map reader functions
# r[39] = readu8 (raw, no varint)
# r[46] = varint reader (LEB128)
# r[40] = readu16
# r[43] = readu32
# r[44] = readi32
# r[49] = readf32
# r[50] = readf64 (or complex state-machine reader)
# r[54] = sub-buffer reader (varint len + buffer.copy)

# Systematic parse of script data section
print(f"\n{'='*60}")
print(f"SYSTEMATIC PARSE OF SCRIPT DATA (offset 94736+)")
print(f"{'='*60}")

SCRIPT_START = 94736

# Step 1: Read sub-buffer
runtime.lua.execute(f"_G._state_r[10] = {SCRIPT_START}")
sub_len = li("_G._state_r[46]()")
sub_off = li("_G._state_r[10]")
print(f"\n[1] Sub-buffer length (varint): {sub_len}")
print(f"    Sub-buffer data at offset {sub_off}")

# Read sub-buffer bytes
sub_bytes = []
for i in range(sub_len):
    b = li(f"buffer.readu8(_G._state_r[33], {sub_off + i})")
    sub_bytes.append(b)
sub_data = bytes(sub_bytes)
print(f"    Sub-buffer hex: {sub_data.hex()}")

# Parse as doubles
for i in range(sub_len // 8):
    v = struct.unpack_from('<d', sub_data, i*8)[0]
    print(f"    double[{i}] = {v}")

# Skip past sub-buffer
runtime.lua.execute(f"_G._state_r[10] = {sub_off + sub_len}")
pos_after_sub = li("_G._state_r[10]")
print(f"\n[2] After sub-buffer: offset {pos_after_sub}")

# Step 2: Read sequential data using different reader functions
# Let me try reading as tagged values first
# In the VM section, the format is: tag_byte (u8), then data based on tag
# The VM section uses tags: 0x73=u8, 0x9E=str, 0x1D=u16, 0xD8=i16, 0x57=i32

# But the script section might use different tags
# Let me read raw bytes and check what's there
print(f"\n[3] First 100 raw bytes after sub-buffer:")
raw = []
for i in range(100):
    b = li(f"buffer.readu8(_G._state_r[33], {pos_after_sub + i})")
    raw.append(b)
print(f"    {bytes(raw).hex()}")

# Identify the pattern
# From earlier: 0x36 appeared frequently = possibly u8 tag in script section
# Let me check: does the VM use different tags per section?

# The VM's deserialization uses state-machine based reading
# r[50] is the complex reader. Let me try it
print(f"\n[4] Testing r[50] (complex reader) at offset {pos_after_sub}:")
runtime.lua.execute(f"_G._state_r[10] = {pos_after_sub}")
try:
    # r[50] returns a value based on the tag dispatch
    result = runtime.lua.eval("_G._state_r[50]()")
    new_off = li("_G._state_r[10]")
    consumed = new_off - pos_after_sub
    rtype = type(result).__name__
    if isinstance(result, (int, float)):
        print(f"    r[50]() = {result} ({rtype}, consumed {consumed} bytes)")
    elif isinstance(result, str):
        is_print = all(32 <= ord(c) < 127 for c in result)
        print(f"    r[50]() = {repr(result[:60])} (str, len={len(result)}, consumed {consumed} bytes, printable={is_print})")
    else:
        print(f"    r[50]() = {result} ({rtype}, consumed {consumed} bytes)")
except Exception as e:
    print(f"    r[50]() ERROR: {str(e)[:200]}")

# If r[50] didn't work, try r[51] or other functions
print(f"\n[5] Testing all reader functions at offset {pos_after_sub}:")
for fn_idx in [37, 39, 40, 41, 43, 44, 45, 46, 47, 49, 50, 51, 54, 55, 56, 58]:
    try:
        runtime.lua.execute(f"_G._state_r[10] = {pos_after_sub}")
        result = runtime.lua.eval(f"_G._state_r[{fn_idx}]()")
        new_off = li("_G._state_r[10]")
        if new_off is None:
            new_off = 0
        consumed = new_off - pos_after_sub
        if result is not None and consumed != 0:
            rtype = type(result).__name__
            if isinstance(result, str) and len(result) > 1:
                print(f"    r[{fn_idx:2d}]() = {repr(str(result)[:50])} ({rtype}, consumed {consumed}B)")
            elif isinstance(result, (int, float)):
                print(f"    r[{fn_idx:2d}]() = {result} ({rtype}, consumed {consumed}B)")
            else:
                print(f"    r[{fn_idx:2d}]() = {str(result)[:30]} ({rtype}, consumed {consumed}B)")
    except Exception as e:
        err = str(e)[:80]
        if 'OP_LIMIT' not in err:
            print(f"    r[{fn_idx:2d}]() ERR: {err}")

# Step 6: Use varint reader to do sequential reading
# This is the most reliable reader
print(f"\n[6] Sequential varint reads from {pos_after_sub}:")
runtime.lua.execute(f"_G._state_r[10] = {pos_after_sub}")

varints = []
for i in range(500):
    try:
        off = li("_G._state_r[10]")
        if off is None or off >= 1064652:
            break
        v = li("_G._state_r[46]()")
        new_off = li("_G._state_r[10]")
        consumed = new_off - off
        varints.append((off, v, consumed))
    except:
        break

print(f"Read {len(varints)} varints")

# Show all and look for patterns
for i, (off, v, c) in enumerate(varints[:150]):
    # Annotate potential meanings
    note = ""
    if v < 128 and c == 1:
        note = f" (raw byte 0x{v:02X})"
    elif c == 2:
        note = f" (2-byte varint)"
    elif c >= 3:
        note = f" ({c}-byte varint)"
    print(f"  [{i:3d}] off={off:7d} val={v:8d}{note}")

# Look for the deserialization function in the source
# The z object methods that handle the actual proto building
# Let me find z:zy (the main deserializer)
print(f"\n[7] Finding deserialization method z:zy in source...")
zy_match = re.search(r'zy\s*=\s*function\s*\(\s*z\s*(?:,\s*\w+)*\s*\)', source)
if zy_match:
    pos = zy_match.start()
    # Extract a chunk around it
    chunk = source[pos:pos+2000]
    # Pretty-print by splitting on semicolons
    lines = chunk.replace(';', ';\n').split('\n')
    print(f"  Found at source pos {pos}:")
    for j, line in enumerate(lines[:30]):
        line = line.strip()
        if line:
            print(f"    {j:3d}: {line[:120]}")

# Save results
with open('systematic_parse_results.json', 'w') as f:
    json.dump({
        'sub_buffer_len': sub_len,
        'sub_buffer_hex': sub_data.hex(),
        'pos_after_sub': pos_after_sub,
        'first_100_bytes_hex': bytes(raw).hex(),
        'varints': [(off, v, c) for off, v, c in varints],
    }, f, indent=2)
print(f"\nSaved to systematic_parse_results.json")
