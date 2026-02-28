from __future__ import annotations
import os
import time
from typing import Any, Callable, Dict, List, Optional

try:
    from lupa import LuaRuntime
    HAS_LUPA = True
except ImportError:
    HAS_LUPA = False


_BIT32_SHIMS = r"""
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
        a = (a or 0) & 0xFFFFFFFF; b = (b or 0) % 32
        return ((a >> b) | (a << (32 - b))) & 0xFFFFFFFF
    end
    function bit32.lrotate(a, b)
        a = (a or 0) & 0xFFFFFFFF; b = (b or 0) % 32
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
        while (x & 0x80000000) == 0 do n = n + 1; x = x << 1 end
        return n
    end
    function bit32.countrz(x)
        x = (x or 0) & 0xFFFFFFFF
        if x == 0 then return 32 end
        local n = 0
        while (x & 1) == 0 do n = n + 1; x = x >> 1 end
        return n
    end
end
"""

_LUAU_COMPAT = r"""
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

if not table.create then
    table.create = function(n, val)
        local t = {}
        if val ~= nil then for i = 1, n do t[i] = val end end
        return t
    end
end
if not table.find then
    table.find = function(t, val, init)
        for i = (init or 1), #t do if t[i] == val then return i end end
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
if not table.freeze then table.freeze = function(t) return t end end
if not table.isfrozen then table.isfrozen = function(t) return false end end
if not table.clear then
    table.clear = function(t) for k in pairs(t) do t[k] = nil end end
end

if not getfenv then
    getfenv = function(f) return _G end
end
if not setfenv then
    setfenv = function(f, env) return f end
end
if not unpack then unpack = table.unpack end
if not loadstring then loadstring = load end
if not getgenv then getgenv = function() return _G end end
"""

