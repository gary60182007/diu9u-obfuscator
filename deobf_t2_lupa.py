import sys, os, traceback, time

from lupa import LuaRuntime

with open('unobfuscator/target2_lua51.lua', 'r', encoding='utf-8') as f:
    converted = f.read()

print(f"Converted source: {len(converted)} chars")

lua = LuaRuntime(unpack_returned_tuples=True)

lua.execute("""
    -- bit32 compatibility for Lua 5.4 (uses native operators)
    if not bit32 then
        bit32 = {}
        function bit32.band(...)
            local r = 0xFFFFFFFF
            for i = 1, select("#", ...) do r = r & (select(i, ...) or 0) end
            return r
        end
        function bit32.bor(...)
            local r = 0
            for i = 1, select("#", ...) do r = r | (select(i, ...) or 0) end
            return r
        end
        function bit32.bxor(...)
            local r = 0
            for i = 1, select("#", ...) do r = r ~ (select(i, ...) or 0) end
            return r & 0xFFFFFFFF
        end
        function bit32.bnot(a) return (~(a or 0)) & 0xFFFFFFFF end
        function bit32.lshift(a, b) return ((a or 0) << (b or 0)) & 0xFFFFFFFF end
        function bit32.rshift(a, b) return ((a or 0) & 0xFFFFFFFF) >> (b or 0) end
        function bit32.rrotate(a, b)
            a = (a or 0) & 0xFFFFFFFF
            b = (b or 0) % 32
            return ((a >> b) | (a << (32 - b))) & 0xFFFFFFFF
        end
        function bit32.lrotate(a, b)
            a = (a or 0) & 0xFFFFFFFF
            b = (b or 0) % 32
            return ((a << b) | (a >> (32 - b))) & 0xFFFFFFFF
        end
        function bit32.arshift(a, b)
            a = (a or 0) & 0xFFFFFFFF
            if a >= 0x80000000 then a = a - 0x100000000 end
            return (a >> (b or 0)) & 0xFFFFFFFF
        end
        function bit32.btest(a, b) return ((a or 0) & (b or 0)) ~= 0 end
        function bit32.extract(n, field, width)
            width = width or 1
            return ((n or 0) >> field) & ((1 << width) - 1)
        end
        function bit32.replace(n, v, field, width)
            width = width or 1
            local mask = ((1 << width) - 1) << field
            return ((n or 0) & ~mask) | (((v or 0) << field) & mask)
        end
        function bit32.countlz(x)
            x = (x or 0) & 0xFFFFFFFF
            if x == 0 then return 32 end
            local n = 0
            while (x & 0x80000000) == 0 do
                n = n + 1
                x = x << 1
            end
            return n
        end
        function bit32.countrz(x)
            x = (x or 0) & 0xFFFFFFFF
            if x == 0 then return 32 end
            local n = 0
            while (x & 1) == 0 do
                n = n + 1
                x = x >> 1
            end
            return n
        end
    end

    -- table.move for Lua 5.3/5.4 (usually built-in but just in case)
    if not table.move then
        table.move = function(a1, f, e, t, a2)
            a2 = a2 or a1
            if t > f then
                for i = e, f, -1 do a2[t + (i - f)] = a1[i] end
            else
                for i = f, e do a2[t + (i - f)] = a1[i] end
            end
            return a2
        end
    end

    -- Luau generalized iteration helper
    function __luau_iter(x)
        if type(x) == "function" then return x end
        if type(x) == "table" then
            local mt = getmetatable(x)
            if mt and mt.__iter then return mt.__iter(x) end
            if mt and mt.__call then return x end
            return next, x
        end
        return x
    end

    -- Luau table extensions
    if not table.create then
        table.create = function(n, val)
            local t = {}
            if val ~= nil then
                for i = 1, n do t[i] = val end
            end
            return t
        end
    end
    if not table.find then
        table.find = function(t, val, init)
            for i = (init or 1), #t do
                if t[i] == val then return i end
            end
            return nil
        end
    end
    if not table.clone then
        table.clone = function(t)
            local c = {}
            for k, v in pairs(t) do c[k] = v end
            return setmetatable(c, getmetatable(t))
        end
    end
    if not table.freeze then
        table.freeze = function(t) return t end
    end
    if not table.isfrozen then
        table.isfrozen = function(t) return false end
    end
    if not table.clear then
        table.clear = function(t)
            for k in pairs(t) do t[k] = nil end
        end
    end

    -- Lua 5.1 compat
    if not getfenv then
        getfenv = function(f)
            if type(f) == "number" or f == nil then return _G end
            return _G
        end
    end
    if not setfenv then
        setfenv = function(f, env) return f end
    end
    if not unpack then
        unpack = table.unpack
    end
    if not loadstring then
        loadstring = load
    end

    -- Luau globals
    if not getgenv then
        getgenv = function() return _G end
    end

    -- string.pack/unpack should be native in 5.3+

    _G._intercepted = {}
    local orig_load = load
    local orig_loadstring = loadstring or load

    function load(src, ...)
        if type(src) == 'string' then
            table.insert(_G._intercepted, src)
        end
        return orig_load(src, ...)
    end

    loadstring = load

    -- Mock Roblox environment
    _G._api_log = {}
    local function log_api(msg)
        table.insert(_G._api_log, msg)
        if #_G._api_log <= 50 then
            io.write("  API: " .. msg .. "\\n")
            io.flush()
        end
    end

    local function make_mock(name)
        local mt = {}
        mt.__index = function(self, key)
            local path = rawget(self, "__path") or name
            local child_path = path .. "." .. tostring(key)
            log_api("GET " .. child_path)
            return setmetatable({__path = child_path}, mt)
        end
        mt.__newindex = function(self, key, val)
            local path = rawget(self, "__path") or name
            log_api("SET " .. path .. "." .. tostring(key) .. " = " .. tostring(val))
        end
        mt.__call = function(self, ...)
            local path = rawget(self, "__path") or name
            local args = {}
            for i = 1, select("#", ...) do
                args[i] = tostring(select(i, ...))
            end
            log_api("CALL " .. path .. "(" .. table.concat(args, ", ") .. ")")
            return setmetatable({__path = path .. "()"}, mt)
        end
        mt.__tostring = function(self)
            return rawget(self, "__path") or name
        end
        mt.__concat = function(a, b) return tostring(a) .. tostring(b) end
        mt.__add = function(a, b) return 0 end
        mt.__sub = function(a, b) return 0 end
        mt.__mul = function(a, b) return 0 end
        mt.__div = function(a, b) return 0 end
        mt.__mod = function(a, b) return 0 end
        mt.__pow = function(a, b) return 0 end
        mt.__unm = function(a) return 0 end
        mt.__idiv = function(a, b) return 0 end
        mt.__eq = function(a, b) return false end
        mt.__lt = function(a, b) return false end
        mt.__le = function(a, b) return false end
        mt.__len = function(a) return 0 end
        mt.__band = function(a, b) return 0 end
        mt.__bor = function(a, b) return 0 end
        mt.__bxor = function(a, b) return 0 end
        mt.__bnot = function(a) return 0 end
        mt.__shl = function(a, b) return 0 end
        mt.__shr = function(a, b) return 0 end
        return setmetatable({__path = name}, mt)
    end

    game = make_mock("game")
    workspace = make_mock("workspace")
    Instance = make_mock("Instance")
    Enum = make_mock("Enum")
    UDim2 = make_mock("UDim2")
    UDim = make_mock("UDim")
    Vector2 = make_mock("Vector2")

    -- Catch-all: any unknown global returns a mock
    setmetatable(_G, {
        __index = function(self, key)
            if type(key) == "string" then
                local m = make_mock(key)
                rawset(self, key, m)
                return m
            end
        end
    })

    -- Override pairs/ipairs to handle mock objects
    local orig_pairs = pairs
    local orig_ipairs = ipairs
    pairs = function(t)
        if type(t) == "table" and rawget(t, "__path") then
            return function() return nil end
        end
        return orig_pairs(t)
    end
    ipairs = function(t)
        if type(t) == "table" and rawget(t, "__path") then
            return function() return nil end, t, 0
        end
        return orig_ipairs(t)
    end

    -- task library (don't call functions to avoid infinite loops - just log)
    _G._task_funcs = {}
    task = {
        spawn = function(f, ...) log_api("task.spawn()"); if type(f) == "function" then table.insert(_G._task_funcs, f) end end,
        defer = function(f, ...) log_api("task.defer()"); if type(f) == "function" then table.insert(_G._task_funcs, f) end end,
        delay = function(t, f, ...) log_api("task.delay()"); end,
        wait = function(t) return 0 end,
        cancel = function() end,
    }
    Vector3 = make_mock("Vector3")
    CFrame = make_mock("CFrame")
    Color3 = make_mock("Color3")
    BrickColor = make_mock("BrickColor")
    NumberRange = make_mock("NumberRange")
    NumberSequence = make_mock("NumberSequence")
    ColorSequence = make_mock("ColorSequence")
    TweenInfo = make_mock("TweenInfo")
    Ray = make_mock("Ray")
    Region3 = make_mock("Region3")
    Rect = make_mock("Rect")
    spawn = function(f, ...) log_api("spawn()"); if type(f) == "function" then pcall(f, ...) end; return end
    wait = function(t) log_api("wait(" .. tostring(t) .. ")"); return 0, os.clock() end
    delay = function(t, f, ...) log_api("delay(" .. tostring(t) .. ")"); if type(f) == "function" then pcall(f, ...) end; return end
    tick = function() return os.clock() end
    time = function() return os.clock() end
    typeof = function(v) return type(v) end
    warn = function(...) log_api("warn(...)") end
""")

