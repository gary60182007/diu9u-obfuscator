"""
Standalone Python parser for Luraph v14.7 bytecode constant table.

Parses the binary buffer to extract all constants (strings, numbers, booleans)
used by the obfuscated Lua VM.

Tag format specification (empirically determined):
  Tag 29  (0x1d): u16le number      (3 bytes)
  Tag 54  (0x36): negative u8       (2 bytes)
  Tag 87  (0x57): i32le number      (5 bytes)
  Tag 100 (0x64): boolean false     (1 byte)
  Tag 115 (0x73): u8 number         (2 bytes)
  Tag 140 (0x8c): f32le number      (5 bytes)
  Tag 158 (0x9e): byte_len + string (variable)
  Tag 161 (0xa1): i64le number      (9 bytes)
  Tag 202 (0xca): u32le number      (5 bytes)
  Tag 216 (0xd8): i16le number      (3 bytes)
  Tag 217 (0xd9): boolean true      (1 byte)

Buffer layout:
  [varint: count + 36578]
  [u8: has_hash flag]
  [entries × count]
  [varint: post_constants - 83963]
"""

import struct
import json
import sys


HEADER_OFFSET = 36578
POST_CONSTANTS_OFFSET = 83963

TAG_U16LE = 29
TAG_NEG_U8 = 54
TAG_I32LE = 87
TAG_BOOL_FALSE = 100
TAG_U8 = 115
TAG_F32LE = 140
TAG_STRING = 158
TAG_I64LE = 161
TAG_U32LE = 202
TAG_I16LE = 216
TAG_BOOL_TRUE = 217


def read_varint(buf, pos):
    result = 0
    shift = 0
    while True:
        b = buf[pos]
        pos += 1
        result |= (b & 0x7F) << shift
        shift += 7
        if b < 128:
            break
    return result, pos


def parse_constant_table(buf, offset=0):
    pos = offset

    header_val, pos = read_varint(buf, pos)
    count = header_val - HEADER_OFFSET

    has_hash = buf[pos] != 0
    pos += 1

    constants = []
    for i in range(count):
        tag = buf[pos]
        pos += 1

        if tag == TAG_BOOL_FALSE:
            constants.append({'type': 'boolean', 'value': False})
        elif tag == TAG_BOOL_TRUE:
            constants.append({'type': 'boolean', 'value': True})
        elif tag == TAG_U8:
            val = buf[pos]
            pos += 1
            constants.append({'type': 'number', 'value': val})
        elif tag == TAG_NEG_U8:
            val = -buf[pos]
            pos += 1
            constants.append({'type': 'number', 'value': val})
        elif tag == TAG_U16LE:
            val = struct.unpack_from('<H', buf, pos)[0]
            pos += 2
            constants.append({'type': 'number', 'value': val})
        elif tag == TAG_I16LE:
            val = struct.unpack_from('<h', buf, pos)[0]
            pos += 2
            constants.append({'type': 'number', 'value': val})
        elif tag == TAG_I32LE:
            val = struct.unpack_from('<i', buf, pos)[0]
            pos += 4
            constants.append({'type': 'number', 'value': val})
        elif tag == TAG_U32LE:
            val = struct.unpack_from('<I', buf, pos)[0]
            pos += 4
            constants.append({'type': 'number', 'value': val})
        elif tag == TAG_F32LE:
            val = struct.unpack_from('<f', buf, pos)[0]
            pos += 4
            constants.append({'type': 'number', 'value': val})
        elif tag == TAG_I64LE:
            val = struct.unpack_from('<q', buf, pos)[0]
            pos += 8
            constants.append({'type': 'number', 'value': val})
        elif tag == TAG_STRING:
            slen = buf[pos]
            pos += 1
            data = buf[pos:pos + slen]
            pos += slen
            constants.append({
                'type': 'string',
                'value': data,
                'length': slen,
            })
        else:
            raise ValueError(
                f"Unknown tag {tag} (0x{tag:02x}) at buffer offset {pos - 1}, "
                f"entry index {i + 1}"
            )

    post_val, pos = read_varint(buf, pos)
    post_val -= POST_CONSTANTS_OFFSET

    return {
        'count': count,
        'has_hash': has_hash,
        'constants': constants,
        'post_constants_value': post_val,
        'end_offset': pos,
    }


