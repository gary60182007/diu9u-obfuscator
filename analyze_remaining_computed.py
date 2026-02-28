import json
from collections import Counter

protos = json.load(open('all_protos_data.json'))
opmap = json.load(open('opcode_map_final.json'))

comp_ops = {int(k): v for k, v in opmap.items() if v.get('lua51') == 'COMPUTED'}
print(f"Remaining COMPUTED: {len(comp_ops)} opcodes, {sum(v['freq'] for v in comp_ops.values())} total instances")

for op in sorted(comp_ops.keys(), key=lambda x: -comp_ops[x]['freq']):
    freq = comp_ops[op]['freq']
    has_q = 0
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
                D = p['C7'][i] if i < len(p.get('C7', [])) else -1
                a = p['C8'][i] if i < len(p.get('C8', [])) else -1
                Z = p['C9'][i] if i < len(p.get('C9', [])) else -1
                if c2.get(str(i + 1)): has_q += 1
                if 0 <= D < nreg: d_valid += 1
                if 0 <= a < nreg: a_valid += 1
                if 0 <= Z < nreg: z_valid += 1
    print(f"  Op {op:>3} ({freq:>3}x): q={has_q}/{total} D={d_valid}/{total} a={a_valid}/{total} Z={z_valid}/{total}")
