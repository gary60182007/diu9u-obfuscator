import sys
import re
sys.path.insert(0, '.')
from unobfuscator.utils.lua_runtime import LuaRuntimeWrapper, LuaRuntimeError

KEYWORDS = {'and','break','do','else','elseif','end','false','for','function',
            'goto','if','in','local','nil','not','or','repeat','return','then',
            'true','until','while'}
LOOP_STARTS = {'while', 'for', 'repeat'}
COMPOUND_OPS = {'+=': '+', '-=': '-', '*=': '*', '/=': '/', '%=': '%',
                '^=': '^', '..=': '..'}

def preprocess_luau(source: str) -> str:
    tokens = tokenize_luau(source)
    tokens = convert_numeric_literals(tokens)
    tokens = convert_string_escapes(tokens)
    tokens = convert_compound_assignments(tokens)
    tokens = convert_continue(tokens)
    tokens = convert_generalized_for(tokens)
    return ''.join(t[1] for t in tokens)

def tokenize_luau(source):
    tokens = []
    i = 0
    n = len(source)
    while i < n:
        c = source[i]
        if c in ' \t\r\n':
            j = i
            while j < n and source[j] in ' \t\r\n':
                j += 1
            tokens.append(('ws', source[i:j]))
            i = j
            continue
        if c == '-' and i+1 < n and source[i+1] == '-':
            end = source.find('\n', i)
            if end == -1: end = n
            tokens.append(('comment', source[i:end]))
            i = end
            continue
        if c in ('"', "'"):
            j = i + 1
            while j < n and source[j] != c:
                if source[j] == '\\': j += 1
                j += 1
            j = min(j + 1, n)
            tokens.append(('string', source[i:j]))
            i = j
            continue
        if c == '[' and i+1 < n and source[i+1] in '[=':
            level = 0
            j = i + 1
            while j < n and source[j] == '=': level += 1; j += 1
            if j < n and source[j] == '[':
                close = ']' + '=' * level + ']'
                end = source.find(close, j+1)
                if end != -1:
                    tokens.append(('string', source[i:end+len(close)]))
                    i = end + len(close)
                    continue
            tokens.append(('punct', c))
            i += 1
            continue
        if c == '0' and i+1 < n and source[i+1] in 'bB':
            j = i + 2
            while j < n and source[j] in '01_': j += 1
            tokens.append(('binnum', source[i:j]))
            i = j
            continue
        if c == '0' and i+1 < n and source[i+1] in 'xX':
            j = i + 2
            while j < n and source[j] in '0123456789abcdefABCDEF_': j += 1
            tokens.append(('hexnum', source[i:j]))
            i = j
            continue
        if c.isdigit():
            j = i
            while j < n and (source[j].isdigit() or source[j] == '_'): j += 1
            if j < n and source[j] == '.':
                j += 1
                while j < n and (source[j].isdigit() or source[j] == '_'): j += 1
            if j < n and source[j] in 'eE':
                j += 1
                if j < n and source[j] in '+-': j += 1
                while j < n and source[j].isdigit(): j += 1
            tokens.append(('decnum', source[i:j]))
            i = j
            continue
        if c.isalpha() or c == '_':
            j = i
            while j < n and (source[j].isalnum() or source[j] == '_'): j += 1
            word = source[i:j]
            tokens.append(('kw' if word in KEYWORDS or word == 'continue' else 'ident', word))
            i = j
            continue
        if c == '.' and i+1 < n and source[i+1] == '.' and i+2 < n and source[i+2] == '=':
            tokens.append(('compound', '..='))
            i += 3
            continue
        if c == '.' and i+1 < n and source[i+1] == '.':
            tokens.append(('op', '..'))
            i += 2
            continue
        if c in '+-*/%^' and i+1 < n and source[i+1] == '=':
            tokens.append(('compound', c + '='))
            i += 2
            continue
        if c in '~<>=' and i+1 < n and source[i+1] == '=':
            tokens.append(('op', c + '='))
            i += 2
            continue
        tokens.append(('punct', c))
        i += 1
    return tokens

def convert_numeric_literals(tokens):
    result = []
    for typ, val in tokens:
        if typ == 'binnum':
            clean = val.replace('_', '')
            try: result.append(('decnum', str(int(clean, 2))))
            except: result.append(('decnum', val))
        elif typ == 'hexnum':
            if '_' in val:
                clean = val.replace('_', '')
                try: result.append(('decnum', str(int(clean, 16))))
                except: result.append(('hexnum', val))
            else:
                result.append((typ, val))
        elif typ == 'decnum' and '_' in val:
            result.append(('decnum', val.replace('_', '')))
        else:
            result.append((typ, val))
    return result

