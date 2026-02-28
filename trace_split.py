import sys, re, time
sys.path.insert(0, '.')

with open(r'unobfuscator\pending crack\bloxburg_script.lua', 'r', encoding='utf-8', errors='replace') as f:
    source = f.read()

exec(open('run_luraph_test.py').read().split("print('Reading source...')")[0])
source = preprocess_luau(source)

lines = source.split('\n')
# The big code is on line 11 (index 10)
big_line = lines[10]

# Split the big line at semicolons to create multiple lines for better tracebacks
# But we need to be careful not to split inside strings
def split_at_semicolons(code):
    result = []
    current = []
    i = 0
    in_string = False
    string_delim = None
    
    while i < len(code):
        ch = code[i]
        
        if in_string:
            current.append(ch)
            if ch == '\\' and i + 1 < len(code):
                i += 1
                current.append(code[i])
            elif ch == string_delim:
                in_string = False
        elif ch in ('"', "'"):
            in_string = True
            string_delim = ch
            current.append(ch)
        elif ch == ';':
            current.append(ch)
            result.append(''.join(current))
            current = []
        else:
            current.append(ch)
        i += 1
    
    if current:
        result.append(''.join(current))
    return result

parts = split_at_semicolons(big_line)
print(f"Split into {len(parts)} parts")

