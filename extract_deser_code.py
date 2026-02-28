import re

with open(r'unobfuscator\pending crack\bloxburg_script.lua', 'r', encoding='utf-8', errors='replace') as f:
    source = f.read()

# Extract the deserialization code around the buffer access points
# Key positions found: 156169 (r[23]), 156354 (r[36]), 165126 (r[22])
# Also the init setup at position 2154 (r[54] definition)

# Extract regions of interest
regions = [
    ("Init setup (r[54] definition)", 2100, 2400),
    ("Main deser loop start", 155000, 158000),
    ("Main deser loop cont", 158000, 162000),
    ("Main deser loop end", 162000, 167000),
]

for label, start, end in regions:
    chunk = source[start:end]
    # Make it readable by splitting at semicolons
    lines = chunk.replace(';', ';\n').split('\n')
    print(f"\n{'='*70}")
    print(f"{label} (source pos {start}-{end})")
    print(f"{'='*70}")
    for i, line in enumerate(lines[:200]):
        line = line.strip()
        if line:
            print(f"  {i:4d}: {line[:120]}")
    if len(lines) > 200:
        print(f"  ... ({len(lines) - 200} more lines)")

# Also find the function that contains the deserialization
# Search for the while loop that contains r[23](r[33], r[10])
print(f"\n{'='*70}")
print(f"Searching for deserialization while loop pattern")
print(f"{'='*70}")

# The deser loop likely has: while true do ... r[23](r[33],...) ... end
# Find the pattern near position 156169
# Look backwards from r[23] call to find the enclosing function
r23_pos = 156169
# Find the nearest function keyword before this position
func_starts = [m.start() for m in re.finditer(r'function\s*\(', source[:r23_pos+1])]
if func_starts:
    nearest_func = func_starts[-1]
    print(f"Nearest function start before r[23]: position {nearest_func}")
    # Extract from function start
    chunk = source[nearest_func:nearest_func+15000]
    # Find matching end by counting function/end pairs
    depth = 0
    end_pos = 0
    for m in re.finditer(r'\bfunction\b|\bend\b', chunk):
        if m.group() == 'function':
            depth += 1
        else:
            depth -= 1
            if depth == 0:
                end_pos = m.end()
                break
    
    if end_pos:
        func_code = chunk[:end_pos]
        print(f"Function length: {len(func_code)} chars")
        # Pretty print
        lines = func_code.replace(';', ';\n').split('\n')
        print(f"\nDeserialization function ({len(lines)} lines):")
        for i, line in enumerate(lines):
            line = line.strip()
            if line:
                print(f"  {i:4d}: {line[:140]}")
