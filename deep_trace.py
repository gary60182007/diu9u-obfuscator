"""
Run VM with very high op limit to capture script data deserialization.
Uses preprocess_luau from run_luraph_test.py for Luau syntax compat.
"""
import sys, time, json, re, struct
sys.path.insert(0, '.')

with open(r'unobfuscator\pending crack\bloxburg_script.lua', 'r', encoding='utf-8', errors='replace') as f:
    source = f.read()

exec(open('run_luraph_test.py').read().split("print('Reading source...')")[0])
source = preprocess_luau(source)

from unobfuscator.utils.lua_runtime import LuaRuntimeWrapper, LuaRuntimeError

runtime = LuaRuntimeWrapper(op_limit=20_000_000_000, timeout=600)
runtime._init_runtime()

runtime.lua.execute("_G._protos = {}; _G._saved = {}")

# Hook buffer reads to track max offset
runtime.lua.execute("""
_G._max_buf_offset = 0
_G._buf_read_count = 0
local _orig_readu8 = buffer.readu8
_G._orig_readu8 = _orig_readu8
buffer.readu8 = function(buf, offset)
    _G._buf_read_count = _G._buf_read_count + 1
    if offset > _G._max_buf_offset then _G._max_buf_offset = offset end
    return _orig_readu8(buf, offset)
end
local _orig_readu32 = buffer.readu32
buffer.readu32 = function(buf, offset)
    _G._buf_read_count = _G._buf_read_count + 1
    if offset > _G._max_buf_offset then _G._max_buf_offset = offset end
    return _orig_readu32(buf, offset)
end
local _orig_readstring = buffer.readstring
buffer.readstring = function(buf, offset, count)
    _G._buf_read_count = _G._buf_read_count + 1
    if offset + (count or 0) > _G._max_buf_offset then _G._max_buf_offset = offset + (count or 0) end
    return _orig_readstring(buf, offset, count)
end
local _orig_readu16 = buffer.readu16
buffer.readu16 = function(buf, offset)
    _G._buf_read_count = _G._buf_read_count + 1
    if offset > _G._max_buf_offset then _G._max_buf_offset = offset end
    return _orig_readu16(buf, offset)
end
local _orig_readf32 = buffer.readf32
buffer.readf32 = function(buf, offset)
    _G._buf_read_count = _G._buf_read_count + 1
    if offset > _G._max_buf_offset then _G._max_buf_offset = offset end
    return _orig_readf32(buf, offset)
end
local _orig_readf64 = buffer.readf64
buffer.readf64 = function(buf, offset)
    _G._buf_read_count = _G._buf_read_count + 1
    if offset > _G._max_buf_offset then _G._max_buf_offset = offset end
    return _orig_readf64(buf, offset)
end
""")

# Inject prototype capture hook (same as halt_after_init2.py)
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

# Also inject state capture after z:zy(r) (same as halt_after_init2.py)
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

print(f"Executing with 20B op limit (may take several minutes)...")
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

# Reset op limit for extraction
runtime.lua.execute("_G._op_count = 0; _G._op_limit = 10000000000")

# Results
max_offset = li("_G._max_buf_offset")
read_count = li("_G._buf_read_count")
n_protos = li("#_G._protos") or 0
saved_done = runtime.lua.eval("_G._saved.done")

print(f"\n{'='*60}")
print(f"RESULTS")
print(f"{'='*60}")
print(f"Buffer reads: {read_count}")
print(f"Max buffer offset: {max_offset} / 1064652 ({max_offset/1064652*100:.1f}%)")
print(f"Prototypes captured: {n_protos}")
print(f"State captured: {saved_done}")

if n_protos > 0:
    # Extract ALL prototypes with their string constants
    print(f"\nExtracting {n_protos} prototypes...")
    
    all_strings = set()
    proto_summaries = []
    
    for i in range(1, n_protos + 1):
        summary = {'id': i}
        
        for k in range(1, 12):
            try:
                t = str(runtime.lua.eval(f"type(_G._protos[{i}][{k}])"))
                if t == 'number':
                    summary[f'f{k}'] = float(runtime.lua.eval(f"_G._protos[{i}][{k}]"))
                elif t == 'string':
                    s = str(runtime.lua.eval(f"_G._protos[{i}][{k}]"))
                    summary[f'f{k}'] = s
                    all_strings.add(s)
                elif t == 'table':
                    tlen = li(f"#{'{'}table.pack(table.unpack(_G._protos[{i}][{k}])){'}'}.n") or 0
                    # Try to get string entries from the table
                    str_entries = []
                    try:
                        runtime.lua.execute(f"""
                        _G._tmp_strs = {{}}
                        for idx, val in pairs(_G._protos[{i}][{k}]) do
                            if type(val) == 'string' then
                                table.insert(_G._tmp_strs, idx .. '=' .. val)
                            end
                        end
                        """)
                        n_str = li("#_G._tmp_strs") or 0
                        for j in range(1, min(n_str + 1, 500)):
                            s = str(runtime.lua.eval(f"_G._tmp_strs[{j}]"))
                            if '=' in s:
                                idx_s, val = s.split('=', 1)
                                str_entries.append(val)
                                all_strings.add(val)
                    except:
                        pass
                    summary[f'f{k}'] = f'table(strings:{len(str_entries)})'
                    if str_entries:
                        summary[f'f{k}_strings'] = str_entries[:20]
                elif t != 'nil':
                    summary[f'f{k}'] = t
            except:
                pass
        
        proto_summaries.append(summary)
        
        if i <= 5 or i == n_protos:
            print(f"  Proto {i}: {', '.join(f'{k}={repr(v)[:40]}' for k,v in sorted(summary.items()) if k != 'id')}")
    
    print(f"\n{'='*60}")
    print(f"STRING ANALYSIS")
    print(f"{'='*60}")
    print(f"Total unique strings: {len(all_strings)}")
    
    # Categorize strings
    printable_strings = [s for s in all_strings if all(32 <= ord(c) < 127 for c in s)]
    non_printable = [s for s in all_strings if not all(32 <= ord(c) < 127 for c in s)]
    
    # Show all printable strings sorted
    print(f"\nPrintable strings ({len(printable_strings)}):")
    for s in sorted(printable_strings):
        print(f"  {repr(s)}")
    
    if non_printable:
        print(f"\nNon-printable strings ({len(non_printable)}):")
        for s in sorted(non_printable, key=len)[:50]:
            print(f"  len={len(s):3d} {repr(s)[:80]}")
    
    # Save everything
    with open('deep_trace_results.json', 'w') as f:
        json.dump({
            'buffer_reads': read_count,
            'max_offset': max_offset,
            'n_protos': n_protos,
            'proto_summaries': proto_summaries,
            'all_strings': sorted(all_strings),
        }, f, indent=2, default=str)
    print(f"\nSaved to deep_trace_results.json")
