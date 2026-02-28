import re

with open(r'unobfuscator\pending crack\bloxburg_script.lua', 'r', encoding='utf-8', errors='replace') as f:
    source = f.read()

exec(open('run_luraph_test.py').read().split("print('Reading source...')")[0])
source = preprocess_luau(source)
lines = source.split('\n')
big_line = lines[10]

parts = []
current = []
i = 0
in_string = False
string_delim = None
while i < len(big_line):
    ch = big_line[i]
    if in_string:
        current.append(ch)
        if ch == '\\' and i+1 < len(big_line):
            i += 1
            current.append(big_line[i])
        elif ch == string_delim:
            in_string = False
    elif ch in ('"', "'"):
        in_string = True
        string_delim = ch
        current.append(ch)
    elif ch == ';':
        current.append(ch)
        parts.append(''.join(current))
        current = []
    else:
        current.append(ch)
    i += 1
if current:
    parts.append(''.join(current))

print(f"Total parts: {len(parts)}")

# Error was at line 342 in the wrapper. Wrapper adds lines before source.
# Let's check multiple possible offsets
for wrapper_offset in [7, 8, 9, 10]:
    src_line = 342 - wrapper_offset
    part_idx = src_line - 11
    print(f"\n=== wrapper_offset={wrapper_offset}, src_line={src_line}, part_idx={part_idx} ===")
    for delta in range(-2, 3):
        idx = part_idx + delta
        if 0 <= idx < len(parts):
            code = parts[idx].strip()[:250]
            print(f"  part[{idx}]: {code}")

# Also check what zy function does and where it's called
print("\n=== SEARCHING FOR 'zy' REFERENCES ===")
for idx, part in enumerate(parts):
    if re.search(r'(?<![a-zA-Z0-9_])zy\b', part):
        code = part.strip()[:200]
        print(f"  part[{idx}]: {code}")
