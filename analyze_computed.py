import json
from collections import Counter

protos = json.load(open('all_protos_data.json'))
opmap = json.load(open('opcode_map_final.json'))
dispatch = json.load(open('opcode_dispatch_map.json'))
hc = dispatch['handler_code']

comp_ops = {int(k): v for k, v in opmap.items() if v.get('lua51') == 'COMPUTED'}
print("=== COMPUTED opcodes ===")
for op in sorted(comp_ops.keys()):
    freq = comp_ops[op]['freq']
    handler = hc.get(str(op), '?')[:600]
    print(f"\nOp {op} ({freq}x):")
    print(f"  HANDLER: {handler}")
    
    has_q = 0
    no_q = 0
    d_valid = 0
    a_valid = 0
    z_valid = 0
    total = 0
    for p in protos:
        c4 = p.get('C4', [])
        c2 = p.get('C2_sparse', {})
        nreg = p.get('C10', 0)
        for i, o in enumerate(c4):
            if o == op:
                total += 1
                D = p['C7'][i] if i < len(p.get('C7',[])) else -1
                a = p['C8'][i] if i < len(p.get('C8',[])) else -1
                Z = p['C9'][i] if i < len(p.get('C9',[])) else -1
                if c2.get(str(i+1)): has_q += 1
                else: no_q += 1
                if 0 <= D < nreg: d_valid += 1
                if 0 <= a < nreg: a_valid += 1
                if 0 <= Z < nreg: z_valid += 1
    print(f"  Stats: total={total} q={has_q}/{total} D_reg={d_valid}/{total} a_reg={a_valid}/{total} Z_reg={z_valid}/{total}")

    samples = []
    for p in protos:
        c4 = p.get('C4', [])
        c7, c8, c9 = p.get('C7', []), p.get('C8', []), p.get('C9', [])
        c2 = p.get('C2_sparse', {})
        c11 = p.get('C11_sparse', {})
        nreg = p.get('C10', 0)
        for i, o in enumerate(c4):
            if o == op and len(samples) < 3:
                D = c7[i] if i < len(c7) else -1
                a = c8[i] if i < len(c8) else -1
                Z = c9[i] if i < len(c9) else -1
                q = c2.get(str(i+1), '')
                m = c11.get(str(i+1), '')
                next_op = c4[i+1] if i+1 < len(c4) else -1
                next_cat = opmap.get(str(next_op), {}).get('lua51', '?')
                prev_op = c4[i-1] if i > 0 else -1
                prev_cat = opmap.get(str(prev_op), {}).get('lua51', '?')
                samples.append(f"  D={D:>4} a={a:>3} Z={Z:>4} q={str(q):>10} nreg={nreg} prev={prev_cat} next={next_cat}")
    for s in samples:
        print(s)

print("\n\n=== What follows COMPUTED? ===")
next_cats = Counter()
for p in protos:
    c4 = p.get('C4', [])
    for i, o in enumerate(c4):
        if opmap.get(str(o), {}).get('lua51') == 'COMPUTED':
            if i + 1 < len(c4):
                next_op = c4[i + 1]
                next_cats[opmap.get(str(next_op), {}).get('lua51', '?')] += 1
for cat, cnt in next_cats.most_common(20):
    print(f"  {cat}: {cnt}")
