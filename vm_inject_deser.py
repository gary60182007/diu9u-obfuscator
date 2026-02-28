"""
Inject code INSIDE the lazy deserializer W (defined in F9) to dump strings.
W ends with: C[12]=z.D;continue;else if D>4 then return q;end;end;end;end);
Inject string dump before the final 'return q' of W.
"""
import sys, time, json, re
sys.path.insert(0, '.')

with open(r'unobfuscator\pending crack\bloxburg_script.lua', 'r', encoding='utf-8', errors='replace') as f:
    source = f.read()

exec(open('run_luraph_test.py').read().split("print('Reading source...')")[0])
source = preprocess_luau(source)

from unobfuscator.utils.lua_runtime import LuaRuntimeWrapper, LuaRuntimeError

# Find the lazy deserializer W's return pattern inside F9
# The pattern: the W function ends with:
# C[12]=z.D;continue;else if D>4 then return q;end;end;end;end);
# where C is the r_table variable inside F9

# First find F9's W definition
# W=(function()local a,q,D,Y;D,Y,q=z:lF(Y,q,D,C);

# Search for the unique pattern of W's end inside F9
# Key: "D>4 then return q" followed by multiple "end;" and ");"
# This is unique to W's function body

# Let's find all "return q" in the source and pick the right one
return_q_matches = list(re.finditer(r'return q;end;end;end;end\);', source))
print(f"Found {len(return_q_matches)} 'return q;end;end;end;end);' matches")
for i, m in enumerate(return_q_matches):
    ctx_before = source[max(0, m.start()-80):m.start()]
    print(f"  [{i}] pos={m.start()}: ...{repr(ctx_before[-60:])}")

# Also try a more specific pattern
pattern2 = re.compile(r'D>(?:0[xXbBoO][0-9a-fA-F_]+|\d+)\s*then\s*return\s+q\s*;')
matches2 = list(pattern2.finditer(source))
print(f"\nFound {len(matches2)} 'D>N then return q' matches")
for i, m in enumerate(matches2):
    ctx = source[max(0, m.start()-60):m.end()+60]
    print(f"  [{i}] pos={m.start()}: {repr(ctx[:100])}")

# Find the W function definition context
w_def = re.compile(r'W=\(function\(\)local\s+\w+,q,')
w_matches = list(w_def.finditer(source))
print(f"\nFound {len(w_matches)} W=(function()local ...,q, definitions")
for i, m in enumerate(w_matches):
    ctx = source[m.start():m.start()+200]
    print(f"  [{i}] pos={m.start()}: {repr(ctx[:150])}")

# Now find the right injection point
# Look for the W function body: starts with W=(function() and ends with end);
# Inside it, find the 'return q' that's preceded by D>4
if w_matches and matches2:
    w_start = w_matches[0].start()
    # Find the matching 'return q' after W's start
    for m2 in matches2:
        if m2.start() > w_start:
            print(f"\n  Best injection point: pos={m2.start()}")
            # Show more context
            ctx = source[m2.start()-100:m2.end()+100]
            print(f"  Context: {repr(ctx[:200])}")
            break

print("\n" + "="*70)
print("Injecting string table dump")
print("="*70)

# Find the exact injection point
# Pattern: D>4 then return q;
# Replace with: D>4 then _G._string_table={};for _k,_v in pairs(C[57]) do if type(_v)=='string' then _G._string_table[_k]=_v elseif type(_v)=='table' and _v[1] then _G._string_table[_k]=_v[1] end end;_G._deser_done=true;return q;

# But C might not be the right variable name. In F9, C is the 3rd parameter 
# which is the r_table. Let me check by looking at F9's parameter list.
# F9=function(z,r,C,W,Q,i,O) — C is the 3rd param (r_table)
# Inside W (closure), C refers to F9's C parameter (captured as upvalue)

# Find the right variable for the r_table in the W context
# From the W body: z:lF(Y,q,D,C) and z:_9(C,w,...) and z:t9(C,Z,D,q)
# C is used as the r_table parameter in all deserializer calls

# Now do the injection
modified = source

# Find the pattern more flexibly
# The key is: D>SOME_NUMBER then return q;end;end;end;end);
# where this is inside F9's W function
inject_pat = re.compile(r'(D>(?:0[xXbBoO][0-9a-fA-F_]+|\d+)\s*then\s*)(return\s+q\s*;)(end\s*;\s*end\s*;\s*end\s*;\s*end\s*\)\s*;)')
inject_matches = list(inject_pat.finditer(modified))
print(f"Injection pattern matches: {len(inject_matches)}")

