import json

protos = json.load(open('all_protos_data.json'))
opmap = json.load(open('opcode_map_final.json'))

def show_samples(category, max_per_op=5):
    ops = {int(k): v for k, v in opmap.items() if v.get('lua51') == category}
    for op in sorted(ops.keys()):
        freq = ops[op]['freq']
        variant = ops[op].get('variant', '?')
        samples = []
        for p in protos:
            c4 = p.get('C4', [])
            c7 = p.get('C7', [])
            c8 = p.get('C8', [])
            c9 = p.get('C9', [])
            c2 = p.get('C2_sparse', {})
            c6 = p.get('C6_sparse', {})
            c11 = p.get('C11_sparse', {})
            nreg = p.get('C10', 0)
            for i, o in enumerate(c4):
                if o == op and len(samples) < max_per_op:
                    D = c7[i] if i < len(c7) else -1
                    a = c8[i] if i < len(c8) else -1
                    Z = c9[i] if i < len(c9) else -1
                    q = c2.get(str(i+1), '')
                    w = c6.get(str(i+1), '')
                    m = c11.get(str(i+1), '')
                    samples.append(dict(D=D, a=a, Z=Z, q=q, w=w, m=m, nreg=nreg))
        print(f"  Op {op} ({freq}x) {variant}:")
        for s in samples:
            extras = ''
            if s['q']: extras += f" q={s['q']}"
            if s['w']: extras += f" w={s['w']}"
            if s['m']: extras += f" m={s['m']}"
            print(f"    D={s['D']:>4} a={s['a']:>4} Z={s['Z']:>4} nreg={s['nreg']}{extras}")

print("=== VARARG ===")
show_samples('VARARG')

print("\n=== EQ (first 3 ops) ===")
eq_ops = {int(k): v for k, v in opmap.items() if v.get('lua51') == 'EQ'}
for op in sorted(eq_ops.keys())[:5]:
    freq = eq_ops[op]['freq']
    variant = eq_ops[op].get('variant', '?')
    samples = []
    for p in protos:
        c4 = p.get('C4', [])
        c7 = p.get('C7', [])
        c8 = p.get('C8', [])
        c9 = p.get('C9', [])
        c2 = p.get('C2_sparse', {})
        c11 = p.get('C11_sparse', {})
        nreg = p.get('C10', 0)
        ninst = len(c4)
        for i, o in enumerate(c4):
            if o == op and len(samples) < 5:
                D = c7[i] if i < len(c7) else -1
                a = c8[i] if i < len(c8) else -1
                Z = c9[i] if i < len(c9) else -1
                q = c2.get(str(i+1), '')
                m = c11.get(str(i+1), '')
                samples.append(dict(D=D, a=a, Z=Z, q=q, m=m, nreg=nreg, ninst=ninst))
    print(f"  Op {op} ({freq}x) {variant}:")
    for s in samples:
        d_reg = 0 <= s['D'] < s['nreg']
        a_jmp = 0 <= s['a'] < s['ninst']
        z_reg = 0 <= s['Z'] < s['nreg']
        extras = ''
        if s['q']: extras += f" q={s['q']}"
        if s['m']: extras += f" m={s['m']}"
        print(f"    D={s['D']:>4}{'(r)' if d_reg else ''} a={s['a']:>4}{'(j)' if a_jmp else ''} Z={s['Z']:>4}{'(r)' if z_reg else ''}{extras}")

print("\n=== SETTABLE op 99 ===")
for p in protos[:5]:
    c4 = p.get('C4', [])
    c7 = p.get('C7', [])
    c8 = p.get('C8', [])
    c9 = p.get('C9', [])
    c2 = p.get('C2_sparse', {})
    c6 = p.get('C6_sparse', {})
    c11 = p.get('C11_sparse', {})
    nreg = p.get('C10', 0)
    for i, o in enumerate(c4):
        if o == 99:
            D = c7[i] if i < len(c7) else -1
            a = c8[i] if i < len(c8) else -1
            Z = c9[i] if i < len(c9) else -1
            q = c2.get(str(i+1), '')
            w = c6.get(str(i+1), '')
            m = c11.get(str(i+1), '')
            extras = ''
            if q: extras += f" q={q}"
            if w: extras += f" w={w}"
            if m: extras += f" m={m}"
            print(f"  Proto {p['id']}: D={D} a={a} Z={Z} nreg={nreg}{extras}")

print("\n=== CLOSE ops (top 3 by freq) ===")
close_ops = sorted([(int(k), v) for k, v in opmap.items() if v.get('lua51') == 'CLOSE'], key=lambda x: -x[1]['freq'])
for op, info in close_ops[:3]:
    freq = info['freq']
    variant = info.get('variant', '?')
    print(f"  Op {op} ({freq}x) {variant}")

print("\n=== LOADNIL op 176 ===")
for p in protos[:10]:
    c4 = p.get('C4', [])
    c7 = p.get('C7', [])
    c8 = p.get('C8', [])
    c9 = p.get('C9', [])
    nreg = p.get('C10', 0)
    for i, o in enumerate(c4):
        if o == 176:
            D = c7[i] if i < len(c7) else -1
            a = c8[i] if i < len(c8) else -1
            Z = c9[i] if i < len(c9) else -1
            print(f"  Proto {p['id']}: D={D} a={a} Z={Z} nreg={nreg} (a<nreg={a<nreg}, Z-a={Z-a})")
