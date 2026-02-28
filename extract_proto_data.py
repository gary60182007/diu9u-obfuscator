"""
Extract detailed prototype data from the VM to correlate with buffer bytes.
Focus on first 5 protos: dump all array contents and scalar values.
"""
import sys, time, json, re
sys.path.insert(0, '.')

with open(r'unobfuscator\pending crack\bloxburg_script.lua', 'r', encoding='utf-8', errors='replace') as f:
    source = f.read()

exec(open('run_luraph_test.py').read().split("print('Reading source...')")[0])
source = preprocess_luau(source)
from unobfuscator.utils.lua_runtime import LuaRuntimeWrapper, LuaRuntimeError

modified = source

# Inject in d9 to wrap r[58] and capture detailed proto data
d9_pat = re.compile(r'(d9=function\((\w+),(\w+),(\w+),(\w+)\))')
d9_m = d9_pat.search(modified)
d9_z, d9_r, d9_C, d9_W = [d9_m.group(j) for j in range(2, 6)]

inject = (
    f'do local _orig={d9_C}[58];'
    f'{d9_C}[58]=function() '
    f'local _n=(_G._c9_n or 0)+1;_G._c9_n=_n;'
    f'local _s={d9_C}[10];'
    f'local _r=_orig();'
    f'local _e={d9_C}[10];'
    f'_G._c9_offsets[_n]=tostring(_s).."|"..tostring(_e);'
    f'if _n<=10 then '
    f'_G._proto_data[_n]={{}};'
    f'local _pd=_G._proto_data[_n];'
    f'for _k=1,11 do '
    f'local _v=_r[_k];'
    f'if type(_v)=="table" then '
    f'_pd[_k]={{}};'
    f'local _tbl=_pd[_k];'
    f'local _max=0;'
    f'for _ki,_vi in pairs(_v) do '
    f'if type(_ki)=="number" and _ki>_max then _max=_ki end '
    f'end;'
    f'_tbl.max=_max;'
    f'for _ki=1,math.min(_max,500) do '
    f'_tbl[_ki]=_v[_ki] '
    f'end '
    f'elseif type(_v)=="number" then '
    f'_pd[_k]=_v '
    f'elseif type(_v)=="function" then '
    f'_pd[_k]="fn" '
    f'else '
    f'_pd[_k]=tostring(_v) '
    f'end end end;'
    f'return _r end end;'
)
modified = modified[:d9_m.end()] + inject + modified[d9_m.end():]

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
_G._c9_offsets = {}
_G._c9_n = 0
_G._proto_data = {}
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

n = li('_G._c9_n') or 0
print(f"Protos: {n}")

# Extract detailed data for first 5 protos
for pi in range(1, 6):
    print(f"\n{'='*60}")
    offset_str = ls(f"_G._c9_offsets[{pi}]")
    if offset_str:
        parts = offset_str.split('|')
        print(f"Proto[{pi}] offset {parts[0]}-{parts[1]} ({int(parts[1])-int(parts[0])} bytes)")
    
    for ki in range(1, 12):
        runtime.lua.execute(f"""
        local _pd = _G._proto_data[{pi}]
        if _pd == nil then _G._tmp_type = 'none'; return end
        local _v = _pd[{ki}]
        if type(_v) == 'table' then
            _G._tmp_type = 'table'
            _G._tmp_max = _v.max or 0
        elseif type(_v) == 'number' then
            _G._tmp_type = 'number'
            _G._tmp_val = _v
        else
            _G._tmp_type = 'other'
            _G._tmp_val = tostring(_v)
        end
        """)
        
        typ = ls('_G._tmp_type')
        if typ == 'none':
            print(f"  C[{ki}]: no data")
            continue
        elif typ == 'number':
            val = li('_G._tmp_val')
            print(f"  C[{ki}] = {val}")
        elif typ == 'table':
            max_idx = li('_G._tmp_max')
            if max_idx and max_idx > 0:
                # Extract first 30 values
                vals = []
                batch_size = 50
                for start in range(1, min(max_idx + 1, 101), batch_size):
                    end_idx = min(start + batch_size - 1, max_idx, 100)
                    runtime.lua.execute(f"""
                    local _pd = _G._proto_data[{pi}]
                    local _tbl = _pd[{ki}]
                    local _parts = {{}}
                    for _j = {start}, {end_idx} do
                        table.insert(_parts, tostring(_tbl[_j] or 'nil'))
                    end
                    _G._tmp_arr = table.concat(_parts, ',')
                    """)
                    arr_str = ls('_G._tmp_arr')
                    if arr_str:
                        for v in arr_str.split(','):
                            try:
                                vals.append(int(float(v)))
                            except:
                                vals.append(v)
                
                preview = vals[:40]
                suffix = f" ...({max_idx} total)" if max_idx > 40 else ""
                print(f"  C[{ki}] = table(max={max_idx}): {preview}{suffix}")
            else:
                print(f"  C[{ki}] = table(empty)")
        else:
            val = ls('_G._tmp_val')
            print(f"  C[{ki}] = {typ}: {val}")

# Now correlate with buffer
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

# Read proto 1 raw data and try to match structure
print(f"\n{'='*60}")
print("BUFFER CORRELATION")
for pi in range(1, 4):
    offset_str = ls(f"_G._c9_offsets[{pi}]")
    if not offset_str: continue
    parts = offset_str.split('|')
    start = int(parts[0])
    end = int(parts[1])
    
    print(f"\nProto[{pi}] raw data from offset {start}:")
    pos = start
    for j in range(30):
        if pos >= end: break
        v, new_pos = read_varint(buf, pos)
        consumed = new_pos - pos
        print(f"  offset {pos-start:4d} ({pos:6d}): varint={v} ({consumed}B)")
        pos = new_pos
