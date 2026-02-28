"""
Analyze the raw buffer from offset 4306 onwards to determine prototype format.
We know:
- 139 prototypes are deserialized
- d9 loops W times calling c9 which calls r[58]()
- r[58] reads from the buffer at r[10]
- Buffer data: 4306 to 94734 (~90KB for prototypes)

Strategy: instrument r[58] to log r[10] before and after each call,
giving us exact byte ranges per prototype.
"""
import sys, time, json, re
sys.path.insert(0, '.')

with open(r'unobfuscator\pending crack\bloxburg_script.lua', 'r', encoding='utf-8', errors='replace') as f:
    source = f.read()

exec(open('run_luraph_test.py').read().split("print('Reading source...')")[0])
source = preprocess_luau(source)
from unobfuscator.utils.lua_runtime import LuaRuntimeWrapper, LuaRuntimeError

modified = source

# Find c9 and wrap it to trace r[10] before/after r[58]() call
# c9=function(z,z,r,C)(C)[z]=r[58]();
c9_pat = re.compile(r'(c9=function\((\w+),(\w+),(\w+),(\w+)\))')
c9_m = c9_pat.search(modified)
if c9_m:
    c9_z1, c9_z2, c9_r, c9_C = [c9_m.group(j) for j in range(2, 6)]
    print(f"c9 params: z={c9_z1}, z2={c9_z2}, r={c9_r}, C={c9_C}")
    
    # c9 body: (C)[z]=r[58]();
    # z2 is the shadowed parameter (= Q from d9, the loop index)
    # r is the state table
    # Inject before r[58]() call
    inject_c9 = (
        f'do local _n=(_G._c9_n or 0)+1;_G._c9_n=_n;'
        f'local _start={c9_r}[10];'
        f'local _result={c9_r}[58]();'
        f'local _end_pos={c9_r}[10];'
        f'({c9_C})[{c9_z2}]=_result;'
        f'if _n<=200 then '
        f'_G._c9_trace[_n]=_start.."|".._end_pos.."|"..{c9_z2} '
        f'end;return end;'
    )
    # Replace the entire c9 body
    # Find the original body: (C)[z]=r[58]();
    body_start = c9_m.end()
    # Find the 'end' that closes c9
    # c9 is short, the body is just: (C)[z]=r[58]();
    body_end = modified.find('end', body_start)
    # Make sure we're finding the right end
    original_body = modified[body_start:body_end+3]
    print(f"Original c9 body: {repr(original_body[:80])}")
    
    # Replace: remove original body and insert our wrapper
    new_body = inject_c9
    modified = modified[:body_start] + new_body + modified[body_end+3:]
    print("c9 instrumented")

# Also need to track what happens AFTER d9 completes
# The m9 function is called before d9 (w=179). m9 might set up r[58].
# Let's trace m9 too.
m9_pat = re.compile(r'(m9=function\((\w+),(\w+),(\w+),(\w+)\))')
m9_m = m9_pat.search(modified)
if m9_m:
    m9_params = [m9_m.group(j) for j in range(2, 6)]
    print(f"m9 params: {m9_params}")
    # m9=function(z,z,r,C) — z is shadowed
    # r is the state table?
    inject_m9 = (
        f'_G._m9_r10_start={m9_params[2]}[10];'
    )
    modified = modified[:m9_m.end()] + inject_m9 + modified[m9_m.end():]

# Extract m9 body for analysis
if m9_m:
    m9_start = m9_m.start()
    body_start = m9_m.end()
    # Find the body by tracking depth
    depth = 1
    pos = body_start
    in_str = False; sc = None
    while pos < len(modified) and depth > 0:
        c = modified[pos]
        if in_str:
            if c == '\\': pos += 2; continue
            if c == sc: in_str = False
            pos += 1; continue
        if c in '"\'': in_str = True; sc = c; pos += 1; continue
        if c.isalpha() or c == '_':
            j = pos
            while j < len(modified) and (modified[j].isalnum() or modified[j] == '_'): j += 1
            w = modified[pos:j]
            if w in ('function', 'do', 'repeat'): depth += 1
            elif w == 'then': depth += 1
            elif w == 'end': depth -= 1
            elif w == 'until': depth -= 1
            pos = j; continue
        pos += 1
    
    m9_body = modified[m9_start:pos]
    print(f"\nm9 body ({len(m9_body)} chars):")
    m9_clean = m9_body[:600].replace(';', ';\n  ')
    print(f"  {m9_clean}")
    
    m9_methods = sorted(set(re.findall(r'z:(\w+)\(', m9_body)))
    print(f"m9 methods: {m9_methods}")

