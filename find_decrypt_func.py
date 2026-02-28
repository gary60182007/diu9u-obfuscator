import re

with open(r'unobfuscator\pending crack\bloxburg_script.lua', 'r', encoding='utf-8', errors='replace') as f:
    source = f.read()

# The VM object 'z' has methods that handle deserialization
# z.l9 = bit32.bxor, z.f9 = bit32.lrotate, z.H9 = bit32.rshift, etc.
# Find all z method definitions

# First, find the z object's class definition
# It's likely a table with methods defined like z.method = function(...) or method = function(z,...)

# Find the big return table that defines the z class
# Look for patterns like: return({...}) or local z = {f9=bit32.lrotate,...}

# Search for the return table pattern
print("=== Finding the VM class/object definition ===")
# The source starts with: return({f9=bit32.lrotate,...
ret_match = re.search(r'return\(\{(\w+=)', source[:100])
if ret_match:
    print(f"Return table starts at position {ret_match.start()}")
    # The entire script is a return statement returning a table
    # This table IS the z object
    
# Find all named function definitions in the return table
# Pattern: name=function(z,...) or name=function(z,r,C,W,...)
func_defs = re.finditer(r'(\w+)=function\(z(?:,(\w+(?:,\w+)*)?)?\)', source)
z_methods = []
for m in func_defs:
    name = m.group(1)
    params = m.group(2) or ''
    pos = m.start()
    z_methods.append((name, params, pos))

print(f"\nFound {len(z_methods)} z-method definitions")
for name, params, pos in z_methods[:50]:
    # Get a snippet of the method body
    body_start = source.index(')', pos) + 1
    body = source[body_start:body_start+200].replace('\n', ' ')
    print(f"  {name}(z,{params}) @ pos {pos}: {body[:100]}")

# Find methods that use bit32.bxor (z.l9)
print(f"\n=== Methods using XOR (z.l9 / bit32.bxor) ===")
xor_methods = []
for name, params, pos in z_methods:
    # Find the end of this method (rough: next method def or end keyword)
    # For now just check the next 2000 chars
    body = source[pos:pos+2000]
    if 'l9' in body or 'bxor' in body or 'lrotate' in body:
        xor_refs = []
        for ref in re.finditer(r'(?:z\.)?l9|bxor|lrotate|rshift|band|bnot', body):
            xor_refs.append(ref.group())
        if xor_refs:
            xor_methods.append((name, params, pos, xor_refs))

print(f"Found {len(xor_methods)} methods with bitwise operations:")
for name, params, pos, refs in xor_methods:
    ref_str = ', '.join(set(refs))
    body = source[pos:pos+500].replace('\n', ' ')
    print(f"\n  {name}(z,{params}) @ {pos} uses: {ref_str}")
    print(f"    body: {body[:200]}")

# Find the string reading function
# It should: read bytes from buffer, XOR them, produce a string
# Look for functions that use both buffer reads AND bit operations
print(f"\n=== Functions with buffer reads AND bit ops ===")
for name, params, pos in z_methods:
    body = source[pos:pos+2000]
    has_buf = any(x in body for x in ['readstring', 'readu8', 'readf32', 'r[33]', 'r[0x21]', 'r[0XA]', 'r[10]'])
    has_bit = any(x in body for x in ['l9', 'bxor', 'rshift', 'lrotate', 'band'])
    has_str = any(x in body for x in ['string.char', 'string.byte', 'r[31]', 'char'])
    if has_buf and has_bit:
        body_short = body[:400].replace('\n', ' ')
        print(f"\n  {name}(z,{params}) @ {pos}")
        print(f"    buf={has_buf}, bit={has_bit}, str={has_str}")
        print(f"    body: {body_short[:200]}")
    elif has_buf and has_str:
        body_short = body[:400].replace('\n', ' ')
        print(f"\n  {name}(z,{params}) @ {pos} [buf+str]")
        print(f"    body: {body_short[:200]}")

# Search for the string decryption pattern directly
# It would look something like: 
#   local result = ""
#   for i = 1, len do
#     local b = readu8(buf, offset)
#     local d = bxor(b, key)
#     result = result .. char_table[d]
#   end
print(f"\n=== Searching for string build loops ===")
# Find for loops that build strings
for_loop_pattern = re.compile(r'for\s+\w+\s*=\s*(?:0[xX]1|1|0[bB]1)\s*,', re.IGNORECASE)
for m in for_loop_pattern.finditer(source):
    pos = m.start()
    # Check if nearby code accesses buffer and does XOR
    ctx = source[max(0,pos-100):min(len(source),pos+300)].replace('\n', ' ')
    if any(x in ctx for x in ['l9', 'bxor', 'char', 'r[31]', 'readstring', 'readu8']):
        print(f"\n  pos={pos}: {ctx[:200]}")

# Also search for the pattern where r[10] is used to read strings
print(f"\n=== r[10] offset usage near string operations ===")
r10_pattern = re.compile(r'r\[(?:10|0[xX][Aa]|0[bB]1010)\]')
for m in r10_pattern.finditer(source):
    pos = m.start()
    ctx = source[max(0,pos-50):min(len(source),pos+100)].replace('\n', ' ')
    if any(x in ctx for x in ['l9', 'bxor', 'char', 'byte', 'string', 'readstring']):
        print(f"  pos={pos}: {ctx[:150]}")
