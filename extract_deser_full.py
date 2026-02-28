"""
Extract all deserialization chain methods to understand buffer format.
"""
import re

with open(r'unobfuscator\pending crack\bloxburg_script.lua', 'r', encoding='utf-8', errors='replace') as f:
    source = f.read()

ret_start = source.index('return({')
content = source[ret_start:]

def extract_method(name, src, max_len=200000):
    pat = re.compile(re.escape(name) + r'=function\(')
    results = []
    for m in pat.finditer(src):
        start = m.start()
        pos = start + len(name) + len('=function(')
        pd = 1
        while pos < len(src) and pd > 0:
            if src[pos] == '(': pd += 1
            elif src[pos] == ')': pd -= 1
            pos += 1
        depth = 1
        last_kw = None
        i = pos
        in_str = False
        sc = None
        while i < len(src) and depth > 0 and (i - start) < max_len:
            c = src[i]
            if in_str:
                if c == '\\': i += 2; continue
                if c == sc: in_str = False
                i += 1; continue
            if c in '"\'': in_str = True; sc = c; i += 1; continue
            if c == '[' and i+1 < len(src) and src[i+1] in '[=':
                eq = 0; j = i + 1
                while j < len(src) and src[j] == '=': eq += 1; j += 1
                if j < len(src) and src[j] == '[':
                    cl = ']' + '=' * eq + ']'
                    ep = src.find(cl, j + 1)
                    if ep >= 0: i = ep + len(cl); continue
                i += 1; continue
            if c == '-' and i+1 < len(src) and src[i+1] == '-':
                nl = src.find('\n', i)
                i = nl + 1 if nl >= 0 else len(src); continue
            if c.isalpha() or c == '_':
                j = i
                while j < len(src) and (src[j].isalnum() or src[j] == '_'): j += 1
                w = src[i:j]
                wb = (i == 0 or not (src[i-1].isalnum() or src[i-1] == '_'))
                wa = (j >= len(src) or not (src[j].isalnum() or src[j] == '_'))
                if wb and wa:
                    if w == 'function': depth += 1
                    elif w == 'do': depth += 1
                    elif w == 'repeat': depth += 1
                    elif w == 'then':
                        if last_kw == 'if': depth += 1
                    elif w == 'end':
                        depth -= 1
                        if depth == 0: i = j; break
                    elif w == 'until':
                        depth -= 1
                        if depth == 0: i = j; break
                    if w in ('if', 'elseif'): last_kw = w
                    elif w == 'then': last_kw = None
                    elif w in ('function', 'do', 'repeat', 'end', 'until'): last_kw = None
                i = j; continue
            i += 1
        results.append((start, src[start:i]))
    return results

def show(name, mx=5000):
    r = extract_method(name, content)
    if not r:
        print(f"\n{name}: NOT FOUND"); return r
    b = r[0][1]
    print(f"\n{'='*70}")
    print(f"{name} (len={len(b)})")
    print(f"{'='*70}")
    p = b.replace(';', ';\n')
    print(p[:mx] if len(p) <= mx else p[:mx] + f"\n... ({len(p)-mx} more)")
    return r

def calls(name):
    r = extract_method(name, content)
    if not r: return []
    return sorted(set(re.findall(r'z:(\w+)\(', r[0][1])))

# Key chain from F9's W (lazy deserializer): lF → _9 → t9 → I9
for n in ['lF', '_9', 't9', 'I9']:
    show(n, 6000)
    c = calls(n)
    if c:
        print(f"  calls: {c}")

# From UF: bF, vF (state machine for prototype field population)
for n in ['bF', 'vF']:
    show(n, 8000)
    c = calls(n)
    if c:
        print(f"  calls: {c}")

# From F9's C[58]: aF, xF
for n in ['aF', 'xF']:
    show(n, 4000)
    c = calls(n)
    if c:
        print(f"  calls: {c}")

# Check what bF/vF call
for n in ['bF', 'vF']:
    c = calls(n)
    for sub in c:
        if sub not in ('bF', 'vF', 'lF', '_9', 't9', 'I9', 'aF', 'xF', 'UF', 'By', 'Wy'):
            show(sub, 4000)

# Also check what O[24] is - from init chain
# r[24] = z.T, set in gy
show('gy', 3000)

# Check z.T, z.M, z.D in the return table
print(f"\n{'='*70}")
print("Looking for z.T, z.M, z.D definitions")
print(f"{'='*70}")
for attr in ['T', 'M', 'D', 'L', 'Q', 'A']:
    # Search for X=something at top level of return table
    for m in re.finditer(rf'(?<![A-Za-z_]){attr}=(?!function)', content[:5000]):
        ctx = content[m.start():m.start()+80]
        print(f"  {attr} at {m.start()}: {ctx}")

# Also look for ZF which was found earlier as having buffer reads + string patterns
show('ZF', 8000)
c = calls('ZF')
if c:
    print(f"  ZF calls: {c}")
    for sub in c:
        if sub not in ('ZF',):
            show(sub, 4000)
