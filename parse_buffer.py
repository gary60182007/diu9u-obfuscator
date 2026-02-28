import struct, json, os
from collections import Counter

buf_path = r'unobfuscator\cracked script\buffer_1_1064652.bin'
with open(buf_path, 'rb') as f:
    data = f.read()

print(f"Buffer size: {len(data)} bytes")

# Type tags identified from VM buffer read operations:
# 0x73 = u8 (1 byte unsigned)
# 0x9E = string (1 byte length + N bytes data)
# 0x1D = u16 (2 bytes LE unsigned)
# 0xD8 = i16 (2 bytes LE signed)
# 0x57 = i32 (4 bytes LE signed)
TAG_U8 = 0x73
TAG_STR = 0x9E
TAG_U16 = 0x1D
TAG_I16 = 0xD8
TAG_I32 = 0x57

KNOWN_TAGS = {TAG_U8, TAG_STR, TAG_U16, TAG_I16, TAG_I32}

class BufferParser:
    def __init__(self, data):
        self.data = data
        self.pos = 0
        self.values = []
        self.errors = []
        self.tag_counts = Counter()
        self.strings = []
        
    def read_u8(self):
        if self.pos >= len(self.data):
            return None
        v = self.data[self.pos]
        self.pos += 1
        return v
    
    def read_u16(self):
        if self.pos + 2 > len(self.data):
            return None
        v = struct.unpack_from('<H', self.data, self.pos)[0]
        self.pos += 2
        return v
    
    def read_i16(self):
        if self.pos + 2 > len(self.data):
            return None
        v = struct.unpack_from('<h', self.data, self.pos)[0]
        self.pos += 2
        return v
    
    def read_i32(self):
        if self.pos + 4 > len(self.data):
            return None
        v = struct.unpack_from('<i', self.data, self.pos)[0]
        self.pos += 4
        return v
    
    def read_string(self):
        length = self.read_u8()
        if length is None:
            return None
        if self.pos + length > len(self.data):
            return None
        raw = self.data[self.pos:self.pos + length]
        self.pos += length
        return raw
    
    def parse(self, max_values=500000):
        # Read 4-byte header first
        if len(self.data) < 4:
            return
        header = struct.unpack_from('<I', self.data, 0)[0]
        self.pos = 4
        print(f"Header value: {header} (0x{header:08X})")
        
        count = 0
        while self.pos < len(self.data) and count < max_values:
            tag_pos = self.pos
            tag = self.read_u8()
            if tag is None:
                break
                
            if tag == TAG_U8:
                v = self.read_u8()
                if v is not None:
                    self.values.append(('u8', v, tag_pos))
                    self.tag_counts['u8'] += 1
            elif tag == TAG_STR:
                raw = self.read_string()
                if raw is not None:
                    self.values.append(('str', raw, tag_pos))
                    self.tag_counts['str'] += 1
                    self.strings.append((raw, tag_pos))
            elif tag == TAG_U16:
                v = self.read_u16()
                if v is not None:
                    self.values.append(('u16', v, tag_pos))
                    self.tag_counts['u16'] += 1
            elif tag == TAG_I16:
                v = self.read_i16()
                if v is not None:
                    self.values.append(('i16', v, tag_pos))
                    self.tag_counts['i16'] += 1
            elif tag == TAG_I32:
                v = self.read_i32()
                if v is not None:
                    self.values.append(('i32', v, tag_pos))
                    self.tag_counts['i32'] += 1
            else:
                # Unknown tag - this means our format understanding is wrong
                # or there's additional tag types
                self.errors.append((tag_pos, tag))
                if len(self.errors) <= 5:
                    print(f"  Unknown tag 0x{tag:02X} at position {tag_pos}")
                if len(self.errors) > 100:
                    print(f"  Too many unknown tags, stopping at pos {tag_pos}")
                    break
                    
            count += 1
        
        return count

parser = BufferParser(data)
total = parser.parse()

print(f"\nParsed {total} values, stopped at position {parser.pos}/{len(data)}")
print(f"Tag counts: {dict(parser.tag_counts)}")
print(f"Unknown tags: {len(parser.errors)}")

if parser.errors:
    # Show error distribution
    error_tags = Counter(tag for _, tag in parser.errors)
    print(f"Unknown tag distribution: {dict(error_tags)}")
    print(f"First few unknown tag positions: {[(pos, f'0x{tag:02x}') for pos, tag in parser.errors[:10]]}")

# Analyze strings
print(f"\nTotal strings read: {len(parser.strings)}")
printable_strings = []
binary_strings = []

for raw, pos in parser.strings:
    try:
        s = raw.decode('ascii')
        is_print = all(32 <= ord(c) < 127 or c in '\t\n\r' for c in s)
        if is_print:
            printable_strings.append((s, pos))
        else:
            binary_strings.append((raw, pos))
    except (UnicodeDecodeError, ValueError):
        binary_strings.append((raw, pos))

print(f"Printable strings: {len(printable_strings)}")
print(f"Binary/encoded strings: {len(binary_strings)}")

print(f"\nAll printable strings:")
for s, pos in printable_strings:
    print(f"  pos={pos:7d}: {repr(s)[:100]}")

# Try to decode binary strings with various XOR keys
print(f"\nTrying to decode binary strings...")
for xor_key in range(256):
    decoded_count = 0
    for raw, pos in binary_strings:
        decoded = bytes(b ^ xor_key for b in raw)
        try:
            s = decoded.decode('ascii')
            if all(32 <= ord(c) < 127 or c in '\t\n\r' for c in s):
                decoded_count += 1
        except (UnicodeDecodeError, ValueError):
            pass
    if decoded_count > 5:
        print(f"  XOR key 0x{xor_key:02X}: {decoded_count} strings decoded")

# Show value sequence patterns (first 100 values)
print(f"\nFirst 100 parsed values:")
for i, (typ, val, pos) in enumerate(parser.values[:100]):
    if typ == 'str':
        try:
            s = val.decode('ascii', errors='replace')
        except:
            s = val.hex()
        print(f"  [{i:4d}] pos={pos:6d} {typ:4s}: {repr(s)[:60]}")
    else:
        print(f"  [{i:4d}] pos={pos:6d} {typ:4s}: {val}")

# Save full parse results
hdr = struct.unpack_from('<I', data, 0)[0]
result = {
    'header': hdr,
    'total_values': total,
    'parse_end_pos': parser.pos,
    'tag_counts': dict(parser.tag_counts),
    'unknown_tag_count': len(parser.errors),
    'printable_strings': [(s, pos) for s, pos in printable_strings],
    'binary_string_count': len(binary_strings),
}
with open('buffer_parse_result.json', 'w', encoding='utf-8') as f:
    json.dump(result, f, indent=2, ensure_ascii=False)
print(f"\nSaved parse results to buffer_parse_result.json")
