import re, json, sys

with open(r'unobfuscator\pending crack\bloxburg_script.lua', 'r', encoding='utf-8', errors='replace') as f:
    source = f.read()

# The dispatch handlers are inside the closure factory's returned function
# They access r[N](...) to call state table functions
# Find all patterns where r[N] is called as a function

# First, find the state variable name (r)
# From closure factory: (r)[56]=function(C,W)
factory_match = re.search(r'\((\w+)\)\[(?:\d+|0[xX][0-9a-fA-F]+)\]=function\(\w+,\w+\)', source)
if factory_match:
    state_var = factory_match.group(1)
    print(f"State variable: {state_var}")
else:
    print("Could not find state variable")
    sys.exit(1)

# Find the dispatch loop inside the closure factory
# The dispatch is inside function(C,W) ... local function created by r[56]
# Look for while loops and if-then chains

# Find all r[N](...) calls where N is a number
r_call_pattern = re.compile(
    rf'{re.escape(state_var)}\[(\d+|0[xX][0-9a-fA-F]+)\]\('
)

calls = {}
for m in r_call_pattern.finditer(source):
    idx_str = m.group(1)
    idx = int(idx_str, 0)
    pos = m.start()
    # Get context (100 chars before and after)
    ctx_start = max(0, pos - 60)
    ctx_end = min(len(source), pos + 100)
    context = source[ctx_start:ctx_end].replace('\n', ' ')
    
    if idx not in calls:
        calls[idx] = []
    calls[idx].append((pos, context))

print(f"\nFound {len(calls)} unique r[N] function call indices")
for idx in sorted(calls.keys()):
    count = len(calls[idx])
    # Show first occurrence context
    first_ctx = calls[idx][0][1]
    print(f"\n  r[{idx}] called {count} time(s):")
    for pos, ctx in calls[idx][:3]:
        # Trim context for readability
        print(f"    pos={pos:8d}: ...{ctx[:120]}...")

# Also look for patterns where a r[N] function result is stored in a register (y)
# Pattern: y[expr] = r[N](expr)
print(f"\n\n=== Looking for y[...] = r[N](...) patterns ===")
assign_pattern = re.compile(
    rf'(\w+)\[([^\]]+)\]\s*=\s*{re.escape(state_var)}\[(\d+|0[xX][0-9a-fA-F]+)\]\(([^)]*)\)'
)

assigns = []
for m in assign_pattern.finditer(source):
    target_var = m.group(1)
    target_idx = m.group(2)
    func_idx = int(m.group(3), 0)
    args = m.group(4)
    pos = m.start()
    assigns.append((target_var, target_idx, func_idx, args, pos))

print(f"Found {len(assigns)} register assignments from r[N] calls")
for tv, ti, fi, args, pos in assigns[:30]:
    print(f"  pos={pos:8d}: {tv}[{ti}] = r[{fi}]({args})")

# Look specifically for string-related operations
# The dispatch handler that loads a string constant would call r[N] 
# and store the result in a register
# Let's also search for where buffer reading happens
print(f"\n\n=== Searching for buffer access patterns ===")
# The buffer is r[33]. Find where it's accessed
buf_pattern = re.compile(
    rf'{re.escape(state_var)}\[(?:33|0[xX]21)\]'
)
buf_refs = list(buf_pattern.finditer(source))
print(f"References to r[33] (buffer): {len(buf_refs)}")
for m in buf_refs[:10]:
    pos = m.start()
    ctx = source[max(0, pos-40):min(len(source), pos+80)].replace('\n', ' ')
    print(f"  pos={pos}: ...{ctx[:100]}...")

# Find string.pack/unpack usage that might decode strings
print(f"\n\n=== String pack/unpack patterns ===")
pack_pattern = re.compile(r'string\.(?:pack|unpack)\([^)]+\)')
for m in pack_pattern.finditer(source):
    pos = m.start()
    ctx = source[max(0, pos-30):min(len(source), pos+80)].replace('\n', ' ')
    print(f"  pos={pos}: {ctx[:100]}")

# Also look for buffer.readstring calls
print(f"\n\n=== buffer.readstring patterns ===")
brs_pattern = re.compile(r'buffer\.readstring\([^)]+\)')
for m in brs_pattern.finditer(source):
    pos = m.start()
    ctx = source[max(0, pos-60):min(len(source), pos+80)].replace('\n', ' ')
    print(f"  pos={pos}: {ctx[:120]}")
