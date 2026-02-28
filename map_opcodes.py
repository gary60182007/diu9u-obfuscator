"""
Map Luraph VM opcodes to Lua 5.1 standard operations by analyzing the VM dispatcher.
The VM loop dispatches on C[4][PC] (opcode) and executes handlers.
We can trace which opcodes produce which effects.
"""
import re, json
from collections import defaultdict

with open(r'unobfuscator\pending crack\bloxburg_script.lua', 'r', encoding='utf-8', errors='replace') as f:
    src = f.read()

# The VM dispatcher is in the C[56] function (the main execution loop)
# It uses a series of if/elseif comparisons on the opcode value
# Let's find the VM loop pattern

# First, find the C[56] assignment - the VM executor
# From earlier analysis, it's assigned via r[0X3a] or similar
# The VM loop compares Y[L] (C[4][PC]) against various values

# Search for the main dispatch patterns
# The VM likely has patterns like: if Y[L]==<number> then ... 
# or uses computed goto via state machine

# Let's look for the function that contains the main VM loop
# It should reference C[4] (opcodes), registers, etc.

# From the F9/q function analysis, the VM executor is created inside F9
# The "q" function is the per-proto deserializer
# After deserialization, the proto's executor function is created

# Look for the large function that has opcode dispatch
# It should contain many numeric comparisons

# Search for patterns like: ==117 then (most common opcode)
matches_117 = list(re.finditer(r'==\s*(?:117|0[xX]75|0[bB]\d+)\s*then', src))
print(f"Matches for ==117: {len(matches_117)}")
for m in matches_117[:5]:
    ctx = src[max(0, m.start()-60):m.end()+100].replace('\n', ' ')
    print(f"  pos={m.start()}: ...{ctx[:200]}...")

# Search for ==232 (second most common)
matches_232 = list(re.finditer(r'==\s*(?:232|0[xX][eE]8|0[bB]\d+)\s*then', src))
print(f"\nMatches for ==232: {len(matches_232)}")
for m in matches_232[:5]:
    ctx = src[max(0, m.start()-60):m.end()+100].replace('\n', ' ')
    print(f"  pos={m.start()}: ...{ctx[:200]}...")

# Search for ==194 (third most common)
matches_194 = list(re.finditer(r'==\s*(?:194|0[xX][cC]2)\s*then', src))
print(f"\nMatches for ==194: {len(matches_194)}")
for m in matches_194[:5]:
    ctx = src[max(0, m.start()-60):m.end()+100].replace('\n', ' ')
    print(f"  pos={m.start()}: ...{ctx[:200]}...")

# The VM dispatcher might not use literal numbers - it might use
# state table lookups like Y[L]==r[xx] where r[xx] holds the opcode value
# Let's search for the pattern where Y[L] is compared

# Y is C[4], L is the PC
# Find patterns like: Y[L]== or ==Y[L]
yl_compares = list(re.finditer(r'(\w+)\[(\w+)\]==', src))
print(f"\nTotal X[Y]== patterns: {len(yl_compares)}")

# Find patterns specifically in the VM loop context
# The VM loop likely uses variable names from the C[56] function body
# From the VM factory pattern: local Y,q,D,a,Z,w,m,J = C[4],C[2],C[7],C[8],C[9],...

# Let's find the C[56] body - search for the pattern where 11 arrays are unpacked
vm_func_pat = re.compile(
    r'local\s+(\w+),(\w+),(\w+),(\w+),(\w+),(\w+),(\w+),(\w+),(\w+),(\w+),(\w+)'
    r'\s*=\s*(\w+)\[',
)
vm_matches = list(vm_func_pat.finditer(src))
print(f"\n11-var unpack patterns: {len(vm_matches)}")
for m in vm_matches:
    vars_list = [m.group(i) for i in range(1, 12)]
    base = m.group(12)
    ctx_end = min(len(src), m.end()+200)
    rest = src[m.end():ctx_end]
    print(f"  vars={vars_list}, base={base}")
    print(f"  context: ...{rest[:200]}...")
    print()

# Also search for the proto hook pattern we used to find C[56]
# The pattern with 11 local vars assigned from array indices 1-11
hook_pat = re.compile(
    r'local\s+(\w+(?:,\w+){9,})\s*=\s*(\w+)\[(\d+|0[xX]\w+)\]'
)
hook_matches = list(hook_pat.finditer(src))
print(f"\nMulti-var array unpack patterns: {len(hook_matches)}")
for m in hook_matches[:5]:
    vars_str = m.group(1)
    n_vars = len(vars_str.split(','))
    base = m.group(2)
    idx = m.group(3)
    ctx = src[m.start():min(len(src), m.end()+300)].replace('\n', ' ')
    print(f"  {n_vars} vars from {base}[{idx}]: {vars_str[:80]}...")
    print(f"  context: {ctx[:250]}...")
    print()
