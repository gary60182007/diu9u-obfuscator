import re

with open(r'unobfuscator\pending crack\bloxburg_script.lua', 'r', encoding='utf-8', errors='replace') as f:
    source = f.read()

def extract_method_body(name, max_len=10000):
    pattern = re.compile(rf'(?<!\w){re.escape(name)}\s*=\s*function\s*\(')
    matches = list(pattern.finditer(source))
    if not matches:
        return None, -1
    m = matches[0]
    start = m.start()
    chunk = source[start:start+max_len]
    depth = 0
    i = 0
    end_pos = len(chunk)
    while i < len(chunk):
        if chunk[i] in ('"', "'"):
            q = chunk[i]
            i += 1
            while i < len(chunk) and chunk[i] != q:
                if chunk[i] == '\\':
                    i += 1
                i += 1
            i += 1
            continue
        if chunk[i:i+2] == '[[':
            i = chunk.index(']]', i) + 2
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
                    end_pos = j
                    break
            i = j
        else:
            i += 1
    return chunk[:end_pos], start

def pretty(body):
    lines = body.replace(';', ';\n').split('\n')
    result = []
    for line in lines:
        line = line.strip()
        if line:
            result.append(line)
    return result

# Extract the full deserialization chain
# iy -> hy -> ly -> ... (all the state machine methods)
methods = ['hy', 'ly', 'Ky', 'Yy', 'ny', 'Sy', 'Ay', 'Qy', 'uy',
           'sF', 'OF', 'HF', 'WF', 'pF', 'Ly', 'RF',
           'C9', 'zy', 'Jy', 'iy',
           'cy', 'wy', 'v9', 'y9', 'U9', 'JF', 'kF', 'AF',
           'lF', 'tF', 'dF', 'cF', '_F', 'IF', 'mF',
           'X9', 'Gy', 'YF', 'hF', 'gy',
           'Xy', 'yF', 'MF', 'Vy', 'L9',
           'By', 'Dy', 'Ey', 'Fy', 'Hy', 'Iy', 'My', 'Ny', 'Oy', 'Py']

print("=== EXTRACTING DESERIALIZATION CHAIN ===\n")

extracted = {}
for name in methods:
    body, pos = extract_method_body(name)
    if body:
        extracted[name] = (body, pos)
        lines = pretty(body)
        print(f"--- z:{name} (pos {pos}, {len(body)} chars, {len(lines)} lines) ---")
        for i, line in enumerate(lines[:40]):
            print(f"  {i:3d}: {line[:160]}")
        if len(lines) > 40:
            print(f"  ... ({len(lines) - 40} more lines)")
        print()

# Now trace the call graph
print("\n=== CALL GRAPH ===")
for name in sorted(extracted.keys()):
    body, pos = extracted[name]
    # Find calls to z:XX() pattern
    calls = re.findall(r'z:(\w+)\(', body)
    # Find calls to r[N]() pattern
    r_calls = re.findall(r'[rCWQ]\[(\d+|0[xXbBoO][0-9a-fA-F_]+)\]\(', body)
    r_indices = set()
    for rc in r_calls:
        try:
            if rc.startswith('0'):
                r_indices.add(int(rc, 0))
            else:
                r_indices.add(int(rc))
        except:
            pass
    
    unique_calls = sorted(set(calls))
    if unique_calls or r_indices:
        print(f"  z:{name} calls: {unique_calls}")
        if r_indices:
            print(f"    reader calls: r[{sorted(r_indices)}]")

# Focus on the MAIN deserialization function
# From the Jy flow: W=73 -> W=41 -> W=20 -> W=99
# W=20 calls z:iy which calls z:hy
# z:hy is the heavy lifter

if 'hy' in extracted:
    print("\n=== DETAILED z:hy ANALYSIS ===")
    body, pos = extracted['hy']
    lines = pretty(body)
    for i, line in enumerate(lines):
        print(f"  {i:3d}: {line[:180]}")

# Find the method that reads prototype fields
# Look for methods that assign to C[1]..C[11] or create tables with 11 fields
print("\n=== Looking for prototype builder (assigns C[1]..C[11]) ===")
for name in sorted(extracted.keys()):
    body, _ = extracted[name]
    # Check for assignments to array indices [1]..[11]
    idx_assigns = re.findall(r'\[(\d+)\]\s*=', body)
    if idx_assigns:
        indices = set(int(x) for x in idx_assigns)
        if len(indices) >= 5 and max(indices) <= 20:
            print(f"  z:{name} assigns to indices: {sorted(indices)}")

# Also find where buffer.readu8 is called directly (not through r[39])
print("\n=== Direct buffer read patterns ===")
for name in sorted(extracted.keys()):
    body, _ = extracted[name]
    if 'readu8' in body or 'readu16' in body or 'readu32' in body or 'readf64' in body or 'readstring' in body:
        reads = re.findall(r'read\w+', body)
        print(f"  z:{name}: {reads}")
