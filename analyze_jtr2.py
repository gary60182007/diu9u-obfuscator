import json
from collections import Counter

protos = json.load(open('all_protos_data.json'))
opmap = json.load(open('opcode_map_final.json'))
dispatch = json.load(open('opcode_dispatch_map.json'))
hc = dispatch['handler_code']

jtr_ops = {int(k): v for k, v in opmap.items() if v.get('lua51') == 'JMP_TEST_RETURN'}
print(f"JMP_TEST_RETURN: {len(jtr_ops)} opcodes, {sum(v['freq'] for v in jtr_ops.values())} instances")

for op in sorted(jtr_ops.keys(), key=lambda x: -jtr_ops[x]['freq']):
    freq = jtr_ops[op]['freq']
    handler = hc.get(str(op), '?')[:300]
    
    d_valid = 0
    a_jmp = 0
    z_reg = 0
    total = 0
    for p in protos:
        c4 = p.get('C4', [])
        nreg = p.get('C10', 0)
        ninst = len(c4)
        for i, o in enumerate(c4):
            if o == op:
                total += 1
                D = p['C7'][i] if i < len(p.get('C7', [])) else -1
                a = p['C8'][i] if i < len(p.get('C8', [])) else -1
                Z = p['C9'][i] if i < len(p.get('C9', [])) else -1
                if 0 <= D < nreg: d_valid += 1
                if 0 <= a < ninst: a_jmp += 1
                if 0 <= Z < nreg: z_reg += 1
    
    print(f"\nOp {op} ({freq}x): D_reg={d_valid}/{total} a_jmp={a_jmp}/{total} Z_reg={z_reg}/{total}")
    print(f"  Handler: {handler[:200]}")
    
    samples = []
    for p in protos:
        c4 = p.get('C4', [])
        c7, c8, c9 = p.get('C7', []), p.get('C8', []), p.get('C9', [])
        nreg = p.get('C10', 0)
        ninst = len(c4)
        for i, o in enumerate(c4):
            if o == op and len(samples) < 3:
                D = c7[i] if i < len(c7) else -1
                a = c8[i] if i < len(c8) else -1
                Z = c9[i] if i < len(c9) else -1
                next_op = c4[i+1] if i+1 < len(c4) else -1
                next_cat = opmap.get(str(next_op), {}).get('lua51', '?')
                samples.append(f"  D={D:>4}{'*' if 0<=D<nreg else ' '} a={a:>3}{'j' if 0<=a<ninst else ' '} Z={Z:>3}{'*' if 0<=Z<nreg else ' '} nreg={nreg} next={next_cat}")
    for s in samples:
        print(s)
