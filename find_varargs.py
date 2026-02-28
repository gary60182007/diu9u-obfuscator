import re

with open(r'unobfuscator\pending crack\bloxburg_script.lua', 'r', encoding='utf-8', errors='replace') as f:
    source = f.read()

line11 = source.split('\n')[10]

# Find all occurrences of ... (varargs) in the source
vararg_positions = [m.start() for m in re.finditer(r'\.\.\.', line11)]
print(f"Total '...' occurrences: {len(vararg_positions)}")

# For each ..., find the enclosing function by tracking backwards
for pos in vararg_positions:
    # Get surrounding context
    start = max(0, pos - 200)
    end = min(len(line11), pos + 50)
    ctx = line11[start:end]
    
    # Find the nearest function declaration before this position
    # Look backwards from pos for function declarations
    search_start = max(0, pos - 2000)
    region = line11[search_start:pos]
    
    # Find all function openings in this region
    func_matches = list(re.finditer(r'function\s*\(([^)]*)\)', region))
    
    # Count depth: each 'function(' adds depth, each 'end' reduces it
    # We need to find which function scope contains this ...
    
    # Simple approach: find the last function declaration before pos
    nearest_func = None
    nearest_func_pos = -1
    if func_matches:
        nearest_func = func_matches[-1]
        nearest_func_pos = search_start + nearest_func.start()
        params = nearest_func.group(1)
    else:
        params = "???"
    
    # Check if the nearest function has ... in its params
    has_vararg = '...' in params if nearest_func else False
    
    # Print context around ...
    ctx_short = line11[max(0,pos-80):pos+10].replace('\n',' ')
    print(f"\n  @{pos}: ...params of nearest func: ({params[:80]})")
    print(f"    vararg in params: {has_vararg}")
    print(f"    context: ...{ctx_short}...")

# Also look at the specific C9 function to verify its parameter list
print("\n\n=== C9 FUNCTION DECLARATION ===")
c9_match = re.search(r'C9\s*=\s*function\s*\(([^)]*)\)', line11)
if c9_match:
    print(f"C9 params: ({c9_match.group(1)})")
    pos = c9_match.start()
    snippet = line11[pos:pos+3000]
    # Find all ... in C9's body
    varargs_in_c9 = [(m.start(), line11[pos+m.start()-30:pos+m.start()+10]) for m in re.finditer(r'\.\.\.', snippet)]
    print(f"'...' in C9 body snippet: {len(varargs_in_c9)}")
    for vp, vc in varargs_in_c9:
        print(f"  @{vp}: {vc}")

# Find the chunk-level function that wraps everything
print("\n\n=== CHUNK LEVEL ===")
# The return statement starts: return({...})
# Find where the table constructor starts and if there's a function wrapper
first200 = line11[:500]
print(f"First 500 chars: {first200}")

# Check if the script ends with (...) which would pass chunk varargs
last200 = line11[-300:]
print(f"\nLast 300 chars: {last200}")

# Find the e array
print("\n\n=== E ARRAY ===")
e_match = re.search(r'e\s*=\s*\{([^}]+)\}', line11)
if e_match:
    e_content = e_match.group(1)
    print(f"e = {{{e_content[:500]}}}")
    # Parse the numbers
    nums = re.findall(r'-?(?:0[xX][0-9a-fA-F_]+|0[bB][01_]+|\d+(?:\.\d+)?)', e_content)
    print(f"e values ({len(nums)}): {nums}")
