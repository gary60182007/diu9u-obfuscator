import json

protos = json.load(open('all_protos_data.json'))
opmap = json.load(open('opcode_map_final.json'))

p = protos[0]
c11 = p.get('C11_sparse', {})
c2 = p.get('C2_sparse', {})
c6 = p.get('C6_sparse', {})

print("Proto 0 C2_sparse keys:", sorted(int(k) for k in c2.keys())[:30])
print("Proto 0 C11_sparse keys:", sorted(int(k) for k in c11.keys())[:30])
print("Proto 0 C6_sparse keys:", sorted(int(k) for k in c6.keys())[:10])

print("\nChecking LT op 110 at pc=16:")
for offset in [16, 17]:
    q = c2.get(str(offset))
    m = c11.get(str(offset))
    print(f"  C2[{offset}]={q}, C11[{offset}]={m}")

print("\nChecking EQ op 3 at pc=48:")
for offset in [48, 49]:
    q = c2.get(str(offset))
    m = c11.get(str(offset))
    print(f"  C2[{offset}]={q}, C11[{offset}]={m}")

print("\nChecking EQ op 10 at pc=88:")
for offset in [88, 89]:
    q = c2.get(str(offset))
    m = c11.get(str(offset))
    print(f"  C2[{offset}]={q}, C11[{offset}]={m}")

print("\nAll C11_sparse entries for Proto 0:")
for k in sorted(c11.keys(), key=int):
    print(f"  C11[{k}] = {c11[k]}")

print("\nSETTABLE op 232 at pc=20 (works correctly):")
for offset in [20, 21]:
    q = c2.get(str(offset))
    m = c11.get(str(offset))
    print(f"  C2[{offset}]={q}, C11[{offset}]={m}")
