"""
Extract the VM executor function body from the Luraph script.
Find the i==3 executor and its opcode dispatch handlers.
"""
import re, json

with open(r'unobfuscator\pending crack\bloxburg_script.lua', 'r', encoding='utf-8', errors='replace') as f:
    src = f.read()

# Find the 11-var unpack pattern
pat = re.compile(r'local\s+Q,i,O,a,q,D,Y,Z,w,m,J\s*=\s*C\[0[xX][aA]\]')
m = pat.search(src)
unpack_pos = m.start()
print(f"VM executor unpack at pos {unpack_pos}")

# The structure is:
# if i<7 then if i>=3 then if i<5 then if i==4 then ... else (i==3) ... end
# We need to find the i==3 branch

# Strategy: find "if i==0x4 then" or "if i==4 then" after the unpack
# Then find the matching else (i==3 case)
chunk_size = 200000
chunk = src[unpack_pos:unpack_pos + chunk_size]

# Find the i==4 check
i4_pat = re.compile(r'if\s+i==0?[xX]?4\s+then')
i4_m = i4_pat.search(chunk)
if i4_m:
    print(f"i==4 check at offset +{i4_m.start()}")
    
    # Find the i==4 function body start
    func_start = chunk.find('function(', i4_m.end())
    print(f"i==4 function at offset +{func_start}")
    
    # Track depth to find the end of the i==4 function
    depth = 0
    pos = func_start
    in_string = False
    i4_func_end = None
    
    # Simple depth tracking
    tokens = re.finditer(r'\b(function|if|for|while|repeat|do)\b|\bend\b|(\belse\b|\belseif\b)', chunk[func_start:])
    depth = 1  # start inside the function
    for tok in tokens:
        word = tok.group(0)
        if word in ('function', 'if', 'for', 'while', 'repeat', 'do'):
            depth += 1
        elif word == 'end':
            depth -= 1
            if depth == 0:
                i4_func_end = func_start + tok.end()
                break
    
    if i4_func_end:
        print(f"i==4 function ends at offset +{i4_func_end}")
        # The i==3 case should be right after: "end)" or similar followed by "else"
        after_i4 = chunk[i4_func_end:i4_func_end + 200]
        print(f"\nAfter i==4 function:")
        print(after_i4[:200])
        
        # Find the else/elseif for i==3
        else_match = re.search(r'else', after_i4)
        if else_match:
            i3_start = i4_func_end + else_match.end()
            print(f"\ni==3 branch starts at offset +{i3_start}")
            # Show the i==3 executor
            i3_chunk = chunk[i3_start:i3_start + 5000]
            print(f"\nFirst 3000 chars of i==3 executor:")
            print(i3_chunk[:3000])

# Also find all the 'i==' comparisons to see what upvalue counts are handled
i_checks = list(re.finditer(r'i==(\d+|0[xXbBoO][\da-fA-F_]+)', chunk[:2000]))
print(f"\n\nAll i== checks in first 2000 chars:")
for ic in i_checks:
    val_str = ic.group(1)
    if val_str.startswith('0x') or val_str.startswith('0X'):
        val = int(val_str, 16)
    elif val_str.startswith('0b') or val_str.startswith('0B'):
        val = int(val_str.replace('_', ''), 2)
    else:
        val = int(val_str)
    print(f"  i=={val} at offset +{ic.start()}")
