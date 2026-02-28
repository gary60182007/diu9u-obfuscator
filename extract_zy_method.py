import re

with open(r'unobfuscator\pending crack\bloxburg_script.lua', 'r', encoding='utf-8', errors='replace') as f:
    source = f.read()

# Find z:zy method definition
# It's defined as zy=function(z,...) inside the return table
# Search for zy= in the source
matches = list(re.finditer(r'zy\s*=\s*function\s*\(', source))
print(f"Found {len(matches)} 'zy=function(' matches")

for m in matches:
    pos = m.start()
    ctx = source[pos:pos+100]
    print(f"  pos {pos}: {ctx[:80]}...")

# Also find the main init function (Jy) that calls z:zy
jy_matches = list(re.finditer(r'Jy\s*=\s*function\s*\(', source))
print(f"\nFound {len(jy_matches)} 'Jy=function(' matches")
for m in jy_matches:
    pos = m.start()
    print(f"  pos {pos}: {source[pos:pos+100]}")

# Find the z:zy call context
zy_call = list(re.finditer(r':zy\(', source))
print(f"\nFound {len(zy_call)} ':zy(' calls")
for m in zy_call:
    pos = m.start()
    print(f"  pos {pos}: ...{source[max(0,pos-30):pos+50]}...")

# Extract the zy method body
# Need to find matching braces/end
if matches:
    start = matches[0].start()
    # Count parentheses and track function...end blocks
    # Simple approach: extract a large chunk and manually find the end
    chunk_size = 20000
    chunk = source[start:start+chunk_size]
    
    # Track nesting depth
    depth = 0
    i = 0
    func_stack = 0
    in_string = False
    string_char = None
    
    while i < len(chunk):
        c = chunk[i]
        if not in_string:
            # Check for function keyword
            if chunk[i:i+8] == 'function':
                func_stack += 1
                i += 8
                continue
            elif chunk[i:i+3] == 'end' and (i+3 >= len(chunk) or not chunk[i+3].isalnum()):
                func_stack -= 1
                if func_stack <= 0:
                    end_pos = i + 3
                    print(f"\nzy method body: pos {start} to {start+end_pos} ({end_pos} chars)")
                    break
                i += 3
                continue
        i += 1
    
    # Extract the method body
    body = chunk[:end_pos] if 'end_pos' in dir() else chunk[:5000]
    
    # Pretty-print by splitting on semicolons
    lines = body.replace(';', ';\n').split('\n')
    print(f"\n=== zy method body ({len(lines)} lines) ===")
    for i, line in enumerate(lines[:200]):
        line = line.strip()
        if line:
            print(f"  {i:4d}: {line[:150]}")

# Also find ALL z methods (the VM class methods)
print(f"\n=== Looking for z methods near zy ===")
# The return table contains method definitions like: methodName=function(z,...)
# Find the return table definition
ret_start = source.find('return({')
if ret_start == -1:
    ret_start = source.find('return(')
if ret_start >= 0:
    print(f"return( at pos {ret_start}")
    # List all method names defined in the return table
    # They look like: name=function(...) or name=value
    ret_chunk = source[ret_start:ret_start+500]
    method_defs = re.findall(r'(\w+)\s*=\s*(?:function|bit32|string|table|select)', ret_chunk)
    print(f"First methods in return table: {method_defs[:30]}")

# Find ALL method definitions of form XX=function(z,
all_methods = re.findall(r'(\w{1,3})\s*=\s*function\s*\(\s*z\s*[,)]', source)
print(f"\nAll z methods: {len(all_methods)} total")
unique_methods = sorted(set(all_methods))
print(f"Unique: {len(unique_methods)}")
for m in unique_methods[:50]:
    print(f"  z:{m}")

# Find the Jy method (main init) and extract it
print(f"\n=== Jy method (main init) ===")
jy_match = re.search(r'Jy\s*=\s*function\s*\(', source)
if jy_match:
    start = jy_match.start()
    chunk = source[start:start+3000]
    lines = chunk.replace(';', ';\n').split('\n')
    for i, line in enumerate(lines[:80]):
        line = line.strip()
        if line:
            print(f"  {i:4d}: {line[:150]}")

# Find the iy method (reader setup) 
print(f"\n=== iy method (reader setup) ===")
iy_match = re.search(r'iy\s*=\s*function\s*\(', source)
if iy_match:
    start = iy_match.start()
    chunk = source[start:start+5000]
    lines = chunk.replace(';', ';\n').split('\n')
    for i, line in enumerate(lines[:100]):
        line = line.strip()
        if line:
            print(f"  {i:4d}: {line[:150]}")