lua.execute("""
    _G._op_count = 0
    _G._op_limit = 100000000
    _G._last_report = 0
    debug.sethook(function()
        _G._op_count = _G._op_count + 1000
        if _G._op_count >= _G._op_limit then
            error("OP_LIMIT_REACHED: " .. tostring(_G._op_count) .. " instructions")
        end
        if _G._op_count - _G._last_report >= 50000000 then
            _G._last_report = _G._op_count
            io.write("  ops: " .. tostring(_G._op_count) .. "\\n")
            io.flush()
        end
    end, "", 1000)
""")

print("Executing in Lua 5.4...")

# Inject tracing into h's while loop and z's computation
converted_dbg = converted.replace(
    'h = function(Z, T, H, n, e)\n        e[27] = nil\n        e[28] = nil\n        n = 67\n        while true do',
    'h = function(Z, T, H, n, e)\n        e[27] = nil\n        e[28] = nil\n        n = 67\n        local _iter = 0\n        while true do\n            _iter = _iter + 1\n            if _iter <= 20 then io.write("  h iter=" .. _iter .. " n=" .. tostring(n) .. "\\n"); io.flush() end'
)
converted_dbg = converted_dbg.replace(
    'z = function(Z, T, H, n, e)\n        n = Z.A\n        for I = 0, 255, 1 do\n            H[15][I] = n(I)\n        end\n        if not not e[7875] then',
    'z = function(Z, T, H, n, e)\n        io.write("  z called: e[1216]=" .. tostring(e[1216]) .. " e[7875]=" .. tostring(e[7875]) .. "\\n"); io.flush()\n        n = Z.A\n        for I = 0, 255, 1 do\n            H[15][I] = n(I)\n        end\n        if not not e[7875] then'
)

