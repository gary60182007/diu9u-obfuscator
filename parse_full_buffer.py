import struct, json
from collections import Counter

buf_path = r'unobfuscator\cracked script\buffer_1_1064652.bin'
with open(buf_path, 'rb') as f:
    data = f.read()

VM_END = 94736
sub = data[VM_END:]
print(f"Sub-buffer: {len(sub)} bytes")

# First 8 doubles (64 bytes) are numeric constants (no tags)
NUM_FLOATS = 8
floats = []
for i in range(NUM_FLOATS):
    v = struct.unpack_from('<d', sub, i * 8)[0]
    floats.append(v)
    print(f"  Float[{i}]: {v}")

# Bytes 64-102 are unknown header/seed data (39 bytes)
header_data = sub[64:103]
print(f"\nHeader/seed data (bytes 64-102, {len(header_data)} bytes):")
print(f"  hex: {header_data.hex()}")

# Tag-based parsing starts at sub-offset 103
TAG_START = 103
TAG_U8 = 0x36
TAG_STR = 0x9E
TAG_U16 = 0x1D
TAG_I16 = 0xD8
TAG_I32 = 0x57

# Additional potential tags from main buffer
TAG_U32_MAYBE = 0xA1  # from main buffer trace (u32 appeared)
TAG_F32_MAYBE = 0x7B  # 123, frequent unknown

# Parse with known tags
pos = TAG_START
values = []
unknowns = []
type_counts = Counter()

while pos < len(sub):
    tag = sub[pos]
    
    if tag == TAG_U8 and pos + 1 < len(sub):
        v = sub[pos + 1]
        values.append(('u8', v, pos))
        type_counts['u8'] += 1
        pos += 2
    elif tag == TAG_STR and pos + 1 < len(sub):
        length = sub[pos + 1]
        if length == 0:
            values.append(('str', b'', pos))
            type_counts['str'] += 1
            pos += 2
        elif pos + 2 + length <= len(sub):
            raw = sub[pos + 2:pos + 2 + length]
            values.append(('str', raw, pos))
            type_counts['str'] += 1
            pos += 2 + length
        else:
            unknowns.append((pos, tag))
            pos += 1
    elif tag == TAG_U16 and pos + 2 < len(sub):
        v = struct.unpack_from('<H', sub, pos + 1)[0]
        values.append(('u16', v, pos))
        type_counts['u16'] += 1
        pos += 3
    elif tag == TAG_I16 and pos + 2 < len(sub):
        v = struct.unpack_from('<h', sub, pos + 1)[0]
        values.append(('i16', v, pos))
        type_counts['i16'] += 1
        pos += 3
    elif tag == TAG_I32 and pos + 4 < len(sub):
        v = struct.unpack_from('<i', sub, pos + 1)[0]
        values.append(('i32', v, pos))
        type_counts['i32'] += 1
        pos += 5
    else:
        unknowns.append((pos, tag))
        pos += 1

print(f"\n=== Parse results ===")
print(f"Total tagged values: {len(values)}")
print(f"Type counts: {dict(type_counts)}")
print(f"Unknown bytes: {len(unknowns)}")

# Analyze unknown tags
unkn_tags = Counter(t for _, t in unknowns)
print(f"\nTop unknown tag bytes:")
for tag, cnt in unkn_tags.most_common(20):
    print(f"  0x{tag:02X} ({tag:3d}): {cnt}")

# The most frequent unknown tags might be additional type tags
# Let me analyze what follows them
print(f"\n=== Analyzing top unknown tags ===")
for tag_val, cnt in unkn_tags.most_common(5):
    positions = [p for p, t in unknowns if t == tag_val][:10]
    print(f"\n0x{tag_val:02X} ({cnt} occurrences), first positions:")
    for p in positions:
        context = sub[p:min(p+10, len(sub))]
        print(f"  sub_pos={p}: {context.hex()}")

# Extract all strings
str_entries = [(raw, pos) for typ, raw, pos in values if typ == 'str']
print(f"\n=== String Analysis ===")
print(f"Total string entries: {len(str_entries)}")

