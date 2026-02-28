import sys, re
sys.path.insert(0, '.')

with open(r'unobfuscator\pending crack\bloxburg_script.lua', 'r', encoding='utf-8', errors='replace') as f:
    source = f.read()

line11 = source.split('\n')[10]

patterns = [
    (r'error\([^,)]+,\s*0\)', 'error(x, 0)'),
    (r'error\([^)]*"Luraph[^)]*\)', 'error("Luraph...")'),
    (r'"Luraph Script:"', '"Luraph Script:"'),
    (r'Luraph Script', 'Luraph Script literal'),
]

for pat, desc in patterns:
    matches = re.findall(pat, line11)
    print(f'{desc}: {len(matches)} matches')
    for m in matches[:5]:
        print(f'  {m[:200]}')

print('\n--- Searching for error re-raise patterns ---')
for m in re.finditer(r'error\([^)]{0,200}\)', line11):
    ctx_start = max(0, m.start() - 50)
    ctx_end = min(len(line11), m.end() + 50)
    text = m.group()
    if len(text) < 300:
        print(f'  pos={m.start()}: {text}')
    if 'Luraph' in line11[ctx_start:ctx_end] or '0)' in text:
        print(f'    context: ...{line11[ctx_start:ctx_end]}...')

print('\n--- Searching for typeof patterns (Luau-specific) ---')
typeof_matches = re.findall(r'typeof\(', line11)
print(f'typeof(): {len(typeof_matches)} matches')

print('\n--- Searching for table access patterns that could cause nil index ---')
# Look for patterns like [nil] or table indexing with function results
nil_idx = re.findall(r'\[nil\]', line11)
print(f'[nil] patterns: {len(nil_idx)}')

# Look for the dispatch table pattern
dispatch_patterns = re.findall(r'(\w+)\[(\w+)\]\s*=\s*function', line11)
print(f'\nTable[key] = function patterns: {len(dispatch_patterns)}')
for k, v in dispatch_patterns[:20]:
    print(f'  {k}[{v}] = function')

# Find the o9 function definition
o9_matches = list(re.finditer(r'o9\s*=\s*function', line11))
print(f'\no9 = function: {len(o9_matches)} matches')
for m in o9_matches:
    start = m.start()
    end = min(len(line11), start + 500)
    print(f'  pos={start}: {line11[start:end]}')
