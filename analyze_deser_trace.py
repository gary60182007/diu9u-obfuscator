import struct, json

# Parse the buffer trace to understand the exact deserialization sequence
# Then apply that sequence to parse the script data section

with open('buffer_trace.txt', 'r') as f:
    trace_lines = f.readlines()

buf_path = r'unobfuscator\cracked script\buffer_1_1064652.bin'
with open(buf_path, 'rb') as f:
    data = f.read()

# Parse trace into structured reads
reads = []
for line in trace_lines:
    line = line.strip()
    if not line:
        continue
    parts = line.split(',', 3)
    typ = parts[0]
    offset = int(parts[1])
    if typ == 'str':
        length = int(parts[2])
        hex_data = parts[3] if len(parts) > 3 else ''
        reads.append({'type': typ, 'offset': offset, 'length': length, 'hex': hex_data})
    elif typ in ('u8', 'u16', 'i16', 'u32', 'i32', 'f32', 'f64'):
        val = parts[2]
        reads.append({'type': typ, 'offset': offset, 'value': val})

print(f"Total reads: {len(reads)}")

# Group sequential u8 reads into higher-level operations
# Key insight: the VM reads tags as single u8, then reads data based on tag
# Let me track what happens after each tag byte

# First, identify the tag-based reading pattern
# From the VM init: offset 4 has value 0x73 (115) = u8 tag
# The VM reads tag, then reads data based on tag type

# Let me identify tag values by finding u8 reads followed by specific patterns
# Tag 0x73 (115): followed by 1 u8 read (the value)
# Tag 0x9E (158): followed by varint length + string read
# Tag 0x1D (29): followed by 2 u8 reads (u16 value)
# Tag 0xD8 (216): followed by 2 u8 reads (i16 value)
# Tag 0x57 (87): followed by 4 u8 reads (i32 value)

# Let me verify by checking the first few tag reads
print(f"\n=== Analyzing tag-based reads ===")

# Reconstruct high-level operations from u8 reads
ops = []
i = 0
# Skip header (first 4 reads = u32 header)
# Header at offsets 0-3
i = 4

tag_counts = {}
while i < len(reads):
    r = reads[i]
    if r['type'] != 'u8':
        # Non-u8 read (str, u32, f32, f64) - these are direct reads
        ops.append({'type': r['type'], 'offset': r['offset'], 'raw': r})
        i += 1
        continue
    
    tag = int(r['value'])
    tag_offset = r['offset']
    
    if tag == 0x73:  # u8 value
        if i + 1 < len(reads) and reads[i+1]['type'] == 'u8':
            val = int(reads[i+1]['value'])
            ops.append({'type': 'tag_u8', 'offset': tag_offset, 'tag': tag, 'value': val})
            tag_counts[0x73] = tag_counts.get(0x73, 0) + 1
            i += 2
        else:
            ops.append({'type': 'raw_u8', 'offset': tag_offset, 'value': tag})
            i += 1
    elif tag == 0x9E:  # string
        # Next reads are varint length, then string data
        i += 1
        # Read varint for length
        length = 0
        shift = 0
        while i < len(reads) and reads[i]['type'] == 'u8':
            b = int(reads[i]['value'])
            length |= (b & 0x7F) << shift
            i += 1
            if b < 128:
                break
            shift += 7
        
        # Next should be the string read or u8 reads for string data
        str_data = b''
        if i < len(reads) and reads[i]['type'] == 'str':
            str_data = bytes.fromhex(reads[i]['hex'])
            i += 1
        else:
            # String might be read as individual u8s
            for j in range(length):
                if i < len(reads) and reads[i]['type'] == 'u8':
                    str_data += bytes([int(reads[i]['value'])])
                    i += 1
        
        ops.append({'type': 'tag_str', 'offset': tag_offset, 'tag': tag, 'length': length, 'data': str_data})
        tag_counts[0x9E] = tag_counts.get(0x9E, 0) + 1
    elif tag == 0x1D:  # u16
        if i + 2 < len(reads):
            b0 = int(reads[i+1]['value'])
            b1 = int(reads[i+2]['value'])
            val = b0 | (b1 << 8)
            ops.append({'type': 'tag_u16', 'offset': tag_offset, 'tag': tag, 'value': val})
            tag_counts[0x1D] = tag_counts.get(0x1D, 0) + 1
            i += 3
        else:
            ops.append({'type': 'raw_u8', 'offset': tag_offset, 'value': tag})
            i += 1
    elif tag == 0xD8:  # i16
        if i + 2 < len(reads):
            b0 = int(reads[i+1]['value'])
            b1 = int(reads[i+2]['value'])
            val = struct.unpack('<h', bytes([b0, b1]))[0]
            ops.append({'type': 'tag_i16', 'offset': tag_offset, 'tag': tag, 'value': val})
            tag_counts[0xD8] = tag_counts.get(0xD8, 0) + 1
            i += 3
        else:
            ops.append({'type': 'raw_u8', 'offset': tag_offset, 'value': tag})
            i += 1
    elif tag == 0x57:  # i32
        if i + 4 < len(reads):
            bs = bytes([int(reads[i+j+1]['value']) for j in range(4)])
            val = struct.unpack('<i', bs)[0]
            ops.append({'type': 'tag_i32', 'offset': tag_offset, 'tag': tag, 'value': val})
            tag_counts[0x57] = tag_counts.get(0x57, 0) + 1
            i += 5
        else:
            ops.append({'type': 'raw_u8', 'offset': tag_offset, 'value': tag})
            i += 1
    else:
        # Unknown tag - just record as raw u8
        ops.append({'type': 'raw_u8', 'offset': tag_offset, 'value': tag})
        i += 1