# Length distribution
lengths = [len(raw) for raw, _ in str_entries]
len_counter = Counter(lengths)
print(f"Length distribution:")
for l, c in sorted(len_counter.items())[:20]:
    print(f"  len={l}: {c} strings")

# Try to find decryption pattern by analyzing byte distributions
# In encrypted text, byte distribution should be roughly uniform
# In plaintext, it should cluster around ASCII range
print(f"\n=== String Decryption Analysis ===")

# Collect all encrypted string bytes
all_str_bytes = b''.join(raw for raw, _ in str_entries)
print(f"Total encrypted string bytes: {len(all_str_bytes)}")

# Byte frequency in encrypted strings
byte_freq = Counter(all_str_bytes)
print(f"Top 20 bytes in encrypted strings:")
for b, c in byte_freq.most_common(20):
    pct = c / len(all_str_bytes) * 100
    print(f"  0x{b:02X}: {c:5d} ({pct:.1f}%)")

# Try each single-byte XOR key and check how many bytes fall in printable range
print(f"\nBest single-byte XOR keys:")
best_keys = []
for key in range(256):
    printable = sum(1 for b in all_str_bytes if 32 <= (b ^ key) < 127)
    score = printable / len(all_str_bytes)
    best_keys.append((key, score))

best_keys.sort(key=lambda x: -x[1])
for key, score in best_keys[:10]:
    print(f"  XOR 0x{key:02X}: {score*100:.1f}% printable")

# Try position-dependent XOR
# If key = position % N for some N, check small N values
print(f"\nPosition-dependent XOR analysis:")
for period in [1, 2, 3, 4, 8]:
    # For each period, find the best key for each position
    best_score = 0
    best_keys_p = []
    for phase in range(period):
        phase_bytes = [all_str_bytes[i] for i in range(phase, len(all_str_bytes), period)]
        best_k = 0
        best_s = 0
        for k in range(256):
            s = sum(1 for b in phase_bytes if 32 <= (b ^ k) < 127)
            if s > best_s:
                best_s = s
                best_k = k
        best_keys_p.append(best_k)
        best_score += best_s
    overall = best_score / len(all_str_bytes) * 100
    print(f"  Period {period}: {overall:.1f}% printable, keys={[f'0x{k:02X}' for k in best_keys_p]}")

# Try per-string XOR (different key per string)
print(f"\nPer-string XOR analysis (first 30 strings):")
for raw, pos in str_entries[:30]:
    if len(raw) < 3:
        continue
    best_k = 0
    best_s = 0
    for k in range(256):
        s = sum(1 for b in raw if 32 <= (b ^ k) < 127)
        if s > best_s:
            best_s = s
            best_k = k
    decoded = bytes(b ^ best_k for b in raw)
    try:
        ds = decoded.decode('ascii', errors='replace')
    except:
        ds = decoded.hex()
    pct = best_s / len(raw) * 100
    print(f"  pos={VM_END+pos:7d} len={len(raw):3d} XOR=0x{best_k:02X} ({pct:.0f}%): {repr(ds)[:50]}")

# Try XOR with index-based key (key = string_index % 256)
print(f"\nIndex-based XOR (key = string_index):")
for idx, (raw, pos) in enumerate(str_entries[:30]):
    if len(raw) < 3:
        continue
    key = idx & 0xFF
    decoded = bytes(b ^ key for b in raw)
    try:
        ds = decoded.decode('ascii', errors='replace')
    except:
        ds = decoded.hex()
    printable = sum(1 for b in decoded if 32 <= b < 127) / len(decoded) * 100
    print(f"  str[{idx}] XOR={key:3d}: ({printable:.0f}%) {repr(ds)[:50]}")

# Save results
with open('full_buffer_parse.json', 'w', encoding='utf-8') as f:
    json.dump({
        'floats': floats,
        'total_tagged': len(values),
        'type_counts': dict(type_counts),
        'unknown_bytes': len(unknowns),
        'string_count': len(str_entries),
        'total_str_bytes': len(all_str_bytes),
    }, f, indent=2)
print(f"\nSaved to full_buffer_parse.json")
