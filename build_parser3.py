"""
Analyze ZF trace data against buffer bytes to determine exact encoding per tag.
Then build and verify the complete parser.
"""
import struct, json

with open('zf_trace.json', 'r') as f:
    trace = json.load(f)

with open(r'unobfuscator\cracked script\buffer_1_1064652.bin', 'rb') as f:
    buf = f.read()

# Group entries by tag
tag_groups = {}
for e in trace:
    tag = buf[e['start']]
    if tag not in tag_groups:
        tag_groups[tag] = []
    tag_groups[tag].append(e)

# Analyze each tag type
print("=== Tag encoding analysis ===\n")

for tag in sorted(tag_groups.keys()):
    entries = tag_groups[tag]
    e0 = entries[0]
    size = e0['end'] - e0['start']
    typ = e0['type']
    print(f"--- Tag {tag} (0x{tag:02x}), {typ}, {size}B, {len(entries)} entries ---")
    
    if typ == 'boolean':
        print(f"  Boolean: tag byte only, no data bytes")
        for e in entries[:5]:
            print(f"    [{e['index']}] val={e.get('val', '?')}")
        continue
    
    if typ == 'number':
        data_bytes = size - 1  # subtract tag byte
        
        # Try different decodings
        for e in entries[:10]:
            raw = buf[e['start']+1:e['end']]  # skip tag byte
            gt_val = e.get('val', None)
            
            decodings = {}
            if data_bytes == 1:
                decodings['u8'] = raw[0]
                decodings['i8'] = struct.unpack('b', raw)[0]
            elif data_bytes == 2:
                decodings['u16le'] = struct.unpack('<H', raw)[0]
                decodings['i16le'] = struct.unpack('<h', raw)[0]
                decodings['u16be'] = struct.unpack('>H', raw)[0]
                decodings['i16be'] = struct.unpack('>h', raw)[0]
            elif data_bytes == 4:
                decodings['u32le'] = struct.unpack('<I', raw)[0]
                decodings['i32le'] = struct.unpack('<i', raw)[0]
                decodings['f32le'] = struct.unpack('<f', raw)[0]
            elif data_bytes == 8:
                decodings['f64le'] = struct.unpack('<d', raw)[0]
                decodings['f64be'] = struct.unpack('>d', raw)[0]
                decodings['i64le'] = struct.unpack('<q', raw)[0]
                decodings['u64le'] = struct.unpack('<Q', raw)[0]
            
            matches = [name for name, val in decodings.items() if val == gt_val]
            
            print(f"    [{e['index']:4d}] raw={raw.hex()} gt={gt_val} matches={matches}")
            if not matches and gt_val is not None:
                # Try with transformations
                for name, val in decodings.items():
                    if val is not None:
                        diff = gt_val - val
                        if abs(diff) < 100000:
                            print(f"           {name}={val} diff={diff}")
        
        # Determine the correct decoding
        correct = None
        for e in entries:
            raw = buf[e['start']+1:e['end']]
            gt_val = e.get('val')
            if gt_val is None:
                continue
            
            if data_bytes == 1:
                if raw[0] == gt_val:
                    correct = 'u8'
                elif struct.unpack('b', raw)[0] == gt_val:
                    correct = 'i8'
            elif data_bytes == 2:
                if struct.unpack('<H', raw)[0] == gt_val:
                    correct = 'u16le'
                elif struct.unpack('<h', raw)[0] == gt_val:
                    correct = 'i16le'
            elif data_bytes == 4:
                if struct.unpack('<I', raw)[0] == gt_val:
                    correct = 'u32le'
                elif struct.unpack('<i', raw)[0] == gt_val:
                    correct = 'i32le'
                elif struct.unpack('<f', raw)[0] == gt_val:
                    correct = 'f32le'
            elif data_bytes == 8:
                if struct.unpack('<d', raw)[0] == gt_val:
                    correct = 'f64le'
            
            if correct:
                break
        
        if correct:
            print(f"  => Encoding: {correct}")
            # Verify all entries
            ok = 0
            fail = 0
            for e in entries:
                raw = buf[e['start']+1:e['end']]
                gt_val = e.get('val')
                if gt_val is None:
                    continue
                if correct == 'u8': parsed = raw[0]
                elif correct == 'i8': parsed = struct.unpack('b', raw)[0]
                elif correct == 'u16le': parsed = struct.unpack('<H', raw)[0]
                elif correct == 'i16le': parsed = struct.unpack('<h', raw)[0]
                elif correct == 'u32le': parsed = struct.unpack('<I', raw)[0]
                elif correct == 'i32le': parsed = struct.unpack('<i', raw)[0]
                elif correct == 'f32le': parsed = struct.unpack('<f', raw)[0]
                elif correct == 'f64le': parsed = struct.unpack('<d', raw)[0]
                else: parsed = None
                
                if parsed == gt_val:
                    ok += 1
                else:
                    fail += 1
                    if fail <= 5:
                        print(f"    MISMATCH [{e['index']}]: parsed={parsed} gt={gt_val}")
            print(f"  Verified: {ok} ok, {fail} fail")
        else:
            print(f"  => Could not determine encoding!")
            # Show more detail for debugging
            for e in entries[:5]:
                raw = buf[e['start']+1:e['end']]
                gt_val = e.get('val')
                print(f"    [{e['index']}] raw={raw.hex()} gt={gt_val}")
                if data_bytes == 2:
                    u16 = struct.unpack('<H', raw)[0]
                    i16 = struct.unpack('<h', raw)[0]
                    # Try transformations
                    for transform_name, transform in [
                        ('u16le-32768', u16 - 32768),
                        ('i16le+offset', None),
                        ('(raw[1]<<8|raw[0])', (raw[1] << 8) | raw[0]),
                        ('(raw[0]<<8|raw[1])', (raw[0] << 8) | raw[1]),
                        ('signed_custom', struct.unpack('<h', raw)[0]),
                    ]:
                        if transform == gt_val:
                            print(f"      MATCH: {transform_name}")
    
    elif typ == 'string':
        # String entries: tag + length_encoding + data
        print(f"  String analysis:")
        for e in entries[:15]:
            raw = buf[e['start']:e['end']]
            gt_len = e.get('len', 0)
            gt_hex = e.get('hex', '')
            total_size = len(raw)
            data_size = total_size - 1  # minus tag
            
            # The data after tag should encode: length + string_bytes
            # Or: string_bytes directly (if length is encoded in tag)
            # Since tag is always 158, length must be in the data
            
            after_tag = raw[1:]
            
            # Try: first byte is length
            if len(after_tag) > 0 and after_tag[0] == gt_len:
                str_data = after_tag[1:1+gt_len]
                if str_data.hex().startswith(gt_hex[:len(str_data.hex())]):
                    print(f"    [{e['index']:4d}] len={gt_len} size={total_size} "
                          f"encoding=byte_len+data "
                          f"text={repr(str_data.decode('utf-8','replace')[:30])}")
                    continue
            
            # Try: varint length
            vpos = e['start'] + 1
            vlen = 0
            shift = 0
            while vpos < e['end']:
                b = buf[vpos]; vpos += 1
                vlen |= (b & 0x7F) << shift
                shift += 7
                if b < 128: break
            
            str_data = buf[vpos:vpos+vlen]
            if vlen == gt_len:
                print(f"    [{e['index']:4d}] len={gt_len} size={total_size} "
                      f"encoding=varint_len+data "
                      f"text={repr(str_data.decode('utf-8','replace')[:30])}")
            else:
                # Just show the raw bytes
                print(f"    [{e['index']:4d}] len={gt_len} size={total_size} "
                      f"raw={raw[:20].hex()} gt_hex={gt_hex[:20]}")
    
    print()

