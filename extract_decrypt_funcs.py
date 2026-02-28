"""
Extract ALL string decryption functions: ZF, RF, BF, LF, EF, sF, iF, WF, SF, KF, HF, uF
and helper functions they call. This gives us the complete decryption algorithm.
"""
import re

with open(r'unobfuscator\pending crack\bloxburg_script.lua', 'r', encoding='utf-8', errors='replace') as f:
    source = f.read()

ret_start = source.index('return({')
content = source[ret_start:]

def extract_method(name, src, max_len=200000):
    pat = re.compile(r'(?<![a-zA-Z0-9_])' + re.escape(name) + r'=function\(')
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
                    elif w == 'end': depth -= 1
                    elif w == 'until': depth -= 1
                    if w in ('if', 'elseif'): last_kw = w
                    elif w in ('then', 'function', 'do', 'repeat', 'end', 'until'): last_kw = None
                    if depth == 0: break
                i = j; continue
            i += 1
        results.append((start, src[start:i]))
    return results

def show(name, mx=5000):
    r = extract_method(name, content)
    if not r:
        print(f"\n{name}: NOT FOUND")
        return None
    for idx, (start, body) in enumerate(r):
        print(f"\n{'='*70}")
        print(f"{name} [{idx}] (len={len(body)}, pos={start})")
        print(f"{'='*70}")
        # Clean up the body for readability
        p = body.replace(';', ';\n')
        # Replace hex/binary literals with decimal for readability
        def hex_to_dec(m):
            try:
                val = int(m.group(0).replace('_', ''), 0)
                return str(val)
            except:
                return m.group(0)
        p_clean = re.sub(r'0[xXbBoO][0-9a-fA-F_]+', hex_to_dec, p)
        print(p_clean[:mx] if len(p_clean) <= mx else p_clean[:mx] + f"\n... ({len(p_clean)-mx} more)")
        
        calls = sorted(set(re.findall(r'z:(\w+)\(', body)))
        if calls: print(f"  calls z: {calls}")
        refs = sorted(set(re.findall(r'(?<![a-zA-Z0-9_\.])r\[(\d+|0[xXbBoO][0-9a-fA-F_]+)\]', body)))
        if refs:
            dec_refs = []
            for ref in refs:
                try:
                    dec_refs.append(str(int(ref.replace('_', ''), 0)))
                except:
                    dec_refs.append(ref)
            print(f"  r[] refs: {sorted(set(dec_refs), key=int)}")
        zrefs = sorted(set(re.findall(r'z\.(\w+)', body)))
        if zrefs: print(f"  z. refs: {zrefs}")
    return r

# Extract all string building/decryption functions
funcs = ['ZF', 'RF', 'BF', 'LF', 'EF', 'sF', 'iF', 'WF', 'SF', 'KF', 'HF', 'uF', 'oF', 'DF', 'jF', 'c9', 'Sy', 'Ry']
for name in funcs:
    show(name)

# Also find what r[11] is (used in ZF for hashing)
print(f"\n{'='*70}")
print("Searching for r[11] assignment")
print(f"{'='*70}")
# r[11] is used as r[11](a) in ZF — it's a hash function
# Look for C[11]= or r[11]= assignments
r11_assigns = list(re.finditer(r'(?:C|r)\[(?:11|0[xXbB]0*[bB])\]\s*=', content))
print(f"r[11] assignments: {len(r11_assigns)}")
for i, m in enumerate(r11_assigns[:5]):
    ctx = content[m.start():m.start()+100]
    print(f"  [{i}] pos={m.start()}: {repr(ctx[:80])}")

# Also check r[43] (used in SF)  
r43_assigns = list(re.finditer(r'(?:C|r)\[(?:43|0[xX]2[bB])\]\s*=', content))
print(f"\nr[43] assignments: {len(r43_assigns)}")
for i, m in enumerate(r43_assigns[:5]):
    ctx = content[m.start():m.start()+100]
    print(f"  [{i}] pos={m.start()}: {repr(ctx[:80])}")

# Check r[14] and r[4] (used in ZF condition)
print(f"\n{'='*70}")
print("Key r[] values used in ZF/string functions")
print(f"{'='*70}")
for idx in [4, 11, 14, 24, 35, 39, 43, 46]:
    assigns = list(re.finditer(r'C\[' + str(idx) + r'\]\s*=', content))
    print(f"  r[{idx}] assignments: {len(assigns)}")
    for i, m in enumerate(assigns[:3]):
        ctx = content[m.start():m.start()+120]
        print(f"    [{i}] {repr(ctx[:100])}")
