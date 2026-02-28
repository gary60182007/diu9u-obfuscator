import json
from collections import Counter, defaultdict

with open('extracted_protos.json') as f:
    protos = json.load(f)

op_stats = defaultdict(lambda: {'count': 0, 'a_vals': [], 'b_vals': [], 'c_vals': []})

for p in protos:
    raw = p.get('raw_fields', {})
    opcodes = raw.get('4', [])
    op_a = raw.get('7', [])
    op_b = raw.get('8', [])
    op_c = raw.get('9', [])
    for idx in range(len(opcodes)):
        op = opcodes[idx]
        a = op_a[idx] if idx < len(op_a) else 0
        b = op_b[idx] if idx < len(op_b) else 0
        c = op_c[idx] if idx < len(op_c) else 0
        s = op_stats[op]
        s['count'] += 1
        if len(s['a_vals']) < 200:
            s['a_vals'].append(a)
            s['b_vals'].append(b)
            s['c_vals'].append(c)

top_ops = sorted(op_stats.keys(), key=lambda x: op_stats[x]['count'], reverse=True)[:30]
for op in top_ops:
    s = op_stats[op]
    a_vals = s['a_vals']
    b_vals = s['b_vals']
    c_vals = s['c_vals']
    a_range = f'[{min(a_vals)},{max(a_vals)}]'
    b_range = f'[{min(b_vals)},{max(b_vals)}]'
    c_range = f'[{min(c_vals)},{max(c_vals)}]'
    a_unique = len(set(a_vals))
    b_unique = len(set(b_vals))
    c_unique = len(set(c_vals))
    b_zero = sum(1 for v in b_vals if v == 0) / len(b_vals) * 100
    c_zero = sum(1 for v in c_vals if v == 0) / len(c_vals) * 100
    b_neg = sum(1 for v in b_vals if v < 0)
    print(f'op={op:3d} n={s["count"]:5d}  '
          f'A:{a_range:15s}({a_unique:3d}u)  '
          f'B:{b_range:20s}({b_unique:3d}u {b_zero:3.0f}%z {b_neg}neg)  '
          f'C:{c_range:15s}({c_unique:3d}u {c_zero:3.0f}%z)')

# Check which opcodes always have B=0 (likely 2-operand instructions)
print("\n=== Opcodes where B is always 0 (likely MOVE/LOADK/LOADNIL/JMP) ===")
for op in sorted(op_stats.keys()):
    s = op_stats[op]
    if s['count'] >= 5:
        b_vals = s['b_vals']
        if all(v == 0 for v in b_vals):
            a_vals = s['a_vals']
            c_vals = s['c_vals']
            print(f'  op={op:3d} n={s["count"]:4d}  A:[{min(a_vals)},{max(a_vals)}]  C:[{min(c_vals)},{max(c_vals)}]')

# Check which opcodes have negative B values (likely signed offsets = JMP/FORLOOP)
print("\n=== Opcodes with negative B values (likely JMP/FORLOOP) ===")
for op in sorted(op_stats.keys()):
    s = op_stats[op]
    b_vals = s['b_vals']
    neg = [v for v in b_vals if v < 0]
    if neg and s['count'] >= 3:
        print(f'  op={op:3d} n={s["count"]:4d}  B_neg_count={len(neg)}  B_neg_range=[{min(neg)},{max(neg)}]  A:[{min(s["a_vals"])},{max(s["a_vals"])}]')

# Check instruction sequences (what follows what)
print("\n=== Common instruction pairs ===")
pair_counts = Counter()
for p in protos:
    raw = p.get('raw_fields', {})
    opcodes = raw.get('4', [])
    for i in range(len(opcodes) - 1):
        pair_counts[(opcodes[i], opcodes[i+1])] += 1

for (a, b), cnt in pair_counts.most_common(20):
    print(f'  {a:3d} -> {b:3d}: {cnt:4d}')
