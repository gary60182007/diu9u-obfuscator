"""Extract F9 and trace the full proto factory call chain."""
import re

with open(r'unobfuscator\pending crack\bloxburg_script.lua', 'r', encoding='utf-8', errors='replace') as f:
    src = f.read()

def extract_func_body(name, src, max_len=5000):
    pat = re.compile(name + r'=function\([^)]+\)')
    m = pat.search(src)
    if not m:
        return None, None
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
    return src[start:pos], start

# Extract F9
body, pos = extract_func_body('F9', src)
if body:
    print(f"F9 ({len(body)} chars) at pos {pos}:")
    clean = body.replace(';', ';\n')
    print(clean)
    
    # Find methods called by F9
    methods = sorted(set(re.findall(r'z:(\w+)\(', body)))
    print(f"\nF9 calls: {methods}")
    
    # Find C[] index accesses
    c_indices = set()
    for m in re.findall(r'(?:C|w|q)\[(\d+|0[xXbBoO][0-9a-fA-F_]+)\]', body):
        try:
            c_indices.add(int(m.replace('_', ''), 0))
        except:
            c_indices.add(m)
    print(f"State indices: {sorted(c_indices)}")

print()

# Now find what calls F9
f9_calls = list(re.finditer(r':F9\(', src))
print(f"F9 called {len(f9_calls)} times:")
for m in f9_calls:
    start = max(0, m.start()-100)
    end = min(len(src), m.end()+100)
    ctx = src[start:end].replace('\n', ' ')
    print(f"  pos={m.start()}: ...{ctx[:250]}...")

print()

# The proto factory is likely in the function that calls F9
# Find the containing function
for m in f9_calls:
    search_start = max(0, m.start()-10000)
    chunk = src[search_start:m.start()]
    func_defs = list(re.finditer(r'(\w+)=function\(([^)]*)\)', chunk))
    if func_defs:
        last_def = func_defs[-1]
        func_name = last_def.group(1)
        func_params = last_def.group(2)
        print(f"F9 is called from: {func_name}({func_params})")
        
        # Extract that function
        body2, pos2 = extract_func_body(func_name, src, max_len=15000)
        if body2:
            print(f"\n{func_name} ({len(body2)} chars):")
            clean2 = body2.replace(';', ';\n')
            print(clean2[:5000])
            if len(body2) > 5000:
                print(f"... ({len(body2)-5000} more chars)")
            
            # Methods called
            methods2 = sorted(set(re.findall(r'z:(\w+)\(', body2)))
            print(f"\n{func_name} calls: {methods2}")
