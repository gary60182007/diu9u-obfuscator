import re

with open(r'unobfuscator\pending crack\bloxburg_script.lua', 'r', encoding='utf-8', errors='replace') as f:
    src = f.read()

def extract_func(name, src):
    pat = re.compile(name + r'=function\([^)]+\)')
    m = pat.search(src)
    if not m:
        print(f"{name}: NOT FOUND")
        return None
    start = m.start()
    pos = m.end()
    depth = 1
    in_str = False
    sc = None
    while pos < len(src) and depth > 0:
        c = src[pos]
        if in_str:
            if c == '\\':
                pos += 2
                continue
            if c == sc:
                in_str = False
            pos += 1
            continue
        if c in '"\'':
            in_str = True
            sc = c
            pos += 1
            continue
        if c.isalpha() or c == '_':
            j = pos
            while j < len(src) and (src[j].isalnum() or src[j] == '_'):
                j += 1
            w = src[pos:j]
            if w in ('function', 'do', 'repeat'):
                depth += 1
            elif w == 'then':
                depth += 1
            elif w == 'end':
                depth -= 1
            elif w == 'until':
                depth -= 1
            pos = j
            continue
        pos += 1
    body = src[start:pos]
    return body

for name in ['DF', 'jF', 'xF']:
    body = extract_func(name, src)
    if body:
        print(f"\n{'='*60}")
        print(f"{name} ({len(body)} chars):")
        print(f"{'='*60}")
        clean = body.replace(';', ';\n')
        print(clean[:3000])
        if len(body) > 3000:
            print(f"... ({len(body)-3000} more chars)")