# Now build the parser
print("\n" + "="*70)
print("BUILDING PARSER")
print("="*70)

def read_varint(buf, pos):
    result = 0; shift = 0
    while True:
        b = buf[pos]; pos += 1
        result |= (b & 0x7F) << shift
        shift += 7
        if b < 128: break
    return result, pos

def parse_constants(buf):
    pos = 0
    header, pos = read_varint(buf, pos)
    count = header - 36578
    
    bool_byte = buf[pos]; pos += 1
    has_hash = bool_byte != 0
    
    constants = []
    for i in range(count):
        tag = buf[pos]; pos += 1
        
        if tag == 100:  # boolean false?
            constants.append({'type': 'boolean', 'val': False, 'tag': tag})
        elif tag == 217:  # boolean true?
            constants.append({'type': 'boolean', 'val': True, 'tag': tag})
        elif tag == 115:  # u8 number
            val = buf[pos]; pos += 1
            constants.append({'type': 'number', 'val': val, 'tag': tag})
        elif tag == 54:  # u8 number (different tag, same format?)
            val = buf[pos]; pos += 1
            constants.append({'type': 'number', 'val': val, 'tag': tag})
        elif tag == 29:  # 2-byte number
            raw = buf[pos:pos+2]; pos += 2
            # Need to determine encoding - check analysis above
            val = struct.unpack('<H', raw)[0]  # tentative
            constants.append({'type': 'number', 'val': val, 'tag': tag, 'raw': raw.hex()})
        elif tag == 216:  # 2-byte number
            raw = buf[pos:pos+2]; pos += 2
            val = struct.unpack('<H', raw)[0]  # tentative
            constants.append({'type': 'number', 'val': val, 'tag': tag, 'raw': raw.hex()})
        elif tag in (87, 140, 202):  # 4-byte number
            raw = buf[pos:pos+4]; pos += 4
            val = struct.unpack('<i', raw)[0]  # tentative
            constants.append({'type': 'number', 'val': val, 'tag': tag, 'raw': raw.hex()})
        elif tag == 161:  # 8-byte number (f64)
            raw = buf[pos:pos+8]; pos += 8
            val = struct.unpack('<d', raw)[0]
            constants.append({'type': 'number', 'val': val, 'tag': tag})
        elif tag == 158:  # string
            # Read length then data
            slen = buf[pos]; pos += 1  # tentative: 1 byte length
            data = buf[pos:pos+slen]; pos += slen
            constants.append({'type': 'string', 'val': data, 'tag': tag, 'len': slen})
        else:
            constants.append({'type': 'unknown', 'tag': tag})
            print(f"  WARNING: unknown tag {tag} at pos {pos-1}")
    
    return constants, pos

# Test the parser
parsed, end_pos = parse_constants(buf)
print(f"Parsed {len(parsed)} constants, end pos = {end_pos}")

# Compare with trace
correct = 0
wrong = 0
for i, (p, t) in enumerate(zip(parsed, trace)):
    tag = buf[t['start']]
    expected_type = t['type']
    
    if expected_type == 'number':
        gt_val = t.get('val')
        if gt_val is not None and p.get('val') == gt_val:
            correct += 1
        else:
            wrong += 1
            if wrong <= 20:
                print(f"  WRONG [{i+1}] tag={tag} parsed={p.get('val')} gt={gt_val} raw={p.get('raw','')}")
    elif expected_type == 'string':
        gt_len = t.get('len')
        if gt_len is not None and p.get('len') == gt_len:
            correct += 1
        else:
            wrong += 1
            if wrong <= 20:
                print(f"  WRONG [{i+1}] tag={tag} parsed_len={p.get('len')} gt_len={gt_len}")
    elif expected_type == 'boolean':
        correct += 1  # booleans are simple

print(f"\nParser accuracy: {correct}/{correct+wrong} ({100*correct/(correct+wrong):.1f}%)")
print(f"Expected end offset: {trace[-1]['end']}, parsed end: {end_pos}")
