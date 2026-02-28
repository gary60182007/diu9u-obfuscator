import sys, time, json, re, struct
sys.path.insert(0, '.')

with open(r'unobfuscator\pending crack\bloxburg_script.lua', 'r', encoding='utf-8', errors='replace') as f:
    source = f.read()

exec(open('run_luraph_test.py').read().split("print('Reading source...')")[0])
source = preprocess_luau(source)

from unobfuscator.utils.lua_runtime import LuaRuntimeWrapper, LuaRuntimeError

runtime = LuaRuntimeWrapper(op_limit=2_000_000_000, timeout=120.0)
runtime._init_runtime()

runtime.lua.execute("_G._protos = {}; _G._state_r = nil")

# Find closure factory and inject hooks  
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

# Capture r state table
r49_pattern = re.compile(r'(\w)\[0X31\]\s*=\s*function\(\)')
r49_match = r49_pattern.search(modified)
if r49_match:
    r_var = r49_match.group(1)
    insert_pos = r49_match.start()
    capture_code = f'_G._state_r={r_var};'
    modified = modified[:insert_pos] + capture_code + modified[insert_pos:]
    print(f"State capture injected")

# Find z:zy(r) call and inject HALT after it
# This stops execution right after deserialization completes
# z:zy is the deserialization function called during init

# Search for the zy call pattern: zy(r);break
# The obfuscated name 'zy' is used in this script
zy_matches = list(re.finditer(r':zy\(\w+\)', modified))
print(f"Found {len(zy_matches)} z:zy() calls")
for zm in zy_matches:
    ctx = modified[max(0, zm.start()-20):zm.end()+30]
    print(f"  pos {zm.start()}: ...{ctx}...")

if zy_matches:
    # Inject halt after the FIRST zy call
    zm = zy_matches[0]
    # Find the end of the statement (;)
    end_pos = modified.index(';', zm.end())
    halt_code = ';_G._init_done=true;error("INIT_HALT")'
    modified = modified[:end_pos] + halt_code + modified[end_pos:]
    print(f"Injected HALT after z:zy() at pos {end_pos}")

# Do NOT suppress errors - let the HALT propagate cleanly
# But wrap in pcall to catch it
modified_wrapped = f"""
local ok, err = pcall(function()
{modified}
end)
if err and tostring(err):find("INIT_HALT") then
    -- Expected halt
else
    -- Unexpected error, ignore
end
"""

print("Executing until INIT_HALT...")
t0 = time.time()
try:
    runtime.execute(modified_wrapped)
    print(f"Completed in {time.time()-t0:.1f}s")
except LuaRuntimeError as e:
    err_str = str(e)
    if 'INIT_HALT' in err_str:
        print(f"HALTED after init in {time.time()-t0:.1f}s (expected)")
    else:
        print(f"Error after {time.time()-t0:.1f}s: {err_str[:200]}")

def li(expr):
    v = runtime.lua.eval(f"tonumber({expr})")
    return int(v) if v is not None else None

init_done = runtime.lua.eval("_G._init_done")
has_r = runtime.lua.eval("_G._state_r ~= nil")
n_protos = li("#_G._protos") or 0
print(f"\nInit done: {init_done}")
print(f"State table captured: {has_r}")
print(f"Prototypes: {n_protos}")

if not has_r:
    print("FAILED: no state table")
    sys.exit(1)

# Test reader functions
print(f"\n=== Testing reader functions ===")
runtime.lua.execute("_G._state_r[10] = 94736")
test = li("_G._state_r[46]()")
new_off = li("_G._state_r[10]")
print(f"r[46]() at 94736 = {test}, new offset = {new_off}")

if new_off != 94737:
    print(f"Reader functions corrupted!")
    # Check what r[46] type is
    t = runtime.lua.eval("type(_G._state_r[46])")
    print(f"r[46] type: {t}")
    # Try direct buffer read
    b = li("buffer.readu8(_G._state_r[33], 94736)")
    print(f"Direct buffer.readu8 at 94736: {b}")
    sys.exit(1)

print("Reader functions OK!")

# Check buffer
buf_len = li("buffer.len(_G._state_r[33])")
print(f"Buffer length: {buf_len}")

