import json

d = json.load(open('opcode_dispatch_map.json'))
opmap = json.load(open('opcode_map_final.json'))

print(f"Dispatch map has {len(d)} entries")
print(f"Opcode map has {len(opmap)} entries")

missing = []
for k, v in opmap.items():
    if k not in d:
        missing.append((int(k), v.get('lua51','?'), v.get('freq',0)))

missing.sort(key=lambda x: x[2], reverse=True)
print(f"\nOpcodes in opmap but NOT in dispatch map ({len(missing)}):")
for op, cat, freq in missing[:30]:
    print(f"  Op {op}: {cat} ({freq}x)")

print("\nDispatch map keys sample:", list(d.keys())[:10])
print("\nDispatch map entry structure:", list(d.get(list(d.keys())[0], {}).keys()) if d else "empty")

for op in [278, 122, 97, 30, 68]:
    entry = d.get(str(op))
    if entry:
        print(f"\nOp {op} dispatch entry keys: {list(entry.keys())}")
        for k2, v2 in entry.items():
            print(f"  {k2}: {str(v2)[:150]}")
