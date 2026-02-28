import json
from collections import Counter

protos = json.load(open('all_protos_data.json'))
opmap = json.load(open('opcode_map_final.json'))

noise_cats = {'CLOSE', 'DISPATCH', 'FRAGMENT', 'RANGE', 'ARITH', 'UNKNOWN'}
structural_cats = {'JMP', 'LOADNIL', 'NEWTABLE'}

total = 0
noise = 0
structural = 0
real = 0
cat_counts = Counter()

for p in protos:
    c4 = p.get('C4', [])
    for op in c4:
        cat = opmap.get(str(op), {}).get('lua51', '?')
        total += 1
        cat_counts[cat] += 1
        if cat in noise_cats:
            noise += 1
        elif cat in structural_cats:
            structural += 1
        else:
            real += 1

print(f"Total instructions: {total}")
print(f"Noise (CLOSE/DISPATCH/etc): {noise} ({noise*100/total:.1f}%)")
print(f"Structural (JMP/LOADNIL/NEWTABLE): {structural} ({structural*100/total:.1f}%)")
print(f"Real operations: {real} ({real*100/total:.1f}%)")
print(f"\nReal instruction breakdown:")
for cat, cnt in cat_counts.most_common():
    if cat not in noise_cats and cat not in structural_cats:
        print(f"  {cat}: {cnt}")

# Check a few small protos to understand structure
print("\n=== Sample small protos ===")
for idx, p in enumerate(protos):
    c4 = p.get('C4', [])
    if 10 <= len(c4) <= 25:
        c7, c8, c9 = p.get('C7', []), p.get('C8', []), p.get('C9', [])
        c2 = p.get('C2_sparse', {})
        nr = p.get('C10', 0)
        print(f"\nProto {idx+1}: {len(c4)} inst, {nr} regs")
        for i, op in enumerate(c4):
            info = opmap.get(str(op), {})
            cat = info.get('lua51', '?')
            var = info.get('variant', '')
            D = c7[i] if i < len(c7) else -1
            a = c8[i] if i < len(c8) else -1
            Z = c9[i] if i < len(c9) else -1
            q = c2.get(str(i+1), '')
            if cat in noise_cats:
                print(f"  {i:3d} [{cat}]")
            else:
                extra = f" q={q}" if q else ""
                print(f"  {i:3d} [{cat}] D={D} a={a} Z={Z}{extra}")
        if idx > 5:
            break
