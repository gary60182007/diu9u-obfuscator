"""IronBrew3 bytecode VM repackager.

Takes extracted IB3 bytecode data (constants, protos, opcode_map) and generates
a clean Lua VM script that faithfully executes the original bytecode without
any IB3 obfuscation layer. The output is injectable into Roblox.
"""

import struct
from typing import List, Dict, Optional, Tuple
from .ironbrew3 import IB3Constant, IB3Instruction, IB3Proto, IB3Chunk, IB3_STDLIB_PARAMS

VM_MOVE = 0
VM_LOADK = 1
VM_LOADBOOL = 2
VM_LOADNIL = 3
VM_LOADI = 4
VM_GETGLOBAL = 5
VM_SETGLOBAL = 6
VM_GETTABLE = 7
VM_SETTABLE = 8
VM_NEWTABLE = 9
VM_SELF = 10
VM_ADD = 11
VM_SUB = 12
VM_MUL = 13
VM_DIV = 14
VM_MOD = 15
VM_POW = 16
VM_UNM = 17
VM_NOT = 18
VM_LEN = 19
VM_CONCAT = 20
VM_JMP = 21
VM_EQ = 22
VM_LT = 23
VM_LE = 24
VM_TEST = 25
VM_CALL = 26
VM_TAILCALL = 27
VM_RETURN = 28
VM_FORLOOP = 29
VM_FORPREP = 30
VM_TFORLOOP = 31
VM_SETLIST = 32
VM_CLOSE = 33
VM_CLOSURE = 34
VM_VARARG = 35
VM_GETUPVAL = 36
VM_SETUPVAL = 37
VM_GETFIELD_ENV = 38
VM_NOP = 39
VM_SUPEROP = 40
VM_ARITH = 41
VM_TEST_NOT = 42

OP_NAME_TO_VM = {
    'MOVE': VM_MOVE, 'LOADK': VM_LOADK, 'LOADBOOL': VM_LOADBOOL,
    'LOADNIL': VM_LOADNIL, 'LOADI': VM_LOADI,
    'GETGLOBAL': VM_GETGLOBAL, 'SETGLOBAL': VM_SETGLOBAL,
    'GETTABLE': VM_GETTABLE, 'SETTABLE': VM_SETTABLE,
    'NEWTABLE': VM_NEWTABLE, 'SELF': VM_SELF,
    'ADD': VM_ADD, 'SUB': VM_SUB, 'MUL': VM_MUL, 'DIV': VM_DIV,
    'MOD': VM_MOD, 'POW': VM_POW,
    'UNM': VM_UNM, 'NOT': VM_NOT, 'LEN': VM_LEN, 'CONCAT': VM_CONCAT,
    'JMP': VM_JMP, 'EQ': VM_EQ, 'LT': VM_LT, 'LE': VM_LE, 'TEST': VM_TEST,
    'CALL': VM_CALL, 'TAILCALL': VM_TAILCALL, 'RETURN': VM_RETURN,
    'FORLOOP': VM_FORLOOP, 'FORPREP': VM_FORPREP, 'TFORLOOP': VM_TFORLOOP,
    'SETLIST': VM_SETLIST, 'CLOSE': VM_CLOSE, 'CLOSURE': VM_CLOSURE,
    'VARARG': VM_VARARG, 'GETUPVAL': VM_GETUPVAL, 'SETUPVAL': VM_SETUPVAL,
    'NOP': VM_NOP, 'SUPEROP': VM_SUPEROP, 'ARITH': VM_ARITH,
    'TEST_NOT': VM_TEST_NOT,
}

STDLIB_RESOLVERS = {
    'math.log': 'math.log',
    'string.unpack': 'string.unpack',
    'string.sub': 'string.sub',
    'math.min': 'math.min',
    'math.abs': 'math.abs',
    '_ENV': '_env',
    'coroutine.yield': 'coroutine.yield',
    'tonumber': 'tonumber',
    'string.byte': 'string.byte',
    'tostring': 'tostring',
    'math.cos': 'math.cos',
    'math.sin': 'math.sin',
    'string.len': 'string.len',
    'math.deg': 'math.deg',
    'math.ceil': 'math.ceil',
    'pcall': 'pcall',
    'math.exp': 'math.exp',
    'table.concat': 'table.concat',
    'math.fmod': 'math.fmod',
    'math.sqrt': 'math.sqrt',
    'math.max': 'math.max',
    'math.pow': '(math.pow or function(a,b) return a^b end)',
    'math.pi': 'math.pi',
    'type': 'type',
    'select': 'select',
    'math.rad': 'math.rad',
    'table.unpack': '(table.unpack or unpack)',
    'getfenv': '(getfenv or function() return _env end)',
    'table.move': 'table.move',
    'string.char': 'string.char',
    'math.atan2': '(math.atan2 or math.atan)',
    'pairs': 'pairs',
    'math.floor': 'math.floor',
    'ipairs': 'ipairs',
    '_byte_table': '_bt',
}


