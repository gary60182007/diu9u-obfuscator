import sys, time, json, re, struct
sys.path.insert(0, '.')

with open(r'unobfuscator\pending crack\bloxburg_script.lua', 'r', encoding='utf-8', errors='replace') as f:
    source = f.read()

exec(open('run_luraph_test.py').read().split("print('Reading source...')")[0])
source = preprocess_luau(source)

from unobfuscator.utils.lua_runtime import LuaRuntimeWrapper, LuaRuntimeError

runtime = LuaRuntimeWrapper(op_limit=2_000_000_000, timeout=120.0)
runtime._init_runtime()

runtime.lua.execute("_G._protos = {}; _G._saved = {}")

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

# Find z:zy(r) and inject state capture AFTER it
# This saves key reader functions before execution phase corrupts them
zy_matches = list(re.finditer(r':zy\((\w+)\)', modified))
print(f"Found {len(zy_matches)} z:zy() calls")

if zy_matches:
    zm = zy_matches[0]
    r_arg = zm.group(1)  # The r argument passed to zy
    # Find semicolon after the call
    semi_pos = modified.index(';', zm.end())
    
    # Inject code to capture the state right after deserialization
    capture_code = (
        f';_G._saved.r10={r_arg}[10]'
        f';_G._saved.r33={r_arg}[33]'
        f';_G._saved.r39={r_arg}[39]'
        f';_G._saved.r40={r_arg}[40]'
        f';_G._saved.r43={r_arg}[43]'
        f';_G._saved.r44={r_arg}[44]'
        f';_G._saved.r46={r_arg}[46]'
        f';_G._saved.r49={r_arg}[49]'
        f';_G._saved.r50={r_arg}[50]'
        f';_G._saved.r54={r_arg}[54]'
        f';_G._saved.r31={r_arg}[31]'
        f';_G._saved.r22={r_arg}[22]'
        f';_G._saved.r23={r_arg}[23]'
        f';_G._saved.done=true'
    )
    modified = modified[:semi_pos+1] + capture_code + modified[semi_pos+1:]
    print(f"Injected state capture after z:zy({r_arg}) at pos {semi_pos}")

modified = runtime.suppress_vm_errors(modified)

print("Executing...")
t0 = time.time()
try:
    runtime.execute(modified)
    print(f"Completed in {time.time()-t0:.1f}s")
except LuaRuntimeError as e:
    print(f"Error after {time.time()-t0:.1f}s: {str(e)[:200]}")

def li(expr):
    v = runtime.lua.eval(f"tonumber({expr})")
    return int(v) if v is not None else None

saved_done = runtime.lua.eval("_G._saved.done")
n_protos = li("#_G._protos") or 0
print(f"\nCapture done: {saved_done}")
print(f"Prototypes: {n_protos}")

# Check saved state
r10 = li("_G._saved.r10")
print(f"Saved r[10] (buffer offset at init end): {r10}")

r33_type = runtime.lua.eval("type(_G._saved.r33)")
print(f"Saved r[33] type: {r33_type}")

r46_type = runtime.lua.eval("type(_G._saved.r46)")
print(f"Saved r[46] type: {r46_type}")

if str(r46_type) != 'function':
    print("r[46] is not a function - state not captured correctly")
    # Check all saved entries
    for k in ['r10', 'r33', 'r39', 'r40', 'r43', 'r44', 'r46', 'r49', 'r50', 'r54', 'r31', 'r22', 'r23']:
        t = runtime.lua.eval(f"type(_G._saved.{k})")
        print(f"  _G._saved.{k} = {t}")
    sys.exit(1)

# Test the saved reader functions
buf_len = li("buffer.len(_G._saved.r33)")
print(f"Buffer length: {buf_len}")

# Create a helper that uses saved functions with a custom offset
runtime.lua.execute("""
_G._read_offset = 0

function _G.set_offset(off)
    _G._read_offset = off
end

function _G.get_offset()
    return _G._read_offset
end

function _G.read_varint()
    local result = 0
    local shift = 0
    local buf = _G._saved.r33
    while true do
        local b = buffer.readu8(buf, _G._read_offset)
        _G._read_offset = _G._read_offset + 1
        result = result + bit32.lshift(bit32.band(b, 0x7F), shift)
        if b < 128 then break end
        shift = shift + 7
    end
    return result
end

function _G.read_u8()
    local b = buffer.readu8(_G._saved.r33, _G._read_offset)
    _G._read_offset = _G._read_offset + 1
    return b
end

function _G.read_u16()
    local v = buffer.readu16(_G._saved.r33, _G._read_offset)
    _G._read_offset = _G._read_offset + 2
    return v
end

function _G.read_i16()
    local v = buffer.readi16(_G._saved.r33, _G._read_offset)
    _G._read_offset = _G._read_offset + 2
    return v
end

function _G.read_u32()
    local v = buffer.readu32(_G._saved.r33, _G._read_offset)
    _G._read_offset = _G._read_offset + 4
    return v
end

function _G.read_i32()
    local v = buffer.readi32(_G._saved.r33, _G._read_offset)
    _G._read_offset = _G._read_offset + 4
    return v
end

function _G.read_f64()
    local v = buffer.readf64(_G._saved.r33, _G._read_offset)
    _G._read_offset = _G._read_offset + 8
    return v
end

function _G.read_string(len)
    local v = buffer.readstring(_G._saved.r33, _G._read_offset, len)
    _G._read_offset = _G._read_offset + len
    return v
end

function _G.read_bytes_hex(len)
    local t = {}
    local buf = _G._saved.r33
    for i = 0, len-1 do
        t[i+1] = string.format("%02x", buffer.readu8(buf, _G._read_offset + i))
    end
    _G._read_offset = _G._read_offset + len
    return table.concat(t)
end

function _G.read_sub_buffer_hex()
    local len = _G.read_varint()
    local hex = _G.read_bytes_hex(len)
    return hex
end
""")

