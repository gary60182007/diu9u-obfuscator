import sys, time, json, re, struct
sys.path.insert(0, '.')

with open(r'unobfuscator\pending crack\bloxburg_script.lua', 'r', encoding='utf-8', errors='replace') as f:
    source = f.read()

exec(open('run_luraph_test.py').read().split("print('Reading source...')")[0])
source = preprocess_luau(source)

from unobfuscator.utils.lua_runtime import LuaRuntimeWrapper, LuaRuntimeError

runtime = LuaRuntimeWrapper(op_limit=2_000_000_000, timeout=120.0)
runtime._init_runtime()

# Hook buffer.copy to capture sub-buffers and track buffer identity
runtime.lua.execute("""
_G._buffers = {}
_G._buf_id = 0
_G._copy_log = {}

local _orig_create = buffer.create
local _orig_copy = buffer.copy
local _orig_readu8 = buffer.readu8
local _orig_readstring = buffer.readstring

buffer.create = function(size)
    local buf = _orig_create(size)
    _G._buf_id = _G._buf_id + 1
    _G._buffers[tostring(buf)] = {id=_G._buf_id, size=size}
    return buf
end

buffer.copy = function(dst, dO, src, sO, c)
    _orig_copy(dst, dO, src, sO, c)
    local src_info = _G._buffers[tostring(src)]
    local dst_info = _G._buffers[tostring(dst)]
    local src_id = src_info and src_info.id or "?"
    local dst_id = dst_info and dst_info.id or "?"
    table.insert(_G._copy_log, {
        src_id=src_id, dst_id=dst_id,
        src_off=sO, dst_off=dO, count=c
    })
end

_G._protos = {}
""")

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
modified = runtime.suppress_vm_errors(modified)

print("Executing with buffer tracking...")
t0 = time.time()
try:
    runtime.execute(modified)
    print(f"Completed in {time.time()-t0:.1f}s")
except LuaRuntimeError as e:
    print(f"Error after {time.time()-t0:.1f}s: {str(e)[:200]}")

# Analyze copy log
copy_count = int(runtime.lua.eval("#_G._copy_log"))
print(f"\nbuffer.copy calls: {copy_count}")

for i in range(1, min(copy_count + 1, 20)):
    try:
        src_id = runtime.lua.eval(f"_G._copy_log[{i}].src_id")
        dst_id = runtime.lua.eval(f"_G._copy_log[{i}].dst_id")
        src_off = int(runtime.lua.eval(f"_G._copy_log[{i}].src_off"))
        dst_off = int(runtime.lua.eval(f"_G._copy_log[{i}].dst_off"))
        count = int(runtime.lua.eval(f"_G._copy_log[{i}].count"))
        print(f"  Copy #{i}: buf#{src_id}[{src_off}:{src_off+count}] -> buf#{dst_id}[{dst_off}:{dst_off+count}] ({count} bytes)")
    except Exception as e:
        print(f"  Copy #{i}: error: {e}")

# Analyze buffer objects
buf_count = int(runtime.lua.eval("_G._buf_id"))
print(f"\nTotal buffer.create calls: {buf_count}")

# Get sizes of all created buffers
get_buf_info = runtime.lua.eval("""
function()
    local result = {}
    local count = 0
    for k, v in pairs(_G._buffers) do
        count = count + 1
        result[count] = {id=v.id, size=v.size}
    end
    result.count = count
    return result
end
""")

buf_info = get_buf_info()
info_count = int(buf_info['count'])
print(f"Tracked buffers: {info_count}")
for i in range(1, info_count + 1):
    try:
        bid = int(buf_info[i]['id'])
        size = int(buf_info[i]['size'])
        print(f"  Buffer #{bid}: size={size}")
    except:
        pass

# Now let's access the state table to find the sub-buffer
# r[33] is the main buffer, check if there are other buffer references
print("\n=== Checking r[] state table for buffer objects ===")
check_fn = runtime.lua.eval("""
function()
    local result = {}
    if type(_G._state_r) == "table" then
        for k, v in pairs(_G._state_r) do
            if type(v) == "userdata" then
                local info = _G._buffers[tostring(v)]
                if info then
                    result[k] = {id=info.id, size=info.size}
                end
            end
        end
    end
    return result
end
""")

# The state table r might not be globally accessible
# Let me try to capture it via the hook
print("(State table may not be directly accessible)")

# Instead, let me read the raw sub-buffer data from the binary file 
# and parse it using the tag format we identified
print("\n=== Parsing sub-buffer from raw file ===")
buf_path = r'unobfuscator\cracked script\buffer_1_1064652.bin'
with open(buf_path, 'rb') as f:
    data = f.read()

