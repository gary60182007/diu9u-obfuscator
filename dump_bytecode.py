import sys, re, json, struct
sys.path.insert(0, '.')

exec(open('run_luraph_test.py').read().split("print('Reading source...')")[0])

print('Reading source...')
with open(r'unobfuscator\pending crack\bloxburg_script.lua', 'r', encoding='utf-8', errors='replace') as f:
    source = f.read()
print(f'Source length: {len(source):,}')

print('Preprocessing...')
source = preprocess_luau(source)
print(f'Preprocessed length: {len(source):,}')

from unobfuscator.utils.lua_runtime import LuaRuntimeWrapper, LuaRuntimeError

print('Initializing runtime...')
runtime = LuaRuntimeWrapper(op_limit=2_000_000_000, timeout=120.0)
runtime._init_runtime()

BUFFER_LIB_HOOKED = r"""
do
    local _pack = string.pack
    local _unpack = string.unpack
    local _byte = string.byte
    local _char = string.char
    local _concat = table.concat

    local buf_mt = {}
    buf_mt.__index = buf_mt

    _G._all_buffers = {}
    local _buf_id = 0

    local function _make_buf(size, data)
        local b = setmetatable({}, buf_mt)
        if data then
            b._data = {}
            for i = 1, #data do b._data[i] = _byte(data, i) end
            for i = #data + 1, size do b._data[i] = 0 end
        else
            b._data = {}
            for i = 1, size do b._data[i] = 0 end
        end
        b._size = size
        _buf_id = _buf_id + 1
        b._id = _buf_id
        table.insert(_G._all_buffers, b)
        return b
    end

    buffer = {}
    function buffer.create(size) return _make_buf(math.floor(size)) end
    function buffer.fromstring(s) return _make_buf(#s, s) end
    function buffer.tostring(b)
        local t = {}
        for i = 1, b._size do t[i] = _char(b._data[i]) end
        return _concat(t)
    end
    function buffer.len(b) return b._size end
    function buffer.readu8(b, offset) return b._data[offset + 1] or 0 end
    function buffer.readi8(b, offset)
        local v = b._data[offset + 1] or 0
        if v >= 128 then v = v - 256 end
        return v
    end
    function buffer.readu16(b, offset)
        local o = offset + 1
        return (b._data[o] or 0) + (b._data[o+1] or 0) * 256
    end
    function buffer.readi16(b, offset)
        local o = offset + 1
        local v = (b._data[o] or 0) + (b._data[o+1] or 0) * 256
        if v >= 32768 then v = v - 65536 end
        return v
    end
    function buffer.readu32(b, offset)
        local o = offset + 1
        return (b._data[o] or 0) + (b._data[o+1] or 0) * 256 + (b._data[o+2] or 0) * 65536 + (b._data[o+3] or 0) * 16777216
    end
    function buffer.readi32(b, offset)
        local o = offset + 1
        local v = (b._data[o] or 0) + (b._data[o+1] or 0) * 256 + (b._data[o+2] or 0) * 65536 + (b._data[o+3] or 0) * 16777216
        if v >= 2147483648 then v = v - 4294967296 end
        return v
    end
    function buffer.readf32(b, offset)
        local o = offset + 1
        local s = _char(b._data[o] or 0, b._data[o+1] or 0, b._data[o+2] or 0, b._data[o+3] or 0)
        return _unpack("<f", s)
    end
    function buffer.readf64(b, offset)
        local o = offset + 1
        local s = _char(b._data[o] or 0, b._data[o+1] or 0, b._data[o+2] or 0, b._data[o+3] or 0,
                        b._data[o+4] or 0, b._data[o+5] or 0, b._data[o+6] or 0, b._data[o+7] or 0)
        return _unpack("<d", s)
    end
    function buffer.writeu8(b, offset, value) b._data[offset + 1] = math.floor(value) % 256 end
    function buffer.writei8(b, offset, value)
        if value < 0 then value = value + 256 end
        b._data[offset + 1] = math.floor(value) % 256
    end
    function buffer.writeu16(b, offset, value)
        local o = offset + 1
        value = math.floor(value)
        b._data[o] = value % 256
        b._data[o+1] = math.floor(value / 256) % 256
    end
    function buffer.writeu32(b, offset, value)
        local o = offset + 1
        value = math.floor(value)
        b._data[o] = value % 256
        b._data[o+1] = math.floor(value / 256) % 256
        b._data[o+2] = math.floor(value / 65536) % 256
        b._data[o+3] = math.floor(value / 16777216) % 256
    end
    function buffer.writei32(b, offset, value)
        if value < 0 then value = value + 4294967296 end
        buffer.writeu32(b, offset, value)
    end
    function buffer.writef32(b, offset, value)
        local s = _pack("<f", value)
        local o = offset + 1
        for i = 1, 4 do b._data[o + i - 1] = _byte(s, i) end
    end
    function buffer.writef64(b, offset, value)
        local s = _pack("<d", value)
        local o = offset + 1
        for i = 1, 8 do b._data[o + i - 1] = _byte(s, i) end
    end
    function buffer.copy(dst, dstOffset, src, srcOffset, count)
        if type(src) == "string" then
            srcOffset = srcOffset or 0
            count = count or #src
            for i = 0, count - 1 do
                dst._data[dstOffset + 1 + i] = _byte(src, srcOffset + 1 + i) or 0
            end
        else
            srcOffset = srcOffset or 0
            count = count or src._size
            for i = 0, count - 1 do
                dst._data[dstOffset + 1 + i] = src._data[srcOffset + 1 + i] or 0
            end
        end
    end
    function buffer.fill(b, offset, value, count)
        count = count or (b._size - offset)
        value = math.floor(value) % 256
        for i = 0, count - 1 do b._data[offset + 1 + i] = value end
    end
    function buffer.readstring(b, offset, count)
        local t = {}
        for i = 0, count - 1 do t[#t+1] = _char(b._data[offset + 1 + i] or 0) end
        return _concat(t)
    end
    function buffer.writestring(b, offset, value, count)
        count = count or #value
        for i = 0, count - 1 do b._data[offset + 1 + i] = _byte(value, i + 1) or 0 end
    end
end
"""
runtime.lua.execute(BUFFER_LIB_HOOKED)

