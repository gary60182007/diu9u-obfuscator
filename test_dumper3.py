import sys, time, json, re
sys.path.insert(0, '.')

with open(r'unobfuscator\pending crack\bloxburg_script.lua', 'r', encoding='utf-8', errors='replace') as f:
    source = f.read()

exec(open('run_luraph_test.py').read().split("print('Reading source...')")[0])
source = preprocess_luau(source)

from unobfuscator.utils.lua_runtime import LuaRuntimeWrapper, LuaRuntimeError

runtime = LuaRuntimeWrapper(op_limit=2_000_000_000, timeout=120.0)
runtime._init_runtime()

runtime.lua.execute("_G._protos = {}")
runtime.lua.execute("_G._upval_tables = {}")

# Find closure factory pattern
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
    print("ERROR: Pattern not found")
    sys.exit(1)

p1 = m.group(2)  # C
p2 = m.group(3)  # W
full_match = m.group(0)
local_pos = full_match.index('local')
prefix = full_match[:local_pos]
suffix = full_match[local_pos:]

# Hook that captures both prototype AND upvalue table reference
hook_code = (
    f'if {p1}==nil then return function(...)return end end;'
    f'do local _p={{}};for _i=1,11 do _p[_i]={p1}[_i] end;'
    f'_p.id=#_G._protos+1;'
    f'_p._W={p2};'  # Store reference to W (upvalue table)
    f'table.insert(_G._protos,_p);'
    f'if {p2} and type({p2})=="table" then '
    f'  table.insert(_G._upval_tables, {{id=_p.id, tbl={p2}}}) '
    f'end '
    f'end;'
)

replacement = prefix + hook_code + suffix
modified = source[:m.start()] + replacement + source[m.end():]
modified = runtime.suppress_vm_errors(modified)

print(f"Hook injected, executing...")
t0 = time.time()
try:
    runtime.execute(modified)
    print(f"Completed in {time.time()-t0:.1f}s")
except LuaRuntimeError as e:
    print(f"Error after {time.time()-t0:.1f}s: {str(e)[:200]}")

# Now dump upvalue tables - they should be populated after execution
print("\n=== Dumping upvalue tables ===")
upval_count = runtime.lua.eval("#_G._upval_tables")
print(f"Captured {upval_count} upvalue tables")

all_upval_strings = {}
all_upval_summary = []

for ui in range(1, int(upval_count) + 1):
    try:
        proto_id = int(runtime.lua.eval(f"_G._upval_tables[{ui}].id"))
        tbl = runtime.lua.eval(f"_G._upval_tables[{ui}].tbl")
        
        # Count entries and collect strings
        strings = {}
        numbers = {}
        tables = {}
        funcs = 0
        nils = 0
        total = 0
        
        # Iterate keys
        extract_fn = runtime.lua.eval("""
        function(tbl)
            local result = {}
            local max_k = 0
            for k, v in pairs(tbl) do
                if type(k) == "number" and k > max_k then max_k = k end
            end
            result.max_k = max_k
            result.strings = {}
            result.str_count = 0
            result.num_count = 0
            result.tbl_count = 0
            result.func_count = 0
            for k, v in pairs(tbl) do
                if type(k) == "number" then
                    local t = type(v)
                    if t == "string" then
                        result.str_count = result.str_count + 1
                        if result.str_count <= 200 then
                            result.strings[k] = v
                        end
                    elseif t == "number" then
                        result.num_count = result.num_count + 1
                    elseif t == "table" then
                        result.tbl_count = result.tbl_count + 1
                    elseif t == "function" then
                        result.func_count = result.func_count + 1
                    end
                end
            end
            return result
        end
        """)
        
        info = extract_fn(tbl)
        max_k = int(info['max_k'])
        str_count = int(info['str_count'])
        num_count = int(info['num_count'])
        tbl_count = int(info['tbl_count'])
        func_count = int(info['func_count'])
        
        summary = f"Proto #{proto_id}: W has {max_k} max_key, {str_count} str, {num_count} num, {tbl_count} tbl, {func_count} func"
        all_upval_summary.append(summary)
        
        if str_count > 0:
            strs_lua = info['strings']
            collected = {}
            for k in strs_lua:
                try:
                    collected[int(k)] = str(strs_lua[k])
                except Exception:
                    pass
            all_upval_strings[proto_id] = collected
            
            if str_count <= 10:
                print(f"  {summary}")
                for k in sorted(collected.keys()):
                    v = collected[k]
                    print(f"    W[{k}] = {repr(v)[:80]}")
            else:
                print(f"  {summary}")
                for k in sorted(collected.keys())[:5]:
                    v = collected[k]
                    print(f"    W[{k}] = {repr(v)[:80]}")
                print(f"    ... and {str_count - 5} more strings")
        elif max_k > 0:
            print(f"  {summary}")
    except Exception as e:
        print(f"  Error extracting upval table {ui}: {e}")

# Save all upvalue strings
all_script_strings = set()
for pid, strs in all_upval_strings.items():
    for k, v in strs.items():
        all_script_strings.add(v)

print(f"\n{'='*60}")
print(f"TOTAL UNIQUE SCRIPT STRINGS: {len(all_script_strings)}")
print(f"{'='*60}")
for s in sorted(all_script_strings):
    if len(s) > 100:
        print(f"  {repr(s[:100])}...")
    else:
        print(f"  {repr(s)}")

# Save everything
result = {
    'upval_summary': all_upval_summary,
    'upval_strings': {str(k): v for k, v in all_upval_strings.items()},
    'all_script_strings': sorted(all_script_strings),
}
with open('upval_dump.json', 'w', encoding='utf-8') as f:
    json.dump(result, f, indent=2, ensure_ascii=False, default=str)
print(f"\nSaved to upval_dump.json")
