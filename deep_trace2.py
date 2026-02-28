"""
Run VM with high op limit, hooking buffer at definition level.
"""
import sys, time, json, re, struct
sys.path.insert(0, '.')

with open(r'unobfuscator\pending crack\bloxburg_script.lua', 'r', encoding='utf-8', errors='replace') as f:
    source = f.read()

exec(open('run_luraph_test.py').read().split("print('Reading source...')")[0])
source = preprocess_luau(source)

from unobfuscator.utils import lua_runtime
from unobfuscator.utils.lua_runtime import LuaRuntimeWrapper, LuaRuntimeError

# Patch the buffer library to include read tracking at definition level
_orig_buffer_lib = lua_runtime._BUFFER_LIB
_patched_buffer_lib = _orig_buffer_lib.replace(
    "function buffer.readu8(b, o) return b._data[o+1] or 0 end",
    """function buffer.readu8(b, o)
        _G._brc = (_G._brc or 0) + 1
        local off = o
        if off > (_G._mbo or 0) then _G._mbo = off end
        return b._data[o+1] or 0
    end"""
)
assert _patched_buffer_lib != _orig_buffer_lib, "Patch failed for readu8"
lua_runtime._BUFFER_LIB = _patched_buffer_lib

runtime = LuaRuntimeWrapper(op_limit=20_000_000_000, timeout=600)
runtime._init_runtime()

# Restore original for future imports
lua_runtime._BUFFER_LIB = _orig_buffer_lib

runtime.lua.execute("_G._protos = {}; _G._saved = {}; _G._brc = 0; _G._mbo = 0")

# Inject prototype capture hook
pattern = re.compile(
    r'(\)\[(?:\d+|0[xXbBoO][0-9a-fA-F_]+)\]=function\()'
    r'([A-Za-z_]\w*)'
    r','
    r'([A-Za-z_]\w*)'
    r'\)'
    r'(local\s+[A-Za-z_]\w*(?:,[A-Za-z_]\w*){9,}=)'
    r'(\2\[)'
)
m = pattern.search(source)
if not m:
    print("ERROR: Could not find closure factory pattern!")
    sys.exit(1)

p1 = m.group(2)
full_match = m.group(0)
local_pos = full_match.index('local')
prefix = full_match[:local_pos]
suffix = full_match[local_pos:]

hook_code = (
    f'if {p1}==nil then return function(...)return end end;'
    f'do local _p={{}};for _i=1,11 do _p[_i]={p1}[_i] end;'
    f'_p.id=#_G._protos+1;table.insert(_G._protos,_p) end;'
)
replacement = prefix + hook_code + suffix
modified = source[:m.start()] + replacement + source[m.end():]
print(f"Injected prototype capture hook")

# Inject state capture after z:zy(r)
zy_matches = list(re.finditer(r':zy\((\w+)\)', modified))
print(f"Found {len(zy_matches)} z:zy() calls")
if zy_matches:
    zm = zy_matches[0]
    r_arg = zm.group(1)
    semi_pos = modified.index(';', zm.end())
    capture_code = (
        f';_G._saved.r10={r_arg}[10]'
        f';_G._saved.r33={r_arg}[33]'
        f';_G._saved.r46={r_arg}[46]'
        f';_G._saved.r50={r_arg}[50]'
        f';_G._saved.done=true'
    )
    modified = modified[:semi_pos+1] + capture_code + modified[semi_pos+1:]

modified = runtime.suppress_vm_errors(modified)

print(f"Executing with 20B op limit...")
t0 = time.time()
try:
    runtime.execute(modified)
    print(f"Completed in {time.time()-t0:.1f}s")
except LuaRuntimeError as e:
    elapsed = time.time() - t0
    print(f"Stopped after {elapsed:.1f}s: {str(e)[:200]}")

def li(expr):
    v = runtime.lua.eval(f"tonumber({expr})")
    return int(v) if v is not None else None

runtime.lua.execute("_G._op_count = 0; _G._op_limit = 10000000000")

max_offset = li("_G._mbo")
read_count = li("_G._brc")
n_protos = li("#_G._protos") or 0
saved_done = runtime.lua.eval("_G._saved.done")

print(f"\n{'='*60}")
print(f"RESULTS")
print(f"{'='*60}")
print(f"Buffer u8 reads: {read_count}")
print(f"Max buffer offset: {max_offset} / 1064652 ({max_offset/1064652*100:.1f}% if >0)")
print(f"Prototypes captured: {n_protos}")
print(f"State captured: {saved_done}")

if n_protos > 0:
    print(f"\nExtracting {n_protos} prototypes...")
    all_strings = set()
    
    for i in range(1, min(n_protos + 1, 500)):
        for k in range(1, 12):
            try:
                t = str(runtime.lua.eval(f"type(_G._protos[{i}][{k}])"))
                if t == 'string':
                    s = str(runtime.lua.eval(f"_G._protos[{i}][{k}]"))
                    all_strings.add(s)
                elif t == 'table':
                    runtime.lua.execute(f"""
                    _G._tmp = {{}}
                    for idx, val in pairs(_G._protos[{i}][{k}]) do
                        if type(val) == 'string' then
                            table.insert(_G._tmp, val)
                        end
                    end""")
                    n_str = li("#_G._tmp") or 0
                    for j in range(1, min(n_str + 1, 1000)):
                        try:
                            s = str(runtime.lua.eval(f"_G._tmp[{j}]"))
                            all_strings.add(s)
                        except:
                            pass
            except:
                pass
    
    printable = sorted([s for s in all_strings if all(32 <= ord(c) < 127 for c in s)])
    print(f"\nUnique strings: {len(all_strings)} ({len(printable)} printable)")
    for s in printable[:200]:
        print(f"  {repr(s)}")
    
    with open('deep_trace2_strings.json', 'w') as f:
        json.dump(sorted(all_strings, key=len), f, indent=2, default=str)
    print(f"\nSaved to deep_trace2_strings.json")
elif max_offset and max_offset > 0:
    print(f"\nNo prototypes but buffer was read up to offset {max_offset}")
    print("The VM deserialized but closure factory was never called")
    print("This might mean the deserialization format is different from expected")
else:
    print(f"\nNo prototypes and no buffer reads detected")
    print("Testing if buffer hooks work...")
    runtime.lua.execute("""
    local b = buffer.create(10)
    buffer.writeu8(b, 0, 42)
    local v = buffer.readu8(b, 0)
    _G._test_val = v
    """)
    test_val = li("_G._test_val")
    test_brc = li("_G._brc")
    print(f"  Test buffer read value: {test_val} (expected 42)")
    print(f"  Buffer read count after test: {test_brc}")
    if test_brc and test_brc > 0:
        print("  Hooks work! The VM must be using a different read path")
    else:
        print("  Hooks NOT working - buffer library wasn't patched correctly")