_BUFFER_LIB = r"""
do
    local _pack = string.pack
    local _unpack = string.unpack
    local _byte = string.byte
    local _char = string.char
    local _concat = table.concat
    local _floor = math.floor
    local buf_mt = {}
    buf_mt.__index = buf_mt
    buffer = {}
    function buffer.create(size)
        local b = setmetatable({}, buf_mt)
        b._data = {}
        local s = _floor(size)
        for i = 1, s do b._data[i] = 0 end
        b._size = s
        return b
    end
    function buffer.fromstring(s)
        local b = setmetatable({}, buf_mt)
        b._data = {}
        for i = 1, #s do b._data[i] = _byte(s, i) end
        b._size = #s
        return b
    end
    function buffer.tostring(b)
        local t = {}
        for i = 1, b._size do t[i] = _char(b._data[i]) end
        return _concat(t)
    end
    function buffer.len(b) return b._size end
    function buffer.readu8(b, o) return b._data[o+1] or 0 end
    function buffer.readi8(b, o)
        local v = b._data[o+1] or 0
        if v >= 128 then v = v - 256 end
        return v
    end
    function buffer.readu16(b, o)
        return (b._data[o+1] or 0) + (b._data[o+2] or 0) * 256
    end
    function buffer.readi16(b, o)
        local v = (b._data[o+1] or 0) + (b._data[o+2] or 0) * 256
        if v >= 32768 then v = v - 65536 end
        return v
    end
    function buffer.readu32(b, o)
        return (b._data[o+1] or 0) + (b._data[o+2] or 0)*256 + (b._data[o+3] or 0)*65536 + (b._data[o+4] or 0)*16777216
    end
    function buffer.readi32(b, o)
        local v = (b._data[o+1] or 0) + (b._data[o+2] or 0)*256 + (b._data[o+3] or 0)*65536 + (b._data[o+4] or 0)*16777216
        if v >= 2147483648 then v = v - 4294967296 end
        return v
    end
    function buffer.readf32(b, o)
        local s = _char(b._data[o+1] or 0, b._data[o+2] or 0, b._data[o+3] or 0, b._data[o+4] or 0)
        return _unpack("<f", s)
    end
    function buffer.readf64(b, o)
        local s = _char(b._data[o+1] or 0, b._data[o+2] or 0, b._data[o+3] or 0, b._data[o+4] or 0,
                       b._data[o+5] or 0, b._data[o+6] or 0, b._data[o+7] or 0, b._data[o+8] or 0)
        return _unpack("<d", s)
    end
    function buffer.writeu8(b, o, v) b._data[o+1] = _floor(v) % 256 end
    function buffer.writei8(b, o, v) if v < 0 then v = v + 256 end; buffer.writeu8(b, o, v) end
    function buffer.writeu16(b, o, v)
        v = _floor(v)
        b._data[o+1] = v % 256
        b._data[o+2] = _floor(v / 256) % 256
    end
    function buffer.writei16(b, o, v) if v < 0 then v = v + 65536 end; buffer.writeu16(b, o, v) end
    function buffer.writeu32(b, o, v)
        v = _floor(v)
        b._data[o+1] = v % 256
        b._data[o+2] = _floor(v / 256) % 256
        b._data[o+3] = _floor(v / 65536) % 256
        b._data[o+4] = _floor(v / 16777216) % 256
    end
    function buffer.writei32(b, o, v) if v < 0 then v = v + 4294967296 end; buffer.writeu32(b, o, v) end
    function buffer.writef32(b, o, v)
        local s = _pack("<f", v)
        for i = 1, 4 do b._data[o+i] = _byte(s, i) end
    end
    function buffer.writef64(b, o, v)
        local s = _pack("<d", v)
        for i = 1, 8 do b._data[o+i] = _byte(s, i) end
    end
    function buffer.copy(dst, dO, src, sO, c)
        if type(src) == "string" then
            sO = sO or 0; c = c or #src
            for i = 0, c-1 do dst._data[dO+1+i] = _byte(src, sO+1+i) or 0 end
        else
            sO = sO or 0; c = c or src._size
            for i = 0, c-1 do dst._data[dO+1+i] = src._data[sO+1+i] or 0 end
        end
    end
    function buffer.fill(b, o, v, c)
        c = c or (b._size - o)
        v = _floor(v) % 256
        for i = 0, c-1 do b._data[o+1+i] = v end
    end
    function buffer.readstring(b, o, c)
        local t = {}
        for i = 0, c-1 do t[#t+1] = _char(b._data[o+1+i] or 0) end
        return _concat(t)
    end
    function buffer.writestring(b, o, v, c)
        c = c or #v
        for i = 0, c-1 do b._data[o+1+i] = _byte(v, i+1) or 0 end
    end
end
"""

