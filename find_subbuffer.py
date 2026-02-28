import re

with open(r'unobfuscator\pending crack\bloxburg_script.lua', 'r', encoding='utf-8', errors='replace') as f:
    source = f.read()

# Find where r[54] (r[0x36]) is called
# r[54] = sub-buffer creator
# 54 = 0x36

patterns = [
    (r'r\[54\]\(', 'r[54]()'),
    (r'r\[0[xX]36\]\(', 'r[0x36]()'),
    (r'r\[0[bB][01_]+\]\(', 'r[0bN]()'),  # binary form
]

for pat, label in patterns:
    matches = list(re.finditer(pat, source))
    for m in matches:
        pos = m.start()
        ctx = source[max(0, pos-80):min(len(source), pos+80)].replace('\n', ' ')
        print(f"  {label} at pos {pos}: ...{ctx}...")

# Also search for C[54] or similar (C might be used instead of r)
print("\nSearching for state table function calls with index 54/0x36:")
for pat in [r'\w\[(?:54|0[xX]36|0[bB]110110)\]\s*\(']:
    for m in re.finditer(pat, source):
        pos = m.start()
        var_char = source[pos]
        ctx = source[max(0, pos-50):min(len(source), pos+60)].replace('\n', ' ')
        print(f"  pos={pos}: ...{ctx}...")

# Now find r[36] calls (0x24 = 36) - this was another buffer read function
print("\nSearching for r[36] calls:")
for m in re.finditer(r'r\[(?:36|0[xX]24)\]\(', source):
    pos = m.start()
    ctx = source[max(0, pos-50):min(len(source), pos+80)].replace('\n', ' ')
    print(f"  pos={pos}: ...{ctx}...")

# Search for the init function that sets up r[54]
print("\nSearching for r[54] or r[0x36] assignment (definition):")
for m in re.finditer(r'r\[(?:54|0[xX]36|0[bB]110110)\]\s*=', source):
    pos = m.start()
    ctx = source[max(0, pos-30):min(len(source), pos+120)].replace('\n', ' ')
    print(f"  pos={pos}: ...{ctx}...")

# Find where r[10] (the offset) is reset after sub-buffer creation
print("\nSearching for r[10] reset patterns:")
for m in re.finditer(r'r\[(?:10|0[xX][Aa]|0[bB]1010)\]\s*=\s*(?:0|nil|r\[10\]\+)', source):
    pos = m.start()
    ctx = source[max(0, pos-50):min(len(source), pos+80)].replace('\n', ' ')
    print(f"  pos={pos}: ...{ctx}...")

# Find the r[22] function definition (another buffer reader)
print("\nSearching for r[22] definition:")
for m in re.finditer(r'r\[(?:22|0[xX]16|0[bB]10110)\]\s*=', source):
    pos = m.start()
    ctx = source[max(0, pos-30):min(len(source), pos+150)].replace('\n', ' ')
    print(f"  pos={pos}: ...{ctx}...")

# Find where sub-buffers are stored
# Look for patterns where r[54]() result is stored
print("\nSearching for sub-buffer storage patterns:")
for m in re.finditer(r'=\s*r\[(?:54|0[xX]36|0[bB]110110)\]\(\)', source):
    pos = m.start()
    ctx = source[max(0, pos-60):min(len(source), pos+40)].replace('\n', ' ')
    print(f"  pos={pos}: ...{ctx}...")