class IB3VMRepackager:
    def __init__(self, constants: List[IB3Constant], protos: List[IB3Proto],
                 opcode_map: Dict[int, str], stdlib_map: Dict[str, str],
                 entry_proto_index: int = 0):
        self.constants = constants
        self.protos = protos
        self.opcode_map = opcode_map
        self.stdlib_map = stdlib_map
        self.entry_proto_index = entry_proto_index

    def repackage(self, debug: bool = False) -> str:
        bytecode = self._serialize()
        return self._generate_vm(bytecode, debug)

    def _get_vm_opcode(self, ib3_opcode: int) -> int:
        op_name = self.opcode_map.get(ib3_opcode, 'NOP')
        if op_name.startswith('GETFIELD_ENV'):
            return VM_GETFIELD_ENV
        if op_name.startswith('PATCH_'):
            return VM_NOP
        return OP_NAME_TO_VM.get(op_name, VM_NOP)

    def _serialize(self) -> bytes:
        parts = []
        nk = len(self.constants)
        parts.append(struct.pack('<H', nk))
        for c in self.constants:
            if c.type == 'nil':
                parts.append(b'\x00')
            elif c.type == 'boolean':
                parts.append(b'\x01' if c.value else b'\x02')
            elif c.type == 'number':
                parts.append(b'\x03')
                parts.append(struct.pack('<d', c.value))
            elif c.type == 'string':
                parts.append(b'\x04')
                encoded = c.value.encode('utf-8', 'replace')
                parts.append(struct.pack('<H', len(encoded)))
                parts.append(encoded)

        parts.append(struct.pack('<H', len(self.protos)))
        for proto in self.protos:
            parts.append(struct.pack('<B', proto.num_params))
            parts.append(struct.pack('<B', 1 if proto.is_vararg else 0))
            parts.append(struct.pack('<H', proto.max_stack))
            ni = len(proto.instructions)
            parts.append(struct.pack('<H', ni))
            for inst in proto.instructions:
                vm_op = self._get_vm_opcode(inst.opcode)
                parts.append(struct.pack('<B', vm_op))
                parts.append(struct.pack('<I', inst.A))
                parts.append(struct.pack('<i', inst.B))
                parts.append(struct.pack('<I', inst.C))
                parts.append(struct.pack('<I', inst.D))
                parts.append(struct.pack('<B', len(inst.sub)))
                for s in inst.sub:
                    parts.append(struct.pack('<H', s & 0xFFFF))

        parts.append(struct.pack('<B', self.entry_proto_index))
        return b''.join(parts)

    def _build_stdlib_args(self) -> str:
        lines = []
        for _, stdlib_func in IB3_STDLIB_PARAMS:
            lua_expr = STDLIB_RESOLVERS.get(stdlib_func, 'nil')
            lines.append(lua_expr)
        return ', '.join(lines)

    def _generate_vm(self, bytecode: bytes, debug: bool = False) -> str:
        hex_data = bytecode.hex()
        stdlib_args = self._build_stdlib_args()
        nk = len(self.constants)

        result = _LUA_VM_TEMPLATE.replace('__BYTECODE_HEX__', hex_data) \
                                 .replace('__STDLIB_ARGS__', stdlib_args) \
                                 .replace('__NCONST__', str(nk))
        if debug:
            result = result.replace('__DEBUG_PRE__', _DEBUG_PRE)
            result = result.replace('__DEBUG_POST__', _DEBUG_POST)
        else:
            result = result.replace('__DEBUG_PRE__', '')
            result = result.replace('__DEBUG_POST__', '')
        return result


