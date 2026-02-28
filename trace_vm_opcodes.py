"""
Trace VM execution to map opcodes to Lua operations.
Instrument the VM executor (r[56]) to log register changes per opcode.
"""
import sys, time, json, re
sys.path.insert(0, '.')

with open(r'unobfuscator\pending crack\bloxburg_script.lua', 'r', encoding='utf-8', errors='replace') as f:
    source = f.read()

exec(open('run_luraph_test.py').read().split("print('Reading source...')")[0])
source = preprocess_luau(source)
from unobfuscator.utils.lua_runtime import LuaRuntimeWrapper, LuaRuntimeError

modified = source

# Find the zy function that assigns r[56] = the VM executor factory
# Pattern: zy=function(z,r)(r)[56]=function(C,W)
zy_pat = re.compile(r'(zy=function\(\w+,(\w+)\)\((\w+)\)\[(?:56|0[xX]38|0[bB]\d+)\]=function\((\w+),(\w+)\))')
zy_m = zy_pat.search(modified)
if not zy_m:
    # Try alternate pattern
    zy_pat2 = re.compile(r'(\w+)\[56\]\s*=\s*function\((\w+),(\w+)\)')
    zy_m2 = zy_pat2.search(modified)
    if zy_m2:
        print(f"Found r[56] assignment at pos {zy_m2.start()}")
    else:
        print("Cannot find r[56] assignment")

# Different approach: find the 11-var unpack and read the VM loop structure  
unpack_pat = re.compile(r'local\s+Q,i,O,a,q,D,Y,Z,w,m,J\s*=\s*C\[')
um = unpack_pat.search(modified)
print(f"Unpack at pos {um.start()}")

# Read the region around the unpack to find the function structure
region = modified[um.start()-500:um.start()]
# Find the function( that contains the unpack
func_matches = list(re.finditer(r'function\(', region))
if func_matches:
    last_func = func_matches[-1]
    print(f"Containing function at offset {um.start()-500+last_func.start()}")
    ctx = region[last_func.start():]
    print(f"Context: ...{ctx[:100]}...")

# The VM dispatcher variable Y = C[4] (opcodes), and k = Y[L] in the loop
# Let me search for what variable is used as the opcode in the dispatch
# For the i==3 case, we need to find the right executor

# Let's just look at the source directly around the unpack for the i<5 and i==3 cases
chunk = modified[um.start():um.start() + 200000]

# Parse the Lua number literals properly
def parse_lua_num(s):
    s = s.replace('_', '').strip()
    if s.startswith('0x') or s.startswith('0X'):
        return int(s, 16)
    elif s.startswith('0b') or s.startswith('0B'):
        return int(s, 2)
    elif s.startswith('0o') or s.startswith('0O'):
        return int(s, 8)
    return int(s)

# Find all i== comparisons
i_checks = []
for m2 in re.finditer(r'i==(0[xXbBoO][\da-fA-F_]+|\d+)', chunk[:5000]):
    raw = m2.group(1)
    try:
        val = parse_lua_num(raw)
        i_checks.append((m2.start(), val, raw))
    except:
        pass

print(f"\ni== checks found:")
for pos, val, raw in i_checks:
    ctx = chunk[max(0,pos-30):pos+30+len(raw)]
    print(f"  offset +{pos}: i=={val} (raw: {raw})")
    print(f"    context: ...{ctx}...")

# Find i<= and i>= comparisons too
for pat_str in [r'i<(0[xXbBoO][\da-fA-F_]+|\d+)', r'i>=(0[xXbBoO][\da-fA-F_]+|\d+)']:
    for m2 in re.finditer(pat_str, chunk[:5000]):
        raw = m2.group(1)
        try:
            val = parse_lua_num(raw)
            print(f"  offset +{m2.start()}: i{'<' if '<' in pat_str else '>='}{val} (raw: {raw})")
        except:
            pass

# Instead of parsing, let me just trace the actual VM at runtime
# I'll hook r[56] to log what the opcode dispatch variable values are

# Find where r[56] is assigned
r56_pat = re.compile(r'\[(?:56|0[xX]38|0[bB]111000)\]\s*=\s*function')
r56_matches = list(r56_pat.finditer(modified))
print(f"\nr[56] assignments: {len(r56_matches)}")
for m2 in r56_matches:
    ctx = modified[max(0,m2.start()-50):m2.end()+50]
    print(f"  pos {m2.start()}: ...{ctx[:120]}...")

# Let me read the actual VM loop to find the opcode dispatch variable
# The VM loop is: while true do local k = Y[L]; ...
# where Y = C[4] (opcodes from the unpack)
# and k is the dispatch variable

# Search for Y[L] pattern in the executor
yl_pat = re.compile(r'local\s+(\w+)\s*=\s*Y\[(\w+)\]')
yl_matches = list(yl_pat.finditer(chunk[:50000]))
print(f"\nY[L] patterns (opcode fetch):")
for m2 in yl_matches[:10]:
    var = m2.group(1)
    idx = m2.group(2)
    ctx = chunk[m2.start():min(len(chunk), m2.end()+100)]
    print(f"  k={var}, L={idx} at offset +{m2.start()}")
    print(f"    {ctx[:150]}")

# Now search for how many opcode values are dispatched
# Each executor has its own set of opcodes
# For i==3 (offset ~280 based on structure), search for dispatch values
# Pattern: k==<number> or k<number>
k_dispatch = []
for m2 in re.finditer(r'\bk[=<>]+\s*(0[xXbBoO][\da-fA-F_]+|\d+)', chunk[:100000]):
    raw = m2.group(1)
    try:
        val = parse_lua_num(raw)
        k_dispatch.append((m2.start(), val, m2.group(0)))
    except:
        pass

if k_dispatch:
    vals = sorted(set(v for _, v, _ in k_dispatch))
    print(f"\nOpcode dispatch values found: {len(vals)} unique")
    print(f"Range: {min(vals)} to {max(vals)}")
    print(f"Values: {vals[:50]}")
    if len(vals) > 50:
        print(f"  ...and {len(vals)-50} more")
