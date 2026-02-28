"""
Properly extract Lua methods using correct block depth counting.
Handles function/end, for/do/end, while/do/end, if/then/end, repeat/until.
"""
import re

with open(r'unobfuscator\pending crack\bloxburg_script.lua', 'r', encoding='utf-8', errors='replace') as f:
    source = f.read()

ret_start = source.index('return({')
content = source[ret_start:]

BLOCK_OPENERS = {'function', 'do', 'then', 'repeat'}
BLOCK_CLOSERS = {'end', 'until'}

def is_word_boundary(src, pos, word_len):
    before_ok = (pos == 0 or not src[pos-1].isalnum() and src[pos-1] != '_')
    after_pos = pos + word_len
    after_ok = (after_pos >= len(src) or not src[after_pos].isalnum() and src[after_pos] != '_')
    return before_ok and after_ok

def extract_method_proper(name, src, max_len=50000):
    pat = re.compile(re.escape(name) + r'=function\(')
    results = []
    for m in pat.finditer(src):
        start = m.start()
        pos = start + len(name) + len('=function(')
        # Skip past params to closing )
        paren_depth = 1
        while pos < len(src) and paren_depth > 0:
            if src[pos] == '(': paren_depth += 1
            elif src[pos] == ')': paren_depth -= 1
            pos += 1
        
        # Now count block depth starting from 1 (for the function keyword)
        depth = 1
        i = pos
        in_string = False
        string_char = None
        
        while i < len(src) and depth > 0 and (i - start) < max_len:
            c = src[i]
            
            # Handle strings
            if in_string:
                if c == '\\':
                    i += 2
                    continue
                if c == string_char:
                    in_string = False
                i += 1
                continue
            
            if c in '"\'':
                in_string = True
                string_char = c
                i += 1
                continue
            
            # Handle long strings [[...]]
            if c == '[' and i+1 < len(src) and src[i+1] in '[=':
                # Find matching ]]
                eq_count = 0
                j = i + 1
                while j < len(src) and src[j] == '=':
                    eq_count += 1
                    j += 1
                if j < len(src) and src[j] == '[':
                    # Long string, find matching close
                    close = ']' + '=' * eq_count + ']'
                    end_pos = src.find(close, j + 1)
                    if end_pos >= 0:
                        i = end_pos + len(close)
                        continue
                i += 1
                continue
            
            # Handle comments
            if c == '-' and i+1 < len(src) and src[i+1] == '-':
                # Skip to end of line
                nl = src.find('\n', i)
                i = nl + 1 if nl >= 0 else len(src)
                continue
            
            # Check for keywords
            if c.isalpha():
                # Extract word
                j = i
                while j < len(src) and (src[j].isalnum() or src[j] == '_'):
                    j += 1
                word = src[i:j]
                
                if word in BLOCK_OPENERS and is_word_boundary(src, i, len(word)):
                    depth += 1
                elif word in BLOCK_CLOSERS and is_word_boundary(src, i, len(word)):
                    depth -= 1
                    if depth == 0:
                        i = j
                        break
                i = j
                continue
            
            i += 1
        
        body = src[start:i]
        results.append((start, body))
    return results

def show(name, max_display=4000):
    results = extract_method_proper(name, content)
    print(f"\n{'='*70}")
    print(f"{name} ({len(results)} match, len={len(results[0][1]) if results else 0})")
    print(f"{'='*70}")
    for _, body in results:
        pretty = body.replace(';', ';\n')
        if len(pretty) > max_display:
            print(pretty[:max_display])
            print(f"\n... ({len(pretty)-max_display} more)")
        else:
            print(pretty)
    return results

# Extract all key deserialization methods
uf = show('UF', 8000)
by = show('By', 4000)
wy = show('Wy', 2000)

# Find what UF actually calls
if uf:
    uf_body = uf[0][1]
    calls = sorted(set(re.findall(r'z:(\w+)\(', uf_body)))
    print(f"\nUF calls: {calls}")
    for c in calls:
        if c not in ('UF', 'By', 'Wy'):
            show(c, 4000)

# Now extract N9 chain
n9 = show('N9', 4000)
if n9:
    n9_body = n9[0][1]
    calls = sorted(set(re.findall(r'z:(\w+)\(', n9_body)))
    print(f"\nN9 calls: {calls}")
    for c in calls:
        show(c, 4000)

# Extract F9 properly
f9 = show('F9', 8000)
if f9:
    f9_body = f9[0][1]
    calls = sorted(set(re.findall(r'z:(\w+)\(', f9_body)))
    print(f"\nF9 calls: {calls}")

# Extract zy (closure factory + VM interpreter) - just show size
zy = extract_method_proper('zy', content)
if zy:
    print(f"\nzy: {len(zy[0][1])} chars (VM interpreter)")

# Also extract the string-related Ny method
show('Ny', 4000)

# Look for the string reader function  
# From Ny: C[29] = function that joins string parts
# The actual string reading from buffer is likely in a method that
# reads bytes and builds a string
# Search for buffer.readstring or string construction
print(f"\n{'='*70}")
print(f"Methods that reference r[31] or r[29] (string functions)")
print(f"{'='*70}")

# Find method 'wy' which was seen setting r[31]
show('wy', 2000)

# Search for methods that read strings from buffer
# Look for patterns like: for i=1,len do ... r[39]() or readu8 ... end
print(f"\n{'='*70}")
print(f"Searching for string reading patterns")
print(f"{'='*70}")

# Find all method names in the return table
all_methods = re.findall(r'([A-Za-z]\w*)=function\(', content[:500000])
method_names = sorted(set(all_methods))
print(f"Total methods: {len(method_names)}")

# For each method, check if it contains both r[46]/r[39] calls AND r[31] access
for name in method_names:
    results = extract_method_proper(name, content)
    if not results:
        continue
    body = results[0][1]
    if len(body) > 50000:
        continue
    # Check for string-building patterns
    has_buf_read = 'r[39]' in body or 'r[46]' in body or 'readu8' in body
    has_str = 'r[31]' in body or 'char' in body or 'concat' in body
    has_loop = 'for ' in body
    if has_buf_read and has_str and has_loop:
        print(f"\n--- {name} (len={len(body)}) ---")
        pretty = body.replace(';', ';\n')
        print(pretty[:2000])