LUAU_COMPAT = r"""
function typeof(v)
    local t = type(v)
    if t == "table" then
        local mt = getmetatable(v)
        if mt and mt.__type then return mt.__type end
        if rawget(v, "__path") then return "Instance" end
        if rawget(v, "_data") and rawget(v, "_size") then return "buffer" end
    end
    return t
end
task = {
    spawn = function(f, ...) if type(f) == "function" then pcall(f, ...) end end,
    defer = function(f, ...) if type(f) == "function" then pcall(f, ...) end end,
    delay = function(t, f, ...) end,
    wait = function(t) return t or 0, 0 end,
    cancel = function() end,
}
function warn(...) end
function tick() return os.time() end
function time() return os.clock() end
function wait(t) return t or 0, 0 end
function spawn(f) if type(f) == "function" then pcall(f) end end
function delay(t, f) end
function unpack(t, i, j) return table.unpack(t, i, j) end
"""
runtime.lua.execute(LUAU_COMPAT)

MOCKS = r"""
local function make_mock(name)
    local mt = {}
    mt.__index = function(self, key)
        if key == "Name" or key == "ClassName" then return rawget(self,"__path") or name end
        if key == "UserId" then return 1 end
        if key == "Enabled" or key == "Visible" then return true end
        if key == "Value" then return 0 end
        if key == "Text" then return "" end
        return setmetatable({__path=(rawget(self,"__path") or name).."."..tostring(key)}, mt)
    end
    mt.__newindex = function() end
    mt.__call = function(self, ...)
        local path = rawget(self,"__path") or name
        local args = {...}
        if path:match("HttpGet$") then return tostring(os.time()) end
        if path:match("GetService$") then
            local s = args[2] or args[1]
            if type(s)=="string" then return setmetatable({__path=s},mt) end
        end
        if path:match("FindFirstChild$") or path:match("WaitForChild$") then
            local c = args[2] or args[1]
            if type(c)=="string" then return setmetatable({__path=path:gsub("%.[^.]+$","").."."..c},mt) end
        end
        if path:match("GetChildren$") or path:match("GetDescendants$") or path:match("GetPlayers$") then return {} end
        if path:match("Destroy$") or path:match("Remove$") then return end
        return setmetatable({__path=path.."()"},mt)
    end
    mt.__tostring = function(self) return rawget(self,"__path") or name end
    mt.__concat = function(a,b) return tostring(a)..tostring(b) end
    mt.__add = function() return 0 end
    mt.__sub = function() return 0 end
    mt.__mul = function() return 0 end
    mt.__div = function() return 0 end
    mt.__mod = function() return 0 end
    mt.__pow = function() return 0 end
    mt.__unm = function() return 0 end
    mt.__eq = function() return false end
    mt.__lt = function() return false end
    mt.__le = function() return false end
    mt.__len = function() return 0 end
    return setmetatable({__path=name},mt)
end
game = make_mock("game")
workspace = make_mock("workspace")
Instance = make_mock("Instance")
Enum = make_mock("Enum")
UDim2 = make_mock("UDim2")
Vector2 = make_mock("Vector2")
Vector3 = make_mock("Vector3")
CFrame = make_mock("CFrame")
Color3 = make_mock("Color3")
BrickColor = make_mock("BrickColor")
TweenInfo = make_mock("TweenInfo")
Ray = make_mock("Ray")
Region3 = make_mock("Region3")
NumberRange = make_mock("NumberRange")
Drawing = make_mock("Drawing")
syn = make_mock("syn")
islclosure = function(f) return type(f)=="function" end
newcclosure = function(f) return f end
iscclosure = function() return false end
hookfunction = function(old) return old end
hookmetamethod = function() return function() end end
getrawmetatable = getmetatable
setrawmetatable = setmetatable
checkcaller = function() return true end
isexecutorclosure = function(f) return type(f)=="function" end
cloneref = function(x) return x end
gethui = function() return make_mock("HiddenUI") end
getgenv = function() return _G end
getrenv = function() return _G end
getnamecallmethod = function() return "" end
setnamecallmethod = function() end
firesignal = function() end
fireproximityprompt = function() end
fireclickdetector = function() end
firetouchinterest = function() end
isnetworkowner = function() return true end
sethiddenproperty = function() end
gethiddenproperty = function() return nil end
request = function() return {StatusCode=200,Body="{}",Headers={}} end
http_request = request
setmetatable(_G, {
    __index = function(self, key)
        if type(key) == "string" then
            local m = make_mock(key)
            rawset(self, key, m)
            return m
        end
    end
})
"""
runtime.lua.execute(MOCKS)

