"""
Full trace: save all reads + final C[] array values for first 3 protos to JSON.
Then analyze the operand transformation.
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

# Wrap r[58] to trace reads AND capture final C[] arrays
inject = (
    f'do local _st={d9_C};'
    f'local _orig39=_st[39];local _orig46=_st[46];local _orig58=_st[58];'
    f'local _tracing=false;'
    f'_st[39]=function() local _v=_orig39();'
    f'if _tracing then local _t=_G._cur_reads;_t[#_t+1]=_v end;return _v end;'
    f'_st[46]=function() local _v=_orig46();'
    f'if _tracing then local _t=_G._cur_varints;_t[#_t+1]=_v end;return _v end;'
    f'_st[58]=function() '
    f'local _pn=(_G._pn or 0)+1;_G._pn=_pn;'
    f'if _pn<=3 then '
    f'_tracing=true;_G._cur_reads={{}};_G._cur_varints={{}};'
    f'end;'
    f'local _r=_orig58();'
    f'if _pn<=3 then '
    f'_tracing=false;'
    f'local _d={{}};_d.varints={{}};_d.arrays={{}};'
    f'for _i,_v in ipairs(_G._cur_varints) do _d.varints[_i]=_v end;'
    f'for _k=1,11 do '
    f'local _v=_r[_k];'
    f'if type(_v)=="number" then _d.arrays[_k]=_v '
    f'elseif type(_v)=="table" then '
    f'local _arr={{}};local _max=0;'
    f'for _ki,_ in pairs(_v) do if type(_ki)=="number" and _ki>_max then _max=_ki end end;'
    f'for _j=1,_max do '
    f'local _vi=_v[_j];'
    f'if type(_vi)=="number" then _arr[_j]=_vi '
    f'elseif _vi==nil then _arr[_j]="nil" '
    f'else _arr[_j]=type(_vi) end end;'
    f'_d.arrays[_k]={{max=_max,data=_arr}} '
    f'end end;'
    f'_d.start=_st[10]-({d9_C}[10]-_st[10]);'
    f'_G._proto_trace[_pn]=_d '
    f'end;return _r end;end;'
)
modified = modified[:d9_m.end()] + inject + modified[d9_m.end():]

# Also need to capture start offset per proto
# Let me revise: track r[10] before and after
inject2_search = f'_st[58]=function() '
inject2_pos = modified.index(inject2_search, d9_m.end()) + len(inject2_search)
inject2 = f'local _start_r10=_st[10];'
modified = modified[:inject2_pos] + inject2 + modified[inject2_pos:]

# Fix: use _start_r10 for the start offset
modified = modified.replace(
    f'_d.start=_st[10]-({d9_C}[10]-_st[10])',
    '_d.start_off=_start_r10;_d.end_off=_st[10]'
)

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
_G._proto_trace = {}
_G._pn = 0
_G._cur_reads = {}
_G._cur_varints = {}
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

print(f"Protos: {li('_G._pn')}")

# Extract trace data to Python
results = {}
for pi in range(1, 4):
    runtime.lua.execute(f"""
    local _d = _G._proto_trace[{pi}]
    if _d then
        _G._tmp_start = _d.start_off
        _G._tmp_end = _d.end_off
        _G._tmp_nvarints = #_d.varints
    end
    """)
    
    start_off = li('_G._tmp_start')
    end_off = li('_G._tmp_end')
    n_varints = li('_G._tmp_nvarints')
    
    if not start_off:
        continue
    
    print(f"\nProto[{pi}] offset {start_off}-{end_off} ({end_off-start_off}B), {n_varints} varints")
    
    # Extract varints in batches
    varints = []
    batch = 200
    for s in range(1, n_varints + 1, batch):
        e = min(s + batch - 1, n_varints)
        runtime.lua.execute(f"""
        local _d = _G._proto_trace[{pi}]
        local _parts = {{}}
        for _i = {s}, {e} do
            table.insert(_parts, tostring(_d.varints[_i]))
        end
        _G._tmp = table.concat(_parts, ",")
        """)
        val = runtime.lua.eval('_G._tmp')
        if val:
            for v in str(val).split(','):
                try: varints.append(int(float(v)))
                except: varints.append(v)
    
    # Extract C[] arrays
    arrays = {}
    for ki in range(1, 12):
        runtime.lua.execute(f"""
        local _d = _G._proto_trace[{pi}]
        local _a = _d.arrays[{ki}]
        if type(_a) == "number" then
            _G._tmp_type = "scalar"
            _G._tmp_val = _a
        elseif type(_a) == "table" then
            _G._tmp_type = "table"
            _G._tmp_max = _a.max
        else
            _G._tmp_type = "nil"
        end
        """)
        typ = str(runtime.lua.eval('_G._tmp_type'))
        if typ == "scalar":
            arrays[ki] = li('_G._tmp_val')
        elif typ == "table":
            max_idx = li('_G._tmp_max')
            arr = []
            for s in range(1, (max_idx or 0) + 1, batch):
                e = min(s + batch - 1, max_idx)
                runtime.lua.execute(f"""
                local _d = _G._proto_trace[{pi}]
                local _a = _d.arrays[{ki}].data
                local _parts = {{}}
                for _i = {s}, {e} do
                    local _v = _a[_i]
                    if _v == nil or _v == "nil" then
                        table.insert(_parts, "N")
                    elseif type(_v) == "number" then
                        table.insert(_parts, tostring(_v))
                    else
                        table.insert(_parts, "X")
                    end
                end
                _G._tmp = table.concat(_parts, ",")
                """)
                val = runtime.lua.eval('_G._tmp')
                if val:
                    for v in str(val).split(','):
                        if v == 'N': arr.append(None)
                        elif v == 'X': arr.append('X')
                        else:
                            try: arr.append(int(float(v)))
                            except: arr.append(v)
            arrays[ki] = {'max': max_idx, 'data': arr}
    
    results[pi] = {
        'start': start_off,
        'end': end_off,
        'varints': varints,
        'arrays': arrays
    }

# Save to JSON
with open('proto_trace_full.json', 'w') as f:
    json.dump(results, f, indent=2, default=str)
print(f"\nSaved to proto_trace_full.json")

# Analyze the transformation
for pi_str, data in results.items():
    pi = int(pi_str)
    varints = data['varints']
    arrays = data['arrays']
    
    if 4 not in arrays or not isinstance(arrays[4], dict):
        continue
    
    opcodes = arrays[4]['data']
    n_inst = arrays[4]['max']
    
    print(f"\n{'='*60}")
    print(f"PROTO[{pi}]: {n_inst} instructions, {len(varints)} varints")
    
    # Header varints
    n_header = len(varints) - n_inst * 4
    print(f"Header varints ({n_header}): {varints[:n_header]}")
    
    # Instructions: starting from varint index n_header
    # Each instruction: 4 varints (opcode, op1, op2, op3)
    operand_a = arrays.get(7, {})
    operand_b = arrays.get(8, {})
    operand_c = arrays.get(9, {})
    
    if isinstance(operand_a, dict): op_a = operand_a.get('data', [])
    else: op_a = []
    if isinstance(operand_b, dict): op_b = operand_b.get('data', [])
    else: op_b = []
    if isinstance(operand_c, dict): op_c = operand_c.get('data', [])
    else: op_c = []
    
    print(f"\nInst# | Raw_op | Raw_1 | Raw_2 | Raw_3 | C4(op) | C7(A)  | C8(B)  | C9(C)")
    print(f"------|--------|-------|-------|-------|--------|--------|--------|------")
    
    for i in range(min(n_inst, 20)):
        vi = n_header + i * 4
        if vi + 3 >= len(varints): break
        
        raw_op = varints[vi]
        raw_1 = varints[vi+1]
        raw_2 = varints[vi+2]
        raw_3 = varints[vi+3]
        
        final_op = opcodes[i] if i < len(opcodes) else '?'
        final_a = op_a[i] if i < len(op_a) else '?'
        final_b = op_b[i] if i < len(op_b) else '?'
        final_c = op_c[i] if i < len(op_c) else '?'
        
        # Check transformation
        op_match = '✓' if raw_op == final_op else '✗'
        
        print(f"  {i+1:3d} | {raw_op:6} | {raw_1:5} | {raw_2:5} | {raw_3:5} | {final_op:6}{op_match} | {final_a:6} | {final_b:6} | {final_c:6}")