VALID_ESCAPES = set('abfnrtv\\\'"xz0123456789')

def convert_string_escapes(tokens):
    result = []
    for typ, val in tokens:
        if typ != 'string' or '\\' not in val:
            result.append((typ, val))
            continue
        quote = val[0]
        if quote not in ('"', "'"):
            result.append((typ, val))
            continue
        new_val = [quote]
        i = 1
        end_i = len(val) - 1
        while i < end_i:
            if val[i] == '\\' and i + 1 < end_i:
                nc = val[i+1]
                if nc == 'u' and i+2 < end_i and val[i+2] == '{':
                    end_b = val.find('}', i+3)
                    if end_b != -1 and end_b < end_i:
                        hx = val[i+3:end_b]
                        try:
                            cp = int(hx, 16)
                            if cp < 128:
                                new_val.append('\\' + str(cp))
                            else:
                                utf8 = chr(cp).encode('utf-8')
                                for b in utf8:
                                    new_val.append('\\' + str(b))
                        except:
                            new_val.append(val[i:end_b+1])
                        i = end_b + 1
                        continue
                if nc in VALID_ESCAPES or nc == '\n':
                    new_val.append('\\')
                    new_val.append(nc)
                    i += 2
                else:
                    new_val.append(nc)
                    i += 2
                continue
            new_val.append(val[i])
            i += 1
        if i <= len(val) - 1:
            new_val.append(val[-1])
        result.append((typ, ''.join(new_val)))
    return result

def convert_compound_assignments(tokens):
    result = []
    i = 0
    while i < len(tokens):
        if tokens[i][0] == 'compound' and tokens[i][1] in COMPOUND_OPS:
            op = COMPOUND_OPS[tokens[i][1]]
            lhs_parts = []
            j = len(result) - 1
            while j >= 0 and result[j][0] == 'ws':
                j -= 1
            paren_depth = 0
            bracket_depth = 0
            while j >= 0:
                t = result[j]
                if t[1] == ')': paren_depth += 1
                elif t[1] == '(': paren_depth -= 1
                elif t[1] == ']': bracket_depth += 1
                elif t[1] == '[': bracket_depth -= 1
                if paren_depth <= 0 and bracket_depth <= 0:
                    if t[0] in ('ident', 'kw'):
                        lhs_parts.insert(0, t)
                        j2 = j - 1
                        while j2 >= 0 and result[j2][0] == 'ws': j2 -= 1
                        if j2 >= 0 and result[j2][1] in ('.', ':'):
                            lhs_parts.insert(0, result[j2])
                            j = j2 - 1
                            while j >= 0 and result[j][0] == 'ws': j -= 1
                            continue
                        break
                    elif t[1] == ']':
                        lhs_parts.insert(0, t)
                        j -= 1
                        continue
                    else:
                        break
                lhs_parts.insert(0, t)
                j -= 1
            lhs_text = ''.join(t[1] for t in lhs_parts)
            result.append(('op', '=' + lhs_text + op))
            i += 1
        else:
            result.append(tokens[i])
            i += 1
    return result

