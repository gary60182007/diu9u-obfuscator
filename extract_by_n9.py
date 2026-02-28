"""
Extract z:By, z:N9, and related deserialization methods.
Also find string decryption mechanism (not XOR-based).
"""
import re

with open(r'unobfuscator\pending crack\bloxburg_script.lua', 'r', encoding='utf-8', errors='replace') as f:
    source = f.read()

ret_start = source.index('return({')
content = source[ret_start:]

def extract_method(name, src, max_len=5000):
    pat = re.compile(re.escape(name) + r'=function\(')
    results = []
    for m in pat.finditer(src):
        start = m.start()
        i = m.end()
        while i < len(src) and src[i] != ')':
            i += 1
        i += 1
        depth = 1
        pos = i
        while pos < len(src) and depth > 0:
            if src[pos:pos+8] == 'function' and (pos == 0 or not src[pos-1].isalnum()):
                after = pos + 8
                if after < len(src) and src[after] in '( ':
                    depth += 1
            elif src[pos:pos+3] == 'end' and (pos == 0 or not src[pos-1].isalnum()):
                after = pos + 3
                if after >= len(src) or not src[after].isalnum():
                    depth -= 1
                    if depth == 0:
                        pos += 3
                        break
            pos += 1
        body = src[start:pos]
        results.append((start, body))
    return results

def print_method(name, src, max_display=5000):
    results = extract_method(name, src)
    print(f"\n{'='*70}")
    print(f"Method: {name} ({len(results)} match(es))")
    print(f"{'='*70}")
    for i, (pos, body) in enumerate(results):
        print(f"--- pos={pos}, len={len(body)} ---")
        pretty = body.replace(';', ';\n')
        if len(pretty) > max_display:
            print(pretty[:max_display])
            print(f"... ({len(pretty) - max_display} more chars)")
        else:
            print(pretty)

# Key deserialization methods
for name in ['By', 'N9', 'Ny', 'Dy', 'Ey', 'Fy']:
    print_method(name, content)

# Find what methods By calls
by_results = extract_method('By', content)
if by_results:
    by_body = by_results[0][1]
    calls = re.findall(r'z:(\w+)\(', by_body)
    print(f"\nBy calls: {sorted(set(calls))}")
    
    # Extract each method By calls
    for called in sorted(set(calls)):
        if called != 'By':
            print_method(called, content, max_display=2000)

# Find what methods N9 calls
n9_results = extract_method('N9', content)
if n9_results:
    n9_body = n9_results[0][1]
    calls = re.findall(r'z:(\w+)\(', n9_body)
    print(f"\nN9 calls: {sorted(set(calls))}")

# Search for string decryption patterns more broadly
print(f"\n{'='*70}")
print(f"BROADER SEARCH: String operations in VM")
print(f"{'='*70}")

# Find all uses of r[31] (char table from Ny)
for m in re.finditer(r'r\[31\]', content[:20000]):
    ctx = content[max(0,m.start()-80):m.start()+80]
    print(f"  r[31] at {m.start()}: ...{ctx}...")

# Search for sub (buffer.readstring might be the string reader)
# The VM might read raw string bytes and then do something with them
for m in re.finditer(r'readstring', content):
    ctx = content[max(0,m.start()-100):m.start()+100]
    print(f"\n  readstring at {m.start()}: ...{ctx}...")

# Search for char(
char_uses = list(re.finditer(r'\.char\(', content))
print(f"\nFound {len(char_uses)} .char( uses")
for m in char_uses[:20]:
    ctx = content[max(0,m.start()-80):m.start()+120]
    print(f"  at {m.start()}: ...{ctx}...")

# Search for Ny method (which sets up r[31] char table and string functions)
print_method('Ny', content, max_display=3000)
