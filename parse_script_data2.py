import struct, json

buf_path = r'unobfuscator\cracked script\buffer_1_1064652.bin'
with open(buf_path, 'rb') as f:
    data = f.read()

VM_END = 94736
script = data[VM_END:]

# Parse floating-point constants at the start
print("=== Floating-point constants at start of script data ===")
floats = []
pos = 0
while pos + 8 <= len(script):
    val = struct.unpack_from('<d', script, pos)[0]
    # Check if it looks like a valid float (not NaN, not too extreme)
    if abs(val) < 1e20 and val == val:  # val==val filters NaN
        floats.append((val, VM_END + pos))
        pos += 8
    else:
        break

print(f"Found {len(floats)} consecutive doubles")
for val, pos in floats[:30]:
    print(f"  pos={pos:7d}: {val}")
if len(floats) > 30:
    print(f"  ... and {len(floats) - 30} more")
    for val, pos in floats[-5:]:
        print(f"  pos={pos:7d}: {val}")

float_end = len(floats) * 8
print(f"\nFloat section ends at offset {VM_END + float_end}")

# Now look at data after the floats
after_floats = script[float_end:]
print(f"\nAfter floats: {len(after_floats)} bytes remaining")
print(f"First 100 bytes after float section:")
for i in range(0, min(100, len(after_floats)), 16):
    abs_pos = VM_END + float_end + i
    hex_str = ' '.join(f'{b:02x}' for b in after_floats[i:i+16])
    ascii_str = ''.join(chr(b) if 32 <= b < 127 else '.' for b in after_floats[i:i+16])
    print(f"  {abs_pos:06x}: {hex_str:48s} {ascii_str}")

# Find all 0x9E tags in the script data (string entries)
print(f"\n=== 0x9E string entries in script data ===")
str_entries = []
i = 0
while i < len(after_floats):
    if after_floats[i] == 0x9E and i + 1 < len(after_floats):
        length = after_floats[i + 1]
        if i + 2 + length <= len(after_floats) and 1 <= length <= 250:
            raw = after_floats[i+2:i+2+length]
            str_entries.append((raw, VM_END + float_end + i, length))
            i += 2 + length
            continue
    i += 1

print(f"Found {len(str_entries)} string entries")

# Try to decode these strings
# The VM init section stores strings as plaintext after 0x9E+length
# But the script section strings are encrypted
# Let's see if there's a position-based or index-based XOR pattern

# First, look at the string decryption function in the VM
# The f2 (q) array has decrypted strings at specific positions
# The raw buffer has encrypted strings read during init
# Let me compare encrypted vs decrypted for the strings we already know

# Actually, let me look for patterns in the encrypted strings
print(f"\nFirst 30 encrypted string entries:")
for raw, pos, length in str_entries[:30]:
    hex_str = raw.hex()
    # Try various single-byte XOR
    best_key = None
    best_score = 0
    for key in range(256):
        decoded = bytes(b ^ key for b in raw)
        score = sum(1 for b in decoded if 32 <= b < 127)
        if score > best_score:
            best_score = score
            best_key = key
    
    decoded = bytes(b ^ best_key for b in raw)
    try:
        decoded_str = decoded.decode('ascii', errors='replace')
    except:
        decoded_str = '???'
    
    print(f"  pos={pos:7d} len={length:3d}: hex={hex_str[:30]:30s} best_xor=0x{best_key:02X} ({best_score}/{length} printable) → {repr(decoded_str)[:40]}")

# Look at the byte pattern after string entries - what kind of data follows?
print(f"\n=== Data structure between strings ===")
# Find the gaps between consecutive 0x9E entries
for idx in range(min(10, len(str_entries) - 1)):
    raw1, pos1, len1 = str_entries[idx]
    raw2, pos2, len2 = str_entries[idx + 1]
    gap_start = pos1 + 2 + len1  # after first string
    gap_end = pos2  # before second string's 0x9E tag
    gap_size = gap_end - gap_start
    
    # Get the gap data
    gap_offset = gap_start - VM_END
    gap_data = data[gap_start:gap_end]
    
    print(f"  Gap between str@{pos1} and str@{pos2}: {gap_size} bytes")
    if gap_size <= 30:
        print(f"    hex: {gap_data.hex()}")
    else:
        print(f"    first 30: {gap_data[:30].hex()}")

# Now analyze the pattern more carefully
# The 0x36 byte appears frequently in the hex dumps
byte_36_count = sum(1 for b in after_floats if b == 0x36)
print(f"\n0x36 frequency in script data (after floats): {byte_36_count} ({byte_36_count/len(after_floats)*100:.1f}%)")

# Look at what comes BETWEEN the 0x36 bytes
print(f"\nLooking at 0x36 pattern (first 200 bytes after floats):")
for i in range(min(200, len(after_floats))):
    if after_floats[i] == 0x36:
        if i + 1 < len(after_floats):
            next_byte = after_floats[i + 1]
            print(f"  pos={VM_END+float_end+i}: 36 {next_byte:02x} (next={next_byte})")

# Save decoded constants
with open('script_constants.json', 'w', encoding='utf-8') as f:
    json.dump({
        'float_count': len(floats),
        'floats': [(val, pos) for val, pos in floats],
        'string_entry_count': len(str_entries),
        'float_section_end': VM_END + float_end,
    }, f, indent=2)
print(f"\nSaved to script_constants.json")
