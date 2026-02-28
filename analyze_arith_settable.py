import json
from collections import Counter

protos = json.load(open('all_protos_data.json'))
opmap = json.load(open('opcode_map_final.json'))
dispatch = json.load(open('opcode_dispatch_map.json'))
hc = dispatch['handler_code']

print("=== MUL ops ===")
mul_ops = {int(k): v for k, v in opmap.items() if v.get('lua51') == 'MUL'}
for op in sorted(mul_ops.keys()):
    freq = mul_ops[op]['freq']
    variant = mul_ops[op].get('variant', '?')
    handler = hc.get(str(op), '?')[:200]
    print(f"Op {op} ({freq}x) {variant}: {handler}")
    samples = []
    for p in protos:
        c4 = p.get('C4', [])
        c7, c8, c9 = p.get('C7', []), p.get('C8', []), p.get('C9', [])
        c2, c6, c11 = p.get('C2_sparse', {}), p.get('C6_sparse', {}), p.get('C11_sparse', {})
        nreg = p.get('C10', 0)
        for i, o in enumerate(c4):
            if o == op and len(samples) < 3:
                key = str(i + 1)
                D = c7[i] if i < len(c7) else -1
                a = c8[i] if i < len(c8) else -1
                Z = c9[i] if i < len(c9) else -1
                q = c2.get(key, '')
                w = c6.get(key, '')
                m = c11.get(key, '')
                samples.append(f"  D={D} a={a} Z={Z} q={q} w={w} m={m} nreg={nreg}")
    for s in samples:
        print(s)

print("\n=== SETTABLE ops 99 and 170 handlers ===")
for op in [99, 170]:
    freq = opmap.get(str(op), {}).get('freq', 0)
    variant = opmap.get(str(op), {}).get('variant', '?')
    handler = hc.get(str(op), '?')[:300]
    print(f"\nOp {op} ({freq}x) {variant}:")
    print(f"  {handler}")

print("\n=== LOADNIL op 176 handler ===")
handler = hc.get('176', '?')[:400]
print(f"  {handler}")

print("\n=== MULTI_WRITE ops ===")
mw_ops = {int(k): v for k, v in opmap.items() if v.get('lua51') == 'MULTI_WRITE'}
for op in sorted(mw_ops.keys()):
    freq = mw_ops[op]['freq']
    variant = mw_ops[op].get('variant', '?')
    handler = hc.get(str(op), '?')[:200]
    print(f"Op {op} ({freq}x) {variant}: {handler}")
    for p in protos[:5]:
        c4 = p.get('C4', [])
        c7, c8, c9 = p.get('C7', []), p.get('C8', []), p.get('C9', [])
        c2, c11 = p.get('C2_sparse', {}), p.get('C11_sparse', {})
        nreg = p.get('C10', 0)
        for i, o in enumerate(c4):
            if o == op:
                key = str(i + 1)
                D = c7[i] if i < len(c7) else -1
                a = c8[i] if i < len(c8) else -1
                Z = c9[i] if i < len(c9) else -1
                q = c2.get(key, '')
                m = c11.get(key, '')
                print(f"  D={D} a={a} Z={Z} q={q} m={m} nreg={nreg}")
