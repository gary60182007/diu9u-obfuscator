"""Analyze extracted bytecode prototypes and build opcode map."""
import json

with open('unobfuscator/cracked script/target2_bytecode.json') as f:
    protos = json.load(f)

def show_op_samples(target_op, label, max_samples=15):
    print(f"\n=== OP={target_op} samples ({label}) ===")
    count = 0
    for pi, p in enumerate(protos):
        for i, op in enumerate(p['opcodes']):
            if op == target_op and count < max_samples:
                M = p["operM"][i]
                L = p["operL"][i]
                P = p["operP"][i]
                t = p["constT"][i]
                Q = p["constQ"][i]
                g = p["constG"][i]
                print(f"  P{pi+1}[{i:3d}]: M={M} L={L} P={P} t={t} Q={Q} g={g}")
                count += 1

# Show samples for all unknown high-frequency opcodes
for op_num, label in [(12, "470 uses"), (157, "71 uses"), (124, "51 uses"),
                       (161, "27 uses"), (110, "19 uses"), (56, "74 uses"),
                       (59, "30 uses"), (43, "160 uses"), (0, "11 uses"),
                       (108, "171 uses")]:
    show_op_samples(op_num, label)

# Also show Proto 1 string constants (API names)
print("\n=== Proto 1 unique strings ===")
for s in protos[0]["strings"]:
    if s and len(s) < 60:
        print(f"  {s}")
