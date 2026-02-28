"""
Properly extract Lua methods with correct block depth counting.
"""
import re

with open(r'unobfuscator\pending crack\bloxburg_script.lua', 'r', encoding='utf-8', errors='replace') as f:
    source = f.read()

ret_start = source.index('return({')
content = source[ret_start:]

def extract_method(name, src, max_len=200000):
    pat = re.compile(re.escape(name) + r'=function\(')
    results = []
    for m in pat.finditer(src):
        start = m.start()
        pos = start + len(name) + len('=function(')
        paren_depth = 1
        while pos < len(src) and paren_depth > 0:
            if src[pos] == '(': paren_depth += 1
            elif src[pos] == ')': paren_depth -= 1
            pos += 1
        
        depth = 1  # for the function keyword
        last_block_kw = None
        i = pos
        in_string = False
        string_char = None
        
        while i < len(src) and depth > 0 and (i - start) < max_len:
            c = src[i]
            
            if in_string:
                if c == '\\': i += 2; continue
                if c == string_char: in_string = False
                i += 1; continue
            
            if c in '"\'':
                in_string = True; string_char = c; i += 1; continue
            
            if c == '[' and i+1 < len(src) and src[i+1] in '[=':
                eq = 0; j = i + 1
                while j < len(src) and src[j] == '=': eq += 1; j += 1
                if j < len(src) and src[j] == '[':
                    close = ']' + '=' * eq + ']'
                    end_pos = src.find(close, j + 1)
                    if end_pos >= 0: i = end_pos + len(close); continue
                i += 1; continue
            
            if c == '-' and i+1 < len(src) and src[i+1] == '-':
                nl = src.find('\n', i)
                i = nl + 1 if nl >= 0 else len(src); continue
            
            if c.isalpha() or c == '_':
                j = i
                while j < len(src) and (src[j].isalnum() or src[j] == '_'): j += 1
                word = src[i:j]
                wb_before = (i == 0 or not (src[i-1].isalnum() or src[i-1] == '_'))
                wb_after = (j >= len(src) or not (src[j].isalnum() or src[j] == '_'))
                
                if wb_before and wb_after:
                    if word == 'function': depth += 1
                    elif word == 'do': depth += 1
                    elif word == 'repeat': depth += 1
                    elif word == 'then':
                        if last_block_kw == 'if': depth += 1
                        # elseif's then doesn't change depth
                    elif word == 'end':
                        depth -= 1
                        if depth == 0: i = j; break
                    elif word == 'until':
                        depth -= 1
                        if depth == 0: i = j; break
                    
                    if word in ('if', 'elseif'):
                        last_block_kw = word
                    elif word == 'then':
                        last_block_kw = None
                    elif word in ('function', 'do', 'repeat', 'end', 'until'):
                        last_block_kw = None
                
                i = j; continue
            i += 1
        
        results.append((start, src[start:i]))
    return results

def show(name, max_display=6000):
    results = extract_method(name, content)
    if not results:
        print(f"\n{name}: NOT FOUND")
        return results
    for _, body in results:
        print(f"\n{'='*70}")
        print(f"{name} (len={len(body)})")
        print(f"{'='*70}")
        pretty = body.replace(';', ';\n')
        if len(pretty) > max_display:
            print(pretty[:max_display])
            print(f"\n... ({len(pretty)-max_display} more)")
        else:
            print(pretty)
    return results

# Extract and analyze key deserialization methods
f9 = show('F9', 10000)
if f9:
    calls = sorted(set(re.findall(r'z:(\w+)\(', f9[0][1])))
    print(f"\nF9 calls: {calls}")

show('UF', 5000)
show('By', 3000)
show('Wy', 2000)

# Extract C9 chain
c9 = show('C9', 5000)
if c9:
    calls = sorted(set(re.findall(r'z:(\w+)\(', c9[0][1])))
    print(f"\nC9 calls: {calls}")
    for c in calls:
        if c not in ('C9', 'F9', 'UF', 'By', 'Wy', 'X9'):
            show(c, 5000)

# Extract V9 → N9 → w9 chain
show('V9', 5000)
show('N9', 5000)
w9 = show('w9', 10000)
if w9:
    calls = sorted(set(re.findall(r'z:(\w+)\(', w9[0][1])))
    print(f"\nw9 calls: {calls}")
    for c in calls:
        if c not in ('w9', 'C9', 'F9', 'V9', 'N9'):
            show(c, 5000)

# The BIG question: where are string constants deserialized?
# Let me look at the closure factory (zy) - it defines r[56]
# r[56](C,W) is called with C = prototype table, W = ?
# C[10]=numregs, C[5]=?, C[1]=type, C[8]=?, C[2]=?, C[7]=?, C[4]=?, C[9]=?, C[6]=?, C[11]=?
# Maybe the deserialization fills Q (from UF) and then r[56] wraps it into a closure

# Let me trace backwards from r[56] to find where prototypes get their fields populated
# The key is: who populates Q[1..11] beyond just Q[5]?

# Check what Hy does (matched as having buffer reads + string patterns)
hy = show('Hy', 5000)
if hy:
    calls = sorted(set(re.findall(r'z:(\w+)\(', hy[0][1])))
    print(f"\nHy calls: {calls}")
    for c in calls:
        show(c, 5000)

# Extract Oy (called by Hy)
show('Oy', 5000)
