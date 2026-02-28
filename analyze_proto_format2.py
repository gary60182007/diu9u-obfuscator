"""
Trace prototype deserialization by wrapping r[58].
Instead of modifying c9, hook r[58] after m9 sets it up.
"""
import sys, time, json, re
sys.path.insert(0, '.')

with open(r'unobfuscator\pending crack\bloxburg_script.lua', 'r', encoding='utf-8', errors='replace') as f:
    source = f.read()

exec(open('run_luraph_test.py').read().split("print('Reading source...')")[0])
source = preprocess_luau(source)
from unobfuscator.utils.lua_runtime import LuaRuntimeWrapper, LuaRuntimeError

modified = source

# Strategy: inject a hook in the W function (lazy deserializer) between 
# the m9 call (w=179) and d9 call (w=413) to wrap r[58].
# The _9 loop iterates w=62,179,296,413,530.
# After w=179 (m9), r[58] is set. Before w=413 (d9), we wrap it.
# We need to find the _9 call inside the W loop and inject after the loop body.

# Actually, simpler: inject in d9 BEFORE the loop, wrapping C[58] (= r[58] = C[0x3a])
d9_pat = re.compile(r'(d9=function\((\w+),(\w+),(\w+),(\w+)\))')
d9_m = d9_pat.search(modified)
if d9_m:
    d9_z, d9_r, d9_C, d9_W = [d9_m.group(j) for j in range(2, 6)]
    print(f"d9 params: z={d9_z}, r={d9_r}, C={d9_C}, W={d9_W}")
    # d9 calls c9 which calls C[58]() (C is the state table here)
    # Inject wrapper for C[58] at d9 start
    # Note: in d9, C is the state table (r from _9's perspective)
    inject = (
        f'do local _orig={d9_C}[58];'
        f'local _ct=_G._c9_trace;'
        f'{d9_C}[58]=function() '
        f'local _n=(_G._c9_n or 0)+1;_G._c9_n=_n;'
        f'local _s={d9_C}[10];'
        f'local _r=_orig();'
        f'local _e={d9_C}[10];'
        f'if _n<=200 then '
        f'_ct[_n]=tostring(_s).."|"..tostring(_e).."|"..tostring(_n) '
        f'end;'
        f'return _r end end;'
    )
    modified = modified[:d9_m.end()] + inject + modified[d9_m.end():]
    print("d9 wrapper injected")

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

print("Executing VM...")
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

n_c9 = li('_G._c9_n') or 0
n_protos = li('#_G._protos') or 0
print(f"\nr[58] calls: {n_c9}")
print(f"Protos captured: {n_protos}")

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

print(f"\n=== Prototype byte ranges ({len(proto_ranges)} traced) ===")
for i, p in enumerate(proto_ranges):
    if i < 20 or i >= len(proto_ranges) - 5:
        print(f"  Proto[{p['idx']:3d}] offset {p['start']:6d}-{p['end']:6d} ({p['size']:5d} bytes)")
    elif i == 20:
        print(f"  ...")

if proto_ranges:
    sizes = [p['size'] for p in proto_ranges]
    print(f"\n  Total: {len(proto_ranges)} protos")
    print(f"  Size range: {min(sizes)}-{max(sizes)}, avg={sum(sizes)/len(sizes):.0f}")
    print(f"  First: {proto_ranges[0]['start']}, Last end: {proto_ranges[-1]['end']}")
    print(f"  Total data: {proto_ranges[-1]['end'] - proto_ranges[0]['start']} bytes")

# Parse first few protos from raw buffer
import struct
with open(r'unobfuscator\cracked script\buffer_1_1064652.bin', 'rb') as f:
    buf = f.read()

def read_varint(buf, pos):
    result = 0; shift = 0
    while True:
        b = buf[pos]; pos += 1
        result |= (b & 0x7F) << shift
        shift += 7
        if b < 128: break
    return result, pos

if proto_ranges:
    print(f"\n=== First 10 proto raw data ===")
    for p in proto_ranges[:10]:
        print(f"\n  Proto[{p['idx']}] ({p['size']} bytes) at offset {p['start']}:")
        raw = buf[p['start']:min(p['end'], p['start']+60)]
        print(f"    hex: {raw.hex()}")
        
        # Try parsing varints from start
        pos = p['start']
        vals = []
        for j in range(15):
            if pos >= p['end']: break
            try:
                v, new_pos = read_varint(buf, pos)
                vals.append((pos - p['start'], v, new_pos - pos))
                pos = new_pos
            except:
                break
        print(f"    varints: {[(off, val) for off, val, _ in vals]}")

    # Also show proto metadata from captured protos
    print(f"\n=== Proto metadata (from VM capture) ===")
    for i in range(1, min(n_protos + 1, 11)):
        runtime.lua.execute(f"""
        local p = _G._protos[{i}]
        local parts = {{}}
        for j=1,11 do
            local v = p[j]
            if type(v) == 'table' then
                parts[j] = 'T#' .. #v
            elseif type(v) == 'function' then
                parts[j] = 'fn'
            elseif v == nil then
                parts[j] = 'nil'
            else
                parts[j] = tostring(v)
            end
        end
        _G._tmp = table.concat(parts, '|')
        """)
        vals = ls('_G._tmp')
        if vals:
            parts = vals.split('|')
            labels = ['r10/a', 'env/b', 'const/c', 'exec/d', 'ups/e', 'src/f', 'r4/g', 'flag/h', 'inst/i', 'debug/j', 'hash/k']
            items = []
            for j, v in enumerate(parts):
                label = labels[j] if j < len(labels) else f'[{j+1}]'
                items.append(f'{label}={v}')
            print(f"  Proto[{i}]: {', '.join(items)}")

# Save proto ranges
with open('proto_ranges.json', 'w') as f:
    json.dump(proto_ranges, f, indent=2)
print(f"\nSaved {len(proto_ranges)} proto ranges to proto_ranges.json")
