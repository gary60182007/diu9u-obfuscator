"""
Build a standalone Python buffer parser for Luraph v14.7.
Uses the extracted ground truth (luraph_strings_full.json) to verify parsing.
Reads the binary buffer and replicates ZF's tag-based dispatch.
"""
import struct, json, sys

# Load ground truth
with open('luraph_strings_full.json', 'r', encoding='utf-8') as f:
    ground_truth = json.load(f)

# Load binary buffer
with open(r'unobfuscator\cracked script\buffer_1_1064652.bin', 'rb') as f:
    buffer = f.read()

print(f"Buffer size: {len(buffer)} bytes")
print(f"Ground truth entries: {len(ground_truth)}")

# Varint reader (LEB128)
def read_varint(buf, offset):
    result = 0
    shift = 0
    while True:
        b = buf[offset]
        offset += 1
        result |= (b & 0x7F) << shift
        shift += 7
        if b < 128:
            break
    return result, offset

# Read header
pos = 0
header_varint, pos = read_varint(buffer, pos)
print(f"Header varint: {header_varint} (pos after: {pos})")
string_count = header_varint - 36578
print(f"String count: {string_count}")

# Read more header bytes
# From diagnostics: lF at r10=0 reads varint, fF at r10=3 creates table, oF at r10=3 reads boolean
# q9 starts at r10=4, ZF first call at r10=? 
# Let's just read the header bytes
print(f"Bytes 0-10: {' '.join(f'{b:02x}' for b in buffer[:10])}")

# After varint (pos=3 or wherever), fF reads the varint again? No, fF uses the return value.
# oF reads 1 byte at the current position
bool_byte = buffer[pos]
pos += 1
has_hash = bool_byte != 0
print(f"Boolean byte at {pos-1}: {bool_byte} (has_hash={has_hash})")
print(f"ZF starts reading at pos: {pos}")

# Now read 1170 constants
# ZF reads a tag byte, then dispatches based on tag value
# Tag <= 123: short constant (RF path)
# Tag > 123: long constant (BF path)

# Let's first just scan the tag bytes and see the distribution
tag_counts = {}
scan_pos = pos
for i in range(min(50, string_count)):
    tag = buffer[scan_pos]
    tag_counts[tag] = tag_counts.get(tag, 0) + 1
    scan_pos += 1  # skip tag, we don't know the data length yet

print(f"\nFirst 50 tag bytes starting at {pos}:")
print(' '.join(f'{buffer[pos+i]:02x}' for i in range(min(50, len(buffer)-pos))))
print(' '.join(f'{buffer[pos+i]:3d}' for i in range(min(50, len(buffer)-pos))))

# Let's try to understand the tag byte encoding
# From ZF: if Q <= 123 → RF path, if Q > 123 → BF path
# From EF (called by RF): if W <= 29 → r = C[40](), else for loop with uF
# From uF: if W <= 54 → C = -r[39]() (negative readu8), if W > 54 → C = r[44]()

# Let's look at what r[40] and r[44] are
# r[39] = readu8
# r[40] = ? (used when W <= 29)
# r[44] = ? (used when W > 54)
# These are buffer reader functions set up during VM init

# Let's try a different approach: trace the actual data
# We know the ground truth values. Let's try to match them with the buffer data.

# First, let me check what the first few constants should be
print(f"\n=== First 20 ground truth entries ===")
for k in sorted(ground_truth.keys(), key=int)[:20]:
    entry = ground_truth[k]
    t = entry['type']
    if t == 'n':
        print(f"  [{k:4s}] NUMBER: {entry['val']}")
    elif t == 's':
        text = entry.get('text', '')
        print(f"  [{k:4s}] STRING: {repr(text[:60])} (len={entry.get('len', '?')})")
    elif t == 'ts':
        text = entry.get('text', '')
        print(f"  [{k:4s}] TUPLE_STR: {repr(text[:60])} (len={entry.get('len', '?')})")
    elif t == 'tn':
        print(f"  [{k:4s}] TUPLE_NUM: {entry.get('val', '?')}")
    elif t == 'b':
        print(f"  [{k:4s}] BOOLEAN: {entry.get('val', '?')}")

# The first entries are indexed 1, 2, 3, ... (from q9's O=1 to 1170)
# Ground truth keys are the indices
# Entry 1: number 40
# Entry 2: number 1
# etc.

# Let's try to parse: tag byte determines the type
# Hypothesis: tag encodes type + value for small numbers, or type + length for strings

# Try reading the first few entries manually
print(f"\n=== Manual parse attempt ===")
parse_pos = pos
for i in range(1, min(30, string_count+1)):
    tag = buffer[parse_pos]
    gt_key = str(i)
    gt_entry = ground_truth.get(gt_key)
    
    if gt_entry:
        gt_type = gt_entry['type']
        if gt_type == 'n':
            gt_val = gt_entry['val']
        elif gt_type in ('s', 'ts'):
            gt_val = f"str({gt_entry.get('len', '?')}B)"
        elif gt_type == 'b':
            gt_val = gt_entry['val']
        else:
            gt_val = '?'
    else:
        gt_type = '?'
        gt_val = '?'
    
    # Show tag and next few bytes for context
    ctx = ' '.join(f'{buffer[parse_pos+j]:02x}' for j in range(min(8, len(buffer)-parse_pos)))
    print(f"  [{i:4d}] tag={tag:3d} (0x{tag:02x}) bytes=[{ctx}]  GT: {gt_type}={gt_val}")
    
    # Try to figure out the encoding
    # If tag <= 123: likely a small number or reference
    # If tag > 123: likely a string
    
    # For numbers: maybe tag IS the value? Or tag - offset = value?
    # Entry 1: GT=40, tag=? 
    # Entry 2: GT=1, tag=?
    
    parse_pos += 1  # Just advance by 1 for now (tag only)

# Let's look at tag byte vs ground truth value correlation for number entries
print(f"\n=== Tag byte analysis (numbers only) ===")
parse_pos = pos
num_entries = []
for i in range(1, string_count + 1):
    if parse_pos >= len(buffer):
        break
    tag = buffer[parse_pos]
    gt_key = str(i)
    gt_entry = ground_truth.get(gt_key)
    if gt_entry and gt_entry['type'] == 'n':
        num_entries.append((i, tag, gt_entry['val']))
    parse_pos += 1  # tentative: tag only

# Show first 30 number entries and their tags
print(f"  {'idx':>5s}  {'tag':>4s}  {'gt_val':>8s}  {'tag-gt':>6s}")
for idx, tag, val in num_entries[:30]:
    diff = tag - val
    print(f"  {idx:5d}  {tag:4d}  {val:8.0f}  {diff:6d}")

# Check if there's a consistent offset
diffs = set()
for idx, tag, val in num_entries[:30]:
    if isinstance(val, (int, float)):
        diffs.add(tag - int(val))
print(f"\nTag-value diffs (first 30): {diffs}")
