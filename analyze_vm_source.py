import re

with open(r'unobfuscator\pending crack\bloxburg_script.lua', 'r', encoding='utf-8', errors='replace') as f:
    source = f.read()

line11 = source.split('\n')[10]
print(f"VM line length: {len(line11):,}")

func_map = {}
pos = 0
depth = 0
current_key = None
i = 0
n = len(line11)

key_pattern = re.compile(r'(\w+)\s*=\s*function\s*\(([^)]*)\)')
for m in key_pattern.finditer(line11):
    name = m.group(1)
    params = m.group(2)
    start = m.start()
    snippet = line11[start:min(start+500, n)]
    func_map[name] = {'params': params, 'start': start, 'snippet': snippet}

print(f"\nTotal named functions in VM table: {len(func_map)}")
print("\n=== ALL VM TABLE FUNCTIONS ===")
for name in sorted(func_map.keys()):
    info = func_map[name]
    print(f"\n  {name}({info['params']}) @ pos {info['start']}")
    print(f"    {info['snippet'][:200]}")

print("\n\n=== LOOKING FOR DESERIALIZER / BYTECODE READER ===")
deser_funcs = []
for name, info in func_map.items():
    snippet = info['snippet']
    if any(kw in snippet for kw in ['buffer.readu', 'buffer.readi', 'buffer.readf', 'buffer.readstring',
                                     'Deserializ', 'deserializ', 'string.byte', 'string.sub']):
        deser_funcs.append((name, info))

print(f"Functions that read from buffer/strings: {len(deser_funcs)}")
for name, info in deser_funcs:
    print(f"\n  {name}({info['params']}) @ {info['start']}")
    snippet = info['snippet'][:500]
    print(f"    {snippet}")

print("\n\n=== LOOKING FOR STRING DECRYPT FUNCTIONS ===")
for name, info in func_map.items():
    snippet = info['snippet']
    if any(kw in snippet for kw in ['bxor', 'bxor', 'char', 'byte', 'XOR', 'decrypt', 'decode']):
        if name not in [n for n, _ in deser_funcs]:
            print(f"\n  {name}({info['params']}) @ {info['start']}")
            print(f"    {snippet[:400]}")

print("\n\n=== LOOKING FOR DISPATCH / HANDLER PATTERNS ===")
dispatch_patterns = re.findall(r'if\s+(\w+)==(0[xXbB][\w_]+|\d+)\s+then', line11)
print(f"if var==const patterns: {len(dispatch_patterns)}")
from collections import Counter
var_counter = Counter()
for var, val in dispatch_patterns:
    var_counter[var] += 1
print("Variables used in dispatch:")
for var, count in var_counter.most_common(20):
    print(f"  {var}: {count} cases")

print("\n\n=== LOOKING FOR TABLE INDEX ASSIGNMENTS (potential nil key sources) ===")
tbl_assign = re.findall(r'(\w+)\[(\w+)\]\s*=', line11)
assign_vars = Counter()
for tbl, key in tbl_assign:
    assign_vars[f"{tbl}[{key}]"] += 1
print(f"Total table[var] = assignments: {len(tbl_assign)}")
print("Most common patterns:")
for pattern, count in assign_vars.most_common(30):
    print(f"  {pattern}: {count}")

print("\n\n=== LOOKING FOR q() FUNCTION ===")
q_match = re.search(r'q\s*=\s*function\s*\([^)]*\)', line11)
if q_match:
    start = q_match.start()
    snippet = line11[start:min(start+2000, n)]
    print(f"q function @ pos {start}:")
    print(snippet[:2000])

print("\n\n=== LOOKING FOR o9() FUNCTION ===")
o9_match = re.search(r'o9\s*=\s*function\s*\([^)]*\)', line11)
if o9_match:
    start = o9_match.start()
    snippet = line11[start:min(start+1000, n)]
    print(f"o9 function @ pos {start}:")
    print(snippet[:1000])

print("\n\n=== LOOKING FOR C9() FUNCTION (DISPATCHER) ===")
c9_match = re.search(r'C9\s*=\s*function\s*\([^)]*\)', line11)
if c9_match:
    start = c9_match.start()
    snippet = line11[start:min(start+3000, n)]
    print(f"C9 function @ pos {start}:")
    print(snippet[:3000])