# The sub-buffer is the data after the VM init section
# From the copy log, find the largest copy (that's the sub-buffer)
# For now, use the known offset
VM_END = 94736
sub_buf = data[VM_END:]

# Parse tag-based format with sub-buffer tags:
# 0x36 = u8 (confirmed from pattern analysis)
# 0x9E = string (same as main buffer)
# 0xD8 = i16 (same as main buffer)
# Need to identify: u16, i32, u32, f32, f64 tags

# First, skip the 8 float constants (64 bytes)
# But we're not sure where they end, so let's try parsing from offset 0
# and see what happens

# Try parsing from sub-buffer offset 0 with ONLY the confirmed tags
pos = 0
values = []
unknown_tags = {}
max_parse = min(50000, len(sub_buf))

while pos < max_parse:
    tag = sub_buf[pos]
    
    if tag == 0x36:  # u8
        if pos + 1 < len(sub_buf):
            values.append(('u8', sub_buf[pos+1], pos))
            pos += 2
        else:
            break
    elif tag == 0x9E:  # string
        if pos + 1 < len(sub_buf):
            length = sub_buf[pos+1]
            if pos + 2 + length <= len(sub_buf):
                raw = sub_buf[pos+2:pos+2+length]
                values.append(('str', raw, pos))
                pos += 2 + length
            else:
                unknown_tags[tag] = unknown_tags.get(tag, 0) + 1
                pos += 1
        else:
            break
    elif tag == 0xD8:  # i16
        if pos + 2 < len(sub_buf):
            v = struct.unpack_from('<h', sub_buf, pos+1)[0]
            values.append(('i16', v, pos))
            pos += 3
        else:
            break
    else:
        unknown_tags[tag] = unknown_tags.get(tag, 0) + 1
        pos += 1

print(f"Parsed {len(values)} tagged values in first {max_parse} bytes")
print(f"Unknown tags: {len(unknown_tags)} unique, {sum(unknown_tags.values())} total")
print(f"Top unknown tags: {sorted(unknown_tags.items(), key=lambda x: -x[1])[:15]}")

# Count types
from collections import Counter
type_counts = Counter(v[0] for v in values)
print(f"Type counts: {dict(type_counts)}")

# Show strings found
str_entries = [(raw, pos) for typ, raw, pos in values if typ == 'str']
print(f"\nString entries: {len(str_entries)}")

# Check which are printable
printable = []
for raw, pos in str_entries[:100]:
    try:
        s = raw.decode('ascii')
        if all(32 <= ord(c) < 127 or c in '\t\n\r' for c in s):
            printable.append((s, pos))
    except:
        pass

print(f"Printable strings in first 50K: {len(printable)}")
for s, pos in printable[:20]:
    print(f"  pos={VM_END+pos:7d}: {repr(s)}")

# The unknown bytes are the key data (floats, opcodes, etc.)
# Let's see if f64 values appear among the unknown bytes
print(f"\nSample unknown byte positions (first 50):")
unkn_positions = []
pos = 0
while pos < min(500, len(sub_buf)):
    tag = sub_buf[pos]
    if tag == 0x36:
        pos += 2
    elif tag == 0x9E:
        if pos + 1 < len(sub_buf):
            length = sub_buf[pos+1]
            pos += 2 + length
        else:
            pos += 1
    elif tag == 0xD8:
        pos += 3
    else:
        unkn_positions.append((pos, tag))
        pos += 1

for pos, tag in unkn_positions[:50]:
    # Try reading as f64
    if pos + 8 <= len(sub_buf):
        f64 = struct.unpack_from('<d', sub_buf, pos)[0]
        f64_str = f"f64={f64:.6g}" if abs(f64) < 1e10 and f64 == f64 else ""
    else:
        f64_str = ""
    print(f"  sub_pos={pos:5d} tag=0x{tag:02X} ({tag:3d}) {f64_str}")

with open('subbuffer_parse.json', 'w', encoding='utf-8') as f:
    json.dump({
        'copy_count': copy_count,
        'buffer_count': buf_count,
        'parsed_values': len(values),
        'type_counts': dict(type_counts),
        'unknown_tag_counts': {f"0x{k:02X}": v for k, v in sorted(unknown_tags.items(), key=lambda x: -x[1])[:20]},
        'string_count': len(str_entries),
        'printable_count': len(printable),
    }, f, indent=2)
print(f"\nSaved to subbuffer_parse.json")