# Reset op limit so our custom reader calls don't hit it
runtime.lua.execute("_G._op_count = 0; _G._op_limit = 10000000000")

# Test our custom readers
print(f"\n=== Testing custom readers ===")
runtime.lua.execute("_G.set_offset(94736)")
v = li("_G.read_varint()")
off = li("_G.get_offset()")
print(f"Varint at 94736: {v}, offset now: {off}")

runtime.lua.execute("_G.set_offset(94852)")
v = li("_G.read_varint()")
off = li("_G.get_offset()")
print(f"Varint at 94852: {v} (expected 1054), offset now: {off}")

# Parse the script data section
SCRIPT_START = 94736
print(f"\n{'='*60}")
print(f"PARSING SCRIPT DATA FROM OFFSET {SCRIPT_START}")
print(f"{'='*60}")

runtime.lua.execute(f"_G.set_offset({SCRIPT_START})")

# Step 1: Sub-buffer (read as hex)
sub_hex = str(runtime.lua.eval("_G.read_sub_buffer_hex()"))
sub_data = bytes.fromhex(sub_hex)
sub_len = len(sub_data)
off = li("_G.get_offset()")
print(f"\n[1] Sub-buffer: {sub_len} bytes")
print(f"    hex: {sub_hex}")
print(f"    Offset after: {off}")

# Parse sub-buffer as doubles
for i in range(sub_len // 8):
    v = struct.unpack_from('<d', sub_data, i*8)[0]
    print(f"    double[{i}] = {v}")

# Step 2: Read varints sequentially  
print(f"\n[2] Sequential varints:")
varints = []
for i in range(2000):
    try:
        off_before = li("_G.get_offset()")
        v = li("_G.read_varint()")
        off_after = li("_G.get_offset()")
        if v is None or off_after is None:
            break
        consumed = off_after - off_before
        varints.append((off_before, v, consumed))
    except:
        break

print(f"Read {len(varints)} varints")
for i, (off, v, c) in enumerate(varints[:200]):
    print(f"  [{i:4d}] off={off:7d} val={v:8d} ({c}B)")

# Step 3: Try using the SAVED r[50] reader (tag-dispatch)
# r[50] needs r[10] to be set in the original r table
# But we saved a snapshot of r, so let's try calling it
print(f"\n[3] Testing saved r[50] (tag-dispatch reader):")
# Set r[10] in a temporary table and try calling the saved r[50]
# But r[50] uses upvalues from the original closure, which reference the ORIGINAL r table
# So we need to set offset in the ORIGINAL r table... which is corrupted
# Instead, let's try to understand the tag dispatch by reading the deserialization source

# Step 4: Analyze the byte patterns to understand the format
print(f"\n[4] Byte pattern analysis:")
vals = [v for _, v, _ in varints]

# Look for a count followed by structured data
# The first value after sub-buffer might be a count
print(f"First varint: {vals[0] if vals else 'N/A'}")

# Check if the first varint is a count
# Look for repeating patterns in the data
if len(vals) > 10:
    first_v = vals[0]
    print(f"\nIf {first_v} is a count of items:")
    # Check what follows: are there structural patterns?
    # Group varints by their size (1-byte vs multi-byte)
    small = sum(1 for v in vals[1:first_v+1] if v < 128)
    large = sum(1 for v in vals[1:first_v+1] if v >= 128)
    print(f"  Next {min(first_v, len(vals)-1)} values: {small} small (<128), {large} large (>=128)")

# Save results
with open('halt_parse_results.json', 'w') as f:
    json.dump({
        'protos': n_protos,
        'saved_r10': r10,
        'sub_buffer_len': sub_len,
        'varint_count': len(varints),
        'first_200_varints': [(o, v, c) for o, v, c in varints[:200]],
    }, f, indent=2)
print(f"\nSaved to halt_parse_results.json")