print(f"Reconstructed {len(ops)} high-level operations from {len(reads)} raw reads")
print(f"Tag counts: {tag_counts}")

# Count operation types
from collections import Counter
op_types = Counter(op['type'] for op in ops)
print(f"Operation types: {dict(op_types)}")

# Check if there are raw_u8 reads (unrecognized tags)
raw_u8_vals = Counter(op['value'] for op in ops if op['type'] == 'raw_u8')
print(f"\nRaw u8 values (not recognized as tags): {len(raw_u8_vals)} unique")
if raw_u8_vals:
    print(f"Top 20: {raw_u8_vals.most_common(20)}")

# Show first 50 high-level operations
print(f"\n=== First 80 high-level operations ===")
for i, op in enumerate(ops[:80]):
    if op['type'] == 'tag_str':
        try:
            s = op['data'].decode('ascii', errors='replace')
            printable = all(32 <= c < 127 for c in op['data'])
        except:
            s = op['data'].hex()
            printable = False
        print(f"  [{i:4d}] offset={op['offset']:6d} {op['type']:10s} len={op['length']:4d} printable={printable} {repr(s)[:60]}")
    elif 'value' in op:
        print(f"  [{i:4d}] offset={op['offset']:6d} {op['type']:10s} value={op['value']}")
    else:
        print(f"  [{i:4d}] offset={op['offset']:6d} {op['type']:10s}")

# Now find the PATTERN in operations
# Look for repeating sequences that indicate prototype definitions
print(f"\n=== Looking for prototype boundary patterns ===")
# Search for sequences that look like:
# tag_u8 (instruction count), followed by many tag_u8/tag_u16/tag_i16 (instructions)
# then tag_str (string constants)

# Find all tag_str positions
str_positions = [(i, op) for i, op in enumerate(ops) if op['type'] == 'tag_str']
print(f"Total string reads: {len(str_positions)}")
print(f"First 20 strings:")
for idx, op in str_positions[:20]:
    s = op['data']
    try:
        decoded = s.decode('ascii')
        print(f"  op[{idx:4d}] offset={op['offset']:6d} len={op['length']:3d}: {repr(decoded)[:60]}")
    except:
        print(f"  op[{idx:4d}] offset={op['offset']:6d} len={op['length']:3d}: {s.hex()[:60]}")

# Find where the first string appears in the operation sequence
# Everything before it is setup/header data
if str_positions:
    first_str_idx = str_positions[0][0]
    print(f"\nFirst string at operation index {first_str_idx}")
    print(f"Operations before first string:")
    for i, op in enumerate(ops[:first_str_idx]):
        if op['type'] == 'tag_u8':
            print(f"  [{i:4d}] tag_u8 value={op['value']}")
        elif 'value' in op:
            print(f"  [{i:4d}] {op['type']} value={op['value']}")

# Find large gaps in operation types to identify section boundaries
print(f"\n=== Section boundaries (gaps > 20 ops without strings) ===")
prev_str_idx = -1
for idx, op in str_positions:
    if prev_str_idx >= 0 and idx - prev_str_idx > 20:
        print(f"  Gap: ops {prev_str_idx} to {idx} ({idx - prev_str_idx} ops between strings)")
    prev_str_idx = idx

# Show the last 30 operations to see the end of deserialization
print(f"\n=== Last 30 operations ===")
for i, op in enumerate(ops[-30:]):
    idx = len(ops) - 30 + i
    if op['type'] == 'tag_str':
        s = op['data']
        try:
            decoded = s.decode('ascii')
            print(f"  [{idx:4d}] offset={op['offset']:6d} {op['type']:10s} {repr(decoded)[:40]}")
        except:
            print(f"  [{idx:4d}] offset={op['offset']:6d} {op['type']:10s} hex={s.hex()[:40]}")
    elif 'value' in op:
        print(f"  [{idx:4d}] offset={op['offset']:6d} {op['type']:10s} value={op['value']}")
    else:
        print(f"  [{idx:4d}] offset={op['offset']:6d} {op['type']:10s}")
