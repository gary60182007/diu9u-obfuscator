"""
Parse the Luraph v14.7 buffer entry by entry.
Tag 0x73 (115) = 2 bytes: tag + u8 number.
Need to discover other tag formats by comparing with ground truth.
"""
import struct, json

with open('luraph_strings_full.json', 'r', encoding='utf-8') as f:
    ground_truth = json.load(f)

with open(r'unobfuscator\cracked script\buffer_1_1064652.bin', 'rb') as f:
    buf = f.read()

def read_varint(buf, pos):
    result = 0
    shift = 0
    while True:
        b = buf[pos]; pos += 1
        result |= (b & 0x7F) << shift
        shift += 7
        if b < 128: break
    return result, pos

# Header
pos = 0
header_v, pos = read_varint(buf, pos)
count = header_v - 36578
print(f"Count: {count}, pos after header varint: {pos}")

bool_byte = buf[pos]; pos += 1
has_hash = bool_byte != 0
print(f"Has hash: {has_hash}")
print(f"Constants start at offset: {pos}")

# Parse each entry
entries = {}
errors = []
tag_type_map = {}

for i in range(1, count + 1):
    gt = ground_truth.get(str(i))
    tag = buf[pos]
    start_pos = pos
    pos += 1
    
    if tag <= 123:
        # Short constant path (RF → EF → uF)
        # tag <= 29: read via r[40] (unknown reader)
        # 30 <= tag <= 54: negative byte
        # 55 <= tag <= 123: read via r[44] (readu8)
        
        if tag >= 55:
            # Read 1 unsigned byte
            val = buf[pos]; pos += 1
            entry = {'type': 'u8', 'val': val, 'tag': tag}
        elif tag >= 30:
            # Read negative byte: -r[39]()
            val = -buf[pos]; pos += 1
            entry = {'type': 'neg_u8', 'val': val, 'tag': tag}
        else:
            # tag <= 29: r[40]() - unknown format
            # Let's check ground truth to figure it out
            entry = {'type': 'r40', 'tag': tag, 'raw_next': buf[pos:pos+8].hex()}
            if gt:
                gt_type = gt['type']
                gt_val = gt.get('val', gt.get('text', '?'))
                entry['gt'] = f"{gt_type}={gt_val}"
            # Try different readers
            # Maybe r[40] is readi8 (signed byte)?
            # Or maybe it's readu16? Or varint?
            # For now, try signed byte
            if gt and gt['type'] == 'n':
                # Find what read produces the ground truth value
                u8 = buf[pos]
                i8 = struct.unpack('b', bytes([buf[pos]]))[0]
                u16le = struct.unpack('<H', buf[pos:pos+2])[0] if pos+2 <= len(buf) else None
                i16le = struct.unpack('<h', buf[pos:pos+2])[0] if pos+2 <= len(buf) else None
                entry['candidates'] = {
                    'u8': u8, 'i8': i8,
                    'u16le': u16le, 'i16le': i16le,
                }
                # Check which matches
                for name, cv in entry['candidates'].items():
                    if cv == gt['val']:
                        entry['match'] = name
                        break
            pos += 1  # tentative: assume 1 byte
    else:
        # tag > 123: BF path (strings/complex)
        # Need to figure out what BF does based on tag value
        entry = {'type': 'bf', 'tag': tag}
        
        if gt:
            gt_type = gt['type']
            if gt_type in ('s', 'ts'):
                gt_text = gt.get('text', '')
                gt_len = gt.get('len', len(gt_text))
                entry['gt_type'] = 'string'
                entry['gt_len'] = gt_len
                entry['gt_text'] = gt_text[:40]
                
                # Try to find the string in the buffer
                # Maybe tag encodes length? Or length follows?
                # tag - 124 could be the length, or length is a varint
                raw_len = tag - 124
                entry['tag_minus_124'] = raw_len
                
                # Check if raw_len matches gt_len
                if raw_len == gt_len:
                    entry['len_match'] = 'tag-124'
                    # Read raw_len bytes as string
                    raw = buf[pos:pos+raw_len]
                    entry['raw_hex'] = raw.hex()
                    pos += raw_len
                else:
                    # Maybe length is encoded differently
                    # Or tag - 128 is the length?
                    for offset in [123, 124, 125, 126, 127, 128]:
                        if tag - offset == gt_len:
                            entry['len_match'] = f'tag-{offset}'
                            break
                    
                    # Try varint length after tag
                    vlen, vpos = read_varint(buf, pos)
                    entry['varint_after_tag'] = vlen
                    if vlen == gt_len:
                        entry['len_match'] = 'varint'
                        raw = buf[vpos:vpos+vlen]
                        entry['raw_hex'] = raw.hex()[:60]
                        pos = vpos + vlen
                    else:
                        # Maybe tag byte IS part of length encoding
                        # For now, use gt_len to advance
                        entry['raw_next_16'] = buf[pos:pos+16].hex()
                        # Try: first byte after tag is string length
                        if buf[pos] == gt_len:
                            entry['len_match'] = 'next_byte'
                            pos += 1
                            raw = buf[pos:pos+gt_len]
                            entry['raw_hex'] = raw.hex()[:60]
                            pos += gt_len
                        else:
                            entry['error'] = 'cannot_determine_length'
                            # Skip using ground truth to stay aligned
                            # BF likely reads string char by char
                            entry['skip'] = True
            elif gt_type == 'n':
                entry['gt_type'] = 'number'
                entry['gt_val'] = gt.get('val')
                entry['raw_next'] = buf[pos:pos+8].hex()
            elif gt_type == 'b':
                entry['gt_type'] = 'boolean'
                entry['gt_val'] = gt.get('val')
        
    entries[i] = entry
    
    # Verify against ground truth
    if gt and 'val' in entry and gt['type'] == 'n':
        if entry['val'] != gt['val']:
            errors.append((i, entry, gt))

