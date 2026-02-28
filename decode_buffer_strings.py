import struct, json, os

buf_path = r'unobfuscator\cracked script\buffer_1_1064652.bin'
with open(buf_path, 'rb') as f:
    data = f.read()

print(f"Buffer size: {len(data)} bytes")

# From earlier analysis:
# Type tags: 0x9E=str, 0x1D=u16, 0xD8=i16, 0x57=i32, 0x73=u8
# XOR pattern: every other byte is 0x73

# Strategy: scan for string read patterns
# When the VM reads a string, it first reads a length (u8, u16, or varint),
# then reads that many bytes. The strings may be XOR-encrypted.

# Let's try multiple XOR keys and see what produces readable text
def try_xor_decode(raw_bytes, key):
    return bytes(b ^ key for b in raw_bytes)

def is_printable(s):
    return all(32 <= c < 127 or c in (9, 10, 13) for c in s)

# Method 1: Scan for length-prefixed strings with various XOR keys
found_strings = []

# Try scanning with different patterns
for xor_key in [0x00, 0x73, 0x9E, 0x1D, 0xD8, 0x57]:
    decoded = try_xor_decode(data, xor_key)
    # Look for length-prefixed strings (u8 length + data)
    pos = 0
    while pos < len(decoded) - 2:
        length = decoded[pos]
        if 3 <= length <= 200 and pos + 1 + length <= len(decoded):
            candidate = decoded[pos+1:pos+1+length]
            if is_printable(candidate):
                s = candidate.decode('ascii', errors='replace')
                found_strings.append((s, pos, xor_key, 'u8_prefix'))
        pos += 1

print(f"\nMethod 1 (length-prefixed scan): {len(found_strings)} candidates")

# Deduplicate
seen = set()
unique = []
for s, pos, key, method in found_strings:
    if s not in seen and len(s) >= 3:
        seen.add(s)
        unique.append((s, pos, key, method))

print(f"Unique strings >= 3 chars: {len(unique)}")
for s, pos, key, method in sorted(unique, key=lambda x: x[1])[:100]:
    print(f"  pos={pos:7d} xor=0x{key:02x} {method}: {repr(s)[:80]}")

# Method 2: Look for null-terminated strings in raw buffer
print(f"\nMethod 2: Scanning for printable sequences in raw buffer...")
raw_strings = []
i = 0
while i < len(data):
    if 32 <= data[i] < 127:
        start = i
        while i < len(data) and (32 <= data[i] < 127 or data[i] in (9, 10, 13)):
            i += 1
        length = i - start
        if length >= 4:
            s = data[start:i].decode('ascii')
            raw_strings.append((s, start))
    else:
        i += 1

print(f"Raw printable sequences >= 4 chars: {len(raw_strings)}")
for s, pos in raw_strings[:50]:
    print(f"  pos={pos:7d}: {repr(s)[:80]}")

# Method 3: XOR with 0x73 (the identified XOR pattern)
print(f"\nMethod 3: Full XOR 0x73 decode, looking for printable sequences...")
xored = try_xor_decode(data, 0x73)
xor_strings = []
i = 0
while i < len(xored):
    if 32 <= xored[i] < 127:
        start = i
        while i < len(xored) and (32 <= xored[i] < 127 or xored[i] in (9, 10, 13)):
            i += 1
        length = i - start
        if length >= 4:
            s = xored[start:i].decode('ascii')
            xor_strings.append((s, start))
    else:
        i += 1

print(f"XOR-0x73 printable sequences >= 4 chars: {len(xor_strings)}")
for s, pos in xor_strings[:50]:
    print(f"  pos={pos:7d}: {repr(s)[:80]}")

# Method 4: Look for the actual string table
# In Luraph, strings are typically stored in a string constant pool
# Let's look for clusters of string data
print(f"\nMethod 4: Analyzing buffer structure...")
# Look at the first 200 bytes for header info
print("First 100 bytes (hex):")
for i in range(0, min(100, len(data)), 16):
    hex_str = ' '.join(f'{b:02x}' for b in data[i:i+16])
    ascii_str = ''.join(chr(b) if 32 <= b < 127 else '.' for b in data[i:i+16])
    print(f"  {i:06x}: {hex_str:48s} {ascii_str}")

# Look for the type tag 0x9E (string read marker)
tag_positions = []
for i in range(len(data)):
    if data[i] == 0x9E:
        tag_positions.append(i)
print(f"\n0x9E tag positions: {len(tag_positions)} (first 20: {tag_positions[:20]})")

# After 0x9E tag, check what follows (length then string data)
print("\nSampling 0x9E tag contexts:")
for pos in tag_positions[:30]:
    context = data[pos:pos+30]
    hex_str = ' '.join(f'{b:02x}' for b in context)
    # Try reading u8 length after tag
    if pos + 1 < len(data):
        u8_len = data[pos + 1]
        if 1 <= u8_len <= 200 and pos + 2 + u8_len <= len(data):
            raw = data[pos+2:pos+2+u8_len]
            xored = bytes(b ^ 0x73 for b in raw)
            raw_s = raw.decode('ascii', errors='replace')
            xor_s = xored.decode('ascii', errors='replace')
            raw_print = is_printable(raw)
            xor_print = is_printable(xored)
            marker = ""
            if raw_print:
                marker = f" RAW={repr(raw_s)}"
            if xor_print:
                marker += f" XOR={repr(xor_s)}"
            print(f"  {pos:6d}: u8_len={u8_len:3d}{marker}  hex={hex_str[:60]}")

# Save all found strings
all_found = set()
for s, pos, key, method in unique:
    all_found.add(s)
for s, pos in raw_strings:
    all_found.add(s)
for s, pos in xor_strings:
    all_found.add(s)

with open('buffer_decoded_strings.json', 'w', encoding='utf-8') as f:
    json.dump(sorted(all_found), f, indent=2, ensure_ascii=False)
print(f"\nTotal unique strings found: {len(all_found)}")
print(f"Saved to buffer_decoded_strings.json")
