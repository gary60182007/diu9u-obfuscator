"""Find the prototype factory function (r[58]) and trace xF calls."""
import re

with open(r'unobfuscator\pending crack\bloxburg_script.lua', 'r', encoding='utf-8', errors='replace') as f:
    src = f.read()

# Search for all xF calls to find what calls it
xf_calls = list(re.finditer(r':xF\(', src))
print(f"xF called {len(xf_calls)} times:")
for m in xf_calls:
    start = max(0, m.start()-80)
    end = min(len(src), m.end()+80)
    ctx = src[start:end].replace('\n', ' ')
    print(f"  pos={m.start()}: ...{ctx}...")

print()

# Find what function contains each xF call
# Look for the nearest function definition before each call
for m in xf_calls:
    # Search backwards for function definition
    search_start = max(0, m.start()-5000)
    chunk = src[search_start:m.start()]
    func_defs = list(re.finditer(r'(\w+)=function\(', chunk))
    if func_defs:
        last_def = func_defs[-1]
        func_name = last_def.group(1)
        # Show context around the xF call
        line_start = src.rfind('\n', max(0, m.start()-200), m.start())
        if line_start == -1: line_start = max(0, m.start()-200)
        line_end = src.find('\n', m.end())
        if line_end == -1: line_end = min(len(src), m.end()+200)
        print(f"  In function '{func_name}':")
        context = src[line_start:min(line_end, line_start+300)]
        print(f"    {context.strip()[:300]}")
        print()

# Also search for where r[58] / r[0X3a] is SET (not just used)
# Look for patterns like: state_var[58] = or state_var[0X3a] =
# But also look for the pattern where a function is stored at index 58
print("="*60)
print("Searching for r[58] factory setup...")

# The factory is likely created as a closure inside the W function
# Look for function definitions near where r[57] and r[58] are mentioned
# r[57] = string table, cleared by I9
# The factory might be defined in the same area

# Search for the W function (lazy deserializer) 
w_func = re.search(r'(W=function\([^)]+\))', src)
if w_func:
    print(f"\nW function found at pos {w_func.start()}: {w_func.group()}")
    # Get the function's full body (it's very large)
    body_start = w_func.end()
    # Just get the first 3000 chars
    w_body = src[body_start:body_start+3000]
    
    # Find all function/method calls in W
    calls = re.findall(r'z:(\w+)\(', w_body)
    print(f"Methods called in W (first 3000 chars): {sorted(set(calls))}")
    
    # Search for r[58] assignment in W
    r58_assign = re.findall(r'\w+\[(?:58|0[xX]3[aA]|0[bB]111010)\]\s*=', w_body)
    print(f"r[58] assignments in W body: {r58_assign}")
    
    # Show the first 1500 chars of W
    clean = w_body[:1500].replace(';', ';\n')
    print(f"\nW body start:\n{clean}")
