import struct, json

buf_path = r'unobfuscator\cracked script\buffer_1_1064652.bin'
with open(buf_path, 'rb') as f:
    buf = f.read()

def u32(o): return struct.unpack_from('<I', buf, o)[0]
def i32(o): return struct.unpack_from('<i', buf, o)[0]
def u16(o): return struct.unpack_from('<H', buf, o)[0]
def i16(o): return struct.unpack_from('<h', buf, o)[0]
def u8(o): return buf[o]
def f64(o): return struct.unpack_from('<d', buf, o)[0]
def f32(o): return struct.unpack_from('<f', buf, o)[0]

print(f"Buffer: {len(buf):,} bytes")
print(f"Header u32: {u32(0)} (0x{u32(0):08x})")

# Phase 1: Extract the permutation table (offset 4 to where pattern breaks)
print("\n=== PERMUTATION TABLE (offset 4+) ===")
perm_table = []
pos = 4
while pos + 1 < len(buf):
    if buf[pos] == 0x73:
        perm_table.append(buf[pos+1])
        pos += 2
    else:
        break
print(f"Permutation table length: {len(perm_table)}")
print(f"Values: {perm_table}")
perm_end = pos
print(f"Permutation table ends at offset {perm_end}")

# Phase 2: Parse entries after permutation table
# Known type tags:
# 0x9E = string (followed by u8 length then string data)
# 0x1D = ?? (some other entry type)
# Let's scan for all 0x9E occurrences to understand the pattern

print(f"\n=== SCANNING FROM OFFSET {perm_end} ===")
pos = perm_end
entry_count = 0
entries = []

# First, let's just dump the next 500 bytes to understand the pattern
print(f"\nBytes {perm_end}-{perm_end+200}:")
for row in range(perm_end, min(perm_end+200, len(buf)), 16):
    hex_str = ' '.join(f'{buf[i]:02x}' for i in range(row, min(row+16, len(buf))))
    ascii_str = ''.join(chr(buf[i]) if 32 <= buf[i] < 127 else '.' for i in range(row, min(row+16, len(buf))))
    print(f"  {row:6d}: {hex_str:<48s}  {ascii_str}")

# Let's look at all 0x9E occurrences in the first 5000 bytes
print(f"\n=== ALL 0x9E OCCURRENCES (first 5000 bytes) ===")
for i in range(perm_end, min(5000, len(buf))):
    if buf[i] == 0x9E:
        length = buf[i+1] if i+1 < len(buf) else 0
        if length > 0 and i+2+length <= len(buf):
            data = buf[i+2:i+2+length]
            printable = sum(1 for b in data if 32 <= b < 127)
            is_readable = printable >= len(data) * 0.6
            text = data.decode('ascii', errors='replace') if is_readable else data.hex()
            tag = 'TEXT' if is_readable else 'HEX '
            print(f"  @{i:5d}: 9e {length:02x} → {tag} {text[:80]}")

# Let's also look at 0x1D occurrences
print(f"\n=== ALL 0x1D OCCURRENCES (first 5000 bytes) ===")
for i in range(perm_end, min(5000, len(buf))):
    if buf[i] == 0x1D:
        # What follows 0x1D?
        following = buf[i+1:i+9]
        hex_str = ' '.join(f'{b:02x}' for b in following)
        # Try as float64
        if i+9 <= len(buf):
            try:
                fval = struct.unpack_from('<d', buf, i+1)[0]
                if abs(fval) < 1e15 and abs(fval) > 1e-15 or fval == 0:
                    print(f"  @{i:5d}: 1d {hex_str} → f64={fval}")
                else:
                    print(f"  @{i:5d}: 1d {hex_str}")
            except:
                print(f"  @{i:5d}: 1d {hex_str}")

# Let's also look for other tag bytes
print(f"\n=== TAG BYTE HISTOGRAM (first 10000 bytes, after perm table) ===")
from collections import Counter
# For each position, look at what byte precedes known structures
# Let's check bytes at positions where we expect entry starts
# Build a simple sequential parser

# Strategy: walk through buffer, identify each entry
pos = perm_end
parsed = []
scan_limit = min(5000, len(buf))

while pos < scan_limit:
    tag = buf[pos]
    
    if tag == 0x9E:  # String
        length = buf[pos+1]
        data = buf[pos+2:pos+2+length]
        printable = sum(1 for b in data if 32 <= b < 127)
        is_readable = printable >= max(len(data) * 0.5, 1)
        parsed.append({
            'offset': pos, 'tag': '0x9E', 'type': 'string',
            'length': length,
            'data': data.decode('ascii', errors='replace') if is_readable else data.hex()
        })
        pos += 2 + length
    elif tag == 0x1D:  # Possible float64
        if pos + 9 <= len(buf):
            fval = struct.unpack_from('<d', buf, pos+1)[0]
            parsed.append({
                'offset': pos, 'tag': '0x1D', 'type': 'f64',
                'value': fval
            })
            pos += 9  # 1 tag + 8 bytes
        else:
            pos += 1
    elif tag == 0xD8:  # Another potential tag
        if pos + 5 <= len(buf):
            following = buf[pos+1:pos+5]
            parsed.append({
                'offset': pos, 'tag': '0xD8', 'type': 'unknown_d8',
                'data': following.hex()
            })
            pos += 5
        else:
            pos += 1
    elif tag == 0x73:  # 0x73 might be a nil or special value
        parsed.append({'offset': pos, 'tag': '0x73', 'type': 'maybe_nil'})
        pos += 1
    else:
        parsed.append({
            'offset': pos, 'tag': f'0x{tag:02X}', 'type': 'unknown',
            'byte': tag
        })
        pos += 1

print(f"\n=== PARSED ENTRIES (first {scan_limit} bytes) ===")
print(f"Total entries: {len(parsed)}")

# Show first 100 entries
for i, e in enumerate(parsed[:200]):
    if e['type'] == 'string':
        print(f"  [{i:3d}] @{e['offset']:5d} STRING len={e['length']:3d}: {e['data'][:80]}")
    elif e['type'] == 'f64':
        print(f"  [{i:3d}] @{e['offset']:5d} F64: {e['value']}")
    elif e['type'] == 'unknown':
        pass  # Skip single unknown bytes for now
    else:
        print(f"  [{i:3d}] @{e['offset']:5d} {e['tag']} {e['type']}")

# Summary of tag types
tag_counts = Counter()
for e in parsed:
    tag_counts[e['tag']] += 1
print(f"\nTag histogram:")
for tag, count in tag_counts.most_common(20):
    print(f"  {tag}: {count}")