def convert_continue(tokens):
    loop_stack = []
    label_counter = [0]
    result_with_markers = []
    block_stack = []

    for i, (typ, val) in enumerate(tokens):
        if typ in ('ws', 'comment'):
            result_with_markers.append((typ, val, None))
            continue
        if typ == 'kw':
            if val in ('while', 'for'):
                label_counter[0] += 1
                lid = label_counter[0]
                loop_stack.append(lid)
                block_stack.append(('loop', lid))
                result_with_markers.append((typ, val, None))
            elif val == 'repeat':
                label_counter[0] += 1
                lid = label_counter[0]
                loop_stack.append(lid)
                block_stack.append(('repeat', lid))
                result_with_markers.append((typ, val, None))
            elif val == 'if' or val == 'function':
                block_stack.append(('block', 0))
                result_with_markers.append((typ, val, None))
            elif val == 'do':
                if block_stack and block_stack[-1][0] == 'loop':
                    pass
                else:
                    block_stack.append(('block', 0))
                result_with_markers.append((typ, val, None))
            elif val == 'end':
                if block_stack:
                    kind, lid = block_stack.pop()
                    if kind == 'loop' and lid > 0:
                        if loop_stack and loop_stack[-1] == lid:
                            loop_stack.pop()
                        result_with_markers.append(('label_insert', f'::__c{lid}__::', lid))
                result_with_markers.append((typ, val, None))
            elif val == 'until':
                if block_stack:
                    kind, lid = block_stack.pop()
                    if kind == 'repeat' and lid > 0:
                        if loop_stack and loop_stack[-1] == lid:
                            loop_stack.pop()
                        result_with_markers.append(('label_insert', f'::__c{lid}__::', lid))
                result_with_markers.append((typ, val, None))
            elif val == 'continue':
                if loop_stack:
                    lid = loop_stack[-1]
                    result_with_markers.append(('kw', f'goto __c{lid}__', None))
                else:
                    result_with_markers.append(('kw', 'goto __c0__', None))
            else:
                result_with_markers.append((typ, val, None))
        else:
            result_with_markers.append((typ, val, None))

    used_labels = set()
    for typ, val, meta in result_with_markers:
        if 'goto __c' in val:
            m = re.search(r'__c(\d+)__', val)
            if m: used_labels.add(int(m.group(1)))

    final = []
    for typ, val, meta in result_with_markers:
        if typ == 'label_insert':
            if meta in used_labels:
                final.append(('label', val, None))
        else:
            final.append((typ, val, meta))

    return [(t, v) for t, v, _ in final]

def convert_generalized_for(tokens):
    result = []
    i = 0
    while i < len(tokens):
        if tokens[i] == ('kw', 'for'):
            j = i + 1
            while j < len(tokens) and tokens[j][0] == 'ws': j += 1
            vars_start = j
            while j < len(tokens) and tokens[j] != ('kw', 'in'):
                j += 1
                if tokens[j-1] == ('kw', 'do') or j - i > 50:
                    break
            if j < len(tokens) and tokens[j] == ('kw', 'in'):
                j += 1
                while j < len(tokens) and tokens[j][0] == 'ws': j += 1
                expr_start = j
                while j < len(tokens) and tokens[j] != ('kw', 'do'):
                    j += 1
                    if j - expr_start > 50: break
                if j < len(tokens) and tokens[j] == ('kw', 'do'):
                    expr_tokens = tokens[expr_start:j]
                    clean = [t for t in expr_tokens if t[0] != 'ws']
                    if len(clean) == 1 and clean[0][0] == 'ident':
                        result.extend(tokens[i:expr_start])
                        result.append(('ident', f'__luau_iter({clean[0][1]})'))
                        result.append(('ws', ' '))
                        i = j
                        continue
            result.append(tokens[i])
            i += 1
        else:
            result.append(tokens[i])
            i += 1
    return result

print('Reading source...')
with open(r'unobfuscator\pending crack\bloxburg_script.lua', 'r', encoding='utf-8', errors='replace') as f:
    source = f.read()
print(f'Source length: {len(source)}')

print('Preprocessing Luau syntax...')
source = preprocess_luau(source)
print(f'Preprocessed length: {len(source)}')

with open(r'unobfuscator\pending crack\bloxburg_script_preprocessed.lua', 'w', encoding='utf-8') as f:
    f.write(source)
print('Saved preprocessed version')

print('Initializing Lua runtime...')
runtime = LuaRuntimeWrapper(op_limit=2_000_000_000, timeout=120.0)
runtime._init_runtime()

