"""
Extract ALL 167 prototype data from the VM at runtime.
For each proto, capture:
- C[4] opcodes, C[7] A operands, C[8] B operands, C[9] C operands (instruction arrays)
- C[2] constant references (sparse, {value, mode} pairs)
- C[5] upvalue count, C[10] register count
- C[11] debug/line info (sparse)
- Buffer offset range
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
d9_z, d9_r, d9_C, d9_W = [d9_m.group(j) for j in range(2, 6)]

inject = (
    f'do local _st={d9_C};'
    f'local _orig58=_st[58];'
    f'_st[58]=function() '
    f'local _s=_st[10];'
    f'local _r=_orig58();'
    f'local _e=_st[10];'
    f'local _n=(_G._pn or 0)+1;_G._pn=_n;'
    f'_G._poff[_n]=tostring(_s).."|"..tostring(_e);'
    # For each proto, store the raw C[] table reference
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
    hook = (
        f'if {p1}==nil then return function(...)return end end;'
    )
    modified = modified[:m.start()] + full_match[:lp] + hook + full_match[lp:] + modified[m.end():]

runtime = LuaRuntimeWrapper(op_limit=15_000_000_000, timeout=600)
runtime._init_runtime()
runtime.lua.execute("""
_G._pn = 0
_G._poff = {}
_G._ptables = {}
""")
modified = runtime.suppress_vm_errors(modified)

print("Executing VM...")
t0 = time.time()
try:
    runtime.execute(modified)
except LuaRuntimeError as e:
    print(f"Stopped after {time.time()-t0:.1f}s: {str(e)[:200]}")

runtime.lua.execute("_G._op_count = 0; _G._op_limit = 10000000000")

def li(expr):
    v = runtime.lua.eval(f"tonumber({expr})")
    return int(v) if v is not None else None

def ls(expr):
    v = runtime.lua.eval(expr)
    return str(v) if v is not None else None

n_protos = li('_G._pn') or 0
print(f"Total protos captured: {n_protos}")

# Extract data for ALL protos
all_protos = []

for pi in range(1, n_protos + 1):
    off_str = ls(f"_G._poff[{pi}]")
    if not off_str:
        continue
    parts = off_str.split('|')
    start_off, end_off = int(parts[0]), int(parts[1])
    
    proto = {
        'id': pi,
        'buf_start': start_off,
        'buf_end': end_off,
        'buf_size': end_off - start_off,
    }
    
    # Extract scalar values (C[5]=upvalues, C[10]=registers)
    for ki in [5, 10]:
        runtime.lua.execute(f"""
        local _t = _G._ptables[{pi}]
        if _t then
            local _v = _t[{ki}]
            if type(_v) == "number" then
                _G._tmp = _v
            else
                _G._tmp = nil
            end
        end
        """)
        v = li('_G._tmp')
        if v is not None:
            proto[f'C{ki}'] = v
    
    # Extract arrays: C[4] opcodes, C[7] A, C[8] B, C[9] C
    for ki in [4, 7, 8, 9]:
        runtime.lua.execute(f"""
        local _t = _G._ptables[{pi}]
        if not _t then _G._arr_max = 0; return end
        local _v = _t[{ki}]
        if type(_v) ~= "table" then _G._arr_max = 0; return end
        local _max = 0
        for _k, _ in pairs(_v) do
            if type(_k) == "number" and _k > _max then _max = _k end
        end
        _G._arr_max = _max
        """)
        max_idx = li('_G._arr_max') or 0
        
        if max_idx > 0:
            arr = []
            batch = 200
            for s in range(1, max_idx + 1, batch):
                e = min(s + batch - 1, max_idx)
                runtime.lua.execute(f"""
                local _t = _G._ptables[{pi}][{ki}]
                local _p = {{}}
                for _i = {s}, {e} do
                    local _v = _t[_i]
                    if type(_v) == "number" then
                        table.insert(_p, tostring(math.floor(_v)))
                    else
                        table.insert(_p, "N")
                    end
                end
                _G._tmp = table.concat(_p, ",")
                """)
                val = ls('_G._tmp')
                if val:
                    for v in val.split(','):
                        if v == 'N':
                            arr.append(None)
                        else:
                            try:
                                arr.append(int(v))
                            except:
                                arr.append(v)
            proto[f'C{ki}'] = arr
            proto[f'C{ki}_len'] = max_idx
    
    # Extract sparse arrays: C[2] (constant refs) and C[11] (debug)
    for ki in [2, 11]:
        runtime.lua.execute(f"""
        local _t = _G._ptables[{pi}]
        if not _t then _G._arr_max = 0; return end
        local _v = _t[{ki}]
        if type(_v) ~= "table" then _G._arr_max = 0; return end
        local _max = 0
        for _k, _ in pairs(_v) do
            if type(_k) == "number" and _k > _max then _max = _k end
        end
        _G._arr_max = _max
        """)
        max_idx = li('_G._arr_max') or 0
        
        if max_idx > 0:
            # For C[2], entries might be tables {value, mode} or numbers
            # For C[11], entries are numbers or tables
            sparse = {}
            batch = 200
            for s in range(1, max_idx + 1, batch):
                e = min(s + batch - 1, max_idx)
                runtime.lua.execute(f"""
                local _t = _G._ptables[{pi}][{ki}]
                local _p = {{}}
                for _i = {s}, {e} do
                    local _v = _t[_i]
                    if _v == nil then
                        table.insert(_p, "N")
                    elseif type(_v) == "number" then
                        table.insert(_p, "n:" .. tostring(math.floor(_v)))
                    elseif type(_v) == "table" then
                        local _v1 = _v[1]
                        local _v2 = _v[2]
                        if type(_v1) == "number" and type(_v2) == "number" then
                            table.insert(_p, "t:" .. tostring(math.floor(_v1)) .. ":" .. tostring(math.floor(_v2)))
                        else
                            table.insert(_p, "t:?:?")
                        end
                    else
                        table.insert(_p, "x:" .. type(_v))
                    end
                end
                _G._tmp = table.concat(_p, ",")
                """)
                val = ls('_G._tmp')
                if val:
                    for idx_off, v in enumerate(val.split(',')):
                        actual_idx = s + idx_off
                        if v == 'N':
                            continue
                        sparse[actual_idx] = v
            
            proto[f'C{ki}_sparse'] = sparse
            proto[f'C{ki}_max'] = max_idx
    
    # Extract C[6] (sparse operand)
    runtime.lua.execute(f"""
    local _t = _G._ptables[{pi}]
    if not _t then _G._arr_max = 0; return end
    local _v = _t[6]
    if type(_v) ~= "table" then _G._arr_max = 0; return end
    local _max = 0
    for _k, _ in pairs(_v) do
        if type(_k) == "number" and _k > _max then _max = _k end
    end
    _G._arr_max = _max
    """)
    c6_max = li('_G._arr_max') or 0
    if c6_max > 0:
        sparse6 = {}
        for s in range(1, c6_max + 1, 200):
            e = min(s + 199, c6_max)
            runtime.lua.execute(f"""
            local _t = _G._ptables[{pi}][6]
            local _p = {{}}
            for _i = {s}, {e} do
                local _v = _t[_i]
                if _v == nil then
                    table.insert(_p, "N")
                elseif type(_v) == "number" then
                    table.insert(_p, tostring(math.floor(_v)))
                else
                    table.insert(_p, "X")
                end
            end
            _G._tmp = table.concat(_p, ",")
            """)
            val = ls('_G._tmp')
            if val:
                for idx_off, v in enumerate(val.split(',')):
                    if v not in ('N', 'X'):
                        sparse6[s + idx_off] = int(v)
        if sparse6:
            proto['C6_sparse'] = sparse6
    
    all_protos.append(proto)
    
    if pi % 20 == 0:
        print(f"  Extracted {pi}/{n_protos} protos...")

print(f"\nExtracted {len(all_protos)} protos total")

# Summary stats
total_instructions = sum(p.get('C4_len', 0) for p in all_protos)
total_const_refs = sum(len(p.get('C2_sparse', {})) for p in all_protos)
print(f"Total instructions: {total_instructions}")
print(f"Total constant references: {total_const_refs}")

# Show summary for first 10 protos
print(f"\n{'Proto':>6} {'Offset':>12} {'Size':>6} {'Inst':>5} {'Ups':>4} {'Regs':>5} {'ConstRefs':>9}")
print("-" * 55)
for p in all_protos[:20]:
    print(f"{p['id']:6d} {p['buf_start']:6d}-{p['buf_end']:<6d} {p['buf_size']:5d} "
          f"{p.get('C4_len', 0):5d} {p.get('C5', '?'):>4} {p.get('C10', '?'):>5} "
          f"{len(p.get('C2_sparse', {})):>9}")

# Save to JSON
with open('all_protos_data.json', 'w', encoding='utf-8') as f:
    json.dump(all_protos, f, indent=1, default=str)
print(f"\nSaved to all_protos_data.json")

# Analyze constant references
print(f"\n=== Constant Reference Analysis ===")
const_usage = {}
for p in all_protos:
    for idx_str, entry in p.get('C2_sparse', {}).items():
        if entry.startswith('t:'):
            parts = entry.split(':')
            if len(parts) >= 3:
                const_idx = int(parts[1])
                mode = int(parts[2])
                if const_idx not in const_usage:
                    const_usage[const_idx] = []
                const_usage[const_idx].append({'proto': p['id'], 'inst': int(idx_str), 'mode': mode})
        elif entry.startswith('n:'):
            val = int(entry.split(':')[1])
            if val not in const_usage:
                const_usage[val] = []
            const_usage[val].append({'proto': p['id'], 'inst': int(idx_str), 'mode': -1})

print(f"Unique constants referenced: {len(const_usage)}")
print(f"Max constant index: {max(const_usage.keys()) if const_usage else 'N/A'}")

# Load ground truth constants
try:
    with open('luraph_strings_full.json', 'r', encoding='utf-8') as f:
        gt = json.load(f)
    
    print(f"\nTop 20 most-used constants:")
    by_usage = sorted(const_usage.items(), key=lambda x: len(x[1]), reverse=True)
    for const_idx, usages in by_usage[:20]:
        if const_idx < len(gt):
            entry = gt[const_idx]
            val = entry.get('value', entry.get('string', '?'))
            if isinstance(val, str) and len(val) > 40:
                val = val[:40] + '...'
            print(f"  const[{const_idx:4d}] used {len(usages):3d}x: {val}")
except:
    pass
