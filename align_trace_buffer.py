import struct, json
from collections import defaultdict

with open('buffer_trace.txt', 'r') as f:
    trace_lines = f.readlines()

with open(r'unobfuscator\cracked script\buffer_1_1064652.bin', 'rb') as f:
    data = f.read()

# Parse trace
reads = []
for line in trace_lines:
    line = line.strip()
    if not line:
        continue
    parts = line.split(',')
    typ = parts[0]
    offset = int(parts[1])
    if typ == 'str':
        length = int(parts[2])
        hex_data = parts[3] if len(parts) > 3 else ''
        reads.append({'type': typ, 'offset': offset, 'length': length, 'hex': hex_data})
    else:
        val = parts[2].strip()
        reads.append({'type': typ, 'offset': offset, 'value': val})

print(f"Total reads: {len(reads)}")

# Create offset->read_info map
# Some offsets may be read multiple times (re-reads), track all
offset_reads = defaultdict(list)
for i, r in enumerate(reads):
    offset_reads[r['offset']].append((i, r))

# Find the maximum offset read
max_offset = max(r['offset'] for r in reads)
print(f"Offset range: 0 to {max_offset}")

# Build byte annotation map: for each byte offset, what was it read as?
byte_role = {}  # offset -> ('tag', 'val_u8', 'val_u16_lo', 'val_u16_hi', 'str_data', etc.)

# Process reads sequentially to identify tag-value patterns
# In the VM section, tags are read as u8, then values follow

# Let me look at sequential u8 reads and find the tag pattern
print(f"\n=== Sequential read pattern analysis ===")

# Find pairs: u8 read followed by another read at adjacent offset
i = 0
tag_candidates = defaultdict(int)
tag_next_type = defaultdict(lambda: defaultdict(int))

while i < len(reads) - 1:
    r1 = reads[i]
    r2 = reads[i + 1]
    
    if r1['type'] == 'u8' and r2['offset'] == r1['offset'] + 1:
        tag_val = int(r1['value'])
        next_type = r2['type']
        tag_candidates[tag_val] += 1
        tag_next_type[tag_val][next_type] += 1
    i += 1

# Show tags that always precede the same type
print("Potential tags (u8 values that always precede specific types):")
for tag in sorted(tag_candidates.keys()):
    if tag_candidates[tag] >= 5:
        types = dict(tag_next_type[tag])
        print(f"  0x{tag:02X} ({tag:3d}): {tag_candidates[tag]:5d} occurrences, followed by: {types}")

# Now let me trace the EXACT sequence of the first 200 reads
print(f"\n=== First 200 reads ===")
for i in range(min(200, len(reads))):
    r = reads[i]
    if r['type'] == 'str':
        print(f"  [{i:4d}] off={r['offset']:6d} STR len={r['length']:3d} hex={r['hex'][:40]}")
    elif r['type'] == 'u8':
        v = int(r['value'])
        raw = data[r['offset']]
        print(f"  [{i:4d}] off={r['offset']:6d} U8  val={v:3d} (0x{v:02X}) raw=0x{raw:02X}")
    elif r['type'] == 'u32':
        v = int(r['value'])
        print(f"  [{i:4d}] off={r['offset']:6d} U32 val={v}")
    elif r['type'] == 'f64':
        v = float(r['value'])
        print(f"  [{i:4d}] off={r['offset']:6d} F64 val={v}")
    elif r['type'] == 'f32':
        v = float(r['value'])
        print(f"  [{i:4d}] off={r['offset']:6d} F32 val={v}")
    else:
        print(f"  [{i:4d}] off={r['offset']:6d} {r['type']} val={r.get('value', '?')}")

# Find where string reads occur
print(f"\n=== String reads ===")
str_reads = [(i, r) for i, r in enumerate(reads) if r['type'] == 'str']
print(f"Total: {len(str_reads)}")
for i, r in str_reads[:30]:
    hex_data = r['hex']
    try:
        raw = bytes.fromhex(hex_data)
        decoded = raw.decode('ascii')
        printable = all(32 <= c < 127 for c in raw)
    except:
        decoded = hex_data[:40]
        printable = False
    print(f"  [{i:4d}] off={r['offset']:6d} len={r['length']:3d} printable={printable} {repr(decoded[:50])}")

# Find where u32 reads occur  
print(f"\n=== U32 reads ===")
u32_reads = [(i, r) for i, r in enumerate(reads) if r['type'] == 'u32']
print(f"Total: {len(u32_reads)}")
for i, r in u32_reads[:20]:
    v = int(r['value'])
    print(f"  [{i:4d}] off={r['offset']:6d} val={v} (0x{v:08X})")
    # What tag byte precedes this u32?
    tag_offset = r['offset'] - 1
    if tag_offset >= 0:
        tag_byte = data[tag_offset]
        print(f"         preceding byte: 0x{tag_byte:02X} ({tag_byte})")

# Find where f64 reads occur
print(f"\n=== F64 reads ===")
f64_reads = [(i, r) for i, r in enumerate(reads) if r['type'] == 'f64']
print(f"Total: {len(f64_reads)}")
for i, r in f64_reads:
    v = float(r['value'])
    print(f"  [{i:4d}] off={r['offset']:6d} val={v}")
    tag_offset = r['offset'] - 1
    if tag_offset >= 0:
        tag_byte = data[tag_offset]
        print(f"         preceding byte: 0x{tag_byte:02X} ({tag_byte})")

# Find where f32 reads occur
print(f"\n=== F32 reads ===")
f32_reads = [(i, r) for i, r in enumerate(reads) if r['type'] == 'f32']
print(f"Total: {len(f32_reads)}")
for i, r in f32_reads:
    v = float(r['value'])
    print(f"  [{i:4d}] off={r['offset']:6d} val={v}")
    tag_offset = r['offset'] - 1
    if tag_offset >= 0:
        tag_byte = data[tag_offset]
        print(f"         preceding byte: 0x{tag_byte:02X} ({tag_byte})")

# Now find the read sequence AROUND the first string read
# to understand how strings are read
if str_reads:
    first_str_idx = str_reads[0][0]
    print(f"\n=== Context around first string read (read #{first_str_idx}) ===")
    start = max(0, first_str_idx - 10)
    end = min(len(reads), first_str_idx + 5)
    for i in range(start, end):
        r = reads[i]
        marker = " <<<" if i == first_str_idx else ""
        if r['type'] == 'str':
            print(f"  [{i:4d}] off={r['offset']:6d} STR len={r['length']:3d} hex={r['hex'][:40]}{marker}")
        elif r['type'] == 'u8':
            v = int(r['value'])
            print(f"  [{i:4d}] off={r['offset']:6d} U8  val={v:3d} (0x{v:02X}){marker}")
        else:
            print(f"  [{i:4d}] off={r['offset']:6d} {r['type']} val={r.get('value','?')}{marker}")