if inject_matches:
    # Use the first match that's after a W=(function() definition
    target_m = None
    for im in inject_matches:
        if w_matches and im.start() > w_matches[0].start():
            target_m = im
            break
    if not target_m:
        target_m = inject_matches[0]
    
    print(f"Injecting at pos {target_m.start()}")
    
    dump_code = (
        '_G._string_table={};'
        '_G._str_count=0;'
        'for _k,_v in pairs(C[57]) do '
        '_G._str_count=_G._str_count+1;'
        'if type(_v)==\"string\" then '
        '_G._string_table[_k]=_v '
        'elseif type(_v)==\"table\" and _v[1] then '
        '_G._string_table[_k]=_v[1] '
        'end '
        'end;'
        '_G._deser_done=true;'
        '_G._r10_after_deser=C[10];'
        '_G._r57_ref=C[57];'
    )
    
    modified = (
        modified[:target_m.start()] +
        target_m.group(1) +  # D>4 then
        dump_code +
        target_m.group(2) +  # return q;
        target_m.group(3) +  # end;end;end;end);
        modified[target_m.end():]
    )
    print("Injection complete")
else:
    # Try simpler pattern
    simple_pat = re.compile(r'then return q;end;end;end;end\);')
    simple_matches = list(simple_pat.finditer(modified))
    print(f"Simple pattern matches: {len(simple_matches)}")
    if simple_matches:
        target_m = simple_matches[0]
        dump_code = (
            '_G._string_table={};'
            '_G._str_count=0;'
            'for _k,_v in pairs(C[57]) do '
            '_G._str_count=_G._str_count+1;'
            'if type(_v)==\"string\" then '
            '_G._string_table[_k]=_v '
            'elseif type(_v)==\"table\" and _v[1] then '
            '_G._string_table[_k]=_v[1] '
            'end '
            'end;'
            '_G._deser_done=true;'
            '_G._r10_after_deser=C[10];'
            '_G._r57_ref=C[57];'
        )
        modified = (
            modified[:target_m.start()] +
            'then ' +
            dump_code +
            'return q;end;end;end;end);' +
            modified[target_m.end():]
        )
        print(f"Simple injection at pos {target_m.start()}")

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

runtime = LuaRuntimeWrapper(op_limit=10_000_000_000, timeout=600)
runtime._init_runtime()
runtime.lua.execute("_G._protos = {}; _G._deser_done = false; _G._string_table = {}")

modified = runtime.suppress_vm_errors(modified)

print("\nExecuting VM (up to 10B ops, 600s timeout)...")
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
str_count = li("_G._str_count")
print(f"\nDeserialization done: {deser_done}")
print(f"String count: {str_count}")
print(f"r[10] after deser: {li('_G._r10_after_deser')}")

if str_count and str_count > 0:
    # Extract strings
    runtime.lua.execute("""
    _G._str_samples = {}
    _G._str_all = {}
    local count = 0
    for k, v in pairs(_G._string_table) do
        count = count + 1
        if type(v) == 'string' then
            table.insert(_G._str_all, {k, v})
            if count <= 100 then
                local safe = ''
                for i = 1, math.min(#v, 80) do
                    local b = string.byte(v, i)
                    if b >= 32 and b <= 126 then
                        safe = safe .. string.char(b)
                    else
                        safe = safe .. '.'
                    end
                end
                table.insert(_G._str_samples, tostring(k) .. ' (len=' .. #v .. '): ' .. safe)
            end
        end
    end
    table.sort(_G._str_samples)
    table.sort(_G._str_all, function(a, b) return a[1] < b[1] end)
    """)
    
    n_samples = li("#_G._str_samples") or 0
    print(f"\nString samples ({n_samples}):")
    for i in range(1, min(n_samples + 1, 101)):
        print(f"  {ls(f'_G._str_samples[{i}]')}")
    
    # Save all strings to JSON
    n_all = li("#_G._str_all") or 0
    print(f"\nTotal strings: {n_all}")
    
    if n_all > 0:
        all_strings = {}
        for i in range(1, n_all + 1):
            k = li(f"_G._str_all[{i}][1]")
            v = runtime.lua.eval(f"_G._str_all[{i}][2]")
            if k is not None and v is not None:
                try:
                    all_strings[k] = v.decode('utf-8', errors='replace') if isinstance(v, bytes) else str(v)
                except:
                    all_strings[k] = repr(v)
        
        with open('luraph_strings_decrypted.json', 'w', encoding='utf-8') as f:
            json.dump(all_strings, f, indent=2, ensure_ascii=False)
        print(f"Saved {len(all_strings)} strings to luraph_strings_decrypted.json")
else:
    print("No strings captured. Checking r[57] via _G._r57_ref...")
    r57_type = ls("type(_G._r57_ref)")
    print(f"  r57_ref type: {r57_type}")
    
    # Check protos
    proto_count = li("#_G._protos")
    print(f"  Protos: {proto_count}")
