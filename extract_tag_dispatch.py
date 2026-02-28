import re

with open(r'unobfuscator\pending crack\bloxburg_script.lua', 'r', encoding='utf-8', errors='replace') as f:
    source = f.read()

def extract_method(name, max_len=5000):
    pattern = re.compile(rf'{re.escape(name)}\s*=\s*function\s*\(')
    m = pattern.search(source)
    if not m:
        return None, -1
    
    start = m.start()
    chunk = source[start:start+max_len]
    
    # Track function/end nesting
    depth = 0
    i = 0
    while i < len(chunk):
        # Skip string literals
        if chunk[i] in ('"', "'"):
            q = chunk[i]
            i += 1
            while i < len(chunk) and chunk[i] != q:
                if chunk[i] == '\\':
                    i += 1
                i += 1
            i += 1
            continue
        
        word = ''
        if chunk[i].isalpha() or chunk[i] == '_':
            j = i
            while j < len(chunk) and (chunk[j].isalnum() or chunk[j] == '_'):
                j += 1
            word = chunk[i:j]
            
            if word == 'function':
                depth += 1
            elif word == 'end':
                depth -= 1
                if depth <= 0:
                    body = chunk[:j]
                    return body, start
            i = j
        else:
            i += 1
    
    return chunk[:3000], start

# Extract key methods in the tag dispatch chain
methods_to_extract = [
    'hy',  # Heavy lifting setup (called from iy)
    'sF',  # Tag dispatcher (C>100 vs <=100)
    'OF',  # Tag handler for C>100 (handles 0x73)
    'HF',  # Tag handler for C<=100 (handles 0x1D, 0x57, etc.)
    'WF',  # Another dispatcher
    'pF',  # Sub-dispatcher
    'Ly',  # String reader? (from earlier analysis: z:Ly(W))
    'ny',  # State machine helper (from r[50])
    'Ay',  # r[46] = function() return z:Ay(r); end
    'uy',  # r[45] calls z:uy
    'Ky',  # Reader function setup
    'Yy',  # Main deserializaton loop?
    'cy',  # Another method with readu8
    'wy',  # r[31][z]=C(z) - char table setup?
]

print("=== Extracting tag dispatch methods ===\n")
for name in methods_to_extract:
    body, pos = extract_method(name)
    if body:
        lines = body.replace(';', ';\n').split('\n')
        print(f"--- z:{name} (pos {pos}, {len(body)} chars) ---")
        for i, line in enumerate(lines[:60]):
            line = line.strip()
            if line:
                print(f"  {i:3d}: {line[:140]}")
        print()
    else:
        print(f"--- z:{name}: NOT FOUND ---\n")

# Also search for specific patterns
print("\n=== Tag value patterns ===")

# Find all comparisons with hex values > 0x70
tag_comparisons = re.findall(r'==\s*0[xX]([0-9a-fA-F]+)', source)
tag_vals = set()
for tc in tag_comparisons:
    v = int(tc, 16)
    if 20 < v < 256:
        tag_vals.add(v)

print(f"All hex constants compared with ==: {sorted(tag_vals)}")

# Focus on the ones that appear in tag dispatch context
for tv in sorted(tag_vals):
    if tv in [0x73, 0x9E, 0x1D, 0xD8, 0x57, 0x36]:
        count = len(re.findall(rf'0[xX]0*{tv:x}', source, re.IGNORECASE))
        print(f"  0x{tv:02X} ({tv}): {count} occurrences")

# Find where 0x36 is used as a tag
print("\n=== 0x36 (54) usage ===")
matches_36 = re.finditer(r'0[xX]0*36[^0-9a-fA-F]', source)
for m in list(matches_36)[:20]:
    ctx = source[max(0,m.start()-40):m.end()+40]
    ctx = ctx.replace('\n', ' ')
    print(f"  pos {m.start()}: ...{ctx}...")

# Find all z method calls that pass tag values
print("\n=== Looking for the main read loop (reads tag, dispatches) ===")
# Pattern: read a byte, then switch/dispatch on it
tag_read_patterns = re.finditer(r'(\w+)\s*=\s*(\w)\[(\d+|0[xXbBoO][0-9a-fA-F_]+)\]\(\)', source)
for m in list(tag_read_patterns)[:30]:
    full = m.group(0)
    var = m.group(1)
    r_var = m.group(2)
    idx_raw = m.group(3)
    try:
        if idx_raw.startswith('0'):
            idx = int(idx_raw, 0)
        else:
            idx = int(idx_raw)
    except:
        idx = -1
    if idx in [39, 46, 47]:  # reader function indices
        pos = m.start()
        ctx = source[pos:pos+200].replace('\n', ' ')
        print(f"  pos {pos}: {ctx[:150]}")
