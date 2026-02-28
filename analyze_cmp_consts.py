import json
from collections import Counter

protos = json.load(open('all_protos_data.json'))
opmap = json.load(open('opcode_map_final.json'))

for cat in ['LT', 'EQ', 'LE']:
    ops = {int(k): v for k, v in opmap.items() if v.get('lua51') == cat}
    print(f"\n=== {cat} opcodes ===")
    for op in sorted(ops.keys()):
        freq = ops[op]['freq']
        variant = ops[op].get('variant', '?')
        has_q = 0
        has_w = 0
        has_m = 0
        no_const = 0
        total = 0
        for p in protos:
            c4 = p.get('C4', [])
            c2 = p.get('C2_sparse', {})
            c6 = p.get('C6_sparse', {})
            c11 = p.get('C11_sparse', {})
            for i, o in enumerate(c4):
                if o == op:
                    total += 1
                    key = str(i + 1)
                    q = c2.get(key)
                    w = c6.get(key)
                    m = c11.get(key)
                    if q: has_q += 1
                    if w: has_w += 1
                    if m: has_m += 1
                    if not q and not w and not m:
                        no_const += 1
        print(f"  Op {op:>3} ({freq:>4}x) {variant:<20s} q={has_q} w={has_w} m={has_m} none={no_const}")
