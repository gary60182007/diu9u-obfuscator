"""
Re-extract C[2] sparse entries with proper string handling.
Also check C[6] and C[11] for string entries.
"""
import sys, time, json, re
sys.path.insert(0, '.')

with open(r'unobfuscator\pending crack\bloxburg_script.lua', 'r', encoding='utf-8', errors='replace') as f:
    source = f.read()

exec(open('run_luraph_test.py').read().split("print('Reading source...')")[0])
source = preprocess_luau(source)
from unobfuscator.utils.lua_runtime import LuaRuntimeWrapper, LuaRuntimeError

modified = source

d9_pat = re.compile(r'(d9=function\((\w+),(\w+),(\w+),(\w+)\))')
d9_m = d9_pat.search(modified)
d9_C = d9_m.group(4)

inject = (
    f'do local _st={d9_C};'
    f'local _orig58=_st[58];'
    f'_st[58]=function() '
    f'local _r=_orig58();'
    f'local _n=(_G._pn or 0)+1;_G._pn=_n;'
    f'_G._ptables[_n]=_r;'
    f'return _r end;end;'
)
modified = modified[:d9_m.end()] + inject + modified[d9_m.end():]

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
    hook = f'if {p1}==nil then return function(...)return end end;'
    modified = modified[:m.start()] + full_match[:lp] + hook + full_match[lp:] + modified[m.end():]

runtime = LuaRuntimeWrapper(op_limit=15_000_000_000, timeout=600)
runtime._init_runtime()
runtime.lua.execute("_G._pn=0;_G._ptables={}")
modified = runtime.suppress_vm_errors(modified)

print("Executing VM...")
t0 = time.time()
try:
    runtime.execute(modified)
except LuaRuntimeError as e:
    print(f"Stopped after {time.time()-t0:.1f}s: {str(e)[:200]}")

runtime.lua.execute("_G._op_count=0;_G._op_limit=10000000000")

def li(expr):
    v = runtime.lua.eval(f"tonumber({expr})")
    return int(v) if v is not None else None

def ls(expr):
    v = runtime.lua.eval(expr)
    return str(v) if v is not None else None

n_protos = li('_G._pn') or 0
print(f"Protos: {n_protos}")

# Extract C[2] entries with full type info for all protos
all_c2_data = {}

for pi in range(1, n_protos + 1):
    runtime.lua.execute(f"""
    local _t = _G._ptables[{pi}]
    if not _t then _G._c2max = 0; return end
    local _v = _t[2]
    if type(_v) ~= "table" then _G._c2max = 0; return end
    local _max = 0
    for _k, _ in pairs(_v) do
        if type(_k) == "number" and _k > _max then _max = _k end
    end
    _G._c2max = _max
    """)
    c2_max = li('_G._c2max') or 0
    if c2_max == 0:
        continue
    
    entries = {}
    batch = 100
    for s in range(1, c2_max + 1, batch):
        e = min(s + batch - 1, c2_max)
        runtime.lua.execute(f"""
        local _t = _G._ptables[{pi}][2]
        local _p = {{}}
        for _i = {s}, {e} do
            local _v = _t[_i]
            if _v == nil then
                table.insert(_p, "N")
            elseif type(_v) == "number" then
                table.insert(_p, "n:" .. tostring(_v))
            elseif type(_v) == "string" then
                local _safe = string.gsub(_v, "[^%w%p%s]", "?")
                table.insert(_p, "s:" .. tostring(#_v) .. ":" .. string.sub(_safe, 1, 60))
            elseif type(_v) == "table" then
                local _v1 = _v[1]
                local _v2 = _v[2]
                if type(_v1) == "number" and type(_v2) == "number" then
                    table.insert(_p, "t:" .. tostring(math.floor(_v1)) .. ":" .. tostring(math.floor(_v2)))
                else
                    table.insert(_p, "t:?:?")
                end
            elseif type(_v) == "boolean" then
                table.insert(_p, "b:" .. tostring(_v))
            else
                table.insert(_p, "x:" .. type(_v))
            end
        end
        _G._tmp = table.concat(_p, "\\n")
        """)
        val = ls('_G._tmp')
        if val:
            for idx_off, line in enumerate(val.split('\n')):
                if line != 'N':
                    entries[s + idx_off] = line
    
    if entries:
        all_c2_data[pi] = entries

# Summary
total_entries = sum(len(v) for v in all_c2_data.values())
type_counts = {'number': 0, 'string': 0, 'table': 0, 'boolean': 0, 'other': 0}
all_strings = []

for pi, entries in all_c2_data.items():
    for idx, entry in entries.items():
        if entry.startswith('n:'):
            type_counts['number'] += 1
        elif entry.startswith('s:'):
            type_counts['string'] += 1
            parts = entry.split(':', 2)
            slen = int(parts[1])
            sval = parts[2] if len(parts) > 2 else ''
            all_strings.append({'proto': pi, 'inst': idx, 'len': slen, 'preview': sval})
        elif entry.startswith('t:'):
            type_counts['table'] += 1
        elif entry.startswith('b:'):
            type_counts['boolean'] += 1
        else:
            type_counts['other'] += 1

print(f"\nTotal C[2] entries: {total_entries}")
print(f"Type distribution: {type_counts}")
print(f"Unique strings: {len(all_strings)}")

# Show all string entries grouped by proto
print(f"\n{'='*70}")
print(f"STRING CONSTANTS IN C[2] BY PROTO")
print(f"{'='*70}")
for pi in sorted(all_c2_data.keys()):
    entries = all_c2_data[pi]
    str_entries = [(idx, e) for idx, e in entries.items() if e.startswith('s:')]
    if str_entries:
        print(f"\nProto[{pi}]:")
        for idx, entry in sorted(str_entries, key=lambda x: x[0]):
            parts = entry.split(':', 2)
            slen = parts[1]
            sval = parts[2] if len(parts) > 2 else ''
            print(f"  inst[{idx:3d}]: len={slen} \"{sval}\"")

# Show table entries (mode pairs)
print(f"\n{'='*70}")
print(f"TABLE ENTRIES IN C[2] (first 50)")
print(f"{'='*70}")

with open('luraph_strings_full.json', 'r', encoding='utf-8') as f:
    gt_raw = json.load(f)

count = 0
for pi in sorted(all_c2_data.keys()):
    entries = all_c2_data[pi]
    tbl_entries = [(idx, e) for idx, e in entries.items() if e.startswith('t:')]
    for idx, entry in sorted(tbl_entries, key=lambda x: x[0]):
        parts = entry.split(':')
        if len(parts) >= 3:
            try:
                v1, v2 = int(parts[1]), int(parts[2])
                const_val = ''
                gt_entry = gt_raw.get(str(v1))
                if gt_entry:
                    cv = gt_entry.get('val', '?')
                    if isinstance(cv, str) and len(cv) > 30:
                        cv = cv[:30] + '..'
                    const_val = f" → const[{v1}]={cv}"
                print(f"  Proto[{pi:3d}] inst[{idx:3d}]: ({v1}, {v2}){const_val}")
                count += 1
                if count >= 50:
                    break
            except:
                pass
    if count >= 50:
        break

# Save complete C[2] data
with open('c2_full_data.json', 'w', encoding='utf-8') as f:
    json.dump(all_c2_data, f, indent=1, default=str)
print(f"\nSaved to c2_full_data.json")
