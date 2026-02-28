import sys, time, json, re
sys.path.insert(0, '.')

with open(r'unobfuscator\pending crack\bloxburg_script.lua', 'r', encoding='utf-8', errors='replace') as f:
    source = f.read()

exec(open('run_luraph_test.py').read().split("print('Reading source...')")[0])
source = preprocess_luau(source)

from unobfuscator.utils.lua_runtime import LuaRuntimeWrapper, LuaRuntimeError

runtime = LuaRuntimeWrapper(op_limit=4_000_000_000, timeout=180.0)
runtime._init_runtime()

# Hook ALL buffer read operations to trace the complete deserialization
runtime.lua.execute("""
_G._reads = {}
_G._read_count = 0
_G._read_limit = 200000

local _orig = {
    readu8 = buffer.readu8,
    readu16 = buffer.readu16,
    readu32 = buffer.readu32,
    readi8 = buffer.readi8,
    readi16 = buffer.readi16,
    readi32 = buffer.readi32,
    readf32 = buffer.readf32,
    readf64 = buffer.readf64,
    readstring = buffer.readstring,
}

local function log_read(typ, offset, value, extra)
    _G._read_count = _G._read_count + 1
    if _G._read_count <= _G._read_limit then
        table.insert(_G._reads, {t=typ, o=offset, v=value, x=extra})
    end
end

buffer.readu8 = function(buf, offset)
    local v = _orig.readu8(buf, offset)
    log_read("u8", offset, v)
    return v
end

buffer.readu16 = function(buf, offset)
    local v = _orig.readu16(buf, offset)
    log_read("u16", offset, v)
    return v
end

buffer.readu32 = function(buf, offset)
    local v = _orig.readu32(buf, offset)
    log_read("u32", offset, v)
    return v
end

buffer.readi8 = function(buf, offset)
    local v = _orig.readi8(buf, offset)
    log_read("i8", offset, v)
    return v
end

buffer.readi16 = function(buf, offset)
    local v = _orig.readi16(buf, offset)
    log_read("i16", offset, v)
    return v
end

buffer.readi32 = function(buf, offset)
    local v = _orig.readi32(buf, offset)
    log_read("i32", offset, v)
    return v
end

buffer.readf32 = function(buf, offset)
    local v = _orig.readf32(buf, offset)
    log_read("f32", offset, v)
    return v
end

buffer.readf64 = function(buf, offset)
    local v = _orig.readf64(buf, offset)
    log_read("f64", offset, v)
    return v
end

buffer.readstring = function(buf, offset, length)
    local v = _orig.readstring(buf, offset, length)
    log_read("str", offset, v, length)
    return v
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

print("Executing with full buffer read trace...")
t0 = time.time()
try:
    runtime.execute(modified)
    print(f"Completed in {time.time()-t0:.1f}s")
except LuaRuntimeError as e:
    print(f"Error after {time.time()-t0:.1f}s: {str(e)[:200]}")

read_count = int(runtime.lua.eval("_G._read_count"))
print(f"\nTotal buffer read operations: {read_count}")

# Extract read log efficiently using Lua-side processing
summary_fn = runtime.lua.eval("""
function()
    local counts = {}
    local str_results = {}
    local str_count = 0
    local max_offset = 0
    
    for i = 1, #_G._reads do
        local r = _G._reads[i]
        counts[r.t] = (counts[r.t] or 0) + 1
        if r.o > max_offset then max_offset = r.o end
        if r.t == "str" and type(r.v) == "string" and #r.v >= 2 then
            str_count = str_count + 1
            if str_count <= 500 then
                table.insert(str_results, {s=r.v, o=r.o, l=r.x})
            end
        end
    end
    
    return {counts=counts, str_results=str_results, str_count=str_count, max_offset=max_offset}
end
""")

info = summary_fn()
print(f"Max buffer offset accessed: {int(info['max_offset'])}")

# Print type counts
counts = info['counts']
for k in counts:
    print(f"  {k}: {int(counts[k])}")

str_count = int(info['str_count'])
print(f"\nString reads (len>=2): {str_count}")

# Extract strings
str_results = info['str_results']
printable = []
encoded = []
for i in range(1, min(501, str_count + 1)):
    try:
        s = str(str_results[i]['s'])
        o = int(str_results[i]['o'])
        l = int(str_results[i]['l'])
        is_print = all(32 <= ord(c) < 127 or c in '\t\n\r' for c in s)
        if is_print:
            printable.append((s, o, l))
        else:
            encoded.append((s, o, l))
    except Exception:
        pass

print(f"Printable: {len(printable)}, Encoded: {len(encoded)}")

print("\nAll printable strings from buffer reads:")
for s, o, l in printable:
    print(f"  off={o:7d} len={l:3d}: {repr(s)[:80]}")

# Now extract the first 1000 reads as a sequence to understand the format
seq_fn = runtime.lua.eval("""
function(start, count)
    local result = {}
    for i = start, math.min(start + count - 1, #_G._reads) do
        local r = _G._reads[i]
        if r.t == "str" then
            result[i - start + 1] = {t=r.t, o=r.o, l=r.x, s=r.v}
        else
            result[i - start + 1] = {t=r.t, o=r.o, v=r.v}
        end
    end
    result.total = #_G._reads
    return result
end
""")

# Show read sequence patterns
print(f"\nFirst 200 read operations:")
seq = seq_fn(1, 200)
for i in range(1, 201):
    try:
        r = seq[i]
        t = str(r['t'])
        o = int(r['o'])
        if t == 'str':
            l = int(r['l'])
            s = str(r['s'])
            is_print = all(32 <= ord(c) < 127 or c in '\t\n\r' for c in s)
            if is_print:
                print(f"  [{i:5d}] off={o:7d} {t:4s} len={l}: {repr(s)[:60]}")
            else:
                print(f"  [{i:5d}] off={o:7d} {t:4s} len={l}: <binary {l}B>")
        else:
            v = r['v']
            try:
                v = int(v) if float(v) == int(float(v)) else float(v)
            except:
                pass
            print(f"  [{i:5d}] off={o:7d} {t:4s}: {v}")
    except Exception:
        break

# Save full trace
with open('buffer_read_trace.json', 'w', encoding='utf-8') as f:
    trace_data = {
        'total_reads': read_count,
        'type_counts': {str(k): int(counts[k]) for k in counts},
        'printable_strings': [(s, o, l) for s, o, l in printable],
        'encoded_string_count': len(encoded),
    }
    json.dump(trace_data, f, indent=2, ensure_ascii=False)
print(f"\nSaved trace to buffer_read_trace.json")