# Add env table dump after h returns
converted_dbg = converted_dbg.replace(
    'e[29] = coroutine.wrap',
    'io.write("  h done, checking e[28]=" .. tostring(e[28]) .. " Z.W=" .. tostring(Z.W) .. "\\n"); io.flush(); e[29] = coroutine.wrap'
)

# Replace VM error re-raise with logging (both B=function variants)
# The VM catches errors with pcall then re-raises via T[39](msg, 0)
# Replace T[39] calls in the error handler sections with print to prevent re-raise
for err_pattern in [
    'T[39]("Luraph Script:" .. ((C[V] or "(internal)") .. (": " .. T[22](i))), 0)',
    'T[39]("Luraph Script:" .. ((C[A] or "(internal)") .. (": " .. T[22](u))), 0)',
]:
    converted_dbg = converted_dbg.replace(
        err_pattern,
        'io.write("  VM_ERROR: " .. tostring(i or u) .. "\\n"); io.flush()'
    )
# Also replace the plain T[39](i, 0) and T[39](u, 0) and T[39](b, 0) error re-raises
for var in ['i', 'u', 'b']:
    converted_dbg = converted_dbg.replace(
        f'T[39]({var}, 0)',
        f'io.write("  VM_ERROR_RAW: " .. tostring({var}) .. "\\n"); io.flush()'
    )

# Inject bytecode dumper into T[43] (closure factory)
# Extract all prototype data: opcodes, operands, constants
converted_dbg = converted_dbg.replace(
    'T[43] = function(e, I, p)\n            local _ = e[6]',
    '''T[43] = function(e, I, p)
            if e == nil then return function(...) return end end
            if not rawget(_G, '_protos') then rawset(_G, '_protos', {}) end
            local proto = {}
            proto.type = e[1]
            proto.numregs = e[6]
            proto.opcodes = {}
            proto.operM = {}
            proto.operL = {}
            proto.operP = {}
            proto.constT = {}
            proto.constQ = {}
            proto.constG = {}
            proto.debug = {}
            local r_arr = e[3]
            local M_arr = e[4]
            local L_arr = e[5]
            local g_arr = e[7]
            local t_arr = e[8]
            local Q_arr = e[9]
            local P_arr = e[10]
            local C_arr = e[11]
            if r_arr then
                local idx = 1
                while true do
                    local v = r_arr[idx]
                    if v == nil then break end
                    proto.opcodes[idx] = v
                    if M_arr then proto.operM[idx] = M_arr[idx] end
                    if L_arr then proto.operL[idx] = L_arr[idx] end
                    if P_arr then proto.operP[idx] = P_arr[idx] end
                    if t_arr then proto.constT[idx] = t_arr[idx] end
                    if Q_arr then proto.constQ[idx] = Q_arr[idx] end
                    if g_arr then proto.constG[idx] = g_arr[idx] end
                    if C_arr then proto.debug[idx] = C_arr[idx] end
                    idx = idx + 1
                    if idx > 50000 then break end
                end
            end
            table.insert(rawget(_G, '_protos'), proto)
            local _ = e[6]'''
)