ERROR_OVERRIDE = r"""
local _real_error = error
_G._error_log = {}
error = function(msg, level)
    if type(msg) == "string" and (msg:find("Luraph Script") or msg:find("table index") or msg:find("attempt to")) then
        if #_G._error_log < 20 then table.insert(_G._error_log, tostring(msg)) end
        return
    end
    _real_error(msg, level)
end
"""
runtime.lua.execute(ERROR_OVERRIDE)

source = "do local __ok, __err = pcall(function(...)\n" + source + "\nend, ...)\nif not __ok then table.insert(_G._error_log, 'PCALL: ' .. tostring(__err)) end\nend"

print('Executing...')
import time as _time
t0 = _time.time()
try:
    runtime.execute(source)
    print(f'Completed in {_time.time()-t0:.1f}s')
except LuaRuntimeError as e:
    print(f'Error after {_time.time()-t0:.1f}s: {str(e)[:300]}')
except Exception as e:
    print(f'{type(e).__name__} after {_time.time()-t0:.1f}s: {str(e)[:300]}')

print('\n=== BUFFER DUMP ===')
try:
    buf_count = runtime.lua.eval('#_G._all_buffers')
    print(f'Total buffers created: {buf_count}')
    
    for bi in range(1, int(buf_count) + 1):
        size = int(runtime.lua.eval(f'_G._all_buffers[{bi}]._size'))
        buf_id = int(runtime.lua.eval(f'_G._all_buffers[{bi}]._id'))
        
        nonzero = int(runtime.lua.eval(f"""
            local b = _G._all_buffers[{bi}]
            local count = 0
            for i = 1, b._size do
                if b._data[i] ~= 0 then count = count + 1 end
            end
            return count
        """))
        
        print(f'\n  Buffer #{buf_id}: size={size}, nonzero_bytes={nonzero}')
        
        if nonzero > 0 and size <= 10_000_000:
            fname = f'unobfuscator/cracked script/buffer_{buf_id}_{size}.bin'
            
            chunk_size = 4096
            data = bytearray()
            for offset in range(0, size, chunk_size):
                end_off = min(offset + chunk_size, size)
                chunk_lua = f"""
                    local b = _G._all_buffers[{bi}]
                    local t = {{}}
                    for i = {offset+1}, {end_off} do
                        t[#t+1] = string.char(b._data[i] or 0)
                    end
                    return table.concat(t)
                """
                chunk_data = runtime.lua.eval(chunk_lua)
                if isinstance(chunk_data, bytes):
                    data.extend(chunk_data)
                else:
                    data.extend(chunk_data.encode('latin-1'))
            
            with open(fname, 'wb') as f:
                f.write(data)
            print(f'    Saved to {fname}')
            
            print(f'    First 64 bytes (hex): {data[:64].hex()}')
            
            strings_found = []
            i = 0
            while i < len(data) - 3:
                if all(32 <= b < 127 for b in data[i:i+4]):
                    j = i
                    while j < len(data) and 32 <= data[j] < 127:
                        j += 1
                    if j - i >= 4:
                        strings_found.append((i, data[i:j].decode('ascii')))
                    i = j
                else:
                    i += 1
            
            print(f'    ASCII strings found: {len(strings_found)}')
            for offset, s in strings_found[:50]:
                if len(s) < 200:
                    print(f'      @{offset:6d}: {s}')

except Exception as e:
    import traceback
    traceback.print_exc()

print('\n=== ERROR LOG ===')
try:
    err_count = runtime.lua.eval('#_G._error_log')
    print(f'Errors: {err_count}')
    for i in range(1, min(int(err_count)+1, 10)):
        print(f'  [{i}] {runtime.lua.eval(f"_G._error_log[{i}]")}')
except:
    pass