BUFFER_LIB = r"""
do
    local _pack = string.pack
    local _unpack = string.unpack
    local _rep = string.rep
    local _sub = string.sub
    local _byte = string.byte
    local _char = string.char
    local _concat = table.concat

    local buf_mt = {}
    buf_mt.__index = buf_mt

    local function _make_buf(size, data)
        local b = setmetatable({}, buf_mt)
        if data then
            b._data = {}
            for i = 1, #data do
                b._data[i] = _byte(data, i)
            end
            for i = #data + 1, size do
                b._data[i] = 0
            end
        else
            b._data = {}
            for i = 1, size do b._data[i] = 0 end
        end
        b._size = size
        return b
    end

    buffer = {}

    function buffer.create(size)
        return _make_buf(math.floor(size))
    end

    function buffer.fromstring(s)
        return _make_buf(#s, s)
    end

    function buffer.tostring(b)
        local t = {}
        for i = 1, b._size do
            t[i] = _char(b._data[i])
        end
        return _concat(t)
    end

    function buffer.len(b)
        return b._size
    end

    function buffer.readu8(b, offset)
        return b._data[offset + 1]
    end

    function buffer.readi8(b, offset)
        local v = b._data[offset + 1]
        if v >= 128 then v = v - 256 end
        return v
    end

    function buffer.readu16(b, offset)
        local o = offset + 1
        return b._data[o] + b._data[o+1] * 256
    end

    function buffer.readi16(b, offset)
        local o = offset + 1
        local v = b._data[o] + b._data[o+1] * 256
        if v >= 32768 then v = v - 65536 end
        return v
    end

    function buffer.readu32(b, offset)
        local o = offset + 1
        return b._data[o] + b._data[o+1] * 256 + b._data[o+2] * 65536 + b._data[o+3] * 16777216
    end

    function buffer.readi32(b, offset)
        local o = offset + 1
        local v = b._data[o] + b._data[o+1] * 256 + b._data[o+2] * 65536 + b._data[o+3] * 16777216
        if v >= 2147483648 then v = v - 4294967296 end
        return v
    end

    function buffer.readf32(b, offset)
        local o = offset + 1
        local s = _char(b._data[o], b._data[o+1], b._data[o+2], b._data[o+3])
        return _unpack("<f", s)
    end

    function buffer.readf64(b, offset)
        local o = offset + 1
        local s = _char(b._data[o], b._data[o+1], b._data[o+2], b._data[o+3],
                        b._data[o+4], b._data[o+5], b._data[o+6], b._data[o+7])
        return _unpack("<d", s)
    end

    function buffer.writeu8(b, offset, value)
        b._data[offset + 1] = value % 256
    end

    function buffer.writei8(b, offset, value)
        if value < 0 then value = value + 256 end
        b._data[offset + 1] = value % 256
    end

    function buffer.writeu16(b, offset, value)
        local o = offset + 1
        b._data[o] = value % 256
        b._data[o+1] = math.floor(value / 256) % 256
    end

    function buffer.writei16(b, offset, value)
        if value < 0 then value = value + 65536 end
        buffer.writeu16(b, offset, value)
    end

    function buffer.writeu32(b, offset, value)
        local o = offset + 1
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
                dst._data[dstOffset + 1 + i] = _byte(src, srcOffset + 1 + i)
            end
        else
            srcOffset = srcOffset or 0
            count = count or src._size
            for i = 0, count - 1 do
                dst._data[dstOffset + 1 + i] = src._data[srcOffset + 1 + i]
            end
        end
    end

    function buffer.fill(b, offset, value, count)
        count = count or (b._size - offset)
        value = value % 256
        for i = 0, count - 1 do
            b._data[offset + 1 + i] = value
        end
    end

    function buffer.readstring(b, offset, count)
        local t = {}
        for i = 0, count - 1 do
            t[#t+1] = _char(b._data[offset + 1 + i])
        end
        return _concat(t)
    end

    function buffer.writestring(b, offset, value, count)
        count = count or #value
        for i = 0, count - 1 do
            b._data[offset + 1 + i] = _byte(value, i + 1)
        end
    end
end
"""
runtime.lua.execute(BUFFER_LIB)

LUAU_COMPAT = r"""
function typeof(v)
    local t = type(v)
    if t == "table" then
        local mt = getmetatable(v)
        if mt and mt.__type then return mt.__type end
        if rawget(v, "__path") then return "Instance" end
        if rawget(v, "_data") and rawget(v, "_size") then return "buffer" end
    end
    if t == "userdata" then
        local mt = getmetatable(v)
        if mt and mt.__type then return mt.__type end
        return "Instance"
    end
    return t
end

task = {
    spawn = function(f, ...) if type(f) == "function" then pcall(f, ...) end end,
    defer = function(f, ...) if type(f) == "function" then pcall(f, ...) end end,
    delay = function(t, f, ...) end,
    wait = function(t) return t or 0, 0 end,
    cancel = function() end,
    desynchronize = function() end,
    synchronize = function() end,
}

function warn(...) end
function tick() return os.time() end
function time() return os.clock() end
function wait(t) return t or 0, 0 end
function spawn(f) if type(f) == "function" then pcall(f) end end
function delay(t, f) end
function shared() return {} end

function unpack(t, i, j) return table.unpack(t, i, j) end
"""
runtime.lua.execute(LUAU_COMPAT)