def constants_to_json(result, output_path=None):
    entries = {}
    for i, c in enumerate(result['constants'], 1):
        entry = {'type': c['type']}
        if c['type'] == 'string':
            raw = c['value']
            entry['hex'] = raw.hex()
            entry['length'] = c['length']
            try:
                entry['text'] = raw.decode('utf-8')
            except UnicodeDecodeError:
                entry['text'] = raw.decode('utf-8', errors='replace')
                entry['decode_error'] = True
        elif c['type'] == 'number':
            entry['value'] = c['value']
        elif c['type'] == 'boolean':
            entry['value'] = c['value']
        entries[i] = entry

    if output_path:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(entries, f, indent=2, ensure_ascii=False,
                      sort_keys=True, default=str)
    return entries


def main():
    import argparse
    parser = argparse.ArgumentParser(
        description='Parse Luraph v14.7 constant table from binary buffer'
    )
    parser.add_argument('buffer_file', help='Path to binary buffer file')
    parser.add_argument('-o', '--output', help='Output JSON file',
                        default='parsed_constants.json')
    parser.add_argument('-v', '--verify', help='Ground truth JSON to verify against')
    parser.add_argument('--offset', type=int, default=0,
                        help='Start offset in buffer')
    args = parser.parse_args()

    with open(args.buffer_file, 'rb') as f:
        buf = f.read()

    print(f"Buffer: {args.buffer_file} ({len(buf)} bytes)")

    result = parse_constant_table(buf, args.offset)
    print(f"Parsed {result['count']} constants")
    print(f"Has hash: {result['has_hash']}")
    print(f"End offset: {result['end_offset']}")
    print(f"Post-constants value: {result['post_constants_value']}")

    type_counts = {}
    for c in result['constants']:
        t = c['type']
        type_counts[t] = type_counts.get(t, 0) + 1
    print(f"Types: {type_counts}")

    entries = constants_to_json(result, args.output)
    print(f"Saved to {args.output}")

    strings = [(i, e) for i, e in entries.items() if e['type'] == 'string']
    readable = [(i, e) for i, e in strings
                if not e.get('decode_error') and len(e['text']) > 1
                and all(c.isprintable() or c in '\n\r\t' for c in e['text'])]

    print(f"\nStrings: {len(strings)} total, {len(readable)} readable")
    for i, e in readable[:30]:
        print(f"  [{i:4d}] {e['text'][:80]}")
    if len(readable) > 30:
        print(f"  ... and {len(readable) - 30} more")

    if args.verify:
        with open(args.verify, 'r', encoding='utf-8') as f:
            gt = json.load(f)
        
        ok = 0
        fail = 0
        for k, gt_entry in gt.items():
            idx = int(k)
            if idx > len(result['constants']):
                continue
            parsed = entries.get(idx)
            if not parsed:
                continue
            
            gt_type = gt_entry['type']
            p_type = parsed['type']
            
            if gt_type in ('s', 'ts') and p_type == 'string':
                gt_hex = gt_entry.get('raw', gt_entry.get('hex', ''))
                p_hex = parsed.get('hex', '')
                if gt_hex == p_hex:
                    ok += 1
                else:
                    fail += 1
                    if fail <= 10:
                        print(f"  STRING MISMATCH [{idx}]: "
                              f"parsed={p_hex[:20]} gt={gt_hex[:20]}")
            elif gt_type in ('n', 'tn') and p_type == 'number':
                gt_val = gt_entry.get('val')
                p_val = parsed.get('value')
                if gt_val is not None and p_val is not None:
                    if gt_val == p_val or (isinstance(gt_val, float) and
                                           isinstance(p_val, float) and
                                           abs(gt_val - p_val) < abs(gt_val) * 1e-6):
                        ok += 1
                    else:
                        fail += 1
                        if fail <= 10:
                            print(f"  NUMBER MISMATCH [{idx}]: "
                                  f"parsed={p_val} gt={gt_val}")
                else:
                    ok += 1
            elif gt_type == 'b' and p_type == 'boolean':
                ok += 1
            else:
                fail += 1
                if fail <= 10:
                    print(f"  TYPE MISMATCH [{idx}]: parsed={p_type} gt={gt_type}")
        
        total = ok + fail
        print(f"\nVerification: {ok}/{total} correct ({100*ok/total:.1f}%)")


if __name__ == '__main__':
    main()
