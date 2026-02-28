"""
Extract z:py, z:UF, and C[58] from the Lua source to understand
the deserialization format.
"""
import re, json

with open(r'unobfuscator\pending crack\bloxburg_script.lua', 'r', encoding='utf-8', errors='replace') as f:
    source = f.read()

# The source is a single return({...}) on line 11
# Extract the return table content
ret_start = source.index('return({')
content = source[ret_start:]

# Find all z: method definitions
# Pattern: name=function(z,...) or name=function(z,z,...) 
method_pat = re.compile(r'([A-Za-z_]\w*)=function\(([^)]*)\)')

# Extract methods by name with proper brace matching
def extract_method(name, src):
    # Find name=function(
    pat = re.compile(re.escape(name) + r'=function\(')
    matches = list(pat.finditer(src))
    results = []
    for m in matches:
        start = m.start()
        # Find matching end by counting braces/keywords
        depth = 0
        i = m.end()
        # We're inside the function params, find the closing )
        while i < len(src) and src[i] != ')':
            i += 1
        i += 1  # skip )
        depth = 1  # function ... end
        
        # Simple approach: count function/end keywords
        pos = i
        while pos < len(src) and depth > 0:
            # Look for keywords
            if src[pos:pos+8] == 'function' and (pos == 0 or not src[pos-1].isalnum()):
                # Check it's followed by ( or whitespace (anonymous function)
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

# Key methods to extract
targets = ['py', 'UF', 'F9', 'o9', 'C9', 'V9', 'X9', 'e9', 'zy']

for name in targets:
    results = extract_method(name, content)
    print(f"\n{'='*60}")
    print(f"Method: {name} ({len(results)} matches)")
    print(f"{'='*60}")
    for i, (pos, body) in enumerate(results):
        print(f"\n--- Match {i} at pos {pos} (len {len(body)}) ---")
        # Pretty print with line breaks
        pretty = body.replace(';', ';\n')
        # Limit output
        if len(pretty) > 3000:
            print(pretty[:3000])
            print(f"... ({len(pretty) - 3000} more chars)")
        else:
            print(pretty)

# Also search for C[58] definition pattern
print(f"\n{'='*60}")
print(f"Searching for C[58] or similar patterns...")
print(f"{'='*60}")

# In preprocessed form, 58 could be 0x3A or 58 or 0b111010
for pat_str in [r'\[58\]\s*=\s*function', r'\[0[xX]3[aA]\]\s*=\s*function']:
    for m in re.finditer(pat_str, content):
        ctx = content[max(0, m.start()-50):m.end()+200]
        print(f"\nFound at pos {m.start()}: ...{ctx[:300]}...")

# Search for patterns that look like prototype deserialization
# (reading multiple fields into a table/array)
print(f"\n{'='*60}")
print(f"Searching for string construction patterns (string.char + bxor)...")
print(f"{'='*60}")

# Look for string.char usage near bxor/lrotate (decryption)
for m in re.finditer(r'string\.char', content):
    ctx = content[max(0, m.start()-100):m.start()+200]
    if 'bxor' in ctx or 'lrotate' in ctx or 'rshift' in ctx or 'band' in ctx:
        print(f"\nAt pos {m.start()}:")
        print(f"  ...{ctx}...")

# Also search for char table construction (building strings byte by byte)
print(f"\n{'='*60}")
print(f"Searching for table.concat near string building...")
print(f"{'='*60}")

for m in re.finditer(r'table\.concat', content):
    ctx = content[max(0, m.start()-200):m.start()+100]
    if 'char' in ctx or 'bxor' in ctx:
        print(f"\nAt pos {m.start()}:")
        print(f"  ...{ctx}...")

# Search for the string reader function (likely in r[31] or nearby)
# It should read a length, then read bytes and XOR-decrypt them
print(f"\n{'='*60}")
print(f"Searching for XOR decryption loops (for + bxor + char)...")
print(f"{'='*60}")

for m in re.finditer(r'for\s+\w+\s*=\s*\d+\s*,', content):
    ctx = content[m.start():m.start()+500]
    if 'bxor' in ctx and ('char' in ctx or 'concat' in ctx):
        print(f"\nAt pos {m.start()}:")
        # Extract the full loop
        depth = 0
        end = m.start()
        for_depth = 0
        i = m.start()
        while i < len(content) and i < m.start() + 2000:
            if content[i:i+3] == 'for' and (i == 0 or not content[i-1].isalnum()):
                for_depth += 1
            elif content[i:i+3] == 'end' and (i == 0 or not content[i-1].isalnum()):
                if i+3 >= len(content) or not content[i+3].isalnum():
                    for_depth -= 1
                    if for_depth == 0:
                        end = i + 3
                        break
            i += 1
        loop = content[m.start():end]
        print(f"  {loop[:800]}")