# Proto capture hook
pat = re.compile(
    r'(\)\[(?:\d+|0[xXbBoO][0-9a-fA-F_]+)\]=function\()'
    r'([A-Za-z_]\w*)' r',' r'([A-Za-z_]\w*)' r'\)'
    r'(local\s+[A-Za-z_]\w*(?:,[A-Za-z_]\w*){9,}=)'
    r'(\2\[)'
)
m = pat.search(modified)
if m:
    p1 = m.group(2)
    full_match = m.group(0)
    lp = full_match.index('local')
    hook = (
        f'if {p1}==nil then return function(...)return end end;'
        f'do local _p={{}};for _i=1,11 do _p[_i]={p1}[_i] end;'
        f'_p.id=#_G._protos+1;table.insert(_G._protos,_p) end;'
    )
    modified = modified[:m.start()] + full_match[:lp] + hook + full_match[lp:] + modified[m.end():]

runtime = LuaRuntimeWrapper(op_limit=15_000_000_000, timeout=600)
runtime._init_runtime()
runtime.lua.execute("""
_G._protos = {}
_G._c9_trace = {}
_G._c9_n = 0
""")

modified = runtime.suppress_vm_errors(modified)

print("\nExecuting VM...")
t0 = time.time()
try:
    runtime.execute(modified)
except LuaRuntimeError as e:
    elapsed = time.time() - t0
    print(f"Stopped after {elapsed:.1f}s: {str(e)[:200]}")

runtime.lua.execute("_G._op_count = 0; _G._op_limit = 10000000000")

def li(expr):
    v = runtime.lua.eval(f"tonumber({expr})")
    return int(v) if v is not None else None

def ls(expr):
    v = runtime.lua.eval(expr)
    return str(v) if v is not None else None

print(f"\n=== Results ===")
print(f"c9 calls: {li('_G._c9_n')}")
print(f"m9 r10 start: {li('_G._m9_r10_start')}")
print(f"Protos: {li('#_G._protos')}")

n_c9 = li('_G._c9_n') or 0
print(f"\n=== Prototype byte ranges ({n_c9} protos) ===")
proto_ranges = []
for i in range(1, min(n_c9 + 1, 201)):
    val = ls(f"_G._c9_trace[{i}]")
    if val and val != 'None':
        parts = val.split('|')
        start = int(parts[0])
        end = int(parts[1])
        idx = int(parts[2])
        size = end - start
        proto_ranges.append({'idx': idx, 'start': start, 'end': end, 'size': size})
        if i <= 30 or i > n_c9 - 5:
            print(f"  Proto[{idx:3d}] offset {start:6d}-{end:6d} ({size:5d} bytes)")
        elif i == 31:
            print(f"  ...")

if proto_ranges:
    sizes = [p['size'] for p in proto_ranges]
    print(f"\n  Total protos: {len(proto_ranges)}")
    print(f"  Min size: {min(sizes)}, Max size: {max(sizes)}, Avg: {sum(sizes)/len(sizes):.0f}")
    print(f"  First proto starts at: {proto_ranges[0]['start']}")
    print(f"  Last proto ends at: {proto_ranges[-1]['end']}")
    print(f"  Total proto data: {proto_ranges[-1]['end'] - proto_ranges[0]['start']} bytes")

# Now analyze the raw bytes of the first few protos
with open(r'unobfuscator\cracked script\buffer_1_1064652.bin', 'rb') as f:
    buf = f.read()

if proto_ranges:
    print(f"\n=== First 5 proto raw analysis ===")
    import struct
    
    def read_varint(buf, pos):
        result = 0; shift = 0
        while True:
            b = buf[pos]; pos += 1
            result |= (b & 0x7F) << shift
            shift += 7
            if b < 128: break
        return result, pos
    
    for p in proto_ranges[:5]:
        raw = buf[p['start']:p['end']]
        print(f"\n  Proto[{p['idx']}] ({p['size']} bytes) offset {p['start']}:")
        print(f"    First 40 bytes: {raw[:40].hex()}")
        
        # Try to parse header
        pos = p['start']
        vals = []
        for j in range(10):
            if pos >= p['end']:
                break
            v, new_pos = read_varint(buf, pos)
            vals.append((pos - p['start'], v))
            pos = new_pos
        
        print(f"    Varints from start: {vals}")
