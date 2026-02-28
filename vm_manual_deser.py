"""
Capture z (VM object) and r (state table) after z:zy.
Then manually call the deserialization chain: lF -> _9 -> t9 -> I9
to populate r[57] (string table) and extract decrypted strings.
"""
import sys, time, json, re
sys.path.insert(0, '.')

with open(r'unobfuscator\pending crack\bloxburg_script.lua', 'r', encoding='utf-8', errors='replace') as f:
    source = f.read()

exec(open('run_luraph_test.py').read().split("print('Reading source...')")[0])
source = preprocess_luau(source)

from unobfuscator.utils.lua_runtime import LuaRuntimeWrapper, LuaRuntimeError

runtime = LuaRuntimeWrapper(op_limit=2_000_000_000, timeout=120)
runtime._init_runtime()
runtime.lua.execute("_G._protos = {}; _G._saved = {}")

# Inject z AND r capture after z:zy(r)
modified = source
zy_matches = list(re.finditer(r':zy\((\w+)\)', modified))
zm = zy_matches[0]
r_arg = zm.group(1)
semi_pos = modified.index(';', zm.end())

# In zy=function(z,r), z=VM object, r=state table
# But zy is called as self:zy(r), so inside zy: z=self, r=param
# We need to capture the CALLER's z and r references
# The caller is Jy, which calls z:zy(r) — z and r are Jy's params
# But Jy's z and r map back to z:q's variables

# Actually, the injection is AFTER the call :zy(r_arg)
# r_arg is the r variable in the calling scope (Jy or z:q)
# We need to also capture the z object (self) from the calling scope
# The self is whatever object the :zy method is called on

# Find the z:zy call pattern: something:zy(r_arg)
# The 'something' before :zy is the z reference in the caller
zy_call_str = modified[zm.start()-50:zm.end()]
# Find the object before :zy
pre = modified[:zm.start()]
# Walk backwards to find the variable name before :zy
i = zm.start() - 1
while i >= 0 and (modified[i].isalnum() or modified[i] == '_'):
    i -= 1
z_var = modified[i+1:zm.start()]
print(f"Found z:zy call: z_var='{z_var}', r_arg='{r_arg}'")

capture = f';_G._r={r_arg};_G._z={z_var};_G._r10_at_zy={r_arg}[10]'
modified = modified[:semi_pos+1] + capture + modified[semi_pos+1:]

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

modified = runtime.suppress_vm_errors(modified)

print("Executing VM...")
t0 = time.time()
try:
    runtime.execute(modified)
except LuaRuntimeError as e:
    elapsed = time.time() - t0
    err_msg = str(e)[:100]
    print(f"Stopped after {elapsed:.1f}s: {err_msg}")

runtime.lua.execute("_G._op_count = 0; _G._op_limit = 10000000000")

def li(expr):
    v = runtime.lua.eval(f"tonumber({expr})")
    return int(v) if v is not None else None

def ls(expr):
    v = runtime.lua.eval(expr)
    return str(v) if v is not None else None

# Check captures
print(f"\nz captured: {ls('type(_G._z)')}")
print(f"r captured: {ls('type(_G._r)')}")
print(f"r[10] at zy: {li('_G._r10_at_zy')}")
print(f"r[10] now: {li('_G._r[10]')}")

# Verify z has methods
runtime.lua.execute("""
_G._z_methods = {}
if type(_G._z) == 'table' then
    for k, v in pairs(_G._z) do
        if type(v) == 'function' then
            table.insert(_G._z_methods, tostring(k))
        end
    end
    table.sort(_G._z_methods)
end
""")
n_methods = li("#_G._z_methods") or 0
print(f"\nz has {n_methods} methods")
if n_methods > 0:
    methods_str = ls("table.concat(_G._z_methods, ',')")
    print(f"Methods: {methods_str[:500]}")

# Verify r has reader functions
for idx in [39, 40, 41, 43, 46, 47, 54, 55, 56]:
    t = ls(f"type(_G._r[{idx}])")
    print(f"  r[{idx}] = {t}")