# Print results
print(f"\n=== Parsed {len(entries)} entries ===")

# Tag distribution
tag_dist = {}
for e in entries.values():
    tag = e.get('tag', '?')
    tag_dist[tag] = tag_dist.get(tag, 0) + 1

print(f"\nTag distribution:")
for tag in sorted(tag_dist.keys()):
    print(f"  tag={tag:3d} (0x{tag:02x}): {tag_dist[tag]} entries")

# Check accuracy for u8 entries
u8_correct = 0
u8_total = 0
for i, e in entries.items():
    if e['type'] == 'u8':
        u8_total += 1
        gt = ground_truth.get(str(i))
        if gt and gt['type'] == 'n' and e['val'] == gt['val']:
            u8_correct += 1

print(f"\nu8 entries: {u8_total}, correct: {u8_correct}")

# Show first few BF entries
print(f"\n=== BF (tag>123) entries ===")
bf_count = 0
for i in sorted(entries.keys()):
    e = entries[i]
    if e['type'] == 'bf':
        bf_count += 1
        if bf_count <= 30:
            print(f"  [{i:4d}] tag={e['tag']:3d} gt={e.get('gt_type','?')} "
                  f"gt_len={e.get('gt_len','?')} tag-124={e.get('tag_minus_124','?')} "
                  f"len_match={e.get('len_match','?')} "
                  f"text={repr(e.get('gt_text',''))[:50]}")

print(f"\nTotal BF entries: {bf_count}")

# Show tag<=29 entries
print(f"\n=== Tag <= 29 entries ===")
for i in sorted(entries.keys()):
    e = entries[i]
    if e['type'] == 'r40':
        gt = ground_truth.get(str(i))
        gt_str = f"{gt['type']}={gt.get('val', gt.get('text', '?'))}" if gt else '?'
        match = e.get('match', 'none')
        print(f"  [{i:4d}] tag={e['tag']:3d} gt={gt_str} match={match} "
              f"candidates={e.get('candidates', {})}")

# Show errors
if errors:
    print(f"\n=== Errors ({len(errors)}) ===")
    for i, e, gt in errors[:20]:
        print(f"  [{i}] parsed={e['val']} gt={gt['val']}")

# Show neg_u8 entries
print(f"\n=== Neg u8 (tag 30-54) entries ===")
neg_count = 0
for i in sorted(entries.keys()):
    e = entries[i]
    if e['type'] == 'neg_u8':
        neg_count += 1
        gt = ground_truth.get(str(i))
        gt_str = f"{gt['type']}={gt.get('val', gt.get('text', '?'))}" if gt else '?'
        if neg_count <= 15:
            print(f"  [{i:4d}] tag={e['tag']:3d} val={e['val']} gt={gt_str}")
print(f"Total neg_u8: {neg_count}")
