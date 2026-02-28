import re

with open(r'unobfuscator\pending crack\bloxburg_script.lua', 'r', encoding='utf-8', errors='replace') as f:
    source = f.read()

def extract_method(name, max_len=30000):
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
            idx = chunk.find(']]', i)
            if idx >= 0:
                i = idx + 2
            else:
                i += 2
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

def pretty(body, max_lines=200):
    lines = body.replace(';', ';\n').split('\n')
    result = []
    for line in lines[:max_lines]:
        line = line.strip()
        if line:
            result.append(line)
    return result

# Extract z:q (the ENTRY POINT)
print("=== z:q (ENTRY POINT) ===")
body, pos = extract_method('q')
if body:
    lines = pretty(body, 300)
    print(f"Position: {pos}, Length: {len(body)} chars, {len(lines)} lines")
    for i, line in enumerate(lines):
        print(f"  {i:3d}: {line[:180]}")

# Find what z:q calls
if body:
    calls = sorted(set(re.findall(r'z:(\w+)\(', body)))
    print(f"\nz:q calls: {calls}")
    
    r_calls = set()
    for rc in re.findall(r'\w\[(\d+|0[xXbBoO][0-9a-fA-F_]+)\]\(', body):
        try:
            r_calls.add(int(rc, 0))
        except:
            pass
    print(f"Reader calls: {sorted(r_calls)}")

# Now extract ALL methods called by z:q
print(f"\n{'='*60}")
print(f"TRACING z:q CALL CHAIN")
print(f"{'='*60}")

# Methods to extract based on z:q's call list
if body:
    for method_name in calls:
        mbody, mpos = extract_method(method_name, 5000)
        if mbody:
            mlines = pretty(mbody, 60)
            print(f"\n--- z:{method_name} (pos {mpos}, {len(mbody)} chars) ---")
            for i, line in enumerate(mlines):
                print(f"  {i:3d}: {line[:180]}")
            
            # Show what this method calls
            sub_calls = sorted(set(re.findall(r'z:(\w+)\(', mbody)))
            sub_r = set()
            for rc in re.findall(r'\w\[(\d+|0[xXbBoO][0-9a-fA-F_]+)\]\(', mbody):
                try:
                    sub_r.add(int(rc, 0))
                except:
                    pass
            if sub_calls:
                print(f"  -> calls: {sub_calls}")
            if sub_r:
                print(f"  -> reader: r[{sorted(sub_r)}]")
