import json
from collections import Counter

protos = json.load(open('all_protos_data.json'))
opmap = json.load(open('opcode_map_final.json'))

oor_counts = Counter()
oor_by_cat = Counter()
total_oor = 0

for p in protos:
    c4 = p.get('C4', [])
    c7, c8, c9 = p.get('C7', []), p.get('C8', []), p.get('C9', [])
    nreg = p.get('C10', 0)
    for i, op_code in enumerate(c4):
        D = c7[i] if i < len(c7) else 0
        a = c8[i] if i < len(c8) else 0
        Z = c9[i] if i < len(c9) else 0
        info = opmap.get(str(op_code), {})
        cat = info.get('lua51', '?')
        
        if cat in ('JMP', 'CLOSE', 'RETURN', 'CLOSURE', 'COMPUTED', 'JMP_TEST_RETURN', 'FORLOOP', 'UNKNOWN', 'FRAGMENT', 'RANGE', 'ARITH'):
            continue
            
        d_oor = D >= nreg and cat in ('LOADK', 'LOADNIL', 'LOADBOOL', 'MOVE', 'NEWTABLE', 'GETTABLE', 'GETGLOBAL', 'GETUPVAL', 'MUL', 'ADD', 'SUB', 'DIV', 'MOD', 'POW', 'UNM', 'NOT', 'LEN', 'CONCAT', 'SETTABLE', 'CALL', 'VARARG')
        
        if d_oor:
            total_oor += 1
            oor_counts[op_code] += 1
            oor_by_cat[cat] += 1

print(f"Total out-of-range D in dest-using ops: {total_oor}")
print("\nBy category:")
for cat, cnt in oor_by_cat.most_common(20):
    print(f"  {cat}: {cnt}")
print("\nBy opcode (top 15):")
for op, cnt in oor_counts.most_common(15):
    cat = opmap.get(str(op), {}).get('lua51', '?')
    var = opmap.get(str(op), {}).get('variant', '?')
    print(f"  Op {op} ({cat}/{var}): {cnt}")
