"""
Instrument ZF to log EXACT buffer positions and values for every entry.
This gives us the complete format specification for building a Python parser.
"""
import sys, time, json, re, struct
sys.path.insert(0, '.')

with open(r'unobfuscator\pending crack\bloxburg_script.lua', 'r', encoding='utf-8', errors='replace') as f:
    source = f.read()

exec(open('run_luraph_test.py').read().split("print('Reading source...')")[0])
source = preprocess_luau(source)

from unobfuscator.utils.lua_runtime import LuaRuntimeWrapper, LuaRuntimeError

modified = source

# ZF=function(z,r,C,W)local Q,i,O,a=r[39](),116;
# After ZF completes, 'a' is the decoded value and it stores to r[57][C]
# We need to log: r[10] BEFORE the tag read, r[10] AFTER storing, tag Q, index C, value a

# Strategy: inject BEFORE ZF's tag read to capture start position,
# and inside the store phase to capture end position and value

# Find ZF and wrap it with logging
zf_pat = re.compile(r'(ZF=function\((\w+),(\w+),(\w+),(\w+)\))')
zf_m = zf_pat.search(modified)
if zf_m:
    z_p, r_p, C_p, W_p = zf_m.group(2), zf_m.group(3), zf_m.group(4), zf_m.group(5)
    print(f"ZF found: params z={z_p}, r={r_p}, C={C_p}, W={W_p}")
    
    # Inject start position capture right after function signature
    inject_start = (
        f'local _zf_start={r_p}[10];'
    )
    modified = modified[:zf_m.end()] + inject_start + modified[zf_m.end():]
    
    # Now find the store point in ZF: r[57][C]=...
    # Pattern: (r[57])[C]=(a) or r[57][C]=({a,...})
    # After the store, inject end position capture
    # Find: (r[57])[C]=(a); — the non-hash storage
    # This is in the i<116 and i>67 branch
    
    # Find the store pattern after ZF
    zf_start_pos = zf_m.start()
    # Search for r[57][C] assignment within ZF (next ~2000 chars)
    store_pat = re.compile(
        r'(\(' + re.escape(r_p) + r'\[57\]\)\[' + re.escape(C_p) + r'\]=\((\w+)\);)'
    )
    store_m = store_pat.search(modified, zf_start_pos)
    if store_m:
        val_var = store_m.group(2)  # the variable being stored (should be 'a')
        print(f"Store pattern found at {store_m.start()}, val_var={val_var}")
        
        # Inject AFTER the store
        inject_end = (
            f'do local _zf_end={r_p}[10];'
            f'local _n=_G._zf_n+1;_G._zf_n=_n;'
            f'if _n<=1170 then '
            f'local _t=type({val_var});'
            f'local _e={{s=_zf_start,e=_zf_end,i={C_p},t=_t}};'
            f'if _t=="number" then _e.v={val_var} '
            f'elseif _t=="string" then '
            f'_e.len=#({val_var});'
            f'local _h="";'
            f'for _j=1,math.min(#({val_var}),32) do _h=_h..string.format("%02x",string.byte({val_var},_j)) end;'
            f'_e.hex=_h '
            f'elseif _t=="boolean" then _e.v={val_var} and 1 or 0 '
            f'end;'
            f'_G._zf_trace[_n]=_e '
            f'end end;'
        )
        modified = modified[:store_m.end()] + inject_end + modified[store_m.end():]
        print("End logging injected after store")
    else:
        print("WARNING: store pattern not found, trying alternative")
        # Try the hash variant too: r[57][C]=({a,(r[11](a))})
        # Or search more broadly
        store_search = modified[zf_start_pos:zf_start_pos+3000]
        r57_refs = list(re.finditer(r'57\]', store_search))
        print(f"r[57] refs in ZF: {len(r57_refs)}")
        for m in r57_refs:
            ctx = store_search[max(0,m.start()-20):m.start()+40]
            print(f"  {repr(ctx)}")

# Also inject in q9 to dump the trace data after all ZF calls
q9_start = modified.find('q9=function(')
q9_params = re.search(r'q9=function\((\w+),(\w+),(\w+),(\w+),(\w+)\)', modified[q9_start:])
W_var = q9_params.group(4)
C_var = q9_params.group(3)
inject_marker = re.search(r'end;end;(' + re.escape(C_var) + r'=\(' + re.escape(W_var) + r'\[)', modified[q9_start:])
inject_pos = q9_start + inject_marker.start() + len('end;end;')

