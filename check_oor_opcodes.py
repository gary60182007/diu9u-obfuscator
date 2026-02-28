import json, re
from collections import Counter

opmap = json.load(open('opcode_map_final.json'))

with open('decompiled_output.lua') as f:
    lines = f.readlines()

oor_by_op = Counter()
current_nreg = 0

for line in lines:
    m = re.match(r'-- Proto \d+ \(index \d+\): \d+ instructions, \d+ upvals, (\d+) regs', line)
    if m:
        current_nreg = int(m.group(1))
        continue
    
    regs = re.findall(r'\br(\d+)\b', line)
    has_oor = False
    for r in regs:
        if int(r) >= current_nreg and int(r) < 1000:
            has_oor = True
            break
    
    if has_oor:
        op_m = re.search(r'\[(\s*\d+)\]', line)
        if op_m:
            op_num = int(op_m.group(1).strip())
            info = opmap.get(str(op_num), {})
            cat = info.get('lua51', '?')
            var = info.get('variant', '?')
            oor_by_op[(op_num, cat, var)] += 1

print("OOR lines by opcode:")
for (op, cat, var), cnt in oor_by_op.most_common(30):
    print(f"  Op {op:3d} ({cat}/{var}): {cnt}")
