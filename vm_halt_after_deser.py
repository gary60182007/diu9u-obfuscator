"""
Replace z:py with a halt function so the VM stops AFTER full deserialization
(F9, o9, C9, W() lazy deserializer all complete) but BEFORE execution.
Then inspect r[57] (string table) and r[58] (proto deserializer).
"""
import sys, time, json, re
sys.path.insert(0, '.')

with open(r'unobfuscator\pending crack\bloxburg_script.lua', 'r', encoding='utf-8', errors='replace') as f:
    source = f.read()

exec(open('run_luraph_test.py').read().split("print('Reading source...')")[0])
source = preprocess_luau(source)

from unobfuscator.utils.lua_runtime import LuaRuntimeWrapper, LuaRuntimeError

runtime = LuaRuntimeWrapper(op_limit=5_000_000_000, timeout=300)
runtime._init_runtime()
runtime.lua.execute("_G._protos = {}; _G._saved = {}")

# Inject r table capture after z:zy(r)
modified = source
zy_matches = list(re.finditer(r':zy\((\w+)\)', modified))
zm = zy_matches[0]
r_arg = zm.group(1)
semi_pos = modified.index(';', zm.end())
capture = f';_G._r={r_arg}'
modified = modified[:semi_pos+1] + capture + modified[semi_pos+1:]
print(f"Injected r table capture after z:zy({r_arg})")

# Replace z:py with a halt function
# py=function(z,...)return(...)[...];end
py_pat = re.compile(r'py=function\(z,\.\.\.\)return\(\.\.\.\)\[\.\.\.\];end')
py_m = py_pat.search(modified)
if py_m:
    halt_fn = 'py=function(z,...)_G._deser_done=true;error("HALT_DESER_DONE");end'
    modified = modified[:py_m.start()] + halt_fn + modified[py_m.end():]
    print(f"Replaced z:py at pos {py_m.start()} with halt function")
else:
    print("ERROR: Could not find z:py pattern!")
    sys.exit(1)

# Also inject prototype capture hook
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
    print("Injected prototype capture hook")

modified = runtime.suppress_vm_errors(modified)

print("Executing (up to 5B ops, 300s timeout)...")
t0 = time.time()
try:
    runtime.execute(modified)
except LuaRuntimeError as e:
    elapsed = time.time() - t0
    err = str(e)[:200]
    print(f"Stopped after {elapsed:.1f}s: {err}")

runtime.lua.execute("_G._op_count = 0; _G._op_limit = 10000000000")

def li(expr):
    v = runtime.lua.eval(f"tonumber({expr})")
    return int(v) if v is not None else None

def ls(expr):
    v = runtime.lua.eval(expr)
    return str(v) if v is not None else None

deser_done = ls("tostring(_G._deser_done)")
print(f"\nDeserialization done: {deser_done}")

# Check r table state AFTER full deserialization
print("\n=== r table state after deserialization ===")
runtime.lua.execute("""
_G._r_info = {}
for k = 1, 200 do
    local v = _G._r[k]
    if v ~= nil then
        local t = type(v)
        local info = t
        if t == 'number' then info = t .. '=' .. tostring(v)
        elseif t == 'table' then
            local count = 0
            for _ in pairs(v) do count = count + 1 end
            info = t .. '(' .. count .. ' entries)'
        elseif t == 'boolean' then info = tostring(v)
        end
        table.insert(_G._r_info, k .. ':' .. info)
    end
end
""")
n = li("#_G._r_info") or 0
for i in range(1, n + 1):
    print(f"  {ls(f'_G._r_info[{i}]')}")

# Check r[57] - string table
r57_type = ls("type(_G._r[57])")
print(f"\nr[57] (string table): {r57_type}")

if str(r57_type) == 'table':
    runtime.lua.execute("""
    _G._str_count = 0
    _G._str_samples = {}
    for k, v in pairs(_G._r[57]) do
        _G._str_count = _G._str_count + 1
        if _G._str_count <= 200 then
            local info = tostring(k) .. ':' .. type(v)
            if type(v) == 'string' then
                local safe = ''
                for i = 1, math.min(#v, 80) do
                    local b = string.byte(v, i)
                    if b >= 32 and b <= 126 then
                        safe = safe .. string.char(b)
                    else
                        safe = safe .. string.format('\\x%02x', b)
                    end
                end
                info = info .. '=' .. safe
            elseif type(v) == 'number' then
                info = info .. '=' .. tostring(v)
            elseif type(v) == 'table' then
                local c = 0
                for _ in pairs(v) do c = c + 1 end
                info = info .. '(tbl ' .. c .. ')'
            end
            table.insert(_G._str_samples, info)
        end
    end
    """)
    str_count = li("_G._str_count")
    print(f"String table entries: {str_count}")
    n_samples = li("#_G._str_samples") or 0
    for i in range(1, n_samples + 1):
        print(f"  {ls(f'_G._str_samples[{i}]')}")

# Check r[58] - prototype deserializer
r58_type = ls("type(_G._r[58])")
print(f"\nr[58] (proto deserializer): {r58_type}")

# Check prototype capture
proto_count = li("#_G._protos") or 0
print(f"\nCaptured prototypes: {proto_count}")
if proto_count > 0:
    for i in range(1, min(proto_count + 1, 20)):
        runtime.lua.execute(f"""
        local p = _G._protos[{i}]
        _G._pi = ''
        for k = 1, 11 do
            local v = p[k]
            if v ~= nil then
                local t = type(v)
                if t == 'table' then
                    local c = 0
                    for _ in pairs(v) do c = c + 1 end
                    _G._pi = _G._pi .. k .. ':tbl(' .. c .. ') '
                elseif t == 'number' then
                    _G._pi = _G._pi .. k .. ':' .. tostring(v) .. ' '
                elseif t == 'function' then
                    _G._pi = _G._pi .. k .. ':fn '
                else
                    _G._pi = _G._pi .. k .. ':' .. t .. ' '
                end
            end
        end
        """)
        info = ls("_G._pi")
        print(f"  Proto[{i}]: {info}")

# Check r[10] (buffer offset)
r10 = li("_G._r[10]")
buf_len = li("buffer.len(_G._r[33])")
print(f"\nr[10] (buffer offset): {r10}")
print(f"Buffer length: {buf_len}")

# Save results
results = {
    'deser_done': deser_done,
    'r57_type': r57_type,
    'r58_type': r58_type,
    'proto_count': proto_count,
    'r10': r10,
    'buf_len': buf_len,
}
with open('vm_deser_results.json', 'w') as f:
    json.dump(results, f, indent=2, default=str)
print("\nSaved to vm_deser_results.json")
