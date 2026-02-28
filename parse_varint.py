import struct, json, sys

buf_path = r'unobfuscator\cracked script\buffer_1_1064652.bin'
with open(buf_path, 'rb') as f:
    data = f.read()

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
    
    def varint(self):
        b = self.data[self.pos]
        self.pos += 1
        if b < 128:
            return b
        # Multi-byte varint
        result = b & 0x7F
        shift = 7
        while True:
            b = self.data[self.pos]
            self.pos += 1
            result |= (b & 0x7F) << shift
            if b < 128:
                break
            shift += 7
        return result
    
    def read_bytes(self, n):
        v = self.data[self.pos:self.pos+n]
        self.pos += n
        return v
    
    def sub_buffer(self):
        length = self.varint()
        data = self.read_bytes(length)
        return data

# Verify varint encoding against known values
# From force_read_strings.py: r[46]() at 94736 = 36 (1 byte)
# r[46]() at 94852 = 1054 (2 bytes), where bytes are 0x9E 0x08
# 0x9E = 158: (158 & 0x7F) = 30, then 0x08 = 8: 30 + 8*128 = 30 + 1024 = 1054
print("=== Varint verification ===")
r = BufferReader(data, 94736)
v = r.varint()
print(f"  offset 94736: varint={v} (expected 36)")

r.pos = 94852
v = r.varint()
print(f"  offset 94852: varint={v} (expected 1054)")

# Now parse the VM init section to understand the format
# by matching against the known buffer trace
print(f"\n=== Parsing VM init section ===")
r = BufferReader(data, 0)

# Header: 4 bytes (from trace: u8,0,244; u8,1,166; u8,2,2; u8,3,0)
header = r.readu32()
print(f"Header: {header} (0x{header:08X})")

# The first 94K is parsed during VM init
# Sequentially read varints to understand the structure
print(f"\nFirst 100 varints from offset 4:")
r.pos = 4
varints = []
for i in range(100):
    pos_before = r.pos
    v = r.varint()
    varints.append((pos_before, v))

for i, (pos, v) in enumerate(varints[:50]):
    print(f"  [{i:3d}] offset={pos:6d}: varint={v:6d}")

# Now parse the SCRIPT DATA section (offset 94736+)
print(f"\n=== Parsing script data section ===")
r = BufferReader(data, 94736)

# r[54]() reads a sub-buffer: varint length + raw bytes
# From force_read_strings.py: r[54]() consumed 37 bytes at offset 94736
# First byte at 94736 is 0x24=36, so varint=36, then 36 bytes of data
sub_buf = r.sub_buffer()
print(f"Sub-buffer: {len(sub_buf)} bytes at offset 94736")
print(f"  hex: {sub_buf.hex()}")

# Parse sub-buffer as f64 values
n_floats = len(sub_buf) // 8
print(f"  As {n_floats} doubles:")
for i in range(n_floats):
    v = struct.unpack_from('<d', sub_buf, i*8)[0]
    print(f"    float[{i}] = {v}")
remaining = len(sub_buf) - n_floats * 8
if remaining:
    print(f"  Remaining {remaining} bytes: {sub_buf[n_floats*8:].hex()}")

# Continue after sub-buffer
print(f"\nOffset after sub-buffer: {r.pos}")

# Now read sequential varints to understand the rest of the structure
print(f"\nFirst 200 varints after sub-buffer:")
varints2 = []
for i in range(200):
    if r.pos >= len(data):
        break
    pos_before = r.pos
    v = r.varint()
    varints2.append((pos_before, v))

for i, (pos, v) in enumerate(varints2[:80]):
    print(f"  [{i:3d}] offset={pos:7d}: varint={v:8d}")

# Look for structure: if this is a constant pool, we'd see:
# count, then for each: type_tag, value
# Strings would have: type=3 (or similar), length, then raw bytes

# Let me try interpreting the varints as a structured format
# Common Luraph constant pool format:
# varint num_constants
# for each:
#   varint type (0=nil, 1=bool, 2=number, 3=string)
#   if type==2: f64 value
#   if type==3: varint length, then raw bytes

print(f"\n=== Attempting structured parse of constant pool ===")
r.pos = 94736 + 37  # after sub-buffer

# First varint might be a count
count_or_type = r.varint()
print(f"First varint after sub-buffer: {count_or_type}")

# Try reading as count of items
r.pos = 94736 + 37
first_v = r.varint()
print(f"\nTrying count={first_v}...")
if first_v < 10000:
    # Reasonable count, try reading that many items
    items = []
    for i in range(min(first_v, 50)):
        pos0 = r.pos
        try:
            type_tag = r.varint()
            if type_tag == 0:
                items.append(('nil', None, pos0))
            elif type_tag == 1:
                val = r.varint()
                items.append(('bool', bool(val), pos0))
            elif type_tag == 2:
                val = r.readf64()
                items.append(('number', val, pos0))
            elif type_tag == 3:
                slen = r.varint()
                sdata = r.read_bytes(slen)
                items.append(('string', sdata, pos0))
            else:
                items.append(('unknown', type_tag, pos0))
        except Exception as e:
            print(f"  Error at item {i}, offset {r.pos}: {e}")
            break
    
    print(f"Parsed {len(items)} items:")
    for i, (typ, val, pos) in enumerate(items[:30]):
        if typ == 'string':
            try:
                s = val.decode('ascii')
                printable = all(32 <= ord(c) < 127 for c in s)
            except:
                printable = False
                s = val.hex()
            print(f"  [{i:3d}] offset={pos:7d} {typ}: {repr(s[:60])} (len={len(val)}, printable={printable})")
        elif typ == 'number':
            print(f"  [{i:3d}] offset={pos:7d} {typ}: {val}")
        else:
            print(f"  [{i:3d}] offset={pos:7d} {typ}: {val}")

# Also try starting directly with type tags (no count prefix)
print(f"\n=== Alternative: no count, direct type-tag pairs ===")
r.pos = 94736 + 37
items2 = []
for i in range(100):
    pos0 = r.pos
    if r.pos >= len(data) - 8:
        break
    v = r.varint()
    items2.append((pos0, v))

print(f"Values:")
for i, (pos, v) in enumerate(items2[:60]):
    print(f"  [{i:3d}] offset={pos:7d}: {v:8d}  (0x{v:04X})")

# Save key data
with open('varint_parse.json', 'w') as f:
    json.dump({
        'sub_buffer_len': len(sub_buf),
        'sub_buffer_hex': sub_buf.hex(),
        'first_varints_after_sub': [(p, v) for p, v in varints2[:100]],
    }, f, indent=2)
print(f"\nSaved to varint_parse.json")
