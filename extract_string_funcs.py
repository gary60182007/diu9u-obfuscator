"""
Extract string building functions: EF, sF, iF, WF, SF, KF
and the full t9 (string table builder) chain.
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
        depth = 1; last_kw = None; i = pos
        in_str = False; sc = None
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
                nl = src.find('\n', i); i = nl + 1 if nl >= 0 else len(src); continue
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
                    elif w == 'end': depth -= 1; (i := j) if depth == 0 else None; (None if depth > 0 else None)
                    elif w == 'until': depth -= 1; (i := j) if depth == 0 else None
                    if w in ('if', 'elseif'): last_kw = w
                    elif w in ('then', 'function', 'do', 'repeat', 'end', 'until'): last_kw = None
                    if depth == 0: break
                i = j; continue
            i += 1
        results.append((start, src[start:i]))
    return results

def show(name, mx=5000):
    r = extract_method(name, content)
    if not r: print(f"\n{name}: NOT FOUND"); return r
    b = r[0][1]
    print(f"\n{'='*70}")
    print(f"{name} (len={len(b)})")
    print(f"{'='*70}")
    p = b.replace(';', ';\n')
    print(p[:mx] if len(p) <= mx else p[:mx] + f"\n... ({len(p)-mx} more)")
    calls = sorted(set(re.findall(r'z:(\w+)\(', b)))
    if calls: print(f"  calls: {calls}")
    # Also show r[N] references
    refs = sorted(set(re.findall(r'r\[(\d+)\]', b)))
    if refs: print(f"  r[] refs: {refs}")
    return r

# String building functions
for n in ['EF', 'sF', 'iF', 'WF', 'SF', 'KF', 'RF', 'BF', 'LF', 'ZF']:
    show(n)

# Lazy deserializer chain
for n in ['t9', 'lF', '_9', 'I9']:
    show(n)

# Also check Ry (used by Sy for varint reading) and Sy
for n in ['Ry', 'Sy', 'Qy']:
    show(n)