# Now systematically parse the script data
SCRIPT_START = 94736

# Step 1: Read sub-buffer using varint reader
runtime.lua.execute(f"_G._state_r[10] = {SCRIPT_START}")
sub_len = li("_G._state_r[46]()")
after_len = li("_G._state_r[10]")
print(f"\nSub-buffer length: {sub_len}, data starts at {after_len}")

# Read sub-buffer bytes directly
sub_bytes = []
for i in range(sub_len):
    b = li(f"buffer.readu8(_G._state_r[33], {after_len + i})")
    sub_bytes.append(b)
sub_data = bytes(sub_bytes)

# Skip past sub-buffer
runtime.lua.execute(f"_G._state_r[10] = {after_len + sub_len}")
pos = li("_G._state_r[10]")
print(f"After sub-buffer: offset {pos}")

# Step 2: Read sequential data with r[46] (varint)
print(f"\n=== Reading varints from offset {pos} ===")
varints = []
for i in range(2000):
    try:
        off = li("_G._state_r[10]")
        if off is None or off >= buf_len:
            break
        v = li("_G._state_r[46]()")
        new_off = li("_G._state_r[10]")
        if new_off is None:
            break
        consumed = new_off - off
        varints.append((off, v, consumed))
    except:
        break

print(f"Read {len(varints)} varints")

# Print first 200 with pattern detection
for i, (off, v, c) in enumerate(varints[:200]):
    note = ""
    if c == 1 and v < 128:
        note = f"  0x{v:02X}"
    print(f"  [{i:4d}] off={off:7d} val={v:8d} ({c}B){note}")

# Step 3: Use r[50] (the complex state-machine reader that does tag dispatch)
print(f"\n=== Testing r[50] (tag-dispatch reader) ===")
runtime.lua.execute(f"_G._state_r[10] = {pos}")
results_r50 = []
for i in range(100):
    try:
        off = li("_G._state_r[10]")
        if off is None:
            break
        result = runtime.lua.eval("_G._state_r[50]()")
        new_off = li("_G._state_r[10]")
        if new_off is None:
            break
        consumed = new_off - off
        rtype = type(result).__name__
        
        if isinstance(result, str):
            is_print = all(32 <= ord(c) < 127 for c in result) if result else True
            results_r50.append(('str', result, off, consumed))
            print(f"  [{i:3d}] off={off:7d} str len={len(result):3d} consumed={consumed:4d}B printable={is_print} {repr(result[:40])}")
        elif isinstance(result, (int, float)):
            results_r50.append(('num', result, off, consumed))
            print(f"  [{i:3d}] off={off:7d} num={result} consumed={consumed}B")
        elif result is None:
            results_r50.append(('nil', None, off, consumed))
            print(f"  [{i:3d}] off={off:7d} nil consumed={consumed}B")
        else:
            results_r50.append(('other', str(result), off, consumed))
            print(f"  [{i:3d}] off={off:7d} {rtype}={str(result)[:30]} consumed={consumed}B")
    except Exception as e:
        err = str(e)[:100]
        print(f"  [{i:3d}] ERROR: {err}")
        break

final_off = li("_G._state_r[10]")
print(f"\nFinal offset after r[50] reads: {final_off}")
print(f"Total r[50] reads: {len(results_r50)}")

# Count types
from collections import Counter
type_counts = Counter(r[0] for r in results_r50)
print(f"Types: {dict(type_counts)}")

# Check if any strings are printable
printable_strs = [r for r in results_r50 if r[0] == 'str' and r[1] and all(32 <= ord(c) < 127 for c in r[1])]
print(f"Printable strings: {len(printable_strs)}")
for typ, val, off, consumed in printable_strs[:20]:
    print(f"  off={off:7d}: {repr(val)}")

# Save results
with open('halt_parse_results.json', 'w') as f:
    json.dump({
        'protos': n_protos,
        'sub_buffer_len': sub_len,
        'pos_after_sub': pos,
        'varint_count': len(varints),
        'r50_count': len(results_r50),
        'r50_types': dict(type_counts),
        'printable_strings': len(printable_strs),
        'varints_first100': [(o, v, c) for o, v, c in varints[:100]],
    }, f, indent=2)
print(f"\nSaved to halt_parse_results.json")
