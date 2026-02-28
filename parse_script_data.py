import struct, json

buf_path = r'unobfuscator\cracked script\buffer_1_1064652.bin'
with open(buf_path, 'rb') as f:
    data = f.read()

VM_END = 94736  # VM init data ends here
print(f"Buffer: {len(data)} bytes, VM data: 0-{VM_END}, Script data: {VM_END}-{len(data)}")
print(f"Script section size: {len(data) - VM_END} bytes")

script_data = data[VM_END:]

# Look at the structure of the script data
print(f"\nFirst 200 bytes of script section (hex):")
for i in range(0, min(200, len(script_data)), 16):
    hex_str = ' '.join(f'{b:02x}' for b in script_data[i:i+16])
    ascii_str = ''.join(chr(b) if 32 <= b < 127 else '.' for b in script_data[i:i+16])
    print(f"  {VM_END+i:06x}: {hex_str:48s} {ascii_str}")

# Scan for printable string sequences in the script data
print(f"\nScanning for printable strings in script data...")
strings_found = []
i = 0
while i < len(script_data):
    if 32 <= script_data[i] < 127:
        start = i
        while i < len(script_data) and (32 <= script_data[i] < 127 or script_data[i] in (9, 10, 13)):
            i += 1
        length = i - start
        if length >= 4:
            s = script_data[start:i].decode('ascii')
            strings_found.append((s, VM_END + start, length))
    else:
        i += 1

print(f"Found {len(strings_found)} printable sequences >= 4 chars")

# Filter out known VM strings and noise
interesting = []
noise_patterns = {'ssss', 'sss', '====', '>>>>','<<<<'}
for s, pos, length in strings_found:
    if any(p in s.lower() for p in noise_patterns):
        continue
    if length >= 4:
        interesting.append((s, pos, length))

print(f"Interesting strings: {len(interesting)}")
for s, pos, length in interesting[:100]:
    if len(s) > 80:
        print(f"  pos={pos:7d} len={length:3d}: {repr(s[:80])}...")
    else:
        print(f"  pos={pos:7d} len={length:3d}: {repr(s)}")

# Also try the tag-based format on the script section
# Check if the script data starts with known type tags
print(f"\nChecking if script data uses tag-based format...")
TAG_U8 = 0x73
TAG_STR = 0x9E
TAG_U16 = 0x1D
TAG_I16 = 0xD8
TAG_I32 = 0x57

first_bytes = list(script_data[:50])
tag_count = sum(1 for b in first_bytes if b in (TAG_U8, TAG_STR, TAG_U16, TAG_I16, TAG_I32))
print(f"First 50 bytes: {tag_count} known tags ({tag_count/50*100:.0f}%)")
print(f"Byte values: {first_bytes}")

# Check byte frequency in script data
from collections import Counter
byte_freq = Counter(script_data)
print(f"\nTop 20 most common bytes in script data:")
for byte, count in byte_freq.most_common(20):
    pct = count / len(script_data) * 100
    print(f"  0x{byte:02X} ({byte:3d}): {count:6d} ({pct:.1f}%)")

# Check if 0x73 is common (would indicate same tag format)
print(f"\n0x73 frequency: {byte_freq.get(0x73, 0)} ({byte_freq.get(0x73, 0)/len(script_data)*100:.2f}%)")

# Try to parse with tag-based format
print(f"\nAttempting tag-based parse of first 10000 bytes of script data...")
pos = 0
values = []
errors = 0
while pos < min(10000, len(script_data)) and errors < 20:
    tag = script_data[pos]
    if tag == TAG_U8 and pos + 1 < len(script_data):
        values.append(('u8', script_data[pos+1], VM_END + pos))
        pos += 2
    elif tag == TAG_STR and pos + 1 < len(script_data):
        length = script_data[pos+1]
        if pos + 2 + length <= len(script_data):
            raw = script_data[pos+2:pos+2+length]
            values.append(('str', raw, VM_END + pos))
            pos += 2 + length
        else:
            errors += 1
            pos += 1
    elif tag == TAG_U16 and pos + 2 < len(script_data):
        v = struct.unpack_from('<H', script_data, pos+1)[0]
        values.append(('u16', v, VM_END + pos))
        pos += 3
    elif tag == TAG_I16 and pos + 2 < len(script_data):
        v = struct.unpack_from('<h', script_data, pos+1)[0]
        values.append(('i16', v, VM_END + pos))
        pos += 3
    elif tag == TAG_I32 and pos + 4 < len(script_data):
        v = struct.unpack_from('<i', script_data, pos+1)[0]
        values.append(('i32', v, VM_END + pos))
        pos += 5
    else:
        errors += 1
        pos += 1

print(f"Parsed {len(values)} values, {errors} errors in first 10KB")
if values:
    print("First 50 parsed values:")
    for i, (typ, val, pos) in enumerate(values[:50]):
        if typ == 'str':
            try:
                s = val.decode('ascii')
                is_print = all(32 <= ord(c) < 127 or c in '\t\n\r' for c in s)
                if is_print:
                    print(f"  [{i}] pos={pos:7d} {typ}: {repr(s)[:60]}")
                else:
                    print(f"  [{i}] pos={pos:7d} {typ}: <hex:{val.hex()[:30]}>")
            except:
                print(f"  [{i}] pos={pos:7d} {typ}: <hex:{val.hex()[:30]}>")
        else:
            print(f"  [{i}] pos={pos:7d} {typ}: {val}")

# Look for length-prefixed strings with various encodings
print(f"\nSearching for length-prefixed strings in script data...")
lp_strings = []
for i in range(len(script_data) - 2):
    length = script_data[i]
    if 3 <= length <= 200 and i + 1 + length <= len(script_data):
        candidate = script_data[i+1:i+1+length]
        try:
            s = candidate.decode('ascii')
            if all(32 <= ord(c) < 127 for c in s):
                lp_strings.append((s, VM_END + i, length))
        except:
            pass

print(f"Found {len(lp_strings)} length-prefixed printable strings")
# Filter duplicates
seen = set()
unique_lp = []
for s, pos, length in lp_strings:
    if s not in seen:
        seen.add(s)
        unique_lp.append((s, pos, length))

print(f"Unique: {len(unique_lp)}")
for s, pos, length in unique_lp[:50]:
    print(f"  pos={pos:7d} len={length}: {repr(s)[:60]}")

# Save results
with open('script_data_analysis.json', 'w', encoding='utf-8') as f:
    json.dump({
        'script_section_start': VM_END,
        'script_section_size': len(script_data),
        'printable_sequences': [(s, pos, l) for s, pos, l in interesting[:500]],
        'length_prefixed_strings': [(s, pos, l) for s, pos, l in unique_lp[:500]],
    }, f, indent=2, ensure_ascii=False)
print(f"\nSaved to script_data_analysis.json")
