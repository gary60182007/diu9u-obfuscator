import sys, time, json, re
sys.path.insert(0, '.')

with open(r'unobfuscator\pending crack\bloxburg_script.lua', 'r', encoding='utf-8', errors='replace') as f:
    source = f.read()

exec(open('run_luraph_test.py').read().split("print('Reading source...')")[0])
source = preprocess_luau(source)

from unobfuscator.utils.lua_runtime import LuaRuntimeWrapper, LuaRuntimeError

runtime = LuaRuntimeWrapper(op_limit=2_000_000_000, timeout=120.0)
runtime._init_runtime()

# Inject string interception hooks BEFORE executing the script
# Capture all unique strings produced by string.char (which is used for decryption)
runtime.lua.execute("""
_G._captured_strings = {}
_G._str_count = 0
_G._str_limit = 50000

local _orig_char = string.char
string.char = function(...)
    local result = _orig_char(...)
    if _G._str_count < _G._str_limit then
        _G._str_count = _G._str_count + 1
        if #result >= 2 then
            _G._captured_strings[result] = (_G._captured_strings[result] or 0) + 1
        end
    end
    return result
end

_G._concat_strings = {}
_G._concat_count = 0

local _mt = getmetatable("") or {}
local _orig_concat = _mt.__concat
if _orig_concat then
    _mt.__concat = function(a, b)
        local result = _orig_concat(a, b)
        if _G._concat_count < 10000 and type(result) == "string" and #result >= 4 and #result <= 200 then
            _G._concat_count = _G._concat_count + 1
            _G._captured_strings[result] = (_G._captured_strings[result] or 0) + 1
        end
        return result
    end
end

_G._table_concats = {}
local _orig_table_concat = table.concat
table.concat = function(t, sep)
    local result = _orig_table_concat(t, sep)
    if type(result) == "string" and #result >= 3 and #result <= 500 then
        _G._table_concats[result] = (_G._table_concats[result] or 0) + 1
    end
    return result
end
""")

# Also set up proto capture
runtime.lua.execute("_G._protos = {}")

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

print(f"Executing with string interception...")
t0 = time.time()
try:
    runtime.execute(modified)
    print(f"Completed in {time.time()-t0:.1f}s")
except LuaRuntimeError as e:
    print(f"Error after {time.time()-t0:.1f}s: {str(e)[:200]}")

# Extract captured strings
print(f"\nstring.char calls: {runtime.lua.eval('_G._str_count')}")

captured = {}
extract_fn = runtime.lua.eval("""
function()
    local result = {}
    local count = 0
    for k, v in pairs(_G._captured_strings) do
        count = count + 1
        if count <= 5000 then
            result[count] = {s=k, n=v}
        end
    end
    result.total = count
    return result
end
""")

info = extract_fn()
total = int(info['total'])
print(f"Unique captured strings: {total}")

all_strings = []
for i in range(1, min(total + 1, 5001)):
    try:
        s = str(info[i]['s'])
        n = int(info[i]['n'])
        all_strings.append((s, n))
    except Exception:
        pass

# Also get table.concat results
tc_fn = runtime.lua.eval("""
function()
    local result = {}
    local count = 0
    for k, v in pairs(_G._table_concats) do
        count = count + 1
        if count <= 2000 then
            result[count] = {s=k, n=v}
        end
    end
    result.total = count
    return result
end
""")

tc_info = tc_fn()
tc_total = int(tc_info['total'])
print(f"table.concat results: {tc_total}")

for i in range(1, min(tc_total + 1, 2001)):
    try:
        s = str(tc_info[i]['s'])
        n = int(tc_info[i]['n'])
        all_strings.append((s, n))
    except Exception:
        pass

# Filter and categorize strings
vm_internal = set()
script_strings = set()

vm_patterns = {
    'string', 'table', 'math', 'debug', 'coroutine', 'bit32',
    'pack', 'unpack', 'byte', 'char', 'sub', 'find', 'match', 'format',
    'concat', 'rep', 'insert', 'remove', 'sort',
    'getinfo', 'traceback', 'sethook',
    'pcall', 'xpcall', 'error', 'select', 'type', 'tonumber', 'tostring',
    'rawget', 'rawset', 'getmetatable', 'setmetatable', '__index', '__newindex',
    'next', 'pairs', 'ipairs', 'create', 'resume', 'wrap', 'close', 'running',
}

for s, n in sorted(all_strings, key=lambda x: -x[1]):
    if len(s) <= 1:
        continue
    is_printable = all(32 <= ord(c) < 127 or c in '\t\n\r' for c in s)
    if s.lower() in vm_patterns:
        vm_internal.add(s)
    elif is_printable and len(s) >= 2:
        script_strings.add((s, n))

print(f"\n{'='*60}")
print(f"SCRIPT STRINGS ({len(script_strings)} unique)")
print(f"{'='*60}")
for s, n in sorted(script_strings, key=lambda x: -x[1])[:200]:
    if len(s) > 100:
        print(f"  [{n:4d}x] {repr(s[:100])}...")
    else:
        print(f"  [{n:4d}x] {repr(s)}")

# Save full results
with open('captured_strings.json', 'w', encoding='utf-8') as f:
    json.dump({
        'script_strings': [(s, n) for s, n in sorted(script_strings, key=lambda x: -x[1])],
        'vm_internal': sorted(vm_internal),
        'total_char_calls': int(runtime.lua.eval('_G._str_count')),
    }, f, indent=2, ensure_ascii=False)
print(f"\nSaved to captured_strings.json")