# Replace line 11 with multiple lines
lines[10] = '\n'.join(parts)
new_source = '\n'.join(lines)
print(f"Original: {len(source)} chars, {source.count(chr(10))} lines")
print(f"New: {len(new_source)} chars, {new_source.count(chr(10))} lines")

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

    local buf_mt = {}
    buf_mt.__index = buf_mt
    buffer = {}
    function buffer.create(size) local b=setmetatable({},buf_mt); b._data={}; for i=1,_floor(size) do b._data[i]=0 end; b._size=_floor(size); return b end
    function buffer.fromstring(s) local b=setmetatable({},buf_mt); b._data={}; for i=1,#s do b._data[i]=_byte(s,i) end; b._size=#s; return b end
    function buffer.tostring(b) local t={}; for i=1,b._size do t[i]=_char(b._data[i]) end; return _concat(t) end
    function buffer.len(b) return b._size end
    function buffer.readu8(b,o) return b._data[o+1] or 0 end
    function buffer.readi8(b,o) local v=b._data[o+1] or 0; if v>=128 then v=v-256 end; return v end
    function buffer.readu16(b,o) return (b._data[o+1] or 0)+(b._data[o+2] or 0)*256 end
    function buffer.readi16(b,o) local v=(b._data[o+1] or 0)+(b._data[o+2] or 0)*256; if v>=32768 then v=v-65536 end; return v end
    function buffer.readu32(b,o) return (b._data[o+1] or 0)+(b._data[o+2] or 0)*256+(b._data[o+3] or 0)*65536+(b._data[o+4] or 0)*16777216 end
    function buffer.readi32(b,o) local v=(b._data[o+1] or 0)+(b._data[o+2] or 0)*256+(b._data[o+3] or 0)*65536+(b._data[o+4] or 0)*16777216; if v>=2147483648 then v=v-4294967296 end; return v end
    function buffer.readf32(b,o) local s=_char(b._data[o+1] or 0,b._data[o+2] or 0,b._data[o+3] or 0,b._data[o+4] or 0); return _unpack("<f",s) end
    function buffer.readf64(b,o) local s=_char(b._data[o+1] or 0,b._data[o+2] or 0,b._data[o+3] or 0,b._data[o+4] or 0,b._data[o+5] or 0,b._data[o+6] or 0,b._data[o+7] or 0,b._data[o+8] or 0); return _unpack("<d",s) end
    function buffer.writeu8(b,o,v) b._data[o+1]=_floor(v)%256 end
    function buffer.writeu16(b,o,v) v=_floor(v); b._data[o+1]=v%256; b._data[o+2]=_floor(v/256)%256 end
    function buffer.writeu32(b,o,v) v=_floor(v); b._data[o+1]=v%256; b._data[o+2]=_floor(v/256)%256; b._data[o+3]=_floor(v/65536)%256; b._data[o+4]=_floor(v/16777216)%256 end
    function buffer.writei32(b,o,v) if v<0 then v=v+4294967296 end; buffer.writeu32(b,o,v) end
    function buffer.writef32(b,o,v) local s=_pack("<f",v); for i=1,4 do b._data[o+i]=_byte(s,i) end end
    function buffer.writef64(b,o,v) local s=_pack("<d",v); for i=1,8 do b._data[o+i]=_byte(s,i) end end
    function buffer.copy(dst,dO,src,sO,c) if type(src)=="string" then sO=sO or 0; c=c or #src; for i=0,c-1 do dst._data[dO+1+i]=_byte(src,sO+1+i) or 0 end else sO=sO or 0; c=c or src._size; for i=0,c-1 do dst._data[dO+1+i]=src._data[sO+1+i] or 0 end end end
    function buffer.fill(b,o,v,c) c=c or(b._size-o); v=_floor(v)%256; for i=0,c-1 do b._data[o+1+i]=v end end
    function buffer.readstring(b,o,c) local t={}; for i=0,c-1 do t[#t+1]=_char(b._data[o+1+i] or 0) end; return _concat(t) end
    function buffer.writestring(b,o,v,c) c=c or #v; for i=0,c-1 do b._data[o+1+i]=_byte(v,i+1) or 0 end end

    function typeof(v) local t=type(v); if t=="table" then if rawget(v,"_data") and rawget(v,"_size") then return "buffer" end; if rawget(v,"__path") then return "Instance" end end; return t end
    task={spawn=function(f,...) if type(f)=="function" then pcall(f,...) end end, defer=function(f,...) if type(f)=="function" then pcall(f,...) end end, delay=function() end, wait=function(t) return t or 0,0 end, cancel=function() end}
    function warn(...) end; function tick() return os.time() end; function time() return os.clock() end
    function wait(t) return t or 0,0 end; function spawn(f) if type(f)=="function" then pcall(f) end end
    function delay(t,f) end; function unpack(t,i,j) return table.unpack(t,i,j) end

    local function make_mock(name) local mt={}; mt.__index=function(self,key) if key=="Name" or key=="ClassName" then return rawget(self,"__path") or name end; if key=="UserId" then return 1 end; return setmetatable({__path=(rawget(self,"__path") or name).."."..tostring(key)},mt) end; mt.__newindex=function() end; mt.__call=function(self,...) local path=rawget(self,"__path") or name; local args={...}; if path:match("HttpGet$") then return tostring(os.time()) end; if path:match("GetService$") then local s=args[2] or args[1]; if type(s)=="string" then return setmetatable({__path=s},mt) end end; if path:match("GetChildren$") or path:match("GetPlayers$") then return {} end; return setmetatable({__path=path.."()"},mt) end; mt.__tostring=function(self) return rawget(self,"__path") or name end; mt.__concat=function(a,b) return tostring(a)..tostring(b) end; mt.__add=function() return 0 end; mt.__sub=function() return 0 end; mt.__mul=function() return 0 end; mt.__div=function() return 0 end; mt.__mod=function() return 0 end; mt.__pow=function() return 0 end; mt.__unm=function() return 0 end; mt.__eq=function() return false end; mt.__lt=function() return false end; mt.__le=function() return false end; mt.__len=function() return 0 end; return setmetatable({__path=name},mt) end
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

    _G._error_traces = {}
    local _err_count = 0
    local _real_error = error
    error = function(msg, level)
        _err_count = _err_count + 1
        if _err_count <= 3 then
            local tb = debug.traceback(tostring(msg), (level or 1) + 1)
            table.insert(_G._error_traces, tb)
        end
        if type(msg) == "string" and (msg:find("Luraph Script") or msg:find("table index") or msg:find("attempt to")) then
            return
        end
        _real_error(msg, level)
    end
    setmetatable(_G, {__index=function(self,key) if type(key)=="string" then local m=make_mock(key); rawset(self,key,m); return m end end})
end
"""
runtime.lua.execute(SETUP)

new_source = "do local __ok,__err=pcall(function(...)\n" + new_source + "\nend,...)\nif not __ok then table.insert(_G._error_traces,'PCALL:'..tostring(__err)..'\\n'..debug.traceback('',2)) end\nend"

print('Executing with split source...')
t0 = time.time()
try:
    runtime.execute(new_source)
    print(f'Completed in {time.time()-t0:.1f}s')
except LuaRuntimeError as e:
    print(f'Error after {time.time()-t0:.1f}s: {str(e)[:200]}')

print('\n=== ERROR TRACES ===')
traces = runtime.lua.globals()['_error_traces']
for k in traces.keys():
    trace_str = str(traces[k])
    print(trace_str[:800])
    print()

# Now map line numbers back to code
print('\n=== LINE MAPPING ===')
split_lines = new_source.split('\n')
# Extract line numbers from traces
import re as _re
for k in traces.keys():
    trace_str = str(traces[k])
    line_nums = set(_re.findall(r'\]:(\d+):', trace_str))
    for ln_str in sorted(line_nums, key=int):
        ln = int(ln_str)
        if 10 <= ln <= len(split_lines) and ln > 11:
            # Offset by 1 for the pcall wrapper
            actual_ln = ln - 1  # account for pcall wrapper
            if actual_ln < len(parts) + 11:
                part_idx = actual_ln - 11
                if 0 <= part_idx < len(parts):
                    code = parts[part_idx].strip()
                    if len(code) > 200:
                        code = code[:200] + '...'
                    print(f"  Line {ln} → part[{part_idx}]: {code}")
    break  # Only first trace
