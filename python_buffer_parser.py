"""
Pure Python parser for Luraph v14.7 buffer.
Reads the binary buffer directly and parses using the format deduced from source analysis.
"""
import struct, json, sys

with open(r'unobfuscator\cracked script\buffer_1_1064652.bin', 'rb') as f:
    buf = f.read()

print(f"Buffer size: {len(buf)} bytes")

class BufferReader:
    def __init__(self, data, offset=0):
        self.data = data
        self.pos = offset
    
    def readu8(self):
        v = self.data[self.pos]
        self.pos += 1
        return v
    
    def readu16(self):
        v = struct.unpack_from('<H', self.data, self.pos)[0]
        self.pos += 2
        return v
    
    def readi16(self):
        v = struct.unpack_from('<h', self.data, self.pos)[0]
        self.pos += 2
        return v
    
    def readu32(self):
        v = struct.unpack_from('<I', self.data, self.pos)[0]
        self.pos += 4
        return v
    
    def readi32(self):
        v = struct.unpack_from('<i', self.data, self.pos)[0]
        self.pos += 4
        return v
    
    def readf32(self):
        v = struct.unpack_from('<f', self.data, self.pos)[0]
        self.pos += 4
        return v
    
    def readf64(self):
        v = struct.unpack_from('<d', self.data, self.pos)[0]
        self.pos += 8
        return v
    
    def read_varint(self):
        value = 0
        shift = 0
        while True:
            b = self.data[self.pos]
            self.pos += 1
            value |= (b & 0x7F) << shift
            shift += 7
            if b < 128:
                break
        return value
    
    def read_bytes(self, n):
        v = self.data[self.pos:self.pos + n]
        self.pos += n
        return v
    
    def peek(self, n=16):
        return self.data[self.pos:self.pos + n]

# First, let's understand the init section
# The init section uses tagged reads: tag byte then data
# From the buffer trace, init reads ~94736 bytes

# Let's skip the init section and look at the script data
SCRIPT_DATA_OFFSET = 94736
print(f"\n=== Script data starts at offset {SCRIPT_DATA_OFFSET} ===")
print(f"Remaining: {len(buf) - SCRIPT_DATA_OFFSET} bytes")

# Show raw bytes at script data start
print(f"\nRaw bytes at {SCRIPT_DATA_OFFSET}:")
for i in range(0, 64, 16):
    off = SCRIPT_DATA_OFFSET + i
    hexs = ' '.join(f'{b:02x}' for b in buf[off:off+16])
    ascs = ''.join(chr(b) if 32 <= b < 127 else '.' for b in buf[off:off+16])
    print(f"  {off:6d}: {hexs}  {ascs}")

# Read the sub-buffer at start
r = BufferReader(buf, SCRIPT_DATA_OFFSET)
sub_len_byte = r.peek(1)[0]
print(f"\nFirst byte at script data: {sub_len_byte} (0x{sub_len_byte:02x})")

# Try reading as varint
r2 = BufferReader(buf, SCRIPT_DATA_OFFSET)
sub_len = r2.read_varint()
print(f"First varint: {sub_len}")

if sub_len <= 1000:
    sub_data = r2.read_bytes(sub_len)
    print(f"Sub-buffer ({sub_len} bytes): {sub_data.hex()}")
    print(f"After sub-buffer, pos: {r2.pos}")
    
    # Now read varints after sub-buffer
    print(f"\nFirst 50 varints after sub-buffer:")
    varints = []
    for i in range(50):
        off = r2.pos
        v = r2.read_varint()
        size = r2.pos - off
        varints.append((off, v, size))
        print(f"  [{i:3d}] off={off:6d} val={v:12d} ({size}B)")

# Now let's try to understand the format
# From lF: first varint = string_count_or_similar - 36578
# From the lazy deserializer W: lF reads header, then t9/ZF reads strings

# Let's also try standard Luau bytecode format at the script data start
print(f"\n{'='*70}")
print("Trying standard Luau bytecode format")
print(f"{'='*70}")

# Standard Luau bytecode:
# 1. Version byte (u8)
# 2. Types version byte (u8) -- if version >= 4
# 3. String count (varint)
# 4. For each string: length (varint) + bytes
# 5. Proto count (varint)
# 6. For each proto: maxstacksize, numparams, nups, isvararg, ... 

# But Luraph modifies the format. Let's just try reading varints
# and see if any make sense as string lengths

print(f"\n{'='*70}")
print("Analyzing varint sequence for string table patterns")
print(f"{'='*70}")

# Reset to after sub-buffer
r3 = BufferReader(buf, SCRIPT_DATA_OFFSET)
sub_len = r3.read_varint()
r3.read_bytes(sub_len)

# Read the first varint (could be string count or something else)
first_varint = r3.read_varint()
print(f"First varint after sub-buffer: {first_varint}")

# Check if it could be a string count
# If first_varint is the string count, then next varints should be string lengths
# followed by that many bytes