ENHANCED_MOCKS = r"""
local _call_log = {}
_G._call_log = _call_log
local _call_count = 0
local _str_log = {}
_G._str_log = _str_log

local function make_logged_mock(name)
    local mt = {}
    local store = {}
    mt.__index = function(self, key)
        local s = rawget(self, "__store")
        if s and s[key] ~= nil then return s[key] end
        local path = rawget(self, "__path") or name
        local child_path = path .. "." .. tostring(key)
        _call_count = _call_count + 1
        if _call_count <= 2000 then
            table.insert(_call_log, "GET: " .. child_path)
        end
        if key == "Name" or key == "ClassName" then return path end
        if key == "Parent" then return setmetatable({__path = "game", __store = {}}, mt) end
        if key == "Enabled" or key == "Visible" then return true end
        if key == "Value" then return 0 end
        if key == "Text" then return "" end
        if key == "Position" then return setmetatable({__path = child_path, __store = {X=0,Y=0,Z=0,Magnitude=0}}, mt) end
        if key == "CFrame" then return setmetatable({__path = child_path, __store = {}}, mt) end
        if key == "Character" or key == "Backpack" or key == "PlayerGui" then
            return setmetatable({__path = child_path, __store = {}}, mt)
        end
        if key == "Humanoid" then
            return setmetatable({__path = child_path, __store = {Health=100,MaxHealth=100,WalkSpeed=16,JumpPower=50}}, mt)
        end
        if key == "HumanoidRootPart" or key == "Head" or key == "Torso" then
            return setmetatable({__path = child_path, __store = {Position=setmetatable({__path=child_path..".Position",__store={X=0,Y=0,Z=0,Magnitude=0}},mt)}}, mt)
        end
        if key == "UserId" then return 1 end
        if key == "DisplayName" then return "Player" end
        if key == "Team" then return setmetatable({__path = child_path, __store = {}}, mt) end
        return setmetatable({__path = child_path, __store = {}}, mt)
    end
    mt.__newindex = function(self, key, val)
        local path = rawget(self, "__path") or name
        _call_count = _call_count + 1
        if _call_count <= 2000 then
            table.insert(_call_log, "SET: " .. path .. "." .. tostring(key) .. " = " .. tostring(val))
        end
        local s = rawget(self, "__store")
        if not s then s = {}; rawset(self, "__store", s) end
        s[key] = val
    end
    mt.__call = function(self, ...)
        local path = rawget(self, "__path") or name
        local args = {...}
        _call_count = _call_count + 1
        if _call_count <= 2000 then
            local arg_strs = {}
            for i, v in ipairs(args) do
                if type(v) == "string" then
                    table.insert(arg_strs, '"'..v..'"')
                    table.insert(_str_log, v)
                else
                    table.insert(arg_strs, tostring(v))
                end
            end
            table.insert(_call_log, "CALL: " .. path .. "(" .. table.concat(arg_strs, ", ") .. ")")
        end
        if path:match("HttpGet$") or path:match("HttpGetAsync$") then
            return tostring(os.time())
        end
        if path:match("GetService$") then
            local svc = args[2] or args[1] or "Unknown"
            if type(svc) == "string" then
                return setmetatable({__path = svc, __store = {}}, mt)
            end
        end
        if path:match("FindFirstChild$") or path:match("WaitForChild$") or path:match("FindFirstChildOfClass$") then
            local cname = args[2] or args[1] or "Child"
            if type(cname) == "string" then
                return setmetatable({__path = path:gsub("%.[^.]+$", "") .. "." .. cname, __store = {}}, mt)
            end
        end
        if path:match("GetChildren$") or path:match("GetDescendants$") then
            return {}
        end
        if path:match("GetPlayers$") then
            return {}
        end
        if path:match("Connect$") or path:match("connect$") then
            return setmetatable({__path = path .. "()", __store = {}}, mt)
        end
        if path:match("Clone$") then
            return setmetatable({__path = path .. "()", __store = {}}, mt)
        end
        if path:match("Destroy$") or path:match("Remove$") or path:match("Disconnect$") then
            return
        end
        if path:match("%.new$") or path:match("%.new%(") then
            return setmetatable({__path = path .. "()", __store = {}}, mt)
        end
        return setmetatable({__path = path .. "()", __store = {}}, mt)
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
    mt.__eq = function(a, b) return false end
    mt.__lt = function(a, b) return false end
    mt.__le = function(a, b) return false end
    mt.__len = function(a) return 0 end
    return setmetatable({__path = name, __store = {}}, mt)
end

game = make_logged_mock("game")
workspace = make_logged_mock("workspace")
Instance = make_logged_mock("Instance")
Enum = make_logged_mock("Enum")
UDim2 = make_logged_mock("UDim2")
Vector2 = make_logged_mock("Vector2")
Vector3 = make_logged_mock("Vector3")
CFrame = make_logged_mock("CFrame")
Color3 = make_logged_mock("Color3")
BrickColor = make_logged_mock("BrickColor")
TweenInfo = make_logged_mock("TweenInfo")
Ray = make_logged_mock("Ray")
Region3 = make_logged_mock("Region3")
NumberRange = make_logged_mock("NumberRange")

islclosure = function(f) return type(f) == "function" end
newcclosure = function(f) return f end
iscclosure = function(f) return false end
hookfunction = function(old, new) return old end
hookmetamethod = function(...) return function() end end
getrawmetatable = function(t) return getmetatable(t) end
setrawmetatable = setmetatable
checkcaller = function() return true end
isexecutorclosure = islclosure
cloneref = function(x) return x end
gethui = function() return make_logged_mock("HiddenUI") end
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
request = function(t) return {StatusCode=200,Body="{}",Headers={}} end
http_request = request
syn = make_logged_mock("syn")
fluxus = make_logged_mock("fluxus")
Drawing = make_logged_mock("Drawing")

setmetatable(_G, {
    __index = function(self, key)
        if type(key) == "string" then
            local m = make_logged_mock(key)
            rawset(self, key, m)
            return m
        end
    end
})
"""
runtime.lua.execute(ENHANCED_MOCKS)

