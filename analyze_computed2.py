import json
from collections import Counter

protos = json.load(open('all_protos_data.json'))
opmap = json.load(open('opcode_map_final.json'))
dispatch = json.load(open('opcode_dispatch_map.json'))
hc = dispatch['handler_code']

comp_ops = {int(k): v for k, v in opmap.items() if v.get('lua51') == 'COMPUTED'}
top_ops = sorted(comp_ops.keys(), key=lambda x: -comp_ops[x]['freq'])[:6]

for op in top_ops:
    freq = comp_ops[op]['freq']
    handler = hc.get(str(op), '?')[:200]
    
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
                if c2.get(str(i+1)): has_q += 1
                else: no_q += 1
                if 0 <= D < nreg: d_valid += 1
                if 0 <= a < nreg: a_valid += 1
    
    print(f"Op {op} ({freq}x): q={has_q}/{total} D_reg={d_valid}/{total} a_reg={a_valid}/{total}")
    print(f"  Handler start: {handler[:100]}")
    
    samples = []
    for p in protos:
        c4 = p.get('C4', [])
        c7, c8, c9 = p.get('C7', []), p.get('C8', []), p.get('C9', [])
        c2 = p.get('C2_sparse', {})
        nreg = p.get('C10', 0)
        ninst = len(c4)
        for i, o in enumerate(c4):
            if o == op and len(samples) < 5:
                D = c7[i] if i < len(c7) else -1
                a = c8[i] if i < len(c8) else -1
                Z = c9[i] if i < len(c9) else -1
                q = c2.get(str(i+1), '')
                next_ops = []
                for j in range(1, 4):
                    if i+j < len(c4):
                        nop = c4[i+j]
                        ncat = opmap.get(str(nop), {}).get('lua51', '?')
                        next_ops.append(f"{ncat}")
                prev_op = c4[i-1] if i > 0 else -1
                prev_cat = opmap.get(str(prev_op), {}).get('lua51', '?')
                samples.append(f"  D={D:>4}{'*' if 0<=D<nreg else ' '} a={a:>3}{'*' if 0<=a<nreg else ' '} Z={Z:>4} q={str(q):>12} nreg={nreg} [{prev_cat} -> {' -> '.join(next_ops)}]")
    for s in samples:
        print(s)
    print()
