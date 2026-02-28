import struct, json
from collections import defaultdict, Counter

with open('buffer_trace.txt', 'r') as f:
    trace_lines = f.readlines()

with open(r'unobfuscator\cracked script\buffer_1_1064652.bin', 'rb') as f:
    data = f.read()

# Parse trace into structured reads
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

# Build a map: byte_offset -> (read_type, read_value)
# For u8 reads, the byte at that offset is the value
# For u32 reads, 4 bytes starting at that offset form the value
# For str reads, 'length' bytes starting at that offset are the string

read_map = {}
for r in reads:
    off = r['offset']
    if r['type'] == 'u8':
        read_map[off] = ('u8', int(r['value']))
    elif r['type'] == 'u32':
        read_map[off] = ('u32', int(r['value']))
    elif r['type'] == 'str':
        read_map[off] = ('str', r['length'])
    elif r['type'] == 'f32':
        read_map[off] = ('f32', float(r['value']))
    elif r['type'] == 'f64':
        read_map[off] = ('f64', float(r['value']))

# Now trace sequential reads and identify tag-value groupings
# A tag is a u8 read whose value determines the next read type
# Let me group consecutive reads into "operations"

print("=== Grouping reads into operations ===")

i = 0
operations = []
while i < len(reads):
    r = reads[i]
    
    if r['type'] == 'u8':
        tag = int(r['value'])
        tag_off = r['offset']
        
        # Check what the next read is
        if i + 1 < len(reads):
            r2 = reads[i + 1]
            
            if tag == 0x73 and r2['type'] == 'u8' and r2['offset'] == tag_off + 1:
                val = int(r2['value'])
                operations.append(('TAG_U8', tag_off, val))
                i += 2
                continue
            
            elif tag == 0x9E and r2['type'] == 'u8' and r2['offset'] == tag_off + 1:
                str_len = int(r2['value'])
                # Check if next is a multi-byte varint or direct string
                if i + 2 < len(reads):
                    r3 = reads[i + 2]
                    if r3['type'] == 'str' and r3['offset'] == tag_off + 2:
                        actual_len = r3['length']
                        operations.append(('TAG_STR', tag_off, actual_len, r3.get('hex', '')))
                        i += 3
                        continue
                    elif str_len >= 128 and r3['type'] == 'u8':
                        # Multi-byte varint for length
                        varint_val = (str_len & 0x7F)
                        shift = 7
                        j = i + 2
                        while j < len(reads) and reads[j]['type'] == 'u8':
                            b = int(reads[j]['value'])
                            varint_val |= (b & 0x7F) << shift
                            j += 1
                            if b < 128:
                                break
                            shift += 7
                        # Next should be str read
                        if j < len(reads) and reads[j]['type'] == 'str':
                            operations.append(('TAG_STR', tag_off, reads[j]['length'], reads[j].get('hex', '')))
                            i = j + 1
                            continue
                        else:
                            operations.append(('TAG_STR_EMPTY', tag_off, varint_val))
                            i = j
                            continue
                # str_len == 0 means empty string
                if str_len == 0:
                    # Check if next is a str read with len 0
                    if i + 2 < len(reads) and reads[i+2]['type'] == 'str' and reads[i+2]['length'] == 0:
                        operations.append(('TAG_STR', tag_off, 0, ''))
                        i += 3
                        continue
                    else:
                        operations.append(('TAG_STR', tag_off, 0, ''))
                        i += 2
                        continue
            
            elif tag == 0xA1 and r2['type'] == 'u32' and r2['offset'] == tag_off + 1:
                val1 = int(r2['value'])
                if i + 2 < len(reads) and reads[i+2]['type'] == 'u32':
                    val2 = int(reads[i+2]['value'])
                    operations.append(('TAG_U32_PAIR', tag_off, val1, val2))
                    i += 3
                    continue
                else:
                    operations.append(('TAG_U32', tag_off, val1))
                    i += 2
                    continue
            
            elif tag == 0x8C and r2['type'] == 'f32' and r2['offset'] == tag_off + 1:
                val = float(r2['value'])
                operations.append(('TAG_F32', tag_off, val))
                i += 2
                continue
            
            elif tag == 0xCA and r2['type'] == 'u32' and r2['offset'] == tag_off + 1:
                val = int(r2['value'])
                operations.append(('TAG_CA_U32', tag_off, val))
                i += 2
                continue
        
        # Not a recognized tag pattern
        operations.append(('RAW_U8', tag_off, tag))
        i += 1
    
    elif r['type'] == 'u32':
        operations.append(('RAW_U32', r['offset'], int(r['value'])))
        i += 1
    elif r['type'] == 'str':
        operations.append(('RAW_STR', r['offset'], r['length'], r.get('hex', '')))
        i += 1
    elif r['type'] == 'f32':
        operations.append(('RAW_F32', r['offset'], float(r['value'])))
        i += 1
    elif r['type'] == 'f64':
        operations.append(('RAW_F64', r['offset'], float(r['value'])))
        i += 1
    else:
        i += 1

