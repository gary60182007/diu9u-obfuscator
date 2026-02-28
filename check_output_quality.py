import re

with open('decompiled_output.lua') as f:
    lines = f.readlines()

oor_lines = []
current_proto = None
current_nreg = 0

for i, line in enumerate(lines, 1):
    m = re.match(r'-- Proto \d+ \(index \d+\): \d+ instructions, \d+ upvals, (\d+) regs', line)
    if m:
        current_nreg = int(m.group(1))
        current_proto = line.strip()
        continue
    
    # Find register references like r123
    regs = re.findall(r'\br(\d+)\b', line)
    for r in regs:
        rv = int(r)
        if rv >= current_nreg and rv < 1000:
            oor_lines.append((i, rv, current_nreg, line.strip()[:100]))
            break

print(f"Lines with out-of-range registers: {len(oor_lines)}")
print(f"\nFirst 30:")
for ln, rv, nr, txt in oor_lines[:30]:
    print(f"  L{ln} (r{rv} >= {nr}): {txt}")

# Count by category
from collections import Counter
cat_counts = Counter()
for ln, rv, nr, txt in oor_lines:
    m2 = re.search(r'\] (\w+)', txt)
    if m2:
        cat_counts[m2.group(1)] += 1
print(f"\nBy category:")
for cat, cnt in cat_counts.most_common():
    print(f"  {cat}: {cnt}")
