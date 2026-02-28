"""
Extract prototype data from the 139 captured protos.
Also trace C[56] to understand prototype deserialization.
Focus on understanding the buffer layout from 4306 onwards.
"""
import sys, time, json, re
sys.path.insert(0, '.')

with open(r'unobfuscator\pending crack\bloxburg_script.lua', 'r', encoding='utf-8', errors='replace') as f:
    source = f.read()

exec(open('run_luraph_test.py').read().split("print('Reading source...')")[0])
source = preprocess_luau(source)

from unobfuscator.utils.lua_runtime import LuaRuntimeWrapper, LuaRuntimeError

modified = source

# Find C[56] and extract its full body to understand structure
ret_start = modified.index('return({')
c56_pat = re.compile(r'\)\[56\]\s*=\s*function\((\w+),(\w+)\)')
c56_m = c56_pat.search(modified, ret_start)
if c56_m:
    c56_start = c56_m.start()
    # Extract parameters
    c56_p1, c56_p2 = c56_m.group(1), c56_m.group(2)
    print(f"C[56] params: ({c56_p1}, {c56_p2})")
    
    # Extract first 600 chars of body for analysis
    body_start = c56_m.end()
    body_preview = modified[body_start:body_start+1500]
    print(f"\nC[56] body preview:")
    # Clean it up with newlines
    clean = body_preview.replace(';', ';\n  ')
    print(f"  {clean[:1200]}")
    
    # Count z: method calls in the body (next 5000 chars)
    body_chunk = modified[body_start:body_start+5000]
    method_calls = re.findall(r'z:(\w+)\(', body_chunk)
    print(f"\nMethods called in C[56]: {sorted(set(method_calls))}")
    
    # Find what r[] indices are accessed
    r_refs = re.findall(r'(?:' + re.escape(c56_p1) + r'|' + re.escape(c56_p2) + r')\[(\d+|0[xXbBoO][0-9a-fA-F_]+)\]', body_chunk)
    dec_refs = set()
    for ref in r_refs:
        try:
            dec_refs.add(int(ref.replace('_', ''), 0))
        except:
            dec_refs.add(ref)
    print(f"r[] indices in C[56]: {sorted(dec_refs)}")

# Inject C[56] tracing
if c56_m:
    inject_c56 = (
        f'do local _n=(_G._c56_n or 0)+1;_G._c56_n=_n;'
        f'if _n<=200 then '
        f'_G._c56_trace[_n]={{r10={c56_p1}[10]}} end end;'
    )
    modified = modified[:c56_m.end()] + inject_c56 + modified[c56_m.end():]
    print("\nC[56] tracing injected")

# Inject in d9 to understand what it does with the buffer
d9_pat = re.compile(r'(d9=function\((\w+),(\w+),(\w+),(\w+)\))')
d9_m = d9_pat.search(modified)
if d9_m:
    d9_z, d9_r, d9_C, d9_W = [d9_m.group(j) for j in range(2, 6)]
    # d9 is called from _9 as z:d9(i,r,W) — so d9's params are (z,i,r,W)
    # r is the state table, i is... something
    # Let's trace r[10] before and after
    inject_d9 = (
        f'_G._d9_start_r10={d9_C}[10];'
    )
    modified = modified[:d9_m.end()] + inject_d9 + modified[d9_m.end():]
    
    # Also inject at the END of d9 to capture final r[10]
    # Find end of d9 function
    d9_body_start = d9_m.end()
    depth = 1
    pos = d9_body_start
    in_str = False
    sc = None
    while pos < len(modified) and depth > 0:
        c = modified[pos]
        if in_str:
            if c == '\\': pos += 2; continue
            if c == sc: in_str = False
            pos += 1; continue
        if c in '"\'': in_str = True; sc = c; pos += 1; continue
        if c == '-' and pos+1 < len(modified) and modified[pos+1] == '-':
            nl = modified.find('\n', pos); pos = nl+1 if nl>=0 else len(modified); continue
        word_start = pos
        if c.isalpha() or c == '_':
            while pos < len(modified) and (modified[pos].isalnum() or modified[pos] == '_'):
                pos += 1
            word = modified[word_start:pos]
            if word in ('function', 'do', 'repeat'): depth += 1
            elif word == 'then':
                # Check if preceded by 'if' or 'elseif'
                before = modified[max(0,word_start-20):word_start].strip()
                if 'if' in before.split()[-1:] or 'elseif' in before.split()[-1:]:
                    depth += 1
            elif word in ('end',): depth -= 1
            elif word == 'until': depth -= 1
            continue
        pos += 1
    
    d9_end = pos
    inject_d9_end = f'_G._d9_end_r10={d9_C}[10];'
    modified = modified[:d9_end] + inject_d9_end + modified[d9_end:]
    print(f"d9 end tracing injected at pos {d9_end}")

# Extract d9 body for analysis
if d9_m:
    d9_body = modified[d9_m.start():d9_end]
    print(f"\nd9 body length: {len(d9_body)}")
    # Show first part
    d9_clean = d9_body[:800].replace(';', ';\n  ')
    print(f"d9 body preview:\n  {d9_clean}")
    
    # Methods called
    d9_methods = re.findall(r'z:(\w+)\(', d9_body)
    print(f"\nMethods in d9: {sorted(set(d9_methods))}")

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
_G._c56_trace = {}
_G._c56_n = 0
""")

modified = runtime.suppress_vm_errors(modified)

print("\n\nExecuting VM...")
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
print(f"C[56] calls: {li('_G._c56_n')}")
print(f"d9 start r10: {li('_G._d9_start_r10')}")
print(f"d9 end r10: {li('_G._d9_end_r10')}")
print(f"Protos: {li('#_G._protos')}")

# Show C[56] call offsets
n_c56 = li('_G._c56_n') or 0
print(f"\n=== C[56] calls (first 30 of {n_c56}) ===")
offsets = []
for i in range(1, min(n_c56+1, 31)):
    runtime.lua.execute(f"""
    local e = _G._c56_trace[{i}]
    _G._tmp = e and tostring(e.r10) or 'nil'
    """)
    r10 = li('_G._tmp')
    offsets.append(r10)
    print(f"  [{i:3d}] r10={r10}")

# Show proto details
print(f"\n=== Proto details (first 20) ===")
for i in range(1, min(li('#_G._protos') or 0, 21) + 1):
    runtime.lua.execute(f"""
    local p = _G._protos[{i}]
    local parts = {{}}
    for j=1,11 do
        local v = p[j]
        if type(v) == 'table' then
            parts[j] = '#' .. #v
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
        print(f"  Proto[{i:3d}]: {' '.join(f'[{j+1}]={v}' for j,v in enumerate(parts))}")

# Compute proto sizes from C[56] call offsets
if len(offsets) > 1:
    print(f"\n=== Proto sizes (from r10 deltas) ===")
    sizes = []
    for i in range(len(offsets)-1):
        if offsets[i] is not None and offsets[i+1] is not None:
            sz = offsets[i+1] - offsets[i]
            sizes.append(sz)
            if i < 20:
                print(f"  Proto[{i+1}]: {offsets[i]} → {offsets[i+1]} ({sz} bytes)")
    if sizes:
        print(f"\n  Total protos in trace: {len(sizes)+1}")
        print(f"  Min size: {min(sizes)}, Max size: {max(sizes)}, Avg: {sum(sizes)/len(sizes):.0f}")
