import re

with open(r'unobfuscator\pending crack\bloxburg_script.lua', 'r', encoding='utf-8', errors='replace') as f:
    source = f.read()

line11 = source.split('\n')[10]

# Find C9 function start
c9_match = re.search(r'C9\s*=\s*function\s*\([^)]*\)', line11)
if not c9_match:
    print("C9 not found!")
    exit()

start = c9_match.start()
print(f"C9 starts at position {start}")

# Now find the matching end by tracking depth
# In Lua: function/do/if/for/while/repeat increase depth, end/until decrease
pos = start
depth = 0
i = start
n = len(line11)
in_string = False
string_delim = None

# Track keywords for depth
keywords_open = {'function', 'do', 'if', 'for', 'while', 'repeat'}
keywords_close = {'end', 'until'}

# Simple approach: count function/end pairs
func_depth = 0
found_start = False
end_pos = -1

# Start from 'function' keyword
i = c9_match.start() + len('C9=')
while i < min(n, start + 50000):
    # Skip strings
    if line11[i] in ('"', "'"):
        delim = line11[i]
        i += 1
        while i < n and line11[i] != delim:
            if line11[i] == '\\':
                i += 1  # skip escape
            i += 1
        i += 1
        continue
    
    # Check for keywords
    if line11[i:i+8] == 'function':
        # Make sure it's a keyword boundary
        if i == 0 or not line11[i-1].isalnum():
            next_ch = line11[i+8] if i+8 < n else ''
            if not next_ch.isalnum() and next_ch != '_':
                func_depth += 1
    elif line11[i:i+3] == 'end' and (i == 0 or not line11[i-1].isalnum()):
        next_ch = line11[i+3] if i+3 < n else ''
        if not next_ch.isalnum() and next_ch != '_':
            func_depth -= 1
            if func_depth == 0:
                end_pos = i + 3
                break
    elif line11[i:i+2] == 'do' and (i == 0 or not line11[i-1].isalnum()):
        next_ch = line11[i+2] if i+2 < n else ''
        if not next_ch.isalnum() and next_ch != '_':
            func_depth += 1
    elif line11[i:i+2] == 'if' and (i == 0 or not line11[i-1].isalnum()):
        next_ch = line11[i+2] if i+2 < n else ''
        if not next_ch.isalnum() and next_ch != '_':
            func_depth += 1
    elif line11[i:i+3] == 'for' and (i == 0 or not line11[i-1].isalnum()):
        next_ch = line11[i+3] if i+3 < n else ''
        if not next_ch.isalnum() and next_ch != '_':
            func_depth += 1
    elif line11[i:i+5] == 'while' and (i == 0 or not line11[i-1].isalnum()):
        next_ch = line11[i+5] if i+5 < n else ''
        if not next_ch.isalnum() and next_ch != '_':
            func_depth += 1
    elif line11[i:i+6] == 'repeat' and (i == 0 or not line11[i-1].isalnum()):
        next_ch = line11[i+6] if i+6 < n else ''
        if not next_ch.isalnum() and next_ch != '_':
            func_depth += 1
    elif line11[i:i+5] == 'until' and (i == 0 or not line11[i-1].isalnum()):
        next_ch = line11[i+5] if i+5 < n else ''
        if not next_ch.isalnum() and next_ch != '_':
            func_depth -= 1
            if func_depth == 0:
                end_pos = i + 5
                break
    i += 1

if end_pos > 0:
    c9_body = line11[start:end_pos]
    print(f"C9 length: {len(c9_body)} chars")
    print(f"\n=== C9 FULL BODY ===")
    print(c9_body)
    
    # Find all ... in C9
    varargs = [m.start() for m in re.finditer(r'\.\.\.', c9_body)]
    print(f"\n\n=== VARARGS IN C9: {len(varargs)} ===")
    for vp in varargs:
        ctx = c9_body[max(0,vp-40):vp+20]
        print(f"  @{vp}: ...{ctx}...")
else:
    print(f"Could not find end of C9 (func_depth={func_depth})")
    # Print first 2000 chars
    print(line11[start:start+2000])

