import json
from collections import Counter

protos = json.load(open('all_protos_data.json'))
opmap = json.load(open('opcode_map_final.json'))
dispatch = json.load(open('opcode_dispatch_map.json'))

print("=== REMAINING COMPUTED ===")
comp_ops = {}
for k, v in opmap.items():
    if v.get('lua51') == 'COMPUTED':
        comp_ops[int(k)] = v

for op in sorted(comp_ops, key=lambda x: comp_ops[x]['freq'], reverse=True):
    freq = comp_ops[op]['freq']
    var = comp_ops[op].get('variant', '?')
    handler = dispatch.get(str(op), {}).get('handler_code', '')[:200]
    
    samples = []
    for p in protos:
        c4 = p.get('C4', [])
        c7, c8, c9 = p.get('C7', []), p.get('C8', []), p.get('C9', [])
        c2, c11 = p.get('C2_sparse', {}), p.get('C11_sparse', {})
        nr = p.get('C10', 0)
        for i, o in enumerate(c4):
            if o == op and len(samples) < 5:
                D = c7[i] if i < len(c7) else -1
                a_v = c8[i] if i < len(c8) else -1
                Z = c9[i] if i < len(c9) else -1
                q = c2.get(str(i+1), '')
                m = c11.get(str(i+1), '')
                d_ok = 0 <= D < nr
                a_ok = 0 <= a_v < nr
                z_ok = 0 <= Z < nr
                next_op = c4[i+1] if i+1 < len(c4) else -1
                next_cat = opmap.get(str(next_op), {}).get('lua51', '?')
                samples.append(f"D={D}({'ok' if d_ok else 'OOR'}) a={a_v}({'ok' if a_ok else 'OOR'}) Z={Z}({'ok' if z_ok else 'OOR'}) q={q} m={m} next={next_cat}")
    print(f"\nOp {op} ({freq}x) variant={var}")
    print(f"  Handler: {handler}")
    for s in samples:
        print(f"  {s}")

print("\n=== REMAINING JMP_TEST_RETURN ===")
jtr_ops = {}
for k, v in opmap.items():
    if v.get('lua51') == 'JMP_TEST_RETURN':
        jtr_ops[int(k)] = v

for op in sorted(jtr_ops, key=lambda x: jtr_ops[x]['freq'], reverse=True):
    freq = jtr_ops[op]['freq']
    var = jtr_ops[op].get('variant', '?')
    handler = dispatch.get(str(op), {}).get('handler_code', '')[:200]
    
    samples = []
    for p in protos:
        c4 = p.get('C4', [])
        c7, c8, c9 = p.get('C7', []), p.get('C8', []), p.get('C9', [])
        nr = p.get('C10', 0)
        ni = len(c4)
        for i, o in enumerate(c4):
            if o == op and len(samples) < 5:
                D = c7[i] if i < len(c7) else -1
                a_v = c8[i] if i < len(c8) else -1
                Z = c9[i] if i < len(c9) else -1
                d_ok = 0 <= D < nr
                a_ok = 0 <= a_v < ni
                z_ok = 0 <= Z < nr
                next_op = c4[i+1] if i+1 < len(c4) else -1
                next_cat = opmap.get(str(next_op), {}).get('lua51', '?')
                prev_op = c4[i-1] if i > 0 else -1
                prev_cat = opmap.get(str(prev_op), {}).get('lua51', '?')
                samples.append(f"D={D}({'ok' if d_ok else 'OOR'}) a={a_v}({'jmp' if a_ok else 'OOR'}) Z={Z}({'ok' if z_ok else 'OOR'}) prev={prev_cat} next={next_cat}")
    print(f"\nOp {op} ({freq}x) variant={var}")
    print(f"  Handler: {handler}")
    for s in samples:
        print(f"  {s}")
