"""
Find where ZF is called from, and trace the full C[58] prototype deserializer chain.
Also extract xF, UF, oF and any functions that call ZF.
"""
import re

with open(r'unobfuscator\pending crack\bloxburg_script.lua', 'r', encoding='utf-8', errors='replace') as f:
    source = f.read()

ret_start = source.index('return({')
content = source[ret_start:]

# Find all callers of ZF
zf_calls = list(re.finditer(r':ZF\(', content))
print(f"ZF is called {len(zf_calls)} times")
for i, m in enumerate(zf_calls):
    ctx = content[max(0, m.start()-80):m.start()+60]
    print(f"  [{i}] pos={m.start()}: ...{repr(ctx[-100:])}")

# Find all callers of xF
xf_calls = list(re.finditer(r':xF\(', content))
print(f"\nxF is called {len(xf_calls)} times")
for i, m in enumerate(xf_calls):
    ctx = content[max(0, m.start()-80):m.start()+60]
    print(f"  [{i}] pos={m.start()}: ...{repr(ctx[-100:])}")

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

def show(name, mx=3000):
    r = extract_method(name, content)
    if not r: print(f"\n{name}: NOT FOUND"); return None
    for idx, (start, body) in enumerate(r):
        print(f"\n{'='*70}")
        print(f"{name} [{idx}] (len={len(body)}, pos={start})")
        print(f"{'='*70}")
        p = body.replace(';', ';\n')
        print(p[:mx] if len(p) <= mx else p[:mx] + f"\n... ({len(p)-mx} more)")
        calls = sorted(set(re.findall(r'z:(\w+)\(', body)))
        if calls: print(f"  calls: {calls}")
        refs = sorted(set(re.findall(r'(?<![a-zA-Z0-9_\.])(?:r|C|Q)\[(\d+)\]', body)))
        if refs: print(f"  table refs: {refs}")
        zrefs = sorted(set(re.findall(r'z\.(\w+)', body)))
        if zrefs: print(f"  z. refs: {zrefs}")
    return r

# Extract key functions
for name in ['xF', 'UF', 'oF', 'aF', 'q9', 'P9', 'd9', 'm9']:
    show(name)

# Also find which METHOD contains the ZF call
print(f"\n{'='*70}")
print("Finding which method contains ZF calls")
print(f"{'='*70}")

# For each ZF call, find the enclosing method
for i, m in enumerate(zf_calls):
    pos = m.start()
    # Search backwards for 'METHODNAME=function('
    search_back = content[max(0, pos-5000):pos]
    # Find the last method definition
    method_defs = list(re.finditer(r'([a-zA-Z_]\w*)=function\(', search_back))
    if method_defs:
        last_def = method_defs[-1]
        method_name = last_def.group(1)
        # Check if it's a z method (part of the return table)
        print(f"  ZF call [{i}] at pos {pos} is inside method: {method_name}")
        # Show the context around the ZF call
        ctx = content[pos-20:pos+60]
        print(f"    Context: {repr(ctx)}")
    else:
        print(f"  ZF call [{i}] at pos {pos}: could not find enclosing method")

# Also check: does C[58] call ZF directly or indirectly?
# C[58] calls xF. Does xF call ZF?
print(f"\n{'='*70}")
print("Call chain from C[58]")
print(f"{'='*70}")

# Already extracted xF above, check if it calls ZF
xf_results = extract_method('xF', content)
if xf_results:
    body = xf_results[0][1]
    if ':ZF(' in body:
        print("xF calls ZF directly!")
    else:
        # What does xF call?
        calls = sorted(set(re.findall(r'z:(\w+)\(', body)))
        print(f"xF calls: {calls}")
        # Check each called method for ZF
        for c in calls:
            c_results = extract_method(c, content)
            if c_results:
                if ':ZF(' in c_results[0][1]:
                    print(f"  -> {c} calls ZF!")
                else:
                    sub_calls = sorted(set(re.findall(r'z:(\w+)\(', c_results[0][1])))
                    print(f"  -> {c} calls: {sub_calls}")
                    for sc in sub_calls:
                        sc_results = extract_method(sc, content)
                        if sc_results and ':ZF(' in sc_results[0][1]:
                            print(f"     -> {sc} calls ZF!")
