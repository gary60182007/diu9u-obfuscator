"""
Trace every buffer read during the first r[58]() call to decode proto format.
Wrap r[39], r[40], r[44], r[46] (reader functions) to log reads.
"""
import sys, time, json, re
sys.path.insert(0, '.')

with open(r'unobfuscator\pending crack\bloxburg_script.lua', 'r', encoding='utf-8', errors='replace') as f:
    source = f.read()

exec(open('run_luraph_test.py').read().split("print('Reading source...')")[0])
source = preprocess_luau(source)
from unobfuscator.utils.lua_runtime import LuaRuntimeWrapper, LuaRuntimeError

modified = source

# Inject in d9 to wrap reader functions for the first proto only
d9_pat = re.compile(r'(d9=function\((\w+),(\w+),(\w+),(\w+)\))')
d9_m = d9_pat.search(modified)
d9_z, d9_r, d9_C, d9_W = [d9_m.group(j) for j in range(2, 6)]

# In d9: z=self, r=proto_idx_from_9, C=state_table, W=count
# We wrap C[39], C[40], C[44], C[46] before the loop starts
inject = (
    f'do '
    f'local _st={d9_C};'
    f'local _orig39=_st[39];'
    f'local _orig40=_st[40];'
    f'local _orig44=_st[44];'
    f'local _orig46=_st[46];'
    f'local _orig58=_st[58];'
    f'local _tracing=false;'
    f'_st[39]=function() '
    f'local _v=_orig39();'
    f'if _tracing then '
    f'local _n=#_G._reads+1;'
    f'_G._reads[_n]="39|"..tostring(_v).."|"..tostring(_st[10]) '
    f'end;return _v end;'
    f'_st[40]=function() '
    f'local _v=_orig40();'
    f'if _tracing then '
    f'local _n=#_G._reads+1;'
    f'_G._reads[_n]="40|"..tostring(_v).."|"..tostring(_st[10]) '
    f'end;return _v end;'
    f'_st[44]=function() '
    f'local _v=_orig44();'
    f'if _tracing then '
    f'local _n=#_G._reads+1;'
    f'_G._reads[_n]="44|"..tostring(_v).."|"..tostring(_st[10]) '
    f'end;return _v end;'
    f'_st[46]=function() '
    f'local _v=_orig46();'
    f'if _tracing then '
    f'local _n=#_G._reads+1;'
    f'_G._reads[_n]="46|"..tostring(_v).."|"..tostring(_st[10]) '
    f'end;return _v end;'
    f'_st[58]=function() '
    f'local _pn=(_G._proto_n or 0)+1;_G._proto_n=_pn;'
    f'local _s=_st[10];'
    f'if _pn<=3 then _tracing=true;_G._reads={{}};end;'
    f'local _r=_orig58();'
    f'local _e=_st[10];'
    f'if _pn<=3 then '
    f'_tracing=false;'
    f'_G._proto_reads[_pn]={{}};'
    f'for _i,_v in ipairs(_G._reads) do _G._proto_reads[_pn][_i]=_v end;'
    f'_G._proto_offsets[_pn]=tostring(_s).."|"..tostring(_e);'
    f'end;'
    f'return _r end;'
    f'end;'
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
_G._reads = {}
_G._proto_reads = {}
_G._proto_offsets = {}
_G._proto_n = 0
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

print(f"Proto calls: {li('_G._proto_n')}")

# Extract reads for first 2 protos
for pi in range(1, 3):
    offset_str = ls(f"_G._proto_offsets[{pi}]")
    if not offset_str:
        print(f"Proto[{pi}]: no data")
        continue
    
    parts = offset_str.split('|')
    start_off, end_off = int(parts[0]), int(parts[1])
    
    n_reads = li(f"#_G._proto_reads[{pi}]") or 0
    print(f"\nProto[{pi}] offset {start_off}-{end_off} ({end_off-start_off} bytes), {n_reads} reads")
    
    # Extract reads in batches
    reads = []
    batch = 100
    for s in range(1, n_reads + 1, batch):
        e = min(s + batch - 1, n_reads)
        runtime.lua.execute(f"""
        local _parts = {{}}
        local _pr = _G._proto_reads[{pi}]
        for _i = {s}, {e} do
            table.insert(_parts, _pr[_i])
        end
        _G._tmp_batch = table.concat(_parts, "\\n")
        """)
        batch_str = ls('_G._tmp_batch')
        if batch_str:
            for line in batch_str.split('\n'):
                if line:
                    p = line.split('|')
                    reads.append({
                        'reader': int(p[0]),
                        'value': p[1],
                        'pos_after': int(p[2]) if len(p) > 2 else None
                    })
    
    print(f"  Extracted {len(reads)} reads")
    
    # Display reads with context
    prev_pos = start_off
    for i, r in enumerate(reads[:80]):
        reader = r['reader']
        val = r['value']
        pos_after = r['pos_after']
        
        reader_names = {39: 'readu8', 40: 'readu16?', 44: 'readXX', 46: 'readvarint'}
        rname = reader_names.get(reader, f'r[{reader}]')
        
        if pos_after:
            consumed = pos_after - prev_pos if prev_pos else '?'
            print(f"  [{i:3d}] {rname:12s} = {val:>12s}  (pos_after={pos_after}, consumed={consumed})")
            prev_pos = pos_after
        else:
            print(f"  [{i:3d}] {rname:12s} = {val:>12s}")
    
    if len(reads) > 80:
        print(f"  ... ({len(reads) - 80} more reads)")
    
    # Group reads by type
    reader_counts = {}
    for r in reads:
        reader_counts[r['reader']] = reader_counts.get(r['reader'], 0) + 1
    print(f"\n  Read function usage: {reader_counts}")