_ROBLOX_MOCKS = r"""
_G._api_log = {}
local function log_api(msg)
    table.insert(_G._api_log, msg)
end

local function make_mock(name)
    local mt = {}
    mt.__index = function(self, key)
        local path = rawget(self, "__path") or name
        local child_path = path .. "." .. tostring(key)
        return setmetatable({__path = child_path}, mt)
    end
    mt.__newindex = function(self, key, val)
        local path = rawget(self, "__path") or name
    end
    mt.__call = function(self, ...)
        local path = rawget(self, "__path") or name
        local args = {...}
        if path:match("HttpGet$") or path:match("HttpGetAsync$") then
            return tostring(os.time())
        end
        if path:match("GetService$") then
            local s = args[2] or args[1]
            if type(s) == "string" then
                return setmetatable({__path = s}, mt)
            end
        end
        if path:match("GetChildren$") or path:match("GetPlayers$") or path:match("GetDescendants$") then
            return {}
        end
        if path:match("FindFirstChild$") or path:match("WaitForChild$") then
            local child = args[2] or args[1]
            if type(child) == "string" then
                return setmetatable({__path = path:gsub("[^%.]+$", "") .. child}, mt)
            end
        end
        return setmetatable({__path = path .. "()"}, mt)
    end
    mt.__tostring = function(self) return rawget(self, "__path") or name end
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

setmetatable(_G, {
    __index = function(self, key)
        if type(key) == "string" then
            local m = make_mock(key)
            rawset(self, key, m)
            return m
        end
    end
})

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

task = {
    spawn = function(f, ...) log_api("task.spawn()") end,
    defer = function(f, ...) log_api("task.defer()") end,
    delay = function(t, f, ...) log_api("task.delay()") end,
    wait = function(t) return 0 end,
    cancel = function() end,
}
spawn = function(f, ...) log_api("spawn()") end
wait = function(t) return 0, os.clock() end
delay = function(t, f, ...) log_api("delay()") end
tick = function() return os.clock() end
time = function() return os.clock() end
typeof = function(v)
    local t = type(v)
    if t == "table" then
        if rawget(v, "_data") and rawget(v, "_size") then return "buffer" end
        if rawget(v, "__path") then return "Instance" end
    end
    return t
end
warn = function(...) end

islclosure = function(f) return type(f) == "function" end
newcclosure = function(f) return f end
iscclosure = function() return false end
hookfunction = function(old) return old end
hookmetamethod = function() return function() end end
getrawmetatable = getmetatable
setrawmetatable = setmetatable
checkcaller = function() return true end
cloneref = function(x) return x end
gethui = function() return make_mock("HiddenUI") end
getrenv = function() return _G end
getnamecallmethod = function() return "" end
setnamecallmethod = function() end
firesignal = function() end
isnetworkowner = function() return true end
sethiddenproperty = function() end
gethiddenproperty = function() return nil end
request = function() return {StatusCode=200, Body="{}", Headers={}} end
http_request = request
isexecutorclosure = function(f) return type(f) == "function" end

local _real_error = error
error = function(msg, level)
    if type(msg) == "string" and msg:find("Luraph Script:") then
        return
    end
    _real_error(msg, level)
end
"""

_INTERCEPTOR_SETUP = r"""
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
"""

_OP_LIMIT_TEMPLATE = r"""
_G._op_count = 0
_G._op_limit = {limit}
debug.sethook(function()
    _G._op_count = _G._op_count + 1000
    if _G._op_count >= _G._op_limit then
        error("OP_LIMIT_REACHED: " .. tostring(_G._op_count))
    end
end, "", 1000)
"""

_BYTECODE_DUMPER = r"""
_G._protos = {}
"""

_DUMPER_HOOK = r"""T[43] = function(e, I, p)
            if e == nil then return function(...) return end end
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
                    idx = idx + 1
                    if idx > 50000 then break end
                end
            end
            proto.num_instructions = (r_arr and #proto.opcodes) or 0
            table.insert(_G._protos, proto)
            local _ = e[6]"""


class LuaRuntimeError(Exception):
    pass


