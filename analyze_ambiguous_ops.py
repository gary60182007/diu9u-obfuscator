import json
from collections import Counter

protos = json.load(open('all_protos_data.json'))
opmap = json.load(open('opcode_map_final.json'))

jtr_ops = {int(k): v for k, v in opmap.items() if v.get('lua51') == 'JMP_TEST_RETURN'}
close_ops = {int(k): v for k, v in opmap.items() if v.get('lua51') == 'CLOSE'}
loadnil_ops = {int(k): v for k, v in opmap.items() if v.get('lua51') == 'LOADNIL'}
computed_ops = {int(k): v for k, v in opmap.items() if v.get('lua51') == 'COMPUTED'}

print("=== JMP_TEST_RETURN opcodes ===")
for op in sorted(jtr_ops.keys()):
    freq = jtr_ops[op]['freq']
    valid_jmp = 0
    total = 0
    a_zero = 0
    z_zero = 0
    for p in protos:
        ops = p.get('C4', [])
        c7 = p.get('C7', [])
        c8 = p.get('C8', [])
        c9 = p.get('C9', [])
        n = len(ops)
        for i, o in enumerate(ops):
            if o == op:
                total += 1
                D = c7[i] if i < len(c7) else -1
                a = c8[i] if i < len(c8) else -1
                Z = c9[i] if i < len(c9) else -1
                if 0 <= D < n:
                    valid_jmp += 1
                if a == 0:
                    a_zero += 1
                if Z == 0:
                    z_zero += 1
    jmp_pct = 100 * valid_jmp / total if total else 0
    print(f"  Op {op:>3} ({freq:>4}x): D_valid_jmp={jmp_pct:.0f}% a=0:{100*a_zero/total:.0f}% Z=0:{100*z_zero/total:.0f}%")

print("\n=== CLOSE opcodes ===")
for op in sorted(close_ops.keys()):
    freq = close_ops[op]['freq']
    d_vals = Counter()
    total = 0
    for p in protos:
        ops = p.get('C4', [])
        c7 = p.get('C7', [])
        for i, o in enumerate(ops):
            if o == op:
                total += 1
                D = c7[i] if i < len(c7) else -1
                d_vals[D] += 1
    print(f"  Op {op:>3} ({freq:>4}x): top D={d_vals.most_common(5)}")

print("\n=== LOADNIL opcodes ===")
for op in sorted(loadnil_ops.keys()):
    freq = loadnil_ops[op]['freq']
    total = 0
    samples = []
    for p in protos:
        ops = p.get('C4', [])
        c7 = p.get('C7', [])
        c8 = p.get('C8', [])
        c9 = p.get('C9', [])
        for i, o in enumerate(ops):
            if o == op:
                total += 1
                D = c7[i] if i < len(c7) else -1
                a = c8[i] if i < len(c8) else -1
                Z = c9[i] if i < len(c9) else -1
                if len(samples) < 5:
                    samples.append((D, a, Z))
    print(f"  Op {op:>3} ({freq:>4}x): samples(D,a,Z)={samples}")

print("\n=== COMPUTED opcodes ===")
for op in sorted(computed_ops.keys()):
    freq = computed_ops[op]['freq']
    if freq < 5:
        continue
    total = 0
    valid_jmp = 0
    samples = []
    for p in protos:
        ops = p.get('C4', [])
        c7 = p.get('C7', [])
        c8 = p.get('C8', [])
        c9 = p.get('C9', [])
        n = len(ops)
        for i, o in enumerate(ops):
            if o == op:
                total += 1
                D = c7[i] if i < len(c7) else -1
                a = c8[i] if i < len(c8) else -1
                Z = c9[i] if i < len(c9) else -1
                if 0 <= D < n:
                    valid_jmp += 1
                if len(samples) < 3:
                    samples.append((D, a, Z))
    jmp_pct = 100 * valid_jmp / total if total else 0
    print(f"  Op {op:>3} ({freq:>4}x): D_valid_jmp={jmp_pct:.0f}% samples={samples}")