print(f"Total operations: {len(operations)}")
op_counts = Counter(op[0] for op in operations)
print(f"Operation types: {dict(op_counts)}")

# Show any RAW (unrecognized) operations
raw_ops = [op for op in operations if op[0].startswith('RAW')]
print(f"\nUnrecognized operations: {len(raw_ops)}")
if raw_ops:
    # Show first 50 raw ops with context
    for op in raw_ops[:50]:
        if op[0] == 'RAW_U8':
            print(f"  RAW_U8 off={op[1]:6d} val={op[2]:3d} (0x{op[2]:02X})")
        elif op[0] == 'RAW_U32':
            print(f"  RAW_U32 off={op[1]:6d} val={op[2]}")
        elif op[0] == 'RAW_STR':
            print(f"  RAW_STR off={op[1]:6d} len={op[2]}")
        elif op[0] == 'RAW_F32':
            print(f"  RAW_F32 off={op[1]:6d} val={op[2]}")

    # Check if RAW_U8 values form patterns (potential new tags)
    raw_u8_vals = Counter(op[2] for op in raw_ops if op[0] == 'RAW_U8')
    if raw_u8_vals:
        print(f"\n  RAW_U8 value frequency:")
        for val, cnt in raw_u8_vals.most_common(30):
            print(f"    0x{val:02X} ({val:3d}): {cnt} times")

# Show operation sequence for a section
print(f"\n=== Operations [0:80] ===")
for i, op in enumerate(operations[:80]):
    if op[0] == 'TAG_U8':
        print(f"  [{i:4d}] TAG_U8  off={op[1]:6d} val={op[2]:3d}")
    elif op[0] == 'TAG_STR':
        hex_data = op[3] if len(op) > 3 else ''
        try:
            s = bytes.fromhex(hex_data).decode('ascii')
        except:
            s = hex_data[:20]
        print(f"  [{i:4d}] TAG_STR off={op[1]:6d} len={op[2]:3d} {repr(s)[:40]}")
    elif op[0] == 'TAG_U32_PAIR':
        print(f"  [{i:4d}] TAG_U32P off={op[1]:6d} lo={op[2]} hi=0x{op[3]:08X}")
    elif op[0] == 'TAG_F32':
        print(f"  [{i:4d}] TAG_F32 off={op[1]:6d} val={op[2]}")
    elif op[0] == 'TAG_CA_U32':
        print(f"  [{i:4d}] TAG_CA  off={op[1]:6d} val={op[2]} (0x{op[2]:08X})")
    elif op[0].startswith('RAW'):
        detail = str(op[2])[:30] if len(op) > 2 else ''
        print(f"  [{i:4d}] {op[0]:8s} off={op[1]:6d} {detail}")

# Show string constants found
print(f"\n=== All TAG_STR operations ===")
str_ops = [op for op in operations if op[0] == 'TAG_STR']
print(f"Total: {len(str_ops)}")
for op in str_ops:
    hex_data = op[3] if len(op) > 3 else ''
    try:
        raw = bytes.fromhex(hex_data)
        s = raw.decode('ascii', errors='replace')
        printable = all(32 <= c < 127 for c in raw) if raw else True
    except:
        s = hex_data[:20]
        printable = False
    print(f"  off={op[1]:6d} len={op[2]:3d} printable={printable:5} {repr(s)[:60]}")

# Show TAG_U32_PAIR values
print(f"\n=== TAG_U32_PAIR analysis ===")
u32_pair_ops = [op for op in operations if op[0] == 'TAG_U32_PAIR']
print(f"Total: {len(u32_pair_ops)}")
hi_vals = Counter(op[3] for op in u32_pair_ops)
print(f"Hi value distribution: {dict(hi_vals)}")
for op in u32_pair_ops[:20]:
    lo, hi = op[2], op[3]
    as_f64 = struct.unpack('<d', struct.pack('<II', lo, hi))[0]
    print(f"  off={op[1]:6d} lo={lo:12d} hi=0x{hi:08X} as_f64={as_f64}")

# Show operations around offset 94700 (near script data boundary)
print(f"\n=== Operations near script data boundary ===")
boundary_ops = [(i, op) for i, op in enumerate(operations) if op[1] >= 94500]
for i, op in boundary_ops[:20]:
    print(f"  [{i:4d}] {op[0]:12s} off={op[1]:6d} {str(op[2:])[:40]}")

# Summary
print(f"\n=== SUMMARY ===")
print(f"Total bytes covered by operations: {max(op[1] for op in operations) if operations else 0}")
print(f"Operations: {dict(op_counts)}")
coverage = sum(1 for op in operations if not op[0].startswith('RAW'))
print(f"Recognized: {coverage} / {len(operations)} ({100*coverage/len(operations):.1f}%)")