# Also extract o9
print("\n\n=== O9 FUNCTION ===")
o9_match = re.search(r'o9\s*=\s*function\s*\([^)]*\)', line11)
if o9_match:
    start = o9_match.start()
    i = start + len('o9=')
    func_depth = 0
    end_pos = -1
    while i < min(n, start + 50000):
        if line11[i] in ('"', "'"):
            delim = line11[i]
            i += 1
            while i < n and line11[i] != delim:
                if line11[i] == '\\': i += 1
                i += 1
            i += 1
            continue
        if line11[i:i+8] == 'function' and (i==0 or not line11[i-1].isalnum()):
            nc = line11[i+8] if i+8<n else ''
            if not nc.isalnum() and nc != '_': func_depth += 1
        elif line11[i:i+3] == 'end' and (i==0 or not line11[i-1].isalnum()):
            nc = line11[i+3] if i+3<n else ''
            if not nc.isalnum() and nc != '_':
                func_depth -= 1
                if func_depth == 0:
                    end_pos = i+3; break
        elif line11[i:i+2] == 'do' and (i==0 or not line11[i-1].isalnum()):
            nc = line11[i+2] if i+2<n else ''
            if not nc.isalnum() and nc != '_': func_depth += 1
        elif line11[i:i+2] == 'if' and (i==0 or not line11[i-1].isalnum()):
            nc = line11[i+2] if i+2<n else ''
            if not nc.isalnum() and nc != '_': func_depth += 1
        elif line11[i:i+3] == 'for' and (i==0 or not line11[i-1].isalnum()):
            nc = line11[i+3] if i+3<n else ''
            if not nc.isalnum() and nc != '_': func_depth += 1
        elif line11[i:i+5] == 'while' and (i==0 or not line11[i-1].isalnum()):
            nc = line11[i+5] if i+5<n else ''
            if not nc.isalnum() and nc != '_': func_depth += 1
        elif line11[i:i+6] == 'repeat' and (i==0 or not line11[i-1].isalnum()):
            nc = line11[i+6] if i+6<n else ''
            if not nc.isalnum() and nc != '_': func_depth += 1
        elif line11[i:i+5] == 'until' and (i==0 or not line11[i-1].isalnum()):
            nc = line11[i+5] if i+5<n else ''
            if not nc.isalnum() and nc != '_':
                func_depth -= 1
                if func_depth == 0: end_pos = i+5; break
        i += 1
    if end_pos > 0:
        o9_body = line11[start:end_pos]
        print(f"o9 length: {len(o9_body)} chars")
        print(o9_body)
    else:
        print(f"Could not find end of o9 (func_depth={func_depth})")
        print(line11[start:start+1000])

# Also extract q function
print("\n\n=== q FUNCTION ===")
q_match = re.search(r',q\s*=\s*function\s*\([^)]*\)', line11)
if q_match:
    start = q_match.start() + 1  # skip comma
    i = start + len('q=')
    func_depth = 0
    end_pos = -1
    while i < min(n, start + 100000):
        if line11[i] in ('"', "'"):
            delim = line11[i]
            i += 1
            while i < n and line11[i] != delim:
                if line11[i] == '\\': i += 1
                i += 1
            i += 1
            continue
        if line11[i:i+8] == 'function' and (i==0 or not line11[i-1].isalnum()):
            nc = line11[i+8] if i+8<n else ''
            if not nc.isalnum() and nc != '_': func_depth += 1
        elif line11[i:i+3] == 'end' and (i==0 or not line11[i-1].isalnum()):
            nc = line11[i+3] if i+3<n else ''
            if not nc.isalnum() and nc != '_':
                func_depth -= 1
                if func_depth == 0:
                    end_pos = i+3; break
        elif line11[i:i+2] == 'do' and (i==0 or not line11[i-1].isalnum()):
            nc = line11[i+2] if i+2<n else ''
            if not nc.isalnum() and nc != '_': func_depth += 1
        elif line11[i:i+2] == 'if' and (i==0 or not line11[i-1].isalnum()):
            nc = line11[i+2] if i+2<n else ''
            if not nc.isalnum() and nc != '_': func_depth += 1
        elif line11[i:i+3] == 'for' and (i==0 or not line11[i-1].isalnum()):
            nc = line11[i+3] if i+3<n else ''
            if not nc.isalnum() and nc != '_': func_depth += 1
        elif line11[i:i+5] == 'while' and (i==0 or not line11[i-1].isalnum()):
            nc = line11[i+5] if i+5<n else ''
            if not nc.isalnum() and nc != '_': func_depth += 1
        elif line11[i:i+6] == 'repeat' and (i==0 or not line11[i-1].isalnum()):
            nc = line11[i+6] if i+6<n else ''
            if not nc.isalnum() and nc != '_': func_depth += 1
        elif line11[i:i+5] == 'until' and (i==0 or not line11[i-1].isalnum()):
            nc = line11[i+5] if i+5<n else ''
            if not nc.isalnum() and nc != '_':
                func_depth -= 1
                if func_depth == 0: end_pos = i+5; break
        i += 1
    if end_pos > 0:
        q_body = line11[start:end_pos]
        print(f"q length: {len(q_body)} chars")
        print(q_body[:5000])
        if len(q_body) > 5000:
            print(f"\n... ({len(q_body)-5000} more chars) ...")
            print(q_body[-500:])
    else:
        print(f"Could not find end of q (func_depth={func_depth})")
