import json
d = json.load(open('opcode_dispatch_map.json'))
for op in [278, 68, 122, 97, 30]:
    h = d.get(str(op), {}).get('handler_code', 'NONE')
    print(f"Op {op}: {h[:300]}")
    print()