ERROR_OVERRIDE = r"""
local _real_error = error
local _error_log = {}
_G._error_log = _error_log
error = function(msg, level)
    if type(msg) == "string" and (msg:find("Luraph Script") or msg:find("table index is nil") or msg:find("attempt to")) then
        if #_error_log < 100 then
            table.insert(_error_log, tostring(msg))
        end
        return
    end
    _real_error(msg, level)
end
"""
runtime.lua.execute(ERROR_OVERRIDE)

source = "do local __ok, __err = pcall(function(...)\n" + source + "\nend, ...)\nif not __ok then table.insert(_G._error_log, 'PCALL: ' .. tostring(__err)) end\nend"

print('Executing (2B ops, 120s timeout)...')
import time as _time
t0 = _time.time()
try:
    result = runtime.execute(source)
    elapsed = _time.time() - t0
    print(f'Execution completed in {elapsed:.1f}s, result type: {type(result)}')
except LuaRuntimeError as e:
    elapsed = _time.time() - t0
    print(f'LuaRuntimeError after {elapsed:.1f}s: {str(e)[:800]}')
except Exception as e:
    elapsed = _time.time() - t0
    print(f'{type(e).__name__} after {elapsed:.1f}s: {str(e)[:800]}')

try:
    err_count = runtime.lua.eval('#_G._error_log')
    print(f'\nError log count: {err_count}')
    if err_count and int(err_count) > 0:
        for i in range(1, min(int(err_count)+1, 50)):
            print(f'  ERR[{i}] {runtime.lua.eval(f"_G._error_log[{i}]")}')
except Exception as e2:
    print(f'Error log error: {e2}')

try:
    str_count = runtime.lua.eval('#_G._str_log')
    print(f'\nString args log count: {str_count}')
    if str_count and int(str_count) > 0:
        for i in range(1, min(int(str_count)+1, 100)):
            print(f'  STR[{i}] {runtime.lua.eval(f"_G._str_log[{i}]")}')
except Exception as e2:
    print(f'String log error: {e2}')

try:
    call_count = runtime.lua.eval('#_G._call_log')
    print(f'\nAPI call log count: {call_count}')
    if call_count and int(call_count) > 0:
        for i in range(1, min(int(call_count)+1, 200)):
            print(f'  [{i}] {runtime.lua.eval(f"_G._call_log[{i}]")}')
except Exception as e2:
    print(f'Log error: {e2}')

loads = runtime.get_intercepted_loads()
print(f'\nIntercepted loads: {len(loads)}')
for i, l in enumerate(loads[:5]):
    print(f'  [{i}] len={len(l)}, preview: {l[:200]}')
