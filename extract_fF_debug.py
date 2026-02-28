"""
Extract fF and debug the lF call issue.
Also check if there are multiple lF definitions.
"""
import re

with open(r'unobfuscator\pending crack\bloxburg_script.lua', 'r', encoding='utf-8', errors='replace') as f:
    source = f.read()

ret_start = source.index('return({')
content = source[ret_start:]

# Check for multiple lF definitions
lf_matches = list(re.finditer(r'(?<![a-zA-Z0-9_])lF=function\(', content))
print(f"Number of lF=function( definitions: {len(lf_matches)}")
for i, m in enumerate(lf_matches):
    ctx = content[m.start():m.start()+200]
    print(f"  [{i}] pos={m.start()}: {repr(ctx[:150])}")

# Also check for _lF or similar
lf2_matches = list(re.finditer(r'(?<![a-zA-Z0-9_])_lF=function\(', content))
print(f"Number of _lF=function( definitions: {len(lf2_matches)}")

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
    if not r: print(f"\n{name}: NOT FOUND"); return r
    for idx, (start, body) in enumerate(r):
        print(f"\n{'='*70}")
        print(f"{name} [{idx}] (len={len(body)}, pos={start})")
        print(f"{'='*70}")
        p = body.replace(';', ';\n')
        print(p[:mx] if len(p) <= mx else p[:mx] + f"\n... ({len(p)-mx} more)")
        calls = sorted(set(re.findall(r'z:(\w+)\(', body)))
        if calls: print(f"  calls: {calls}")
        refs = sorted(set(re.findall(r'(?<![a-zA-Z0-9_])r\[(\d+)\]', body)))
        if refs: print(f"  r[] refs: {refs}")
        zrefs = sorted(set(re.findall(r'z\.(\w+)', body)))
        if zrefs: print(f"  z. refs: {zrefs}")
    return r

# Key functions to extract
for n in ['fF', 'lF', 'kF', 'AF', 'SF', 'PF']:
    show(n)

# Also check: what other functions does fF call?
# And check F9 which defines the lazy deserializer W
print(f"\n{'='*70}")
print("Checking F9 structure")
print(f"{'='*70}")
f9_matches = list(re.finditer(r'(?<![a-zA-Z0-9_])F9=function\(', content))
print(f"F9 definitions: {len(f9_matches)}")
for i, m in enumerate(f9_matches):
    start = m.start()
    # Show first 300 chars
    ctx = content[start:start+500]
    print(f"  [{i}] pos={start}: {repr(ctx[:400])}")

# Extract the W (lazy deserializer) function from inside F9
# Look for the pattern where W is defined as a local function
print(f"\n{'='*70}")
print("Looking for lazy deserializer W inside F9")
print(f"{'='*70}")

# F9 defines: C[58] = function() ... end and W = function() ... end
# Let me find F9 and look for local function definitions inside it
f9_body = extract_method('F9', content)
if f9_body:
    body = f9_body[0][1]
    print(f"F9 body length: {len(body)}")
    # Find function assignments inside F9
    func_defs = list(re.finditer(r'(\w+)\s*=\s*function\(', body))
    for fd in func_defs:
        fname = fd.group(1)
        pos = fd.start()
        ctx = body[pos:pos+100]
        print(f"  {fname} at pos {pos}: {repr(ctx[:80])}")
    
    # Show the first 2000 chars of F9
    p = body.replace(';', ';\n')
    print(f"\nF9 first 3000 chars:")
    print(p[:3000])
