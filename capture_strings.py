import sys, re, json
sys.path.insert(0, '.')

exec(open('run_luraph_test.py').read().split("print('Reading source...')")[0])

with open(r'unobfuscator\pending crack\bloxburg_script.lua', 'r', encoding='utf-8', errors='replace') as f:
    source = f.read()
source = preprocess_luau(source)

from unobfuscator.utils.lua_runtime import LuaRuntimeWrapper, LuaRuntimeError

runtime = LuaRuntimeWrapper(op_limit=2_000_000_000, timeout=120.0)
runtime._init_runtime()

SETUP = r"""
do
    local _pack = string.pack
    local _unpack = string.unpack
    local _byte = string.byte
    local _char = string.char
    local _rep = string.rep
    local _sub = string.sub
    local _concat = table.concat
    local _floor = math.floor

    _G._captured_strings = {}
    _G._concat_log = {}
    local _cap_count = 0
    local _concat_count = 0

    local _orig_char = string.char
    local _orig_concat = table.concat
    local _orig_sub = string.sub
    local _orig_gsub = string.gsub
    local _orig_rep = string.rep

    string.char = function(...)
        local result = _orig_char(...)
        if #result >= 3 and _cap_count < 5000 then
            local dominated_by_printable = true
            local printable = 0
            for i = 1, math.min(#result, 20) do
                local b = _byte(result, i)
                if b >= 32 and b < 127 then printable = printable + 1 end
            end
            if printable >= math.min(#result, 20) * 0.6 then
                _cap_count = _cap_count + 1
                _G._captured_strings[_cap_count] = result
            end
        end
        return result
    end

    table.concat = function(t, sep)
        local result = _orig_concat(t, sep)
        if #result >= 4 and _concat_count < 5000 then
            local printable = 0
            for i = 1, math.min(#result, 20) do
                local b = _byte(result, i)
                if b >= 32 and b < 127 then printable = printable + 1 end
            end
            if printable >= math.min(#result, 20) * 0.6 then
                _concat_count = _concat_count + 1
                _G._concat_log[_concat_count] = result
            end
        end
        return result
    end

    local buf_mt = {}
    buf_mt.__index = buf_mt
    local function _make_buf(size, data)
        local b = setmetatable({}, buf_mt)
        b._data = {}
        if data then
            for i = 1, #data do b._data[i] = _byte(data, i) end
            for i = #data + 1, size do b._data[i] = 0 end
        else
            for i = 1, size do b._data[i] = 0 end
        end
        b._size = size
        return b
    end
    buffer = {}
    function buffer.create(size) return _make_buf(_floor(size)) end
    function buffer.fromstring(s) return _make_buf(#s, s) end
    function buffer.tostring(b) local t={}; for i=1,b._size do t[i]=_char(b._data[i]) end; return _orig_concat(t) end
    function buffer.len(b) return b._size end
    function buffer.readu8(b, o) return b._data[o+1] or 0 end
    function buffer.readi8(b, o) local v=b._data[o+1] or 0; if v>=128 then v=v-256 end; return v end
    function buffer.readu16(b, o) return (b._data[o+1] or 0)+(b._data[o+2] or 0)*256 end
    function buffer.readi16(b, o) local v=(b._data[o+1] or 0)+(b._data[o+2] or 0)*256; if v>=32768 then v=v-65536 end; return v end
    function buffer.readu32(b, o) return (b._data[o+1] or 0)+(b._data[o+2] or 0)*256+(b._data[o+3] or 0)*65536+(b._data[o+4] or 0)*16777216 end
    function buffer.readi32(b, o) local v=(b._data[o+1] or 0)+(b._data[o+2] or 0)*256+(b._data[o+3] or 0)*65536+(b._data[o+4] or 0)*16777216; if v>=2147483648 then v=v-4294967296 end; return v end
    function buffer.readf32(b, o) return _unpack("<f", _char(b._data[o+1] or 0,b._data[o+2] or 0,b._data[o+3] or 0,b._data[o+4] or 0)) end
    function buffer.readf64(b, o) return _unpack("<d", _char(b._data[o+1] or 0,b._data[o+2] or 0,b._data[o+3] or 0,b._data[o+4] or 0,b._data[o+5] or 0,b._data[o+6] or 0,b._data[o+7] or 0,b._data[o+8] or 0)) end
    function buffer.writeu8(b, o, v) b._data[o+1]=_floor(v)%256 end
    function buffer.writeu16(b, o, v) v=_floor(v); b._data[o+1]=v%256; b._data[o+2]=_floor(v/256)%256 end
    function buffer.writeu32(b, o, v) v=_floor(v); b._data[o+1]=v%256; b._data[o+2]=_floor(v/256)%256; b._data[o+3]=_floor(v/65536)%256; b._data[o+4]=_floor(v/16777216)%256 end
    function buffer.writei32(b, o, v) if v<0 then v=v+4294967296 end; buffer.writeu32(b,o,v) end
    function buffer.writef32(b, o, v) local s=_pack("<f",v); for i=1,4 do b._data[o+i]=_byte(s,i) end end
    function buffer.writef64(b, o, v) local s=_pack("<d",v); for i=1,8 do b._data[o+i]=_byte(s,i) end end
    function buffer.copy(dst, dO, src, sO, c)
        if type(src)=="string" then sO=sO or 0; c=c or #src; for i=0,c-1 do dst._data[dO+1+i]=_byte(src,sO+1+i) or 0 end
        else sO=sO or 0; c=c or src._size; for i=0,c-1 do dst._data[dO+1+i]=src._data[sO+1+i] or 0 end end
    end
    function buffer.fill(b, o, v, c) c=c or(b._size-o); v=_floor(v)%256; for i=0,c-1 do b._data[o+1+i]=v end end
    function buffer.readstring(b, o, c) local t={}; for i=0,c-1 do t[#t+1]=_char(b._data[o+1+i] or 0) end; return _orig_concat(t) end
    function buffer.writestring(b, o, v, c) c=c or #v; for i=0,c-1 do b._data[o+1+i]=_byte(v,i+1) or 0 end end

    function typeof(v)
        local t = type(v)
        if t=="table" then
            if rawget(v,"_data") and rawget(v,"_size") then return "buffer" end
            if rawget(v,"__path") then return "Instance" end
        end
        return t
    end
    task={spawn=function(f,...) if type(f)=="function" then pcall(f,...) end end, defer=function(f,...) if type(f)=="function" then pcall(f,...) end end, delay=function() end, wait=function(t) return t or 0,0 end, cancel=function() end}
    function warn(...) end
    function tick() return os.time() end
    function time() return os.clock() end
    function wait(t) return t or 0,0 end
    function spawn(f) if type(f)=="function" then pcall(f) end end
    function delay(t,f) end
    function unpack(t,i,j) return table.unpack(t,i,j) end

    local function make_mock(name)
        local mt={}
        mt.__index=function(self,key) if key=="Name" or key=="ClassName" then return rawget(self,"__path") or name end; if key=="UserId" then return 1 end; return setmetatable({__path=(rawget(self,"__path") or name).."."..tostring(key)},mt) end
        mt.__newindex=function() end
        mt.__call=function(self,...) local path=rawget(self,"__path") or name; local args={...}; if path:match("HttpGet$") then return tostring(os.time()) end; if path:match("GetService$") then local s=args[2] or args[1]; if type(s)=="string" then return setmetatable({__path=s},mt) end end; if path:match("GetChildren$") or path:match("GetPlayers$") then return {} end; return setmetatable({__path=path.."()"},mt) end
        mt.__tostring=function(self) return rawget(self,"__path") or name end
        mt.__concat=function(a,b) return tostring(a)..tostring(b) end
        mt.__add=function() return 0 end; mt.__sub=function() return 0 end; mt.__mul=function() return 0 end
        mt.__div=function() return 0 end; mt.__mod=function() return 0 end; mt.__pow=function() return 0 end
        mt.__unm=function() return 0 end; mt.__eq=function() return false end
        mt.__lt=function() return false end; mt.__le=function() return false end; mt.__len=function() return 0 end
        return setmetatable({__path=name},mt)
    end
    game=make_mock("game"); workspace=make_mock("workspace"); Instance=make_mock("Instance"); Enum=make_mock("Enum")
    UDim2=make_mock("UDim2"); Vector2=make_mock("Vector2"); Vector3=make_mock("Vector3"); CFrame=make_mock("CFrame")
    Color3=make_mock("Color3"); Drawing=make_mock("Drawing"); syn=make_mock("syn")
    islclosure=function(f) return type(f)=="function" end; newcclosure=function(f) return f end
    iscclosure=function() return false end; hookfunction=function(old) return old end
    hookmetamethod=function() return function() end end; getrawmetatable=getmetatable; setrawmetatable=setmetatable
    checkcaller=function() return true end; cloneref=function(x) return x end
    gethui=function() return make_mock("HiddenUI") end; getgenv=function() return _G end; getrenv=function() return _G end
    getnamecallmethod=function() return "" end; setnamecallmethod=function() end
    firesignal=function() end; isnetworkowner=function() return true end
    sethiddenproperty=function() end; gethiddenproperty=function() return nil end
    request=function() return {StatusCode=200,Body="{}",Headers={}} end; http_request=request
    isexecutorclosure=function(f) return type(f)=="function" end
    setmetatable(_G, {__index=function(self,key) if type(key)=="string" then local m=make_mock(key); rawset(self,key,m); return m end end})

    local _real_error=error; _G._error_log={}
    error=function(msg,level) if type(msg)=="string" and (msg:find("Luraph Script") or msg:find("table index") or msg:find("attempt to")) then if #_G._error_log<20 then table.insert(_G._error_log,tostring(msg)) end; return end; _real_error(msg,level) end
end
"""
runtime.lua.execute(SETUP)

