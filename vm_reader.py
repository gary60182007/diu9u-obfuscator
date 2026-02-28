"""
Capture the VM's r table reference and use its own reader functions
to deserialize the script data section.
"""
import sys, time, json, re, struct
sys.path.insert(0, '.')

with open(r'unobfuscator\pending crack\bloxburg_script.lua', 'r', encoding='utf-8', errors='replace') as f:
    source = f.read()

exec(open('run_luraph_test.py').read().split("print('Reading source...')")[0])
source = preprocess_luau(source)

from unobfuscator.utils.lua_runtime import LuaRuntimeWrapper, LuaRuntimeError

runtime = LuaRuntimeWrapper(op_limit=2_000_000_000, timeout=120)
runtime._init_runtime()
runtime.lua.execute("_G._protos = {}; _G._saved = {}")

# Inject prototype capture hook
pat = re.compile(
    r'(\)\[(?:\d+|0[xXbBoO][0-9a-fA-F_]+)\]=function\()'
    r'([A-Za-z_]\w*)' r',' r'([A-Za-z_]\w*)' r'\)'
    r'(local\s+[A-Za-z_]\w*(?:,[A-Za-z_]\w*){9,}=)'
    r'(\2\[)'
)
m = pat.search(source)
p1 = m.group(2)
full_match = m.group(0)
lp = full_match.index('local')
hook = (
    f'if {p1}==nil then return function(...)return end end;'
    f'do local _p={{}};for _i=1,11 do _p[_i]={p1}[_i] end;'
    f'_p.id=#_G._protos+1;table.insert(_G._protos,_p) end;'
)
modified = source[:m.start()] + full_match[:lp] + hook + full_match[lp:] + source[m.end():]

# Inject: save REFERENCE to the r table after z:zy(r)
zy_matches = list(re.finditer(r':zy\((\w+)\)', modified))
zm = zy_matches[0]
r_arg = zm.group(1)
semi_pos = modified.index(';', zm.end())
capture = f';_G._r={r_arg};_G._saved.done=true'
modified = modified[:semi_pos+1] + capture + modified[semi_pos+1:]
print(f"Injected r table capture after z:zy({r_arg})")

modified = runtime.suppress_vm_errors(modified)

print("Executing...")
t0 = time.time()
try:
    runtime.execute(modified)
except LuaRuntimeError as e:
    print(f"Stopped after {time.time()-t0:.1f}s: {str(e)[:100]}")

def li(expr):
    v = runtime.lua.eval(f"tonumber({expr})")
    return int(v) if v is not None else None

def ls(expr):
    v = runtime.lua.eval(expr)
    return str(v) if v is not None else None

runtime.lua.execute("_G._op_count = 0; _G._op_limit = 10000000000")

# Verify r table captured
r_type = ls("type(_G._r)")
print(f"_G._r type: {r_type}")
if str(r_type) != 'table':
    print("ERROR: r table not captured!")
    sys.exit(1)

# Check key entries
r10 = li("_G._r[10]")
buf_len = li("buffer.len(_G._r[33])")
print(f"r[10] (offset after init): {r10}")
print(f"Buffer length: {buf_len}")

# Enumerate all function entries in r
print("\nFunction entries in r table:")
runtime.lua.execute("""
_G._r_funcs = {}
for k = 1, 200 do
    if type(_G._r[k]) == 'function' then
        table.insert(_G._r_funcs, k)
    end
end
""")
n_funcs = li("#_G._r_funcs") or 0
func_indices = []
for i in range(1, n_funcs + 1):
    idx = li(f"_G._r_funcs[{i}]")
    func_indices.append(idx)
print(f"  Indices: {func_indices}")

# Set r[10] to start of script data
SCRIPT_START = 94736
runtime.lua.execute(f"_G._r[10] = {SCRIPT_START}")
print(f"\nSet r[10] to {SCRIPT_START}")

