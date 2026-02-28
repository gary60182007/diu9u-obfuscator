import sys, re, json, struct
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
    local _concat = table.concat
    local _floor = math.floor
    local _format = string.format

    _G._read_log = {}
    local _log_count = 0
    local function _log_read(op, buf_id, offset, count, result_hex)
        if _log_count < 50000 then
            _log_count = _log_count + 1
            _G._read_log[_log_count] = op.."|"..tostring(offset).."|"..tostring(count).."|"..result_hex
        end
    end

    local buf_id_counter = 0
    local buf_mt = {}
    buf_mt.__index = buf_mt
    local function _make_buf(size, data)
        local b = setmetatable({}, buf_mt)
        b._data = {}
        buf_id_counter = buf_id_counter + 1
        b._id = buf_id_counter
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
    function buffer.create(size)
        local b = _make_buf(_floor(size))
        _log_read("CREATE", b._id, 0, b._size, "")
        return b
    end
    function buffer.fromstring(s)
        local b = _make_buf(#s, s)
        _log_read("FROM", b._id, 0, b._size, "")
        return b
    end
    function buffer.tostring(b) local t={}; for i=1,b._size do t[i]=_char(b._data[i]) end; return _concat(t) end
    function buffer.len(b) return b._size end
    function buffer.readu8(b, o)
        local v = b._data[o+1] or 0
        _log_read("u8", b._id, o, 1, _format("%02x",v))
        return v
    end
    function buffer.readi8(b, o) local v=b._data[o+1] or 0; if v>=128 then v=v-256 end; _log_read("i8",b._id,o,1,_format("%02x",v&0xFF)); return v end
    function buffer.readu16(b, o)
        local v = (b._data[o+1] or 0)+(b._data[o+2] or 0)*256
        _log_read("u16", b._id, o, 2, _format("%04x",v))
        return v
    end
    function buffer.readi16(b, o) local v=(b._data[o+1] or 0)+(b._data[o+2] or 0)*256; if v>=32768 then v=v-65536 end; _log_read("i16",b._id,o,2,_format("%04x",v&0xFFFF)); return v end
    function buffer.readu32(b, o)
        local v = (b._data[o+1] or 0)+(b._data[o+2] or 0)*256+(b._data[o+3] or 0)*65536+(b._data[o+4] or 0)*16777216
        _log_read("u32", b._id, o, 4, _format("%08x",v))
        return v
    end
    function buffer.readi32(b, o) local v=(b._data[o+1] or 0)+(b._data[o+2] or 0)*256+(b._data[o+3] or 0)*65536+(b._data[o+4] or 0)*16777216; if v>=2147483648 then v=v-4294967296 end; _log_read("i32",b._id,o,4,_format("%08x",v&0xFFFFFFFF)); return v end
    function buffer.readf32(b, o) local s=_char(b._data[o+1] or 0,b._data[o+2] or 0,b._data[o+3] or 0,b._data[o+4] or 0); local v=_unpack("<f",s); _log_read("f32",b._id,o,4,""); return v end
    function buffer.readf64(b, o) local s=_char(b._data[o+1] or 0,b._data[o+2] or 0,b._data[o+3] or 0,b._data[o+4] or 0,b._data[o+5] or 0,b._data[o+6] or 0,b._data[o+7] or 0,b._data[o+8] or 0); local v=_unpack("<d",s); _log_read("f64",b._id,o,8,""); return v end
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
    function buffer.readstring(b, o, c)
        local t={}; for i=0,c-1 do t[#t+1]=_char(b._data[o+1+i] or 0) end
        local result = _concat(t)
        local hex = {}
        for i = 1, math.min(c, 100) do hex[i] = _format("%02x", _byte(result, i) or 0) end
        _log_read("str", b._id, o, c, _concat(hex))
        return result
    end
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

    local _real_error=error; _G._error_log={}; local _err_count=0
    error=function(msg,level)
        if type(msg)=="string" and (msg:find("Luraph Script") or msg:find("table index") or msg:find("attempt to")) then
            _err_count=_err_count+1
            if _err_count<=5 then table.insert(_G._error_log,tostring(msg)) end
            return
        end
        _real_error(msg,level)
    end
end
"""
runtime.lua.execute(SETUP)

source = "do local __ok,__err=pcall(function(...)\n" + source + "\nend,...)\nif not __ok then table.insert(_G._error_log,'PCALL:'..tostring(__err)) end\nend"

print('Executing with full buffer read logging...')
import time as _time
t0 = _time.time()
try:
    runtime.execute(source)
    print(f'Completed in {_time.time()-t0:.1f}s')
except LuaRuntimeError as e:
    print(f'Error after {_time.time()-t0:.1f}s: {str(e)[:200]}')

log = runtime.lua.globals()['_read_log']
log_count = 0
reads = []
for k in log.keys():
    log_count += 1
    entry = str(log[k])
    parts = entry.split('|')
    if len(parts) >= 4:
        op = parts[0]
        offset = int(parts[1])
        count = int(parts[2])
        hex_data = parts[3]
        reads.append({'op': op, 'offset': offset, 'count': count, 'hex': hex_data})

print(f'Total read operations: {log_count}')

with open('all_reads_log.txt', 'w', encoding='utf-8') as out:
    out.write(f'Total read operations: {log_count}\n\n')
    for i, r in enumerate(reads):
        if r['op'] in ('CREATE', 'FROM'):
            out.write(f"[{i:5d}] {r['op']:6s} size={r['count']}\n")
        elif r['op'] == 'str':
            data = bytes.fromhex(r['hex']) if r['hex'] else b''
            printable = sum(1 for b in data if 32 <= b < 127)
            if len(data) > 0 and printable >= len(data) * 0.6:
                text = data.decode('ascii', errors='replace')
                out.write(f"[{i:5d}] {r['op']:6s} @{r['offset']:8d} len={r['count']:5d} TEXT: {text[:100]}\n")
            else:
                out.write(f"[{i:5d}] {r['op']:6s} @{r['offset']:8d} len={r['count']:5d} HEX:  {r['hex'][:80]}\n")
        else:
            val = int(r['hex'], 16) if r['hex'] else 0
            if r['op'] in ('i32', 'i16', 'i8'):
                bits = {'i32': 32, 'i16': 16, 'i8': 8}[r['op']]
                if val >= 2**(bits-1): val -= 2**bits
            out.write(f"[{i:5d}] {r['op']:6s} @{r['offset']:8d} = {val}\n")

print(f'Written {log_count} reads to all_reads_log.txt')

# Print first 100 and last 50 entries
print('\n=== FIRST 100 READS ===')
for i, r in enumerate(reads[:100]):
    if r['op'] in ('CREATE', 'FROM'):
        print(f"  [{i:4d}] {r['op']:6s} size={r['count']}")
    elif r['op'] == 'str':
        data = bytes.fromhex(r['hex']) if r['hex'] else b''
        printable = sum(1 for b in data if 32 <= b < 127)
        if len(data) > 0 and printable >= len(data) * 0.6:
            text = data.decode('ascii', errors='replace')
            print(f"  [{i:4d}] {r['op']:6s} @{r['offset']:8d} len={r['count']:5d} TEXT: {text[:80]}")
        else:
            print(f"  [{i:4d}] {r['op']:6s} @{r['offset']:8d} len={r['count']:5d} HEX:  {r['hex'][:60]}")
    else:
        val = int(r['hex'], 16) if r['hex'] else 0
        if r['op'] in ('i32', 'i16', 'i8'):
            bits = {'i32': 32, 'i16': 16, 'i8': 8}[r['op']]
            if val >= 2**(bits-1): val -= 2**bits
        print(f"  [{i:4d}] {r['op']:6s} @{r['offset']:8d} = {val}")

# Op type summary
from collections import Counter
op_counts = Counter(r['op'] for r in reads)
print(f'\n=== OPERATION TYPE COUNTS ===')
for op, cnt in op_counts.most_common():
    print(f'  {op:6s}: {cnt}')

# Max offset reached
max_offset = max(r['offset'] for r in reads if r['op'] not in ('CREATE', 'FROM'))
print(f'\nMax buffer offset read: {max_offset}')
print(f'Buffer size: 1,064,652')
print(f'Coverage: {max_offset/1064652*100:.1f}%')

# Show errors
print('\n=== ERRORS ===')
error_log = runtime.lua.globals()['_error_log']
for k in error_log.keys():
    try: print(f'  {error_log[k]}')
    except: print('  <decode error>')
