import sys, time, json, re
sys.path.insert(0, '.')

with open(r'unobfuscator\pending crack\bloxburg_script.lua', 'r', encoding='utf-8', errors='replace') as f:
    source = f.read()

exec(open('run_luraph_test.py').read().split("print('Reading source...')")[0])
source = preprocess_luau(source)

from unobfuscator.utils.lua_runtime import LuaRuntimeWrapper, LuaRuntimeError

runtime = LuaRuntimeWrapper(op_limit=2_000_000_000, timeout=120.0)
runtime._init_runtime()

# Hook buffer.readstring and string operations used during deserialization
runtime.lua.execute("""
_G._buf_strings = {}
_G._buf_str_count = 0

local _orig_readstring = buffer.readstring
buffer.readstring = function(buf, offset, length)
    local result = _orig_readstring(buf, offset, length)
    if length >= 2 then
        _G._buf_str_count = _G._buf_str_count + 1
        if _G._buf_str_count <= 10000 then
            table.insert(_G._buf_strings, {s=result, off=offset, len=length})
        end
    end
    return result
end

_G._string_sub_results = {}
_G._sub_count = 0
local _orig_sub = string.sub
string.sub = function(s, i, j)
    local result = _orig_sub(s, i, j)
    if #result >= 3 and #result <= 500 then
        _G._sub_count = _G._sub_count + 1
        if _G._sub_count <= 20000 then
            _G._string_sub_results[result] = (_G._string_sub_results[result] or 0) + 1
        end
    end
    return result
end

_G._string_rep_results = {}
local _orig_rep = string.rep
string.rep = function(s, n)
    local result = _orig_rep(s, n)
    if #result >= 2 then
        _G._string_rep_results[result] = (_G._string_rep_results[result] or 0) + 1
    end
    return result
end

_G._string_format_results = {}
local _orig_format = string.format
string.format = function(fmt, ...)
    local result = _orig_format(fmt, ...)
    if #result >= 2 then
        _G._string_format_results[result] = (_G._string_format_results[result] or 0) + 1
    end
    return result
end

_G._protos = {}
""")

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
modified = runtime.suppress_vm_errors(modified)

print("Executing with buffer/string hooks...")
t0 = time.time()
try:
    runtime.execute(modified)
    print(f"Completed in {time.time()-t0:.1f}s")
except LuaRuntimeError as e:
    print(f"Error after {time.time()-t0:.1f}s: {str(e)[:200]}")

# Extract buffer.readstring results
buf_count = int(runtime.lua.eval("#_G._buf_strings"))
print(f"\nbuffer.readstring calls: {buf_count}")

buf_strings = []
for i in range(1, min(buf_count + 1, 10001)):
    try:
        s = str(runtime.lua.eval(f"_G._buf_strings[{i}].s"))
        off = int(runtime.lua.eval(f"_G._buf_strings[{i}].off"))
        length = int(runtime.lua.eval(f"_G._buf_strings[{i}].len"))
        buf_strings.append((s, off, length))
    except Exception:
        pass

# Filter printable strings
printable_strings = []
for s, off, length in buf_strings:
    is_printable = all(32 <= ord(c) < 127 or c in '\t\n\r' for c in s)
    if is_printable and len(s) >= 2:
        printable_strings.append((s, off, length))

print(f"Printable strings from buffer: {len(printable_strings)}")
for s, off, length in printable_strings[:50]:
    print(f"  offset={off:7d} len={length:3d}: {repr(s)[:80]}")

# Also check string.sub results
sub_fn = runtime.lua.eval("""
function()
    local result = {}
    local count = 0
    for k, v in pairs(_G._string_sub_results) do
        count = count + 1
        if count <= 3000 then result[count] = {s=k, n=v} end
    end
    result.total = count
    return result
end
""")
sub_info = sub_fn()
sub_total = int(sub_info['total'])
print(f"\nstring.sub unique results: {sub_total}")

sub_strings = []
for i in range(1, min(sub_total + 1, 3001)):
    try:
        s = str(sub_info[i]['s'])
        n = int(sub_info[i]['n'])
        is_printable = all(32 <= ord(c) < 127 or c in '\t\n\r' for c in s)
        if is_printable and len(s) >= 3:
            sub_strings.append((s, n))
    except Exception:
        pass

print(f"Printable string.sub results: {len(sub_strings)}")
for s, n in sorted(sub_strings, key=lambda x: -x[1])[:50]:
    print(f"  [{n:4d}x] {repr(s)[:80]}")

# Save everything
all_script_strings = set()
for s, off, length in printable_strings:
    all_script_strings.add(s)
for s, n in sub_strings:
    all_script_strings.add(s)

print(f"\n{'='*60}")
print(f"TOTAL UNIQUE SCRIPT STRINGS: {len(all_script_strings)}")
print(f"{'='*60}")

with open('all_script_strings.json', 'w', encoding='utf-8') as f:
    json.dump({
        'buffer_strings': [(s, off, l) for s, off, l in printable_strings],
        'sub_strings': [(s, n) for s, n in sorted(sub_strings, key=lambda x: -x[1])],
        'all_unique': sorted(all_script_strings),
    }, f, indent=2, ensure_ascii=False)
print(f"Saved to all_script_strings.json")
