import sys, time, json, re, struct
sys.path.insert(0, '.')

with open(r'unobfuscator\pending crack\bloxburg_script.lua', 'r', encoding='utf-8', errors='replace') as f:
    source = f.read()

exec(open('run_luraph_test.py').read().split("print('Reading source...')")[0])
source = preprocess_luau(source)

from unobfuscator.utils.lua_runtime import LuaRuntimeWrapper, LuaRuntimeError

runtime = LuaRuntimeWrapper(op_limit=2_000_000_000, timeout=120.0)
runtime._init_runtime()

# Write trace to file directly from Lua hooks using io.write
runtime.lua.execute("""
local trace_file = io.open("buffer_trace.txt", "w")
_G._read_count = 0

local _orig = {
    readu8 = buffer.readu8,
    readu16 = buffer.readu16,
    readu32 = buffer.readu32,
    readi8 = buffer.readi8,
    readi16 = buffer.readi16,
    readi32 = buffer.readi32,
    readf32 = buffer.readf32,
    readf64 = buffer.readf64,
    readstring = buffer.readstring,
}

local function log(line)
    _G._read_count = _G._read_count + 1
    trace_file:write(line)
    trace_file:write("\\n")
end

buffer.readu8 = function(buf, offset)
    local v = _orig.readu8(buf, offset)
    log("u8," .. offset .. "," .. v)
    return v
end
buffer.readu16 = function(buf, offset)
    local v = _orig.readu16(buf, offset)
    log("u16," .. offset .. "," .. v)
    return v
end
buffer.readu32 = function(buf, offset)
    local v = _orig.readu32(buf, offset)
    log("u32," .. offset .. "," .. v)
    return v
end
buffer.readi8 = function(buf, offset)
    local v = _orig.readi8(buf, offset)
    log("i8," .. offset .. "," .. v)
    return v
end
buffer.readi16 = function(buf, offset)
    local v = _orig.readi16(buf, offset)
    log("i16," .. offset .. "," .. v)
    return v
end
buffer.readi32 = function(buf, offset)
    local v = _orig.readi32(buf, offset)
    log("i32," .. offset .. "," .. v)
    return v
end
buffer.readf32 = function(buf, offset)
    local v = _orig.readf32(buf, offset)
    log("f32," .. offset .. "," .. v)
    return v
end
buffer.readf64 = function(buf, offset)
    local v = _orig.readf64(buf, offset)
    log("f64," .. offset .. "," .. v)
    return v
end
buffer.readstring = function(buf, offset, length)
    local v = _orig.readstring(buf, offset, length)
    local hex_bytes = {}
    for i = 1, #v do
        hex_bytes[#hex_bytes+1] = string.format("%02x", string.byte(v, i))
    end
    log("str," .. offset .. "," .. length .. "," .. table.concat(hex_bytes, ""))
    return v
end

_G._trace_file = trace_file
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

print("Executing with file-based buffer trace...")
t0 = time.time()
try:
    runtime.execute(modified)
    print(f"Completed in {time.time()-t0:.1f}s")
except LuaRuntimeError as e:
    print(f"Error after {time.time()-t0:.1f}s: {str(e)[:200]}")

# Close the trace file
runtime.lua.execute("_G._trace_file:close()")
read_count = int(runtime.lua.eval("_G._read_count"))
print(f"Total reads: {read_count}")

# Now parse the trace file in Python
print("\nParsing trace file...")
from collections import Counter

type_counts = Counter()
offsets = []
strings_raw = []
all_reads = []
max_offset = 0

with open('buffer_trace.txt', 'r') as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        parts = line.split(',', 3)
        typ = parts[0]
        offset = int(parts[1])
        type_counts[typ] += 1
        if offset > max_offset:
            max_offset = offset

        if typ == 'str':
            length = int(parts[2])
            hex_data = parts[3] if len(parts) > 3 else ''
            raw = bytes.fromhex(hex_data)
            all_reads.append((typ, offset, length, raw))
            if length >= 2:
                strings_raw.append((raw, offset, length))
        else:
            val = float(parts[2]) if '.' in parts[2] else int(parts[2])
            all_reads.append((typ, offset, val, None))

print(f"Total reads parsed: {len(all_reads)}")
print(f"Max offset: {max_offset}")
print(f"Type counts: {dict(type_counts)}")

# Analyze strings
printable = []
encoded = []
for raw, offset, length in strings_raw:
    try:
        s = raw.decode('ascii')
        if all(32 <= ord(c) < 127 or c in '\t\n\r' for c in s):
            printable.append((s, offset, length))
        else:
            encoded.append((raw, offset, length))
    except:
        encoded.append((raw, offset, length))

print(f"\nPrintable strings: {len(printable)}")
print(f"Encoded strings: {len(encoded)}")

print("\nAll printable strings:")
for s, o, l in printable:
    print(f"  off={o:7d} len={l:3d}: {repr(s)[:80]}")

# Try multi-byte XOR on encoded strings
# First, look for patterns in the encoded data
print(f"\nAnalyzing {len(encoded)} encoded strings...")
# Check if there's a per-string XOR key pattern
for raw, offset, length in encoded[:20]:
    print(f"  off={offset:7d} len={length:3d}: {raw.hex()}")
    # Try XOR with position-based keys
    for key in range(256):
        decoded = bytes(b ^ key for b in raw)
        try:
            s = decoded.decode('ascii')
            if all(32 <= ord(c) < 127 for c in s) and len(s) >= 3:
                print(f"    XOR 0x{key:02X} → {repr(s)}")
        except:
            pass

# Show the read sequence to understand deserialization structure
print(f"\nRead sequence (first 300):")
for i, (typ, offset, val, raw) in enumerate(all_reads[:300]):
    if typ == 'str':
        length = val
        try:
            s = raw.decode('ascii')
            is_print = all(32 <= ord(c) < 127 or c in '\t\n\r' for c in s)
            if is_print:
                print(f"  [{i:5d}] off={offset:7d} {typ:4s} len={length:3d}: {repr(s)[:50]}")
            else:
                print(f"  [{i:5d}] off={offset:7d} {typ:4s} len={length:3d}: <hex:{raw.hex()[:40]}>")
        except:
            print(f"  [{i:5d}] off={offset:7d} {typ:4s} len={length:3d}: <hex:{raw.hex()[:40]}>")
    else:
        print(f"  [{i:5d}] off={offset:7d} {typ:4s}: {val}")

# Save structured trace
with open('buffer_trace_parsed.json', 'w', encoding='utf-8') as f:
    json.dump({
        'total_reads': len(all_reads),
        'max_offset': max_offset,
        'type_counts': dict(type_counts),
        'printable_strings': [(s, o, l) for s, o, l in printable],
        'encoded_count': len(encoded),
    }, f, indent=2)
print(f"\nSaved to buffer_trace_parsed.json")
