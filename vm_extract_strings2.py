"""
Extract ALL entries from r[57] - strings, tuples, numbers, everything.
Also capture the full tuple format (string + hash) for table entries.
"""
import sys, time, json, re, struct
sys.path.insert(0, '.')

with open(r'unobfuscator\pending crack\bloxburg_script.lua', 'r', encoding='utf-8', errors='replace') as f:
    source = f.read()

exec(open('run_luraph_test.py').read().split("print('Reading source...')")[0])
source = preprocess_luau(source)

from unobfuscator.utils.lua_runtime import LuaRuntimeWrapper, LuaRuntimeError

modified = source

# Inject in q9 after ZF loop - dump ALL entries from W[57]
q9_start = modified.find('q9=function(')
q9_params = re.search(r'q9=function\((\w+),(\w+),(\w+),(\w+),(\w+)\)', modified[q9_start:])
W_var = q9_params.group(4)
C_var = q9_params.group(3)

inject_marker = re.search(r'end;end;(' + re.escape(C_var) + r'=\(' + re.escape(W_var) + r'\[)', modified[q9_start:])
inject_pos = q9_start + inject_marker.start() + len('end;end;')

dump_code = (
    f'_G._str_count=0;'
    f'_G._type_counts={{}};'
    f'for _k,_v in pairs({W_var}[57]) do '
    f'_G._str_count=_G._str_count+1;'
    f'local _t=type(_v);'
    f'_G._type_counts[_t]=(_G._type_counts[_t] or 0)+1;'
    f'if _t=="string" then '
    f'local _h="";'
    f'for _j=1,#_v do _h=_h..string.format("%02x",string.byte(_v,_j)) end;'
    f'_G._string_dump[_k]={{t="s",hex=_h,len=#_v}} '
    f'elseif _t=="table" then '
    f'local _v1=_v[1];'
    f'local _v2=_v[2];'
    f'if type(_v1)=="string" then '
    f'local _h="";'
    f'for _j=1,#_v1 do _h=_h..string.format("%02x",string.byte(_v1,_j)) end;'
    f'_G._string_dump[_k]={{t="ts",hex=_h,len=#_v1,hash=_v2}} '
    f'elseif type(_v1)=="number" then '
    f'_G._string_dump[_k]={{t="tn",val=_v1,hash=_v2}} '
    f'else '
    f'_G._string_dump[_k]={{t="t?",v1t=type(_v1),v2t=type(_v2)}} '
    f'end '
    f'elseif _t=="number" then '
    f'_G._string_dump[_k]={{t="n",val=_v}} '
    f'elseif _t=="boolean" then '
    f'_G._string_dump[_k]={{t="b",val=_v}} '
    f'else '
    f'_G._string_dump[_k]={{t=_t}} '
    f'end '
    f'end;'
    f'_G._dump_r10={W_var}[10];'
)

modified = modified[:inject_pos] + dump_code + modified[inject_pos:]
print(f"Dump injected at pos {inject_pos}")

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
runtime.lua.execute("_G._protos = {}; _G._string_dump = {}; _G._str_count = 0; _G._type_counts = {}")

modified = runtime.suppress_vm_errors(modified)

print("Executing VM (15B ops, 600s)...")
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

str_count = li('_G._str_count')
dump_r10 = li('_G._dump_r10')
print(f"\nTotal entries: {str_count}")
print(f"r[10] at dump: {dump_r10}")

# Type counts
runtime.lua.execute("""
_G._tc_str = ''
for k, v in pairs(_G._type_counts) do
    _G._tc_str = _G._tc_str .. k .. '=' .. v .. ' '
end
""")
print(f"Type distribution: {ls('_G._tc_str')}")

# Get all keys
runtime.lua.execute("""
_G._all_keys = {}
for k in pairs(_G._string_dump) do
    table.insert(_G._all_keys, k)
end
table.sort(_G._all_keys)
""")
n_keys = li("#_G._all_keys") or 0
print(f"Dump entries: {n_keys}")

