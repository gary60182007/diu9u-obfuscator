import sys, time, json, re
sys.path.insert(0, '.')

with open(r'unobfuscator\pending crack\bloxburg_script.lua', 'r', encoding='utf-8', errors='replace') as f:
    source = f.read()

exec(open('run_luraph_test.py').read().split("print('Reading source...')")[0])
source = preprocess_luau(source)

from unobfuscator.utils.lua_runtime import LuaRuntimeWrapper, LuaRuntimeError

runtime = LuaRuntimeWrapper(op_limit=2_000_000_000, timeout=120.0)
runtime._init_runtime()

# Enhanced hook: capture protos AND the state table r
runtime.lua.execute("_G._protos = {}")
runtime.lua.execute("_G._r_dump = nil")

# Find and inject enhanced hook
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
    print("ERROR: Closure factory pattern not found!")
    sys.exit(1)

p1 = m.group(2)  # first param name (C)
full_match = m.group(0)
local_pos = full_match.index('local')
prefix = full_match[:local_pos]
suffix = full_match[local_pos:]

# The zy function has params (z,r) where r is the state table
# We need to find the outer function's r parameter name
# Look at what's before the closure factory assignment
# Pattern: zy=function(z,r)(r)[56]=function(C,W)
context_before = source[max(0, m.start()-200):m.start()]
outer_match = re.search(r'=function\(([A-Za-z_]\w*),([A-Za-z_]\w*)\)\s*$', context_before)
if outer_match:
    outer_self = outer_match.group(1)  # z
    outer_state = outer_match.group(2)  # r (state table)
    print(f"Outer function params: ({outer_self}, {outer_state})")
else:
    outer_state = 'r'
    print(f"Could not find outer params, assuming state var = 'r'")

hook_code = (
    f'if {p1}==nil then return function(...)return end end;'
    f'do local _p={{}};for _i=1,11 do _p[_i]={p1}[_i] end;'
    f'_p.id=#_G._protos+1;table.insert(_G._protos,_p);'
    f'if _p.id==1 then '
    f'  _G._r_dump={{}};'
    f'  for _k,_v in pairs({outer_state}) do '
    f'    if type(_k)==\"number\" then '
    f'      local _t=type(_v);'
    f'      if _t==\"string\" then _G._r_dump[_k]={{t=\"s\",v=_v}} '
    f'      elseif _t==\"number\" then _G._r_dump[_k]={{t=\"n\",v=_v}} '
    f'      elseif _t==\"boolean\" then _G._r_dump[_k]={{t=\"b\",v=_v}} '
    f'      elseif _t==\"table\" then '
    f'        local _items={{}};local _cnt=0;'
    f'        for _sk,_sv in pairs(_v) do '
    f'          _cnt=_cnt+1;if _cnt>500 then break end;'
    f'          if type(_sv)==\"string\" then _items[_sk]={{t=\"s\",v=_sv}} '
    f'          elseif type(_sv)==\"number\" then _items[_sk]={{t=\"n\",v=_sv}} '
    f'          elseif type(_sv)==\"boolean\" then _items[_sk]={{t=\"b\",v=tostring(_sv)}} '
    f'          end '
    f'        end;'
    f'        _G._r_dump[_k]={{t=\"T\",items=_items,count=_cnt}} '
    f'      elseif _t==\"function\" then _G._r_dump[_k]={{t=\"f\"}} '
    f'      end '
    f'    end '
    f'  end '
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

# Extract state table dump
r_dump_lua = runtime.lua.eval("_G._r_dump")
if r_dump_lua is None:
    print("No r_dump captured!")
else:
    print("\n=== State table (r) dump ===")
    strings = {}
    numbers = {}
    tables = {}
    functions = []

    for k in r_dump_lua:
        entry = r_dump_lua[k]
        k_int = int(k)
        try:
            t = str(entry['t'])
        except Exception:
            continue
        if t == 's':
            strings[k_int] = str(entry['v'])
        elif t == 'n':
            try:
                numbers[k_int] = float(entry['v'])
            except Exception:
                pass
        elif t == 'b':
            pass
        elif t == 'T':
            try:
                items = entry['items']
                count = int(entry['count'])
            except Exception:
                items = None
                count = 0
            tbl = {}
            if items:
                for sk in items:
                    try:
                        item = items[sk]
                        it = str(item['t'])
                        sk_key = int(sk) if str(sk).lstrip('-').isdigit() else str(sk)
                        if it == 's':
                            tbl[sk_key] = str(item['v'])
                        elif it == 'n':
                            tbl[sk_key] = float(item['v'])
                        elif it == 'b':
                            tbl[sk_key] = str(item['v'])
                    except Exception:
                        pass
            tables[k_int] = {'count': count, 'items': tbl}
        elif t == 'f':
            functions.append(k_int)

    print(f"  Strings: {len(strings)}")
    for k in sorted(strings.keys())[:30]:
        v = strings[k]
        if len(v) > 80:
            v = v[:80] + '...'
        print(f"    r[{k}] = {repr(v)}")

    print(f"\n  Numbers: {len(numbers)}")
    for k in sorted(numbers.keys())[:20]:
        print(f"    r[{k}] = {numbers[k]}")

    print(f"\n  Tables: {len(tables)}")
    for k in sorted(tables.keys())[:10]:
        tbl = tables[k]
        print(f"    r[{k}]: {tbl['count']} entries")
        items = tbl['items']
        if items:
            for sk in sorted(items.keys(), key=lambda x: (isinstance(x, str), x))[:10]:
                v = items[sk]
                if isinstance(v, str) and len(v) > 60:
                    v = v[:60] + '...'
                print(f"      [{sk}] = {repr(v)}")

    print(f"\n  Functions: {len(functions)} at indices {sorted(functions)[:20]}...")

    # Save full dump
    dump = {
        'strings': {str(k): v for k, v in strings.items()},
        'numbers': {str(k): v for k, v in numbers.items()},
        'tables': {str(k): v for k, v in tables.items()},
        'functions': functions,
    }
    with open('state_table_dump.json', 'w', encoding='utf-8') as f:
        json.dump(dump, f, indent=2, ensure_ascii=False, default=str)
    print(f"\nSaved state table dump to state_table_dump.json")

# Also extract proto count
protos = runtime.extract_prototypes()
print(f"\nExtracted {len(protos)} prototypes")
