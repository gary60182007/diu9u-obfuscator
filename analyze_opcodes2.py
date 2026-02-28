import json
from collections import defaultdict

with open('extracted_protos.json') as f:
    protos = json.load(f)

# For each opcode, check what sparse arrays (f2, f6, f11) hold at those positions
op_const_assoc = defaultdict(lambda: {'str_count': 0, 'num_count': 0, 'none_count': 0,
                                       'strs': [], 'has_m': 0, 'has_w': 0})

for p in protos:
    raw = p.get('raw_fields', {})
    opcodes = raw.get(4, raw.get('4', []))
    f2 = raw.get(2, raw.get('2', []))  # q - constants
    f6 = raw.get(6, raw.get('6', []))  # w - sparse regs
    f11 = raw.get(11, raw.get('11', []))  # m - sparse values

    for L in range(len(opcodes)):
        if opcodes[L] is None:
            continue
        op = opcodes[L]
        s = op_const_assoc[op]

        q_val = f2[L] if L < len(f2) else None
        if q_val is not None:
            if isinstance(q_val, str):
                s['str_count'] += 1
                if len(s['strs']) < 5:
                    s['strs'].append(q_val)
            else:
                s['num_count'] += 1
        else:
            s['none_count'] += 1

        w_val = f6[L] if L < len(f6) else None
        if w_val is not None:
            s['has_w'] += 1

        m_val = f11[L] if L < len(f11) else None
        if m_val is not None:
            s['has_m'] += 1

# Print top opcodes with their constant associations
top_ops = sorted(op_const_assoc.keys(), key=lambda x: op_const_assoc[x]['str_count'] + op_const_assoc[x]['num_count'] + op_const_assoc[x]['none_count'], reverse=True)

print("=== Opcodes with constant pool associations ===")
print(f"{'OP':>4s} {'Total':>6s} {'qStr':>5s} {'qNum':>5s} {'qNone':>6s} {'hasW':>5s} {'hasM':>5s}  Sample strings")
print("-" * 100)
for op in top_ops[:40]:
    s = op_const_assoc[op]
    total = s['str_count'] + s['num_count'] + s['none_count']
    strs = s['strs'][:3]
    str_display = ', '.join(repr(x)[:30] for x in strs) if strs else ''
    print(f"{op:4d} {total:6d} {s['str_count']:5d} {s['num_count']:5d} {s['none_count']:6d} {s['has_w']:5d} {s['has_m']:5d}  {str_display}")

# Now correlate: which opcodes ALWAYS have string constants at q[L]?
print("\n=== Opcodes that always have string constants in q[L] ===")
for op in sorted(op_const_assoc.keys()):
    s = op_const_assoc[op]
    total = s['str_count'] + s['num_count'] + s['none_count']
    if total >= 5 and s['str_count'] == total:
        print(f"  op={op:3d} n={total:4d} strings={s['strs'][:5]}")

print("\n=== Opcodes that always have numeric constants in q[L] ===")
for op in sorted(op_const_assoc.keys()):
    s = op_const_assoc[op]
    total = s['str_count'] + s['num_count'] + s['none_count']
    if total >= 5 and s['num_count'] == total:
        print(f"  op={op:3d} n={total:4d}")

print("\n=== Opcodes with w[L] (register) data ===")
for op in sorted(op_const_assoc.keys()):
    s = op_const_assoc[op]
    total = s['str_count'] + s['num_count'] + s['none_count']
    if s['has_w'] > 0 and total >= 3:
        pct = s['has_w'] / total * 100
        print(f"  op={op:3d} n={total:4d} w_count={s['has_w']:4d} ({pct:.0f}%)")

print("\n=== Opcodes with m[L] (comparison) data ===")
for op in sorted(op_const_assoc.keys()):
    s = op_const_assoc[op]
    total = s['str_count'] + s['num_count'] + s['none_count']
    if s['has_m'] > 0 and total >= 3:
        pct = s['has_m'] / total * 100
        print(f"  op={op:3d} n={total:4d} m_count={s['has_m']:4d} ({pct:.0f}%)")

# Show a few instruction sequences with their constants
print("\n=== Sample instruction trace (Proto #1, first 30) ===")
p1 = protos[0]
raw = p1.get('raw_fields', {})
opcodes = raw.get(4, raw.get('4', []))
f2 = raw.get(2, raw.get('2', []))
f6 = raw.get(6, raw.get('6', []))
f7 = raw.get(7, raw.get('7', []))
f8 = raw.get(8, raw.get('8', []))
f9 = raw.get(9, raw.get('9', []))
f11 = raw.get(11, raw.get('11', []))

for L in range(min(50, len(opcodes))):
    op = opcodes[L] if L < len(opcodes) else None
    d = f7[L] if L < len(f7) else None
    a = f8[L] if L < len(f8) else None
    z = f9[L] if L < len(f9) else None
    q = f2[L] if L < len(f2) else None
    w = f6[L] if L < len(f6) else None
    m = f11[L] if L < len(f11) else None

    parts = [f"L={L:3d} op={op:4d}" if op else f"L={L:3d} op=None"]
    parts.append(f"D={d}" if d is not None else "")
    parts.append(f"a={a}" if a is not None else "")
    parts.append(f"Z={z}" if z is not None else "")
    if q is not None:
        parts.append(f"q={repr(q)[:40]}")
    if w is not None:
        parts.append(f"w={w}")
    if m is not None:
        parts.append(f"m={m}")
    print("  " + "  ".join(p for p in parts if p))
