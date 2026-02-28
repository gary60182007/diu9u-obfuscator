import json

d = json.load(open('opcode_dispatch_map.json'))
hc = d['handler_code']
om = json.load(open('opcode_map_final.json'))
protos = json.load(open('all_protos_data.json'))

jtr = [int(k) for k, v in om.items() if v.get('lua51') == 'JMP_TEST_RETURN']

print("=== JMP_TEST_RETURN handler codes ===")
for o in sorted(jtr):
    freq = om[str(o)]['freq']
    handler = hc.get(str(o), '?')[:400]
    print(f"\nOp {o} ({freq}x):")
    print(f"  {handler}")

print("\n\n=== JMP_TEST_RETURN operand analysis ===")
for o in sorted(jtr):
    freq = om[str(o)]['freq']
    samples = []
    for p in protos:
        c4 = p.get('C4', [])
        c7 = p.get('C7', [])
        c8 = p.get('C8', [])
        c9 = p.get('C9', [])
        c2 = p.get('C2_sparse', {})
        c11 = p.get('C11_sparse', {})
        nreg = p.get('C10', 0)
        ninst = len(c4)
        for i, op in enumerate(c4):
            if op == o and len(samples) < 5:
                D = c7[i] if i < len(c7) else -1
                a = c8[i] if i < len(c8) else -1
                Z = c9[i] if i < len(c9) else -1
                q = c2.get(str(i+1), '')
                m = c11.get(str(i+1), '')
                d_reg = 0 <= D < nreg
                a_jmp = 0 <= a < ninst
                z_reg = 0 <= Z < nreg
                samples.append(f"D={D:>4}{'(r)' if d_reg else ''} a={a:>4}{'(j)' if a_jmp else ''} Z={Z:>4}{'(r)' if z_reg else ''} q={q} m={m} nreg={nreg}")
    print(f"\n  Op {o} ({freq}x):")
    for s in samples:
        print(f"    {s}")
