"""
Extract numeric proto data safely, avoiding binary string encoding issues.
"""
import sys, time, json, re, struct
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
    f'do local _orig={d9_C}[58];'
    f'{d9_C}[58]=function() '
    f'local _n=(_G._c9_n or 0)+1;_G._c9_n=_n;'
    f'local _s={d9_C}[10];'
    f'local _r=_orig();'
    f'local _e={d9_C}[10];'
    f'_G._c9_offsets[_n]=tostring(_s).."|"..tostring(_e);'
    f'if _n<=5 then '
    f'local _pd={{}};_G._proto_data[_n]=_pd;'
    f'for _k=1,11 do '
    f'local _v=_r[_k];'
    f'if type(_v)=="number" then _pd["s".._k]=_v '
    f'elseif type(_v)=="table" then '
    f'local _max=0;'
    f'for _ki,_ in pairs(_v) do if type(_ki)=="number" and _ki>_max then _max=_ki end end;'
    f'_pd["m".._k]=_max;'
    f'local _nums={{}};local _types={{}};'
    f'for _j=1,math.min(_max,200) do '
    f'local _vi=_v[_j];'
    f'if type(_vi)=="number" then _nums[_j]=_vi;_types[_j]="n" '
    f'elseif type(_vi)=="string" then _nums[_j]=#_vi;_types[_j]="s" '
    f'elseif type(_vi)=="table" then '
    f'local _tc=0;for _ in pairs(_vi) do _tc=_tc+1 end;'
    f'_nums[_j]=_tc;_types[_j]="t" '
    f'elseif _vi==nil then _types[_j]="x" '
    f'elseif type(_vi)=="boolean" then _nums[_j]=_vi and 1 or 0;_types[_j]="b" '
    f'end end;'
    f'_pd["n".._k]=_nums;_pd["t".._k]=_types '
    f'end end end;'
    f'return _r end end;'
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
    print(f"Stopped after {time.time()-t0:.1f}s: {str(e)[:200]}")

runtime.lua.execute("_G._op_count = 0; _G._op_limit = 10000000000")

def li(expr):
    v = runtime.lua.eval(f"tonumber({expr})")
    return int(v) if v is not None else None

def ls(expr):
    v = runtime.lua.eval(expr)
    return str(v) if v is not None else None

def extract_num_array(pi, ki, max_n):
    """Extract numeric array from _G._proto_data[pi][nKI] safely."""
    vals = []
    batch = 100
    for start in range(1, min(max_n + 1, 201), batch):
        end_idx = min(start + batch - 1, max_n, 200)
        runtime.lua.execute(f"""
        local _nums = _G._proto_data[{pi}]["n{ki}"]
        local _types = _G._proto_data[{pi}]["t{ki}"]
        local _parts = {{}}
        for _j = {start}, {end_idx} do
            local _t = _types[_j] or "x"
            local _n = _nums[_j]
            if _n ~= nil then
                table.insert(_parts, _t .. tostring(_n))
            else
                table.insert(_parts, _t)
            end
        end
        _G._tmp_arr = table.concat(_parts, ",")
        """)
        arr_str = ls('_G._tmp_arr')
        if arr_str:
            for item in arr_str.split(','):
                t = item[0] if item else 'x'
                rest = item[1:] if len(item) > 1 else ''
                if t == 'n' and rest:
                    try: vals.append(int(float(rest)))
                    except: vals.append(rest)
                elif t == 's' and rest:
                    vals.append(f'str({rest})')
                elif t == 't' and rest:
                    vals.append(f'tbl({rest})')
                elif t == 'b' and rest:
                    vals.append(f'bool({rest})')
                else:
                    vals.append(None)
    return vals

n = li('_G._c9_n') or 0
print(f"Protos: {n}")

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

for pi in range(1, 4):
    offset_str = ls(f"_G._c9_offsets[{pi}]")
    if not offset_str: continue
    parts = offset_str.split('|')
    start_off, end_off = int(parts[0]), int(parts[1])
    
    print(f"\n{'='*70}")
    print(f"PROTO[{pi}] offset {start_off}-{end_off} ({end_off-start_off} bytes)")
    print(f"{'='*70}")
    
    # Show scalar values
    for ki in range(1, 12):
        s_val = li(f"_G._proto_data[{pi}]['s{ki}']")
        m_val = li(f"_G._proto_data[{pi}]['m{ki}']")
        
        if s_val is not None:
            print(f"  C[{ki:2d}] = {s_val} (scalar)")
        elif m_val is not None:
            if m_val > 0:
                arr = extract_num_array(pi, ki, m_val)
                preview = arr[:30]
                extra = f" ...({m_val} total)" if m_val > 30 else ""
                print(f"  C[{ki:2d}] = table(max={m_val}): {preview}{extra}")
            else:
                print(f"  C[{ki:2d}] = table(empty)")
        else:
            print(f"  C[{ki:2d}] = nil/other")
    
    # Show raw buffer varints
    print(f"\n  Buffer varints from offset {start_off}:")
    pos = start_off
    for j in range(25):
        if pos >= end_off: break
        v, new_pos = read_varint(buf, pos)
        print(f"    [{pos-start_off:4d}] varint={v:10d} ({new_pos-pos}B)")
        pos = new_pos