_LUA_VM_TEMPLATE = r'''local _hex = "__BYTECODE_HEX__"
local _raw = {}
for i = 1, #_hex, 2 do
  _raw[#_raw+1] = string.char(tonumber(string.sub(_hex, i, i+1), 16))
end
local _data = table.concat(_raw)
_raw = nil

local _env
if getfenv then
  _env = getfenv(0)
elseif _ENV then
  _env = _ENV
else
  _env = _G
end
if not _env.game and typeof then
  _env = {}
  for k,v in pairs({
    game=game, workspace=workspace, script=script,
    Instance=Instance, Vector3=Vector3, CFrame=CFrame,
    UDim2=UDim2, Color3=Color3, BrickColor=BrickColor,
    Enum=Enum, task=task, wait=wait, spawn=spawn,
    delay=delay, tick=tick, time=time, typeof=typeof,
    pcall=pcall, xpcall=xpcall, error=error, warn=warn,
    print=print, tostring=tostring, tonumber=tonumber,
    type=type, select=select, pairs=pairs, ipairs=ipairs,
    next=next, unpack=unpack, table=table, math=math,
    string=string, coroutine=coroutine, require=require,
    setmetatable=setmetatable, getmetatable=getmetatable,
    rawget=rawget, rawset=rawset, rawequal=rawequal,
    loadstring=loadstring, setfenv=setfenv, getfenv=getfenv,
  }) do _env[k] = v end
end
local _unpack = table.unpack or unpack
local _bt = {}
for i = 0, 255 do _bt[i] = string.char(i) end

local _pos = 1
local function rb()
  local b = string.byte(_data, _pos); _pos = _pos + 1; return b
end
local function ru16()
  local lo, hi = string.byte(_data, _pos, _pos+1); _pos = _pos + 2
  return lo + hi * 256
end
local function ru32()
  local a, b, c, d = string.byte(_data, _pos, _pos+3); _pos = _pos + 4
  return a + b*256 + c*65536 + d*16777216
end
local function ri32()
  local v = ru32()
  if v >= 2147483648 then v = v - 4294967296 end
  return v
end
local function rf64()
  if string.unpack then
    local v = string.unpack("<d", _data, _pos); _pos = _pos + 8; return v
  end
  local a,b,c,d,e,f,g,h = string.byte(_data, _pos, _pos+7); _pos = _pos + 8
  local sign = (h > 127) and -1 or 1
  local exp = (h % 128) * 16 + math.floor(g / 16) - 1023
  local frac = (g % 16) * 2^48 + f * 2^40 + e * 2^32 + d * 2^24 + c * 2^16 + b * 2^8 + a
  if exp == 1024 then return frac == 0 and sign * math.huge or 0/0 end
  if exp == -1023 then
    if frac == 0 then return sign * 0 end
    return sign * 2^(-1022) * (frac / 2^52)
  end
  return sign * 2^exp * (1 + frac / 2^52)
end
local function rstr()
  local len = ru16()
  local s = string.sub(_data, _pos, _pos + len - 1); _pos = _pos + len; return s
end

local nk = ru16()
local K = {}
for i = 0, nk - 1 do
  local t = rb()
  if t == 0 then K[i] = nil
  elseif t == 1 then K[i] = true
  elseif t == 2 then K[i] = false
  elseif t == 3 then K[i] = rf64()
  elseif t == 4 then K[i] = rstr()
  end
end

local nprot = ru16()
local P = {}
for pi = 1, nprot do
  local p = {}
  p.np = rb()
  p.va = rb() ~= 0
  p.ms = ru16()
  local ni = ru16()
  local code = {}
  for ii = 1, ni do
    local op = rb()
    local A = ru32()
    local B = ri32()
    local C = ru32()
    local D = ru32()
    local ns = rb()
    local sub = {}
    for si = 1, ns do sub[si] = ru16() end
    code[ii] = {op, A, B, C, D, sub}
  end
  p.code = code
  P[pi] = p
end
local _entry = rb() + 1
local _F = {}

local function wrap(proto, env, parentUpvals)
  local code = proto.code
  local np = proto.np

  local function execute(...)
    local R = {}
    local upvals = parentUpvals or {}
    local args = {...}
    local nargs = select("#", ...)
    for i = 1, np do R[i-1] = args[i] end

    local pc = 1
    local top = -1
    local ni = #code

    while true do
      local inst = code[pc]
      local op = inst[1]
      local A = inst[2]
      pc = pc + 1
__DEBUG_PRE__
      if op == 0 then -- MOVE
        R[A] = R[inst[3]]

      elseif op == 1 then -- LOADK
        R[A] = K[inst[4]]

      elseif op == 2 then -- LOADBOOL
        R[A] = inst[4] ~= 0
        if inst[5] ~= 0 then pc = pc + 1 end

      elseif op == 3 then -- LOADNIL
        for i = A, A + inst[3] do R[i] = nil end

      elseif op == 4 then -- LOADI
        local v = inst[4]
        if v > 2147483647 then v = v - 4294967296 end
        R[A] = v

      elseif op == 5 then -- GETGLOBAL
        R[A] = env[K[inst[4]]]

      elseif op == 6 then -- SETGLOBAL
        env[K[inst[4]]] = R[A]

      elseif op == 7 then -- GETTABLE
        local sub = inst[6]
        if #sub > 0 then
          R[A] = R[inst[3]][K[sub[1]]]
        else
          R[A] = R[inst[3]][R[inst[4]]]
        end

      elseif op == 8 then -- SETTABLE
        local sub = inst[6]
        if #sub > 0 then
          R[inst[3]][K[sub[1]]] = R[A]
        else
          R[inst[3]][R[inst[5]]] = R[A]
        end

      elseif op == 9 then -- NEWTABLE
        R[A] = {}

      elseif op == 10 then -- SELF
        local sub = inst[6]
        R[A+1] = R[inst[3]]
        if #sub > 0 then
          R[A] = R[inst[3]][K[sub[1]]]
        else
          R[A] = R[inst[3]][R[inst[4]]]
        end

      elseif op == 11 then R[A] = R[inst[3]] + R[inst[5]] -- ADD
      elseif op == 12 then R[A] = R[inst[3]] - R[inst[5]] -- SUB
      elseif op == 13 then R[A] = R[inst[3]] * R[inst[5]] -- MUL
      elseif op == 14 then R[A] = R[inst[3]] / R[inst[5]] -- DIV
      elseif op == 15 then R[A] = R[inst[3]] % R[inst[5]] -- MOD
      elseif op == 16 then R[A] = R[inst[3]] ^ R[inst[5]] -- POW
      elseif op == 17 then R[A] = -R[inst[3]] -- UNM
      elseif op == 18 then R[A] = not R[inst[3]] -- NOT
      elseif op == 19 then R[A] = #R[inst[3]] -- LEN

      elseif op == 20 then -- CONCAT
        local B = inst[3]
        local D = inst[5]
        local e = D > B and D or (B + 1)
        local s = R[B]
        for i = B+1, e do s = s .. R[i] end
        R[A] = s

      elseif op == 21 then -- JMP
        pc = inst[4] + 1

      elseif op == 22 then -- EQ
        local sub = inst[6]
        if #sub > 0 then
          local target = inst[4] <= ni and inst[4] or inst[5]
          if R[A] == R[sub[1]] then pc = target + 1 end
        elseif inst[3] > 0 and inst[5] > 0 then
          local target = inst[4] <= ni and inst[4] or inst[5]
          if R[inst[3]] == R[inst[5]] then pc = target + 1 end
        else
          local target = inst[4] <= ni and inst[4] or inst[5]
          if R[A] == nil then pc = target + 1 end
        end

      elseif op == 23 then -- LT
        local sub = inst[6]
        if #sub > 0 then
          if R[A] < R[sub[1]] then pc = inst[4] + 1 end
        else
          if A ~= 0 then
            if R[inst[3]] >= R[inst[5]] then pc = inst[4] + 1 end
          else
            if R[inst[3]] < R[inst[5]] then pc = inst[4] + 1 end
          end
        end

      elseif op == 24 then -- LE
        if A ~= 0 then
          if R[inst[3]] > R[inst[5]] then pc = inst[4] + 1 end
        else
          if R[inst[3]] <= R[inst[5]] then pc = inst[4] + 1 end
        end

      elseif op == 25 then -- TEST
        local target
        if inst[4] >= 0 and inst[4] <= ni then target = inst[4]
        else target = inst[5] end
        if R[A] then pc = target + 1 end

      elseif op == 42 then -- TEST_NOT
        local target
        if inst[4] >= 0 and inst[4] <= ni then target = inst[4]
        else target = inst[5] end
        if not R[A] then pc = target + 1 end

      elseif op == 26 then -- CALL
        local B = inst[3]
        local D = inst[5]
        local fn = R[A]
        if B > 0 then
          local a = {}
          for i = 1, B do a[i] = R[A+i] end
          if D == 0 then
            local rets = {fn(_unpack(a, 1, B))}
            for i = 0, #rets-1 do R[A+i] = rets[i+1] end
            top = A + #rets - 1
          elseif D == 1 then R[A] = fn(_unpack(a, 1, B))
          else
            local rets = {fn(_unpack(a, 1, B))}
            for i = 1, D do R[A+i-1] = rets[i] end
          end
        else
          local a = {}
          for i = A+1, top do a[#a+1] = R[i] end
          if D == 0 then
            local rets = {fn(_unpack(a))}
            for i = 0, #rets-1 do R[A+i] = rets[i+1] end
            top = A + #rets - 1
          elseif D == 1 then R[A] = fn(_unpack(a))
          else
            local rets = {fn(_unpack(a))}
            for i = 1, D do R[A+i-1] = rets[i] end
          end
        end

      elseif op == 27 then -- TAILCALL
        local B = inst[3]
        local fn = R[A]
        if B > 0 then
          local a = {}
          for i = 1, B do a[i] = R[A+i] end
          return fn(_unpack(a, 1, B))
        else
          local a = {}
          for i = A+1, top do a[#a+1] = R[i] end
          return fn(_unpack(a))
        end

      elseif op == 28 then -- RETURN
        local B = inst[3]
        if B == 0 then
          if top >= A then
            local rets = {}
            for i = A, top do rets[#rets+1] = R[i] end
            return _unpack(rets)
          end
          return
        end
        if B == 1 then return R[A] end
        if B == 2 then return R[A], R[A+1] end
        local rets = {}
        for i = 1, B do rets[i] = R[A+i-1] end
        return _unpack(rets, 1, B)

      elseif op == 29 then -- FORLOOP
        local step = R[A+2]
        R[A] = R[A] + step
        if step > 0 then
          if R[A] <= R[A+1] then
            pc = inst[4] + 1
            R[A+3] = R[A]
          end
        else
          if R[A] >= R[A+1] then
            pc = inst[4] + 1
            R[A+3] = R[A]
          end
        end

      elseif op == 30 then -- FORPREP
        R[A] = R[A] - R[A+2]
        pc = inst[4] + 1

      elseif op == 31 then -- TFORLOOP
        local base = A
        local rets = {R[base](R[base+1], R[base+2])}
        for i = 1, #rets do R[base+2+i] = rets[i] end
        if rets[1] ~= nil then
          R[base+2] = rets[1]
        else
          pc = inst[4] + 1
        end

      elseif op == 32 then -- SETLIST
        local B = inst[3]
        local C = inst[4]
        local tbl = R[A]
        if B == 0 then
          for i = 1, top - A do
            tbl[C*50 + i] = R[A+i]
          end
        else
          for i = 1, B do
            tbl[C*50 + i] = R[A+i]
          end
        end

      elseif op == 33 then -- CLOSE (no-op in clean VM)

      elseif op == 34 then -- CLOSURE
        local child_idx = inst[4] + 1
        local child = P[child_idx]
        local ns = inst[6]
        local num_uv = (#ns > 0) and ns[1] or 0
        local child_upvals = {}
        for ui = 1, num_uv do
          local desc = code[pc]
          pc = pc + 1
          local uv_type = desc[2]
          local uv_src = desc[3]
          if uv_type == 0 then
            local cell = {[0] = R[uv_src]}
            child_upvals[ui] = {cell, 0}
          elseif uv_type == 1 then
            child_upvals[ui] = {R, uv_src}
          elseif uv_type == 2 then
            child_upvals[ui] = upvals[uv_src + 1]
          else
            local cell = {[0] = R[uv_src]}
            child_upvals[ui] = {cell, 0}
          end
        end
        R[A] = wrap(child, env, child_upvals)

      elseif op == 35 then -- VARARG
        local B = inst[3]
        if B == 0 then
          local nva = nargs - np
          for i = 1, nva do R[A + i - 1] = args[np + i] end
          top = A + nva - 1
        else
          for i = 0, B - 1 do
            R[A + i] = args[np + 1 + i]
          end
        end

      elseif op == 36 then -- GETUPVAL
        local box = upvals[inst[3] + 1]
        if box then R[A] = box[1][box[2]] end

      elseif op == 37 then -- SETUPVAL
        local box = upvals[inst[3] + 1]
        if box then box[1][box[2]] = R[A] end

      elseif op == 38 then -- GETFIELD_ENV
        local sub = inst[6]
        if #sub >= 1 then
          local val = env[K[sub[1]]]
          for i = 2, #sub do
            if val then val = val[K[sub[i]]] end
          end
          R[A] = val
        else
          R[A] = env
        end

      elseif op == 40 then -- SUPEROP
        local B = inst[3]
        local C = inst[4]
        local D = inst[5]
        local sub = inst[6]
        if #sub > 0 and B > 0 then
          R[A] = R[B][K[sub[1]]]
        elseif #sub > 0 and B == 0 then
          R[A] = env[K[sub[1]]]
        elseif B == 0 and C == 0 and D == 0 and #sub == 0 then
          R[A] = nil
        elseif B == 0 and #sub == 0 and C > 0 and C < __NCONST__ and D == 0 then
          R[A] = K[C]
        elseif B > 0 and C == 0 and D == 0 and #sub == 0 then
          if B == A + 1 then
            R[A](R[B])
          elseif B > A then
            local a = {}
            for i = A+1, B do a[#a+1] = R[i] end
            R[A](_unpack(a))
          else
            R[A] = R[B]
          end
        elseif C > 0 and C <= ni and D == 0 then
          pc = C + 1
        end

      elseif op == 41 then -- ARITH
        local B = inst[3]
        local C = inst[4]
        local D = inst[5]
        if B == A + 1 and D < A then
          R[A] = R[B](R[D])
        elseif B == A + 1 and D == A + 2 then
          R[A] = R[B](R[D])
        elseif B <= 5 and D <= 3 and (B + D) > 0 then
          local fn = R[A]
          if B > 0 then
            local a = {}
            for i = 1, B do a[i] = R[A+i] end
            if D == 0 then fn(_unpack(a, 1, B))
            elseif D == 1 then R[A] = fn(_unpack(a, 1, B))
            else
              local rets = {fn(_unpack(a, 1, B))}
              for i = 1, D do R[A+i-1] = rets[i] end
            end
          else
            local a = {}
            for i = A+1, top do a[#a+1] = R[i] end
            if D == 0 then
              local rets = {fn(_unpack(a))}
              for i = 0, #rets-1 do R[A+i] = rets[i+1] end
              top = A + #rets - 1
            elseif D == 1 then R[A] = fn(_unpack(a))
            else
              local rets = {fn(_unpack(a))}
              for i = 1, D do R[A+i-1] = rets[i] end
            end
          end
        elseif A == B and A == D then
          R[A] = R[A] * R[A]
        elseif C == 0 then
          R[A] = R[B] % R[D]
        else
          R[A] = R[B] % K[C]
        end

      -- op == 39: NOP
      end
__DEBUG_POST__
    end
  end

  return execute
end

for pi = 1, nprot do
  _F[pi] = wrap(P[pi], _env, nil)
end
local main = _F[_entry]
main(__STDLIB_ARGS__)
'''