source = "do local __ok,__err=pcall(function(...)\n" + source + "\nend,...)\nif not __ok then table.insert(_G._error_log,'PCALL:'..tostring(__err)) end\nend"

print('Executing with string hooks...')
import time as _time
t0 = _time.time()
try:
    runtime.execute(source)
    print(f'Completed in {_time.time()-t0:.1f}s')
except LuaRuntimeError as e:
    print(f'Error after {_time.time()-t0:.1f}s: {str(e)[:300]}')

print('\n=== CAPTURED STRINGS (string.char) ===')
cap = runtime.lua.globals()['_captured_strings']
cap_count = 0
all_strings = []
for k in cap.keys():
    cap_count += 1
    s = str(cap[k])
    all_strings.append(s)
print(f'Total: {cap_count}')
for i, s in enumerate(all_strings[:200]):
    if len(s) < 500:
        print(f'  [{i+1}] ({len(s):4d}) {repr(s)[:200]}')

print('\n=== CAPTURED STRINGS (table.concat) ===')
conc = runtime.lua.globals()['_concat_log']
conc_count = 0
concat_strings = []
for k in conc.keys():
    conc_count += 1
    s = str(conc[k])
    concat_strings.append(s)
print(f'Total: {conc_count}')
for i, s in enumerate(concat_strings[:200]):
    if len(s) < 500:
        print(f'  [{i+1}] ({len(s):4d}) {repr(s)[:200]}')

interesting = [s for s in all_strings + concat_strings 
               if any(kw in s.lower() for kw in ['game', 'player', 'service', 'remote', 'event', 
                                                   'gui', 'frame', 'button', 'label', 'text',
                                                   'plot', 'build', 'place', 'furniture', 'room',
                                                   'money', 'cash', 'speed', 'fly', 'noclip',
                                                   'http', 'api', 'key', 'discord', 'webhook',
                                                   'bloxburg', 'exploit', 'hack', 'cheat',
                                                   'function', 'module', 'script', 'require'])]
if interesting:
    print(f'\n=== INTERESTING STRINGS ({len(interesting)}) ===')
    for s in interesting[:100]:
        print(f'  {repr(s)[:200]}')

with open(r'unobfuscator/cracked script/captured_strings.json', 'w', encoding='utf-8') as f:
    json.dump({
        'char_strings': all_strings,
        'concat_strings': concat_strings,
        'interesting': interesting,
    }, f, indent=2, ensure_ascii=False)
print('\nSaved to captured_strings.json')