# Set r[10] to the script data offset (after sub-buffer)
r10_at_zy = li('_G._r10_at_zy')
print(f"\n=== Setting up for manual deserialization ===")
print(f"r[10] was {r10_at_zy} at z:zy injection point")

# Initialize r[57] as string table
runtime.lua.execute("if not _G._r[57] then _G._r[57] = {} end")

# First, let's set r[10] back to where z:zy left off
if r10_at_zy is not None and r10_at_zy > 0:
    runtime.lua.execute(f"_G._r[10] = {r10_at_zy}")
    print(f"Set r[10] = {r10_at_zy}")
else:
    # r[10] might have been 0 or nil, try known offset
    runtime.lua.execute("_G._r[10] = 94773")
    print("Set r[10] = 94773 (after sub-buffer, estimated)")

# Now try calling z:lF manually
# lF=function(z,r,C,W,Q) where Q is the r table
# Called as: D,Y,q = z:lF(Y,q,D,C)  -- C is r table
# So: z:lF(nil, nil, nil, r_table)
print(f"\n=== Calling z:lF ===")
try:
    runtime.lua.execute("""
    _G._op_count = 0
    local ok, W_or_err, r_result, C_result = pcall(function()
        return _G._z.lF(_G._z, nil, nil, nil, _G._r)
    end)
    _G._lF_ok = ok
    if ok then
        _G._lF_W = W_or_err
        _G._lF_r = r_result
        _G._lF_C = C_result
        _G._lF_r10 = _G._r[10]
    else
        _G._lF_err = tostring(W_or_err)
    end
    """)
    ok = ls("tostring(_G._lF_ok)")
    if str(ok) == 'true':
        W_type = ls("type(_G._lF_W)")
        C_val = li("_G._lF_C")
        r10_after = li("_G._lF_r10")
        print(f"  lF returned: W type={W_type}, C={C_val}, r[10]={r10_after}")
        
        # Check r[42] (set by lF)
        r42_type = ls("type(_G._r[42])")
        print(f"  r[42] = {r42_type}")
        
        # Check r[12] (set by lF to empty table)
        r12_type = ls("type(_G._r[12])")
        r12_len = li("#_G._r[12]") if str(r12_type) == 'table' else None
        print(f"  r[12] = {r12_type} (len={r12_len})")
        
        # Now try calling z:_9
        # _9=function(z,r,C,W,Q,i,O) 
        # Called as: a,Y,Z = z:_9(C,w,Y,q,Z,D)
        # where C=r_table, w=30 (first iteration), Y=lF_r=nil, q=lF_C, Z=nil, D=lF_W
        print(f"\n=== Calling z:_9 loop ===")
        runtime.lua.execute("""
        _G._op_count = 0
        local W = _G._lF_W  -- D from lF
        local Y = _G._lF_r  -- Y from lF (nil)
        local q = _G._lF_C  -- C from lF
        local Z = nil
        local ok, err_msg
        
        -- _9 loop: for w=30,530,117 do
        for w = 30, 530, 117 do
            local a
            ok, a, Y, Z = pcall(function()
                return _G._z._9(_G._z, _G._r, w, Y, q, Z, W)
            end)
            if not ok then
                _G.__9_err = tostring(a)
                break
            end
            _G.__9_a = a
            _G.__9_Y = Y
            _G.__9_Z = Z
            if a == 62586 then
                -- continue
            elseif a == -1 then
                _G.__9_err = "returned -1"
                break
            end
        end
        
        _G.__9_ok = ok
        _G.__9_r10 = _G._r[10]
        _G.__9_Z_type = type(Z)
        _G.__9_W = W
        _G.__9_q = q
        """)
        
        ok9 = ls("tostring(_G.__9_ok)")
        r10_9 = li("_G.__9_r10")
        Z_type = ls("_G.__9_Z_type")
        print(f"  _9 ok={ok9}, r[10]={r10_9}, Z type={Z_type}")
        if str(ok9) != 'true':
            print(f"  _9 error: {ls('_G.__9_err')}")
        else:
            a9 = li("_G.__9_a")
            print(f"  _9 last a={a9}")
            
            # Now call t9
            # t9=function(z,z,r,C,W) -- note z is shadowed!
            # Called as: q = z:t9(C,Z,D,q) 
            # where C=r_table, Z=Z from _9, D=lF_W, q=lF_C
            print(f"\n=== Calling z:t9 ===")
            runtime.lua.execute("""
            _G._op_count = 0
            local ok, result = pcall(function()
                return _G._z.t9(_G._z, _G._r, _G.__9_Z, _G.__9_W, _G.__9_q)
            end)
            _G._t9_ok = ok
            if ok then
                _G._t9_result = result
                _G._t9_r10 = _G._r[10]
            else
                _G._t9_err = tostring(result)
            end
            """)
            
            t9_ok = ls("tostring(_G._t9_ok)")
            print(f"  t9 ok={t9_ok}")
            if str(t9_ok) == 'true':
                r10_t9 = li("_G._t9_r10")
                t9_type = ls("type(_G._t9_result)")
                print(f"  t9 result type={t9_type}, r[10]={r10_t9}")
                
                # Check r[57] for strings
                runtime.lua.execute("""
                _G._str_count = 0
                _G._str_samples = {}
                if type(_G._r[57]) == 'table' then
                    for k, v in pairs(_G._r[57]) do
                        _G._str_count = _G._str_count + 1
                        if _G._str_count <= 100 then
                            local info = tostring(k) .. ':' .. type(v)
                            if type(v) == 'string' then
                                local safe = ''
                                for i = 1, math.min(#v, 80) do
                                    local b = string.byte(v, i)
                                    if b >= 32 and b <= 126 then
                                        safe = safe .. string.char(b)
                                    else
                                        safe = safe .. '.'
                                    end
                                end
                                info = info .. '=' .. safe .. ' (len=' .. #v .. ')'
                            elseif type(v) == 'table' then
                                local c = 0
                                for _ in pairs(v) do c = c + 1 end
                                info = info .. '(tbl ' .. c .. ')'
                                if c >= 1 then
                                    local v1 = v[1]
                                    if type(v1) == 'string' then
                                        local safe = ''
                                        for i = 1, math.min(#v1, 80) do
                                            local b = string.byte(v1, i)
                                            if b >= 32 and b <= 126 then
                                                safe = safe .. string.char(b)
                                            else
                                                safe = safe .. '.'
                                            end
                                        end
                                        info = info .. '=' .. safe
                                    end
                                end
                            end
                            table.insert(_G._str_samples, info)
                        end
                    end
                end
                """)
                str_count = li("_G._str_count")
                print(f"\n=== String table r[57]: {str_count} entries ===")
                n_samples = li("#_G._str_samples") or 0
                for i in range(1, n_samples + 1):
                    print(f"  {ls(f'_G._str_samples[{i}]')}")
                
                # Now call I9 to finalize
                runtime.lua.execute("""
                _G._op_count = 0
                pcall(function()
                    _G._z.I9(_G._z, _G._r)
                end)
                """)
                
                # Call t9 second time (the loop calls it twice: a=56 and a=181)
                runtime.lua.execute("""
                _G._op_count = 0
                local ok, result = pcall(function()
                    return _G._z.t9(_G._z, _G._r, _G.__9_Z, _G.__9_W, _G._t9_result)
                end)
                _G._t9b_ok = ok
                if ok then
                    _G._t9b_result = result
                else
                    _G._t9b_err = tostring(result)
                end
                """)
                t9b_ok = ls("tostring(_G._t9b_ok)")
                if str(t9b_ok) == 'true':
                    print(f"\n  Second t9 call OK, result type={ls('type(_G._t9b_result)')}")
            else:
                print(f"  t9 error: {ls('_G._t9_err')}")
    else:
        print(f"  lF error: {ls('_G._lF_err')}")
except Exception as e:
    print(f"  Exception: {e}")

# Final state
print(f"\n=== Final state ===")
print(f"r[10] = {li('_G._r[10]')}")
print(f"Protos captured: {li('#_G._protos')}")
