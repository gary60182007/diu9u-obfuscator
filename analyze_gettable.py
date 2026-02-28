import json

protos = json.load(open('all_protos_data.json'))
opmap = json.load(open('opcode_map_final.json'))

gt_ops = {int(k): v for k, v in opmap.items() if v.get('lua51') == 'GETTABLE'}
for op in sorted(gt_ops.keys()):
    freq = gt_ops[op]['freq']
    variant = gt_ops[op].get('variant', '?')
    samples = []
    for p in protos:
        ops = p.get('C4', [])
        c7 = p.get('C7', [])
        c8 = p.get('C8', [])
        c9 = p.get('C9', [])
        c2 = p.get('C2_sparse', {})
        c6 = p.get('C6_sparse', {})
        c11 = p.get('C11_sparse', {})
        nreg = p.get('C10', 0)
        for i, o in enumerate(ops):
            if o == op and len(samples) < 8:
                D = c7[i] if i < len(c7) else -1
                a = c8[i] if i < len(c8) else -1
                Z = c9[i] if i < len(c9) else -1
                q = c2.get(str(i), '')
                w = c6.get(str(i), '')
                m = c11.get(str(i), '')
                samples.append((D, a, Z, q, w, m, nreg))
    print(f"Op {op} ({freq}x) variant={variant}:")
    for s in samples:
        print(f"  D={s[0]} a={s[1]} Z={s[2]} q={s[3]} w={s[4]} m={s[5]} nreg={s[6]}")

print("\n=== CALL opcodes ===")
call_ops = {int(k): v for k, v in opmap.items() if v.get('lua51') == 'CALL'}
for op in sorted(call_ops.keys()):
    freq = call_ops[op]['freq']
    variant = call_ops[op].get('variant', '?')
    samples = []
    for p in protos:
        ops = p.get('C4', [])
        c7 = p.get('C7', [])
        c8 = p.get('C8', [])
        c9 = p.get('C9', [])
        nreg = p.get('C10', 0)
        for i, o in enumerate(ops):
            if o == op and len(samples) < 5:
                D = c7[i] if i < len(c7) else -1
                a = c8[i] if i < len(c8) else -1
                Z = c9[i] if i < len(c9) else -1
                samples.append((D, a, Z, nreg))
    if freq >= 5:
        print(f"Op {op} ({freq}x) variant={variant}:")
        for s in samples:
            print(f"  D={s[0]} a={s[1]} Z={s[2]} nreg={s[3]}")

print("\n=== Remaining JMP_TEST_RETURN opcodes ===")
jtr_ops = {int(k): v for k, v in opmap.items() if v.get('lua51') == 'JMP_TEST_RETURN'}
for op in sorted(jtr_ops.keys()):
    freq = jtr_ops[op]['freq']
    samples = []
    for p in protos:
        ops = p.get('C4', [])
        c7 = p.get('C7', [])
        c8 = p.get('C8', [])
        c9 = p.get('C9', [])
        nreg = p.get('C10', 0)
        ninst = len(ops)
        for i, o in enumerate(ops):
            if o == op and len(samples) < 5:
                D = c7[i] if i < len(c7) else -1
                a = c8[i] if i < len(c8) else -1
                Z = c9[i] if i < len(c9) else -1
                samples.append((D, a, Z, nreg, ninst))
    print(f"Op {op} ({freq}x):")
    for s in samples:
        d_reg = s[0] < s[3]
        a_reg = s[1] < s[3]
        z_reg = s[2] < s[3]
        d_jmp = 0 <= s[0] < s[4]
        print(f"  D={s[0]}{'(reg)' if d_reg else ''}{'(jmp)' if d_jmp else ''} a={s[1]}{'(reg)' if a_reg else ''} Z={s[2]}{'(reg)' if z_reg else ''} nreg={s[3]} ninst={s[4]}")