class LuaRuntimeWrapper:
    def __init__(self, op_limit: int = 100_000_000, timeout: float = 120.0):
        if not HAS_LUPA:
            raise ImportError("lupa is required: pip install lupa")
        self.op_limit = op_limit
        self.timeout = timeout
        self.lua: Optional[LuaRuntime] = None
        self._setup_done = False

    def _init_runtime(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute(_BIT32_SHIMS)
        self.lua.execute(_LUAU_COMPAT)
        self.lua.execute(_BUFFER_LIB)
        self.lua.execute(_ROBLOX_MOCKS)
        self.lua.execute(_INTERCEPTOR_SETUP)
        self.lua.execute(_OP_LIMIT_TEMPLATE.format(limit=self.op_limit))
        self._setup_done = True

    def execute(self, source: str) -> Any:
        if not self._setup_done:
            self._init_runtime()
        t0 = time.time()
        try:
            result = self.lua.execute(source)
            return result
        except Exception as e:
            elapsed = time.time() - t0
            err_str = str(e)
            if 'OP_LIMIT_REACHED' in err_str:
                raise LuaRuntimeError(f"Operation limit reached ({self.op_limit} ops) after {elapsed:.1f}s")
            raise LuaRuntimeError(f"Lua execution error after {elapsed:.1f}s: {err_str[:500]}")

    def eval(self, expr: str) -> Any:
        if not self._setup_done:
            self._init_runtime()
        return self.lua.eval(expr)

    def inject_bytecode_dumper(self, source: str) -> str:
        import re
        self.lua.execute(_BYTECODE_DUMPER)

        # v14.7+ pattern: )[N]=function(P1,P2)local vars=P1[idx],...
        # The closure factory destructures its first param into 10+ variables
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
        if m:
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
            return source[:m.start()] + replacement + source[m.end():]

        # Legacy pattern for older Luraph versions
        closure_factory = 'T[43] = function(e, I, p)\n            local _ = e[6]'
        if closure_factory in source:
            return source.replace(closure_factory, _DUMPER_HOOK)
        return source

    def suppress_vm_errors(self, source: str) -> str:
        import re
        # Luraph error re-raise: error("Luraph Script:" .. ..., 0)
        # Now handled by error() override in _ROBLOX_MOCKS, but also
        # try to neutralize direct re-raises in source for robustness
        source = re.sub(
            r'error\s*\(\s*"Luraph Script:"[^)]*,\s*0\s*\)',
            '(nil)',
            source
        )
        return source

    def extract_prototypes(self) -> List[Dict[str, Any]]:
        if not self._setup_done:
            return []
        self.lua.execute("debug.sethook()")
        try:
            proto_count = self.lua.eval("#_G._protos") if self.lua.eval("_G._protos ~= nil") else 0
        except Exception:
            return []
        if not proto_count or int(proto_count) == 0:
            return []

        extract_raw_fn = self.lua.eval("""
        function(proto)
            local result = {}
            result.id = proto.id or 0
            result.is_v14 = (proto[1] ~= nil)
            if result.is_v14 then
                for i = 1, 11 do
                    result["f" .. i] = proto[i]
                end
                local arrays = {}
                for i = 1, 11 do
                    local v = proto[i]
                    if type(v) == "table" then
                        local count = 0
                        local idx = 1
                        while v[idx] ~= nil do count = count + 1; idx = idx + 1; if idx > 50000 then break end end
                        arrays[i] = count
                    end
                end
                result.arrays = arrays
            else
                result.proto_type = proto.type or 0
                result.numregs = proto.numregs or 0
                result.num_instructions = proto.num_instructions or 0
            end
            return result
        end
        """)

        extract_legacy_fn = self.lua.eval("""
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

        def _safe_val(v):
            if v is None:
                return None
            try:
                fv = float(v)
                if fv == int(fv):
                    return int(fv)
                return fv
            except (TypeError, ValueError):
                return str(v)

        extract_sparse_fn = self.lua.eval("""
        function(tbl, max_idx)
            local result = {}
            local has_data = false
            if max_idx and max_idx > 0 then
                for i = 1, max_idx do
                    local v = tbl[i]
                    if v ~= nil then
                        result[i] = v
                        has_data = true
                    end
                end
            end
            if not has_data then
                for k, v in pairs(tbl) do
                    if type(k) == "number" then
                        result[k] = v
                        has_data = true
                    end
                end
            end
            result._has_data = has_data
            result._max = max_idx or 0
            return result
        end
        """)

        def _extract_array(lua_table, max_len=0):
            result = []
            if lua_table is None:
                return result
            try:
                sparse = extract_sparse_fn(lua_table, max_len)
                has_data = bool(sparse['_has_data'])
                if not has_data:
                    idx = 1
                    while True:
                        try:
                            v = lua_table[idx]
                            if v is None:
                                break
                            result.append(_safe_val(v))
                        except (KeyError, IndexError):
                            break
                        idx += 1
                        if idx > 50000:
                            break
                    return result
                actual_max = int(sparse['_max']) if sparse['_max'] else 0
                if actual_max > 0:
                    for i in range(1, actual_max + 1):
                        try:
                            v = sparse[i]
                            result.append(_safe_val(v))
                        except (KeyError, TypeError):
                            result.append(None)
                else:
                    max_key = 0
                    for k in sparse:
                        if isinstance(k, (int, float)) and str(k) not in ('_has_data', '_max'):
                            max_key = max(max_key, int(k))
                    for i in range(1, max_key + 1):
                        try:
                            v = sparse[i]
                            result.append(_safe_val(v))
                        except (KeyError, TypeError):
                            result.append(None)
            except Exception:
                idx = 1
                while True:
                    try:
                        v = lua_table[idx]
                        if v is None:
                            break
                        result.append(_safe_val(v))
                    except (KeyError, IndexError):
                        break
                    idx += 1
                    if idx > 50000:
                        break
            return result

        all_protos = []
        for i in range(1, int(proto_count) + 1):
            proto_data = self.lua.eval(f"rawget(_G, '_protos')[{i}]")
            try:
                info = extract_raw_fn(proto_data)
            except Exception:
                all_protos.append({'id': i, 'raw_fields': {}, 'is_v14': False})
                continue

            proto: Dict[str, Any] = {'id': i}

            if info['is_v14']:
                proto['is_v14'] = True
                raw = {}
                instr_count = 0
                for fi in range(1, 12):
                    key = f'f{fi}'
                    val = info[key]
                    if val is not None:
                        try:
                            lua_type = self.lua.eval(f"type(rawget(_G, '_protos')[{i}][{fi}])")
                            if str(lua_type) == 'table':
                                arr = _extract_array(self.lua.eval(f"rawget(_G, '_protos')[{i}][{fi}]"))
                                raw[fi] = arr
                                if len(arr) > instr_count:
                                    instr_count = len(arr)
                            else:
                                raw[fi] = _safe_val(val)
                        except Exception:
                            raw[fi] = _safe_val(val)
                if instr_count > 0:
                    for fi in range(1, 12):
                        if fi in raw and isinstance(raw[fi], list) and len(raw[fi]) == 0:
                            try:
                                lua_type = self.lua.eval(f"type(rawget(_G, '_protos')[{i}][{fi}])")
                                if str(lua_type) == 'table':
                                    raw[fi] = _extract_array(
                                        self.lua.eval(f"rawget(_G, '_protos')[{i}][{fi}]"),
                                        max_len=instr_count
                                    )
                            except Exception:
                                pass
                proto['raw_fields'] = raw
            else:
                proto['is_v14'] = False
                proto['type'] = int(info.get('proto_type', 0) or 0)
                proto['numregs'] = int(info.get('numregs', 0) or 0)
                try:
                    extracted = extract_legacy_fn(proto_data)
                    op_count = int(extracted['count'])
                    opcodes, operM, operL, operP = [], [], [], []
                    constT, constQ, constG = [], [], []
                    for j in range(1, op_count + 1):
                        opcodes.append(int(extracted['opcodes'][j]))
                        operM.append(_safe_val(extracted['operM'][j]))
                        operL.append(_safe_val(extracted['operL'][j]))
                        operP.append(_safe_val(extracted['operP'][j]))
                        t_v = extracted['constT'][j]
                        constT.append(str(t_v) if t_v is not None else None)
                        constQ.append(_safe_val(extracted['constQ'][j]))
                        constG.append(_safe_val(extracted['constG'][j]))
                    proto['num_instructions'] = op_count
                    proto['opcodes'] = opcodes
                    proto['operM'] = operM
                    proto['operL'] = operL
                    proto['operP'] = operP
                    proto['constT'] = constT
                    proto['constQ'] = constQ
                    proto['constG'] = constG
                except Exception:
                    proto['num_instructions'] = 0
            all_protos.append(proto)

        return all_protos

    def get_intercepted_loads(self) -> List[str]:
        if not self._setup_done:
            return []
        try:
            count = self.lua.eval("#_G._intercepted")
            if not count or int(count) == 0:
                return []
            results = []
            for i in range(1, int(count) + 1):
                s = self.lua.eval(f"_G._intercepted[{i}]")
                results.append(str(s))
            return results
        except Exception:
            return []

    def reset(self):
        self.lua = None
        self._setup_done = False
