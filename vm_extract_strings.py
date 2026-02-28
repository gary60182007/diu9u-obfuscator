"""
Extract strings by dumping r[57] INSIDE q9, right after the ZF loop completes.
q9 reads 1170 strings via ZF, stores them in W[57] (= r[57]).
Inject dump between the for loop end and the varint read.
"""
import sys, time, json, re
sys.path.insert(0, '.')

with open(r'unobfuscator\pending crack\bloxburg_script.lua', 'r', encoding='utf-8', errors='replace') as f:
    source = f.read()

exec(open('run_luraph_test.py').read().split("print('Reading source...')")[0])
source = preprocess_luau(source)

from unobfuscator.utils.lua_runtime import LuaRuntimeWrapper, LuaRuntimeError

modified = source

# Find q9 function and inject string dump after the ZF loop
# q9=function(z,r,C,W,Q)local i;for O=1,Q do i=z:ZF(W,O,r);if i~=-1 then else return-1,C;end;end;C=(W[46]()-83963);return 0xBEAB,C;end
# W = r_table, W[57] = string table

q9_start = modified.find('q9=function(')
if q9_start < 0:
    print("ERROR: q9 not found")
    sys.exit(1)

# Find the ZF call within q9
zf_call_pos = modified.find(':ZF(', q9_start)
print(f"q9 at {q9_start}, ZF call at {zf_call_pos}")

# Find the varint read after the for loop: W[46]()
# Search for pattern: end;end;C=(W[  or end;end;C=(  after q9
# The W variable name is the 4th parameter of q9
q9_params = re.search(r'q9=function\((\w+),(\w+),(\w+),(\w+),(\w+)\)', modified[q9_start:])
W_var = q9_params.group(4)
C_var = q9_params.group(3)
print(f"  W_var={W_var}, C_var={C_var}")

# Find the string: end;end;C=(W[46 after q9
# But first need to find end of the for loop
# Pattern: end;end; before C=( after q9_start
search_after = modified[q9_start:q9_start+500]
print(f"  q9 body: {repr(search_after[:300])}")

# Find the exact injection point: between 'end;end;' and 'C=('
# Use pattern matching after ZF call
inject_marker = re.search(r'end;end;(' + re.escape(C_var) + r'=\(' + re.escape(W_var) + r'\[)', modified[q9_start:])
if inject_marker:
    inject_pos = q9_start + inject_marker.start() + len('end;end;')
    print(f"  Injection point at absolute pos {inject_pos}")
    
    dump_code = (
        f'_G._string_dump={{}};'
        f'_G._str_count=0;'
        f'for _k,_v in pairs({W_var}[57]) do '
        f'_G._str_count=_G._str_count+1;'
        f'if type(_v)=="string" then '
        f'_G._string_dump[_k]=_v '
        f'elseif type(_v)=="table" and type(_v[1])=="string" then '
        f'_G._string_dump[_k]=_v[1] '
        f'end '
        f'end;'
        f'_G._dump_r10={W_var}[10];'
    )
    
    modified = modified[:inject_pos] + dump_code + modified[inject_pos:]
    print("  String dump injected!")
else:
    # Try more flexible pattern
    print("  Trying flexible pattern...")
    # Look for 'end;end;' followed by assignment to C_var
    for m in re.finditer(r'end;end;', modified[q9_start:q9_start+500]):
        pos = q9_start + m.end()
        rest = modified[pos:pos+50]
        print(f"    end;end; at {pos}: next={repr(rest[:40])}")
        if rest.startswith(C_var + '=('):
            inject_pos = pos
            dump_code = (
                f'_G._string_dump={{}};'
                f'_G._str_count=0;'
                f'for _k,_v in pairs({W_var}[57]) do '
                f'_G._str_count=_G._str_count+1;'
                f'if type(_v)=="string" then '
                f'_G._string_dump[_k]=_v '
                f'elseif type(_v)=="table" and type(_v[1])=="string" then '
                f'_G._string_dump[_k]=_v[1] '
                f'end '
                f'end;'
                f'_G._dump_r10={W_var}[10];'
            )
            modified = modified[:inject_pos] + dump_code + modified[inject_pos:]
            print("    String dump injected!")
            break

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
runtime.lua.execute("_G._protos = {}; _G._string_dump = {}; _G._str_count = 0")

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

str_count = li('_G._str_count')
dump_r10 = li('_G._dump_r10')
print(f"\nString count: {str_count}")
print(f"r[10] at dump: {dump_r10}")
print(f"Protos: {li('#_G._protos')}")

if str_count and str_count > 0:
    # Extract all strings via hex encoding
    print(f"\nExtracting {str_count} strings...")
    
    # Get all keys
    runtime.lua.execute("""
    _G._all_keys = {}
    for k, v in pairs(_G._string_dump) do
        table.insert(_G._all_keys, k)
    end
    table.sort(_G._all_keys)
    """)
    
    n_keys = li("#_G._all_keys") or 0
    print(f"Keys found: {n_keys}")
    
    all_strings = {}
    batch = 20
    for start in range(1, n_keys + 1, batch):
        end_idx = min(start + batch - 1, n_keys)
        runtime.lua.execute(f"""
        _G._batch = {{}}
        for i = {start}, {end_idx} do
            local k = _G._all_keys[i]
            local v = _G._string_dump[k]
            if type(v) == "string" then
                local hex = ""
                for j = 1, #v do
                    hex = hex .. string.format("%02x", string.byte(v, j))
                end
                table.insert(_G._batch, {{k, #v, hex}})
            end
        end
        """)
        bn = li("#_G._batch") or 0
        for bi in range(1, bn + 1):
            k = li(f"_G._batch[{bi}][1]")
            slen = li(f"_G._batch[{bi}][2]")
            hex_str = ls(f"_G._batch[{bi}][3]")
            if k is not None and hex_str:
                try:
                    raw = bytes.fromhex(hex_str)
                    text = raw.decode('utf-8', errors='replace')
                    all_strings[k] = text
                except:
                    all_strings[k] = f"<hex:{hex_str[:100]}>"
    
    # Save to JSON
    with open('luraph_strings_decrypted.json', 'w', encoding='utf-8') as f:
        json.dump(all_strings, f, indent=2, ensure_ascii=False, sort_keys=True)
    print(f"\nSaved {len(all_strings)} strings to luraph_strings_decrypted.json")
    
    # Show samples
    print(f"\nSample strings:")
    readable = []
    for k in sorted(all_strings.keys()):
        v = all_strings[k]
        printable_ratio = sum(1 for c in v if c.isprintable()) / max(len(v), 1)
        if len(v) > 2 and printable_ratio > 0.6:
            readable.append((k, v))
    
    print(f"Readable strings ({len(readable)} of {len(all_strings)}):")
    for k, v in readable[:100]:
        print(f"  [{k:4d}] {v[:120]}")
    
    if len(readable) > 100:
        print(f"  ... and {len(readable) - 100} more")
else:
    print("No strings captured!")
