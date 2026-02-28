import json
from collections import Counter

protos = json.load(open('all_protos_data.json'))

valid_jmp = 0
invalid_jmp = 0
total_117 = 0
a_vals = Counter()
z_vals = Counter()

for pi, p in enumerate(protos):
    ops = p.get('C4', [])
    c7 = p.get('C7', [])
    c8 = p.get('C8', [])
    c9 = p.get('C9', [])
    n = len(ops)
    for i, op in enumerate(ops):
        if op == 117:
            total_117 += 1
            D = c7[i] if i < len(c7) else -1
            a = c8[i] if i < len(c8) else -1
            Z = c9[i] if i < len(c9) else -1
            a_vals[a] += 1
            z_vals[Z] += 1
            if 0 <= D < n:
                valid_jmp += 1
            else:
                invalid_jmp += 1

print(f"Op 117: {total_117} total")
print(f"  D as jump target: {valid_jmp} valid ({100*valid_jmp/total_117:.1f}%), {invalid_jmp} invalid")
print(f"  Top a values: {a_vals.most_common(10)}")
print(f"  Top Z values: {z_vals.most_common(10)}")

# Check the same for known JMP-like opcodes
for check_op in [110, 103, 0, 89]:
    valid = 0
    total = 0
    for p in protos:
        ops = p.get('C4', [])
        c7 = p.get('C7', [])
        n = len(ops)
        for i, op in enumerate(ops):
            if op == check_op:
                total += 1
                D = c7[i] if i < len(c7) else -1
                if 0 <= D < n:
                    valid += 1
    if total > 0:
        print(f"\nOp {check_op}: {total} total, D valid as jmp: {valid} ({100*valid/total:.1f}%)")

# Check if op 117 D values could be register indices
reg_range = 0
for p in protos:
    ops = p.get('C4', [])
    c7 = p.get('C7', [])
    nreg = p.get('C10', 0)
    for i, op in enumerate(ops):
        if op == 117:
            D = c7[i] if i < len(c7) else -1
            if 0 <= D < nreg:
                reg_range += 1

print(f"\nOp 117 D values within register range: {reg_range}/{total_117} ({100*reg_range/total_117:.1f}%)")