_DEBUG_PRE = r'''
      local _ok, _err = pcall(function()
'''

_DEBUG_POST = r'''
      end)
      if not _ok then
        local _OP = {"MOVE","LOADK","LOADBOOL","LOADNIL","LOADI","GETGLOBAL","SETGLOBAL",
          "GETTABLE","SETTABLE","NEWTABLE","SELF","ADD","SUB","MUL","DIV","MOD","POW",
          "UNM","NOT","LEN","CONCAT","JMP","EQ","LT","LE","TEST","TEST_NOT","CALL",
          "TAILCALL","RETURN","FORLOOP","FORPREP","TFORLOOP","SETLIST","CLOSE","CLOSURE",
          "VARARG","GETUPVAL","SETUPVAL","GETFIELD_ENV","NOP","SUPEROP","PATCH","ARITH"}
        local opn = _OP[op+1] or ("OP_"..tostring(op))
        local msg = string.format("[VM DEBUG] Error at pc=%d op=%s(%d) A=%d B=%s C=%s D=%s sub=%s\n  err: %s",
          pc-1, opn, op, A,
          tostring(inst[3]), tostring(inst[4]), tostring(inst[5]),
          tostring(inst[6] and #inst[6] or 0), tostring(_err))
        local rd = {}
        for ri = 0, 20 do
          if R[ri] ~= nil then rd[#rd+1] = string.format("R[%d]=%s", ri, tostring(R[ri])) end
        end
        if #rd > 0 then msg = msg .. "\n  regs: " .. table.concat(rd, ", ") end
        warn(msg)
        error(_err)
      end
'''
