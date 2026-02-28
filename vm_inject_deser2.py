"""
Inject string dump inside lazy deserializer W.
Match the PREPROCESSED source (with goto labels instead of continue).
"""
import sys, time, json, re
sys.path.insert(0, '.')

with open(r'unobfuscator\pending crack\bloxburg_script.lua', 'r', encoding='utf-8', errors='replace') as f:
    source = f.read()

exec(open('run_luraph_test.py').read().split("print('Reading source...')")[0])
source = preprocess_luau(source)

from unobfuscator.utils.lua_runtime import LuaRuntimeWrapper, LuaRuntimeError

# Find the exact injection point in preprocessed source
# From the previous run, we know the pattern is:
# D>4 then return q;end;end;::__cNNN__::end;end);
# Right after W=(function()...

# Find W definition
w_def_m = re.search(r'W=\(function\(\)local\s+\w+,q,', source)
if w_def_m:
    w_start = w_def_m.start()
    print(f"W definition at pos {w_start}")
    
    # Find 'return q;' after W definition but before the next top-level function
    # Look for the specific pattern: D>NUMBER then return q;
    return_q_pat = re.compile(r'D>(?:0[xXbBoO][0-9a-fA-F_]+|\d+)\s*then\s*return\s+q\s*;')
    return_q_matches = list(return_q_pat.finditer(source, w_start))
    
    if return_q_matches:
        target = return_q_matches[0]
        print(f"Found injection point at pos {target.start()}")
        print(f"Match: {repr(target.group())}")
        # Show context
        ctx = source[target.start()-50:target.end()+100]
        print(f"Context: {repr(ctx[:200])}")
        
        # Inject: replace 'D>N then return q;' with 'D>N then DUMP_CODE return q;'
        dump_code = (
            '_G._string_table={};'
            '_G._str_count=0;'
            'if type(C)=="table" and type(C[57])=="table" then '
            'for _k,_v in pairs(C[57]) do '
            '_G._str_count=_G._str_count+1;'
            'if type(_v)=="string" then '
            '_G._string_table[_k]=_v '
            'elseif type(_v)=="table" and _v[1] then '
            '_G._string_table[_k]=_v[1] '
            'end '
            'end '
            'end;'
            '_G._deser_done=true;'
            '_G._r10_after_deser=C[10];'
        )
        
        # Find 'then' in the match and inject after it
        then_end = target.group().index('then') + 4
        modified = (
            source[:target.start()] +
            target.group()[:then_end] + ' ' +
            dump_code +
            target.group()[then_end:] +
            source[target.end():]
        )
        print("Injection complete!")
        
        # Verify injection
        verify = modified[target.start():target.start()+300]
        print(f"Verify: {repr(verify[:250])}")
    else:
        print("ERROR: Could not find D>N then return q pattern after W definition")
        sys.exit(1)
else:
    print("ERROR: Could not find W=(function() definition")
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
    print("Proto capture hook injected")

runtime = LuaRuntimeWrapper(op_limit=15_000_000_000, timeout=600)
runtime._init_runtime()
runtime.lua.execute("_G._protos = {}; _G._deser_done = false; _G._string_table = {}; _G._str_count = 0")

modified = runtime.suppress_vm_errors(modified)

print("\nExecuting VM (up to 15B ops, 600s timeout)...")
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
    runtime.lua.execute("""
    _G._str_samples = {}
    _G._str_all_keys = {}
    local count = 0
    for k, v in pairs(_G._string_table) do
        count = count + 1
        table.insert(_G._str_all_keys, k)
        if count <= 150 then
            local safe = ''
            if type(v) == 'string' then
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
    table.sort(_G._str_all_keys)
    table.sort(_G._str_samples)
    """)
    
    n_samples = li("#_G._str_samples") or 0
    print(f"\nString samples (first {n_samples}):")
    for i in range(1, min(n_samples + 1, 151)):
        s = ls(f'_G._str_samples[{i}]')
        if s:
            print(f"  {s}")
    
    n_keys = li("#_G._str_all_keys") or 0
    print(f"\nTotal string keys: {n_keys}")
    
    # Save all strings
    if n_keys > 0:
        all_strings = {}
        batch_size = 50
        for batch_start in range(1, n_keys + 1, batch_size):
            batch_end = min(batch_start + batch_size - 1, n_keys)
            runtime.lua.execute(f"""
            _G._batch = {{}}
            for i = {batch_start}, {batch_end} do
                local k = _G._str_all_keys[i]
                local v = _G._string_table[k]
                if type(v) == 'string' then
                    local hex = ''
                    for j = 1, #v do
                        hex = hex .. string.format('%02x', string.byte(v, j))
                    end
                    table.insert(_G._batch, {{k, #v, hex}})
                end
            end
            """)
            bn = li("#_G._batch") or 0
            for bi in range(1, bn + 1):
                k = li(f"_G._batch[{bi}][1]")
                slen = li(f"_G._batch[{bi}][2]")
                hex_str = ls(f"_G._batch[{bi}][3]")
                if k is not None and hex_str:
                    try:
                        raw = bytes.fromhex(hex_str)
                        text = raw.decode('utf-8', errors='replace')
                        all_strings[k] = text
                    except:
                        all_strings[k] = f"<hex:{hex_str[:100]}>"
        
        with open('luraph_strings_decrypted.json', 'w', encoding='utf-8') as f:
            json.dump(all_strings, f, indent=2, ensure_ascii=False, sort_keys=True)
        print(f"\nSaved {len(all_strings)} strings to luraph_strings_decrypted.json")
        
        # Show some interesting strings
        print("\nInteresting strings:")
        for k in sorted(all_strings.keys()):
            v = all_strings[k]
            if len(v) > 3 and sum(1 for c in v if c.isalpha()) > len(v) * 0.5:
                print(f"  [{k}] {v[:100]}")
else:
    print("\nNo strings captured via dump injection.")
    print("VM may not have reached the deserialization point within op limit.")
    print(f"Protos captured: {li('#_G._protos')}")