t0 = time.time()
try:
    result = lua.execute(converted_dbg)
    print(f"Result: {result}")
except Exception as e:
    err_str = str(e)
    print(f"Error: {type(e).__name__}: {err_str[:1200]}")

elapsed = time.time() - t0
print(f"Elapsed: {elapsed:.2f}s")
print(f"Op count: {lua.eval('_G._op_count')}")

try:
    count = lua.eval("#_G._intercepted")
    print(f"\nIntercepted loads: {count}")
    if count and int(count) > 0:
        os.makedirs('unobfuscator/cracked script', exist_ok=True)
        for i in range(1, int(count) + 1):
            s = lua.eval(f"_G._intercepted[{i}]")
            s_str = str(s)
            print(f"  [{i}] {len(s_str)} chars: {s_str[:200]}...")
            path = f'unobfuscator/cracked script/target2_raw_{i}.lua'
            with open(path, 'w', encoding='utf-8', errors='replace') as f:
                f.write(s_str)
            print(f"  Saved to {path}")
except Exception as e:
    print(f"Error checking intercepted: {e}")

# Disable debug hook before extraction
lua.execute("debug.sethook()")

# Extract bytecode prototypes
try:
    proto_count = lua.eval("#_G._protos") if lua.eval("_G._protos ~= nil") else 0
    print(f"\nExtracted prototypes: {proto_count}")
    if proto_count and int(proto_count) > 0:
        import json
        os.makedirs('unobfuscator/cracked script', exist_ok=True)
        all_protos = []
        for i in range(1, int(proto_count) + 1):
            proto = {}
            proto['id'] = i
            proto['type'] = lua.eval(f"_G._protos[{i}].type")
            proto['numregs'] = lua.eval(f"_G._protos[{i}].numregs")
            
            # Extract opcodes
            opcodes = []
            operM = []
            operL = []
            operP = []
            constT = []
            constQ = []
            constG = []
            
            # Use a Lua helper to extract arrays efficiently
            extract_fn = lua.eval("""
            function(proto)
                local result = {}
                result.opcodes = {}
                result.operM = {}
                result.operL = {}
                result.operP = {}
                result.constT = {}
                result.constQ = {}
                result.constG = {}
                local idx = 1
                while proto.opcodes[idx] ~= nil do
                    result.opcodes[idx] = proto.opcodes[idx]
                    result.operM[idx] = proto.operM[idx]
                    result.operL[idx] = proto.operL[idx]
                    result.operP[idx] = proto.operP[idx]
                    result.constT[idx] = proto.constT[idx]
                    result.constQ[idx] = proto.constQ[idx]
                    result.constG[idx] = proto.constG[idx]
                    idx = idx + 1
                    if idx > 50000 then break end
                end
                result.count = idx - 1
                return result
            end
            """)
            proto_data = lua.eval(f"rawget(_G, '_protos')[{i}]")
            extracted = extract_fn(proto_data)
            op_count = int(extracted['count'])
            for j in range(1, op_count + 1):
                opcodes.append(int(extracted['opcodes'][j]))
                m = extracted['operM'][j]
                l = extracted['operL'][j]
                p_v = extracted['operP'][j]
                t_v = extracted['constT'][j]
                q_v = extracted['constQ'][j]
                g_v = extracted['constG'][j]
                def safe_num(v):
                    if v is None: return None
                    try: return float(v)
                    except: return str(v)
                operM.append(safe_num(m))
                operL.append(safe_num(l))
                operP.append(safe_num(p_v))
                constT.append(str(t_v) if t_v is not None else None)
                constQ.append(safe_num(q_v))
                constG.append(safe_num(g_v))
            
            proto['num_instructions'] = op_count
            proto['opcodes'] = opcodes
            proto['operM'] = operM
            proto['operL'] = operL
            proto['operP'] = operP
            proto['constT'] = constT
            proto['constQ'] = constQ
            proto['constG'] = constG
            
            # Collect unique string constants
            strings = sorted(set(s for s in constT if s is not None))
            proto['strings'] = strings
            
            print(f"  Proto {i}: type={proto['type']} regs={proto['numregs']} ops={op_count} strings={len(strings)}")
            if strings:
                print(f"    Strings: {strings[:20]}")
            
            all_protos.append(proto)
        
        with open('unobfuscator/cracked script/target2_bytecode.json', 'w') as f:
            json.dump(all_protos, f, indent=2, default=str)
        print(f"\nSaved bytecode data to unobfuscator/cracked script/target2_bytecode.json")
except Exception as e:
    print(f"Error extracting prototypes: {e}")
    traceback.print_exc()