# Read sub-buffer using r[54]
print("\n=== Sub-buffer via r[54] ===")
try:
    runtime.lua.execute("""
    _G._op_count = 0
    _G._sub = _G._r[54]()
    _G._sub_len = buffer.len(_G._sub)
    """)
    sub_len = li("_G._sub_len")
    r10_after = li("_G._r[10]")
    print(f"Sub-buffer: {sub_len} bytes, r[10] now: {r10_after}")
    
    runtime.lua.execute("""
    _G._sh = ""
    for i = 0, _G._sub_len - 1 do
        _G._sh = _G._sh .. string.format("%02x", buffer.readu8(_G._sub, i))
    end
    """)
    sub_hex = ls("_G._sh")
    sub_data = bytes.fromhex(sub_hex)
    print(f"Hex: {sub_hex}")
    for i in range(sub_len // 8):
        print(f"  double[{i}]: {struct.unpack_from('<d', sub_data, i*8)[0]}")
except Exception as e:
    print(f"Error: {e}")

# Read varints using r[46]
print("\n=== Varints via r[46] ===")
varints = []
try:
    for i in range(200):
        runtime.lua.execute("_G._op_count = 0")
        off_b = li("_G._r[10]")
        runtime.lua.execute("_G._tv = _G._r[46]()")
        v = li("_G._tv")
        off_a = li("_G._r[10]")
        if v is None or off_a is None:
            break
        varints.append((off_b, v, off_a - off_b))
except Exception as e:
    print(f"Error after {len(varints)} varints: {e}")

print(f"Read {len(varints)} varints")
for i, (off, v, c) in enumerate(varints[:80]):
    print(f"  [{i:3d}] off={off:7d} val={v:10d} ({c}B)")

# Reset to after sub-buffer and try r[50] (complex/tag-dispatch reader)
print("\n=== Complex reader r[50] ===")
r10_after_sub = varints[0][0] if varints else (r10_after if r10_after else SCRIPT_START + 37)
runtime.lua.execute(f"_G._r[10] = {r10_after_sub}")
print(f"Reset r[10] to {r10_after_sub}")

complex_vals = []
try:
    for i in range(100):
        runtime.lua.execute("_G._op_count = 0")
        off_b = li("_G._r[10]")
        runtime.lua.execute("""
        local ok, val = pcall(_G._r[50])
        if ok then
            _G._cv = val
            _G._cvt = type(val)
            if type(val) == 'number' then _G._cvs = tostring(val)
            elseif type(val) == 'string' then _G._cvs = val
            elseif type(val) == 'boolean' then _G._cvs = tostring(val)
            elseif val == nil then _G._cvs = 'nil'; _G._cvt = 'nil'
            else _G._cvs = tostring(val) end
        else
            _G._cvt = 'error'
            _G._cvs = tostring(val)
        end
        """)
        off_a = li("_G._r[10]")
        cvt = ls("_G._cvt")
        cvs = ls("_G._cvs")
        consumed = (off_a - off_b) if off_a and off_b else 0
        complex_vals.append((off_b, cvt, cvs, consumed))
        if str(cvt) == 'error':
            print(f"  [{i}] off={off_b} ERROR: {cvs}")
            break
except Exception as e:
    print(f"Error after {len(complex_vals)} values: {e}")

print(f"Read {len(complex_vals)} complex values")
for i, (off, t, s, c) in enumerate(complex_vals[:80]):
    disp = repr(s)[:60] if t == 'string' else s
    print(f"  [{i:3d}] off={off:7d} type={t:8s} val={disp} ({c}B)")

# Now try the FULL reader chain: read from 94773 trying to deserialize a prototype
# The deserialization function is C[58] defined in F9
# Let me try to find and call it
print("\n=== Exploring C table (from F9) ===")
# C was a parameter in F9, we need to find it
# Actually, let me check if there's a stored reference to the deserialization function
# The r table might have additional entries set by F9/o9/C9

# Check for table entries in r
print("Table entries in r:")
runtime.lua.execute("""
_G._r_tables = {}
for k = 1, 200 do
    if type(_G._r[k]) == 'table' then
        table.insert(_G._r_tables, k)
    end
end
""")
n_tables = li("#_G._r_tables") or 0
for i in range(1, n_tables + 1):
    idx = li(f"_G._r_tables[{i}]")
    tlen = li(f"#{'{'}for k,v in pairs(_G._r[{idx}]) do end; return 0{'}'}")
    # Get table info
    runtime.lua.execute(f"""
    _G._tk = {{}}
    for k, v in pairs(_G._r[{idx}]) do
        table.insert(_G._tk, tostring(k) .. "=" .. type(v))
    end
    """)
    n_tk = li("#_G._tk") or 0
    entries = []
    for j in range(1, min(n_tk + 1, 20)):
        entries.append(ls(f"_G._tk[{j}]"))
    print(f"  r[{idx}]: {entries[:10]}")

# Save all results
results = {
    'r10_init_end': r10,
    'buf_len': buf_len,
    'func_indices': func_indices,
    'sub_buffer_len': sub_len if 'sub_len' in dir() else None,
    'varints': [(o, v, c) for o, v, c in varints[:200]],
    'complex_vals': [(o, t, s[:100], c) for o, t, s, c in complex_vals],
}
with open('vm_reader_results.json', 'w') as f:
    json.dump(results, f, indent=2, default=str)
print(f"\nSaved to vm_reader_results.json")