# Extract all entries
all_entries = {}
batch = 20
for start in range(1, n_keys + 1, batch):
    end_idx = min(start + batch - 1, n_keys)
    runtime.lua.execute(f"""
    _G._batch = {{}}
    for i = {start}, {end_idx} do
        local k = _G._all_keys[i]
        local e = _G._string_dump[k]
        if e then
            local info = tostring(k) .. '|' .. (e.t or '?')
            if e.hex then
                info = info .. '|' .. e.hex .. '|' .. tostring(e.len)
            elseif e.val ~= nil then
                info = info .. '|' .. tostring(e.val)
            elseif e.v1t then
                info = info .. '|v1=' .. e.v1t .. ',v2=' .. tostring(e.v2t)
            end
            if e.hash ~= nil then
                info = info .. '|h=' .. tostring(e.hash)
            end
            table.insert(_G._batch, info)
        end
    end
    """)
    bn = li("#_G._batch") or 0
    for bi in range(1, bn + 1):
        line = ls(f"_G._batch[{bi}]")
        if line:
            parts = line.split('|')
            k = int(parts[0])
            t = parts[1]
            entry = {'type': t}
            if t in ('s', 'ts'):
                hex_str = parts[2]
                slen = int(parts[3])
                try:
                    raw = bytes.fromhex(hex_str)
                    entry['raw'] = hex_str
                    entry['text'] = raw.decode('utf-8', errors='replace')
                    entry['len'] = slen
                except:
                    entry['raw'] = hex_str
                    entry['text'] = f'<decode_error>'
                if t == 'ts' and len(parts) > 4:
                    entry['hash'] = parts[4].replace('h=', '')
            elif t == 'tn':
                entry['val'] = float(parts[2]) if '.' in parts[2] else int(parts[2])
                if len(parts) > 3:
                    entry['hash'] = parts[3].replace('h=', '')
            elif t == 'n':
                entry['val'] = float(parts[2]) if '.' in parts[2] or 'e' in parts[2].lower() or 'inf' in parts[2].lower() else int(parts[2])
            elif t == 'b':
                entry['val'] = parts[2] == 'true'
            elif t == 't?':
                entry['info'] = parts[2] if len(parts) > 2 else 'unknown'
            all_entries[k] = entry

# Save full dump
with open('luraph_strings_full.json', 'w', encoding='utf-8') as f:
    json.dump(all_entries, f, indent=2, ensure_ascii=False, sort_keys=True)
print(f"\nSaved {len(all_entries)} entries to luraph_strings_full.json")

# Analyze
strings = {k: v for k, v in all_entries.items() if v['type'] in ('s', 'ts')}
numbers = {k: v for k, v in all_entries.items() if v['type'] in ('n', 'tn')}
bools = {k: v for k, v in all_entries.items() if v['type'] == 'b'}
other = {k: v for k, v in all_entries.items() if v['type'] not in ('s', 'ts', 'n', 'tn', 'b')}

print(f"\n=== Entry Types ===")
print(f"  Strings: {len(strings)}")
print(f"  Numbers: {len(numbers)}")
print(f"  Booleans: {len(bools)}")
print(f"  Other: {len(other)}")

# Show readable strings
print(f"\n=== Readable Strings ===")
readable = []
for k in sorted(strings.keys()):
    v = strings[k]
    text = v.get('text', '')
    if text and len(text) > 0:
        printable = sum(1 for c in text if c.isprintable() or c in '\n\r\t')
        if printable > len(text) * 0.7 and len(text) > 1:
            readable.append((k, text))

for k, text in readable[:150]:
    print(f"  [{k:4d}] {text[:120]}")
if len(readable) > 150:
    print(f"  ... and {len(readable) - 150} more")

# Show binary/constant strings (likely f64 or format strings)
print(f"\n=== Binary Constants (8-byte) ===")
binary_count = 0
for k in sorted(strings.keys()):
    v = strings[k]
    if v.get('len') == 8:
        raw = bytes.fromhex(v['raw'])
        f64_val = struct.unpack('<d', raw)[0]
        f64_be = struct.unpack('>d', raw)[0]
        binary_count += 1
        if binary_count <= 30:
            print(f"  [{k:4d}] hex={v['raw']} f64_le={f64_val:.6g} f64_be={f64_be:.6g}")
if binary_count > 30:
    print(f"  ... and {binary_count - 30} more 8-byte entries")

# Show number constants
print(f"\n=== Number Constants (first 50) ===")
for k in sorted(numbers.keys())[:50]:
    v = numbers[k]
    val = v.get('val', 'N/A')
    print(f"  [{k:4d}] {val}")
if len(numbers) > 50:
    print(f"  ... and {len(numbers) - 50} more")

# Show "other" types
if other:
    print(f"\n=== Other Types ===")
    for k in sorted(other.keys())[:20]:
        print(f"  [{k:4d}] {other[k]}")
