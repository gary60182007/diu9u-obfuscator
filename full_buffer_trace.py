"""
Run the VM with high op limit, tracing ALL buffer reads.
Goal: capture the deserialization of the script data section (94K+).
"""
import sys, os, time, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'unobfuscator'))
from utils.lua_runtime import LuaRuntimeWrapper

# Much higher op limit to capture script data deserialization
runtime = LuaRuntimeWrapper(op_limit=20_000_000_000, timeout=600)
runtime._init_runtime()

with open(r'unobfuscator\pending crack\bloxburg_script.lua', 'r', encoding='utf-8', errors='replace') as f:
    source = f.read()

# Inject enhanced buffer read tracing
# We want to capture ALL reads and write them to a Lua table for extraction
trace_hook = """
_G._buf_trace = {}
_G._trace_count = 0
_G._max_offset_seen = 0
_G._trace_limit = 500000

local _orig_readu8 = buffer.readu8
local _orig_readu16 = buffer.readu16
local _orig_readu32 = buffer.readu32
local _orig_readf32 = buffer.readf32
local _orig_readf64 = buffer.readf64
local _orig_readstring = buffer.readstring

buffer.readu8 = function(buf, offset)
    local val = _orig_readu8(buf, offset)
    if _G._trace_count < _G._trace_limit then
        _G._trace_count = _G._trace_count + 1
        if offset > _G._max_offset_seen then
            _G._max_offset_seen = offset
        end
    end
    return val
end

buffer.readu16 = function(buf, offset)
    local val = _orig_readu16(buf, offset)
    if _G._trace_count < _G._trace_limit then
        _G._trace_count = _G._trace_count + 1
        if offset > _G._max_offset_seen then
            _G._max_offset_seen = offset
        end
    end
    return val
end

buffer.readu32 = function(buf, offset)
    local val = _orig_readu32(buf, offset)
    if _G._trace_count < _G._trace_limit then
        _G._trace_count = _G._trace_count + 1
        if offset > _G._max_offset_seen then
            _G._max_offset_seen = offset
        end
    end
    return val
end

buffer.readf32 = function(buf, offset)
    local val = _orig_readf32(buf, offset)
    if _G._trace_count < _G._trace_limit then
        _G._trace_count = _G._trace_count + 1
        if offset > _G._max_offset_seen then
            _G._max_offset_seen = offset
        end
    end
    return val
end

buffer.readf64 = function(buf, offset)
    local val = _orig_readf64(buf, offset)
    if _G._trace_count < _G._trace_limit then
        _G._trace_count = _G._trace_count + 1
        if offset > _G._max_offset_seen then
            _G._max_offset_seen = offset
        end
    end
    return val
end

buffer.readstring = function(buf, offset, count)
    local val = _orig_readstring(buf, offset, count)
    if _G._trace_count < _G._trace_limit then
        _G._trace_count = _G._trace_count + 1
        if offset > _G._max_offset_seen then
            _G._max_offset_seen = offset
        end
    end
    return val
end
"""

runtime.lua.execute(trace_hook)

# Also inject prototype capture hook
# Find the closure factory definition and add capture code
closure_factory = '(r)[56]=function(C,W)'
if closure_factory in source:
    hook_code = """(r)[56]=function(C,W)
if not _G._protos then _G._protos = {} end
local p = {}
for k=1,11 do
    local v = C[k]
    if v ~= nil then
        local t = type(v)
        if t == 'number' then p[k] = v
        elseif t == 'string' then p[k] = v
        elseif t == 'table' then
            local arr = {}
            for idx, val in pairs(v) do
                if type(val) == 'string' or type(val) == 'number' then
                    arr[idx] = val
                else
                    arr[idx] = tostring(val)
                end
            end
            p[k] = arr
        elseif t == 'boolean' then p[k] = v
        else p[k] = t end
    end
end
table.insert(_G._protos, p)
local """
    source = source.replace(closure_factory, hook_code)
    print("Injected prototype capture hook")
else:
    print("WARNING: Could not find closure factory pattern!")

print(f"Source length: {len(source)}")
print(f"Executing with 20B op limit...")

t0 = time.time()
try:
    runtime.execute(source)
except Exception as e:
    elapsed = time.time() - t0
    print(f"Error after {elapsed:.1f}s: {e}")

elapsed = time.time() - t0
print(f"Elapsed: {elapsed:.1f}s")

# Extract results
trace_count = int(runtime.lua.eval("_G._trace_count"))
max_offset = int(runtime.lua.eval("_G._max_offset_seen"))
print(f"\nBuffer reads: {trace_count}")
print(f"Max offset seen: {max_offset}")
print(f"Buffer size: 1064652")
print(f"Coverage: {max_offset / 1064652 * 100:.1f}%")

# Extract prototypes
protos_table = runtime.lua.eval("_G._protos")
if protos_table:
    num_protos = int(runtime.lua.eval("#_G._protos"))
    print(f"\nPrototypes captured: {num_protos}")
    
    # Extract prototype data
    protos = []
    for i in range(1, num_protos + 1):
        proto = {}
        p = protos_table[i]
        if p is None:
            continue
        for k in range(1, 12):
            v = p[k]
            if v is not None:
                t = type(v)
                if t in (int, float, str, bool):
                    proto[k] = v
                else:
                    # It's a Lua table - extract
                    arr = {}
                    try:
                        tlen = runtime.lua.eval(f"#{{}}")  # can't easily get length
                        # Just iterate with pairs
                        items = list(v.items()) if hasattr(v, 'items') else []
                        for idx, val in items:
                            arr[int(idx)] = val if isinstance(val, (int, float, str)) else str(val)
                    except:
                        arr = str(v)
                    proto[k] = arr
        protos.append(proto)
    
    # Show first few prototypes
    for i, p in enumerate(protos[:5]):
        print(f"\n  Proto {i}:")
        for k, v in sorted(p.items()):
            if isinstance(v, dict):
                sample = {k2: v2 for k2, v2 in list(v.items())[:5]}
                print(f"    [{k}] table({len(v)} items): {sample}")
            elif isinstance(v, str) and len(v) > 50:
                print(f"    [{k}] str({len(v)}): {repr(v[:50])}...")
            else:
                print(f"    [{k}] = {repr(v)}")
    
    # Count strings across all prototypes
    all_strings = set()
    for p in protos:
        for k, v in p.items():
            if isinstance(v, str):
                all_strings.add(v)
            elif isinstance(v, dict):
                for sv in v.values():
                    if isinstance(sv, str):
                        all_strings.add(sv)
    
    print(f"\nTotal unique strings across {len(protos)} prototypes: {len(all_strings)}")
    
    # Show all strings sorted by length
    sorted_strings = sorted(all_strings, key=len, reverse=True)
    print("\nAll strings found:")
    for s in sorted_strings[:100]:
        printable = all(32 <= ord(c) < 127 for c in s)
        print(f"  len={len(s):3d} printable={printable:5} {repr(s)[:80]}")
    
    # Save prototypes
    with open('full_trace_protos.json', 'w') as f:
        json.dump(protos, f, indent=2, default=str)
    print(f"\nSaved {len(protos)} prototypes to full_trace_protos.json")
else:
    print("\nNo prototypes captured!")