# Try interpreting as string count
if 0 < first_varint < 100000:
    test_r = BufferReader(buf, r3.pos)
    valid_strings = 0
    for i in range(min(first_varint, 20)):
        try:
            slen = test_r.read_varint()
            if slen < 0 or slen > 100000:
                print(f"  String {i}: length={slen} — too large, probably not string count")
                break
            if slen > 0:
                sdata = test_r.read_bytes(slen)
                # Check if printable
                printable = sum(1 for b in sdata if 32 <= b < 127) / max(len(sdata), 1)
                safe = ''.join(chr(b) if 32 <= b < 127 else '.' for b in sdata[:50])
                print(f"  String {i}: len={slen}, printable={printable:.0%}, data='{safe}'")
                valid_strings += 1
            else:
                print(f"  String {i}: empty (len=0)")
                valid_strings += 1
        except Exception as e:
            print(f"  String {i}: ERROR: {e}")
            break
    print(f"  Valid strings: {valid_strings}")

# Also try: maybe the format uses the tag byte from ZF
# ZF reads Q = readu8, then dispatches based on Q value
# Let's try reading bytes and see if they fall in the expected ranges

print(f"\n{'='*70}")
print("Trying ZF-style tag-based string reading")
print(f"{'='*70}")

# Start from various offsets and try reading tag + data
for start_off in [r3.pos, r3.pos + 1, r3.pos + 2]:
    test_r = BufferReader(buf, start_off)
    print(f"\nStarting at offset {start_off}:")
    for i in range(10):
        tag = test_r.readu8()
        tag_range = "???"
        if tag <= 29: tag_range = "EF:r[40]()"
        elif tag <= 87: tag_range = "EF:uF loop"
        elif tag <= 100: tag_range = "sF:HF"
        elif tag <= 123: tag_range = "sF:OF"
        elif tag <= 140: tag_range = "BF:iF:nF"
        elif tag <= 161: tag_range = "BF:iF:hF"
        elif tag <= 202: tag_range = "BF:WF:pF"
        elif tag <= 217: tag_range = "BF:WF:r[41]()"
        else: tag_range = "BF:WF:z.a"
        print(f"  [{i:2d}] tag={tag:3d} (0x{tag:02x}) → {tag_range}")

# Let's also look at what the data looks like as mixed varint + u8 sequences
# Based on the lazy deserializer structure:
# lF reads: varint (C = val - 36578), then calls fF in a loop
# _9 processes something
# t9 reads: r[r[46]()] — reads a varint as an INDEX into some table

print(f"\n{'='*70}")
print("Trying to trace the lazy deserializer path")
print(f"{'='*70}")

r4 = BufferReader(buf, SCRIPT_DATA_OFFSET)

# Step 1: Read sub-buffer (from z:zy init)
sub_len = r4.read_varint()
sub_data = r4.read_bytes(sub_len)
print(f"1. Sub-buffer: len={sub_len}, data={sub_data.hex()}")

# Step 2: lF reads first varint and subtracts 36578
C = r4.read_varint() - 36578
print(f"2. lF first read: varint - 36578 = {C}")

# lF then calls fF in a loop. fF is unknown. Let's try reading more varints.
print(f"3. Next 20 reads (mixed types):")
for i in range(20):
    off = r4.pos
    b = buf[off]
    # Try as varint
    v = r4.read_varint()
    r4.pos = off  # reset
    # Also show raw bytes
    raw = buf[off:off+8]
    print(f"   off={off:6d} byte=0x{b:02x}({b:3d}) varint={v:12d} raw={raw.hex()}")
    r4.pos = off + 1  # advance by 1 byte for next attempt

# Let me also check: what if the format after sub-buffer is actually
# the Luau bytecode format (version + strings + protos)?
print(f"\n{'='*70}")  
print("Trying Luau bytecode format after sub-buffer")
print(f"{'='*70}")

r5 = BufferReader(buf, SCRIPT_DATA_OFFSET)
sub_len = r5.read_varint()
r5.read_bytes(sub_len)

# Read version byte
version = r5.readu8()
print(f"Version byte: {version}")

# Read types version if version >= 4
if version >= 4:
    types_ver = r5.readu8()
    print(f"Types version: {types_ver}")

# Read string count
str_count = r5.read_varint()
print(f"String count: {str_count}")

if 0 < str_count < 100000:
    strings = []
    for i in range(min(str_count, 30)):
        slen = r5.read_varint()
        if slen > 100000:
            print(f"  String {i}: len={slen} — too large, wrong format")
            break
        sdata = r5.read_bytes(slen)
        printable = sum(1 for b in sdata if 32 <= b < 127) / max(len(sdata), 1)
        safe = ''.join(chr(b) if 32 <= b < 127 else '.' for b in sdata[:60])
        strings.append(sdata)
        if i < 20 or printable > 0.5:
            print(f"  String {i}: len={slen:4d} print={printable:.0%} '{safe}'")
    print(f"  Read {len(strings)} strings")
    
    if len(strings) == str_count or len(strings) >= 20:
        # Try reading proto count
        proto_count = r5.read_varint()
        print(f"\nProto count: {proto_count}")