dump_code = (
    f'_G._zf_done=true;'
    f'_G._dump_r10={W_var}[10];'
)
modified = modified[:inject_pos] + dump_code + modified[inject_pos:]
print("q9 dump injected")

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
_G._zf_trace = {}
_G._zf_n = 0
_G._zf_done = false
""")

modified = runtime.suppress_vm_errors(modified)

print("\nExecuting VM (15B ops, 600s)...")
t0 = time.time()
try:
    runtime.execute(modified)
except LuaRuntimeError as e:
    elapsed = time.time() - t0
    print(f"Stopped after {elapsed:.1f}s: {str(e)[:100]}")

runtime.lua.execute("_G._op_count = 0; _G._op_limit = 10000000000")

def li(expr):
    v = runtime.lua.eval(f"tonumber({expr})")
    return int(v) if v is not None else None

def ls(expr):
    v = runtime.lua.eval(expr)
    return str(v) if v is not None else None

print(f"\nZF done: {ls('tostring(_G._zf_done)')}")
print(f"ZF trace entries: {li('_G._zf_n')}")
print(f"r[10] at dump: {li('_G._dump_r10')}")

n = li('_G._zf_n') or 0
if n == 0:
    print("No trace data!")
    sys.exit(1)

# Extract trace data in batches
trace_data = []
batch = 50
for start in range(1, min(n+1, 1171), batch):
    end_idx = min(start + batch - 1, n, 1170)
    runtime.lua.execute(f"""
    _G._batch = {{}}
    for i = {start}, {end_idx} do
        local e = _G._zf_trace[i]
        if e then
            local line = e.s .. '|' .. e.e .. '|' .. e.i .. '|' .. e.t
            if e.v ~= nil then
                line = line .. '|v=' .. tostring(e.v)
            end
            if e.len then
                line = line .. '|len=' .. e.len
            end
            if e.hex then
                line = line .. '|hex=' .. e.hex
            end
            table.insert(_G._batch, line)
        end
    end
    """)
    bn = li("#_G._batch") or 0
    for bi in range(1, bn + 1):
        line = ls(f"_G._batch[{bi}]")
        if line:
            parts = line.split('|')
            entry = {
                'start': int(parts[0]),
                'end': int(parts[1]),
                'index': int(parts[2]),
                'type': parts[3],
            }
            for p in parts[4:]:
                if p.startswith('v='):
                    try:
                        entry['val'] = float(p[2:]) if '.' in p[2:] or 'e' in p[2:].lower() else int(p[2:])
                    except:
                        entry['val'] = p[2:]
                elif p.startswith('len='):
                    entry['len'] = int(p[4:])
                elif p.startswith('hex='):
                    entry['hex'] = p[4:]
            trace_data.append(entry)

print(f"\nExtracted {len(trace_data)} trace entries")

# Save trace
with open('zf_trace.json', 'w') as f:
    json.dump(trace_data, f, indent=2)
print("Saved to zf_trace.json")

# Analyze: bytes consumed per entry
with open(r'unobfuscator\cracked script\buffer_1_1064652.bin', 'rb') as fb:
    buf = fb.read()

print(f"\n=== Buffer format analysis ===")
# For each entry, show: start_offset, bytes_consumed, tag_byte, type, value
tag_sizes = {}
for i, e in enumerate(trace_data[:50]):
    consumed = e['end'] - e['start']
    tag = buf[e['start']]
    raw = buf[e['start']:e['end']]
    
    val_str = ''
    if e['type'] == 'number':
        val_str = f"val={e.get('val', '?')}"
    elif e['type'] == 'string':
        val_str = f"len={e.get('len', '?')} hex={e.get('hex', '')[:20]}"
    elif e['type'] == 'boolean':
        val_str = f"val={e.get('val', '?')}"
    
    if consumed <= 20:
        raw_hex = raw.hex()
    else:
        raw_hex = raw[:10].hex() + f'...({consumed}B)'
    
    print(f"  [{e['index']:4d}] off={e['start']:5d}-{e['end']:5d} "
          f"({consumed:3d}B) tag={tag:3d}(0x{tag:02x}) "
          f"raw=[{raw_hex}] {e['type']}: {val_str}")
    
    key = (tag, e['type'])
    if key not in tag_sizes:
        tag_sizes[key] = []
    tag_sizes[key].append(consumed)

print(f"\n=== Tag → size mapping ===")
for (tag, typ), sizes in sorted(tag_sizes.items()):
    min_s = min(sizes)
    max_s = max(sizes)
    avg_s = sum(sizes) / len(sizes)
    print(f"  tag={tag:3d}(0x{tag:02x}) type={typ:8s}: count={len(sizes):4d}, "
          f"size={min_s}-{max_s} (avg={avg_s:.1f})")

# Full tag size analysis (all entries)
tag_sizes_full = {}
for e in trace_data:
    consumed = e['end'] - e['start']
    tag = buf[e['start']]
    key = (tag, e['type'])
    if key not in tag_sizes_full:
        tag_sizes_full[key] = {'count': 0, 'sizes': set()}
    tag_sizes_full[key]['count'] += 1
    tag_sizes_full[key]['sizes'].add(consumed)

print(f"\n=== Full tag analysis (all {len(trace_data)} entries) ===")
for (tag, typ), info in sorted(tag_sizes_full.items()):
    sizes = sorted(info['sizes'])
    print(f"  tag={tag:3d}(0x{tag:02x}) type={typ:8s}: count={info['count']:4d}, sizes={sizes}")
