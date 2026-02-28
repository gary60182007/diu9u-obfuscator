from __future__ import annotations
from typing import List, Optional, Dict, Tuple, Any
from dataclasses import dataclass, field
from enum import IntEnum


class OpCode(IntEnum):
    MOVE = 0
    LOADK = 1
    LOADBOOL = 2
    LOADNIL = 3
    GETUPVAL = 4
    GETGLOBAL = 5
    GETTABLE = 6
    SETGLOBAL = 7
    SETUPVAL = 8
    SETTABLE = 9
    NEWTABLE = 10
    SELF = 11
    ADD = 12
    SUB = 13
    MUL = 14
    DIV = 15
    MOD = 16
    POW = 17
    UNM = 18
    NOT = 19
    LEN = 20
    CONCAT = 21
    JMP = 22
    EQ = 23
    LT = 24
    LE = 25
    TEST = 26
    TESTSET = 27
    CALL = 28
    TAILCALL = 29
    RETURN = 30
    FORLOOP = 31
    FORPREP = 32
    TFORLOOP = 33
    SETLIST = 34
    CLOSE = 35
    CLOSURE = 36
    VARARG = 37


OP_NAMES = {v: v.name for v in OpCode}


class ArgMode(IntEnum):
    A = 0
    B = 1
    C = 2
    Bx = 3
    sBx = 4
    Ax = 5


@dataclass
class Instruction:
    opcode: OpCode
    A: int = 0
    B: int = 0
    C: int = 0
    Bx: int = 0
    sBx: int = 0
    line: int = 0

    @property
    def name(self) -> str:
        return OP_NAMES.get(self.opcode, f"OP_{self.opcode}")

    def __repr__(self):
        return f"{self.name} A={self.A} B={self.B} C={self.C} Bx={self.Bx} sBx={self.sBx}"


@dataclass
class Constant:
    type: str
    value: Any = None

    @staticmethod
    def nil() -> Constant:
        return Constant(type='nil', value=None)

    @staticmethod
    def boolean(v: bool) -> Constant:
        return Constant(type='boolean', value=v)

    @staticmethod
    def number(v: float) -> Constant:
        return Constant(type='number', value=v)

    @staticmethod
    def string(v: str) -> Constant:
        return Constant(type='string', value=v)


@dataclass
class UpvalueDesc:
    name: str = ""
    in_stack: bool = False
    index: int = 0


@dataclass
class LocalVar:
    name: str
    start_pc: int = 0
    end_pc: int = 0


@dataclass
class Prototype:
    source: str = ""
    line_defined: int = 0
    last_line_defined: int = 0
    num_upvalues: int = 0
    num_params: int = 0
    is_vararg: bool = False
    max_stack_size: int = 0
    instructions: List[Instruction] = field(default_factory=list)
    constants: List[Constant] = field(default_factory=list)
    protos: List[Prototype] = field(default_factory=list)
    upvalue_descs: List[UpvalueDesc] = field(default_factory=list)
    local_vars: List[LocalVar] = field(default_factory=list)
    line_info: List[int] = field(default_factory=list)

    def get_constant(self, idx: int) -> Any:
        if 0 <= idx < len(self.constants):
            return self.constants[idx].value
        return None

    def rk(self, val: int) -> Tuple[bool, int]:
        if val >= 256:
            return True, val - 256
        return False, val


def decode_instruction(raw: int) -> Instruction:
    opcode = OpCode(raw & 0x3F)
    A = (raw >> 6) & 0xFF
    B = (raw >> 23) & 0x1FF
    C = (raw >> 14) & 0x1FF
    Bx = (raw >> 14) & 0x3FFFF
    sBx = Bx - 131071
    return Instruction(opcode=opcode, A=A, B=B, C=C, Bx=Bx, sBx=sBx)


def encode_instruction(inst: Instruction) -> int:
    op = int(inst.opcode)
    if inst.opcode in (OpCode.JMP, OpCode.FORLOOP, OpCode.FORPREP, OpCode.TFORLOOP):
        Bx = inst.sBx + 131071
        return op | (inst.A << 6) | (Bx << 14)
    elif inst.opcode in (OpCode.LOADK, OpCode.GETGLOBAL, OpCode.SETGLOBAL, OpCode.CLOSURE):
        return op | (inst.A << 6) | (inst.Bx << 14)
    else:
        return op | (inst.A << 6) | (inst.C << 14) | (inst.B << 23)


class BytecodeReader:
    def __init__(self, data: bytes):
        self.data = data
        self.pos = 0

    def read_byte(self) -> int:
        b = self.data[self.pos]
        self.pos += 1
        return b

    def read_int(self) -> int:
        b = self.data[self.pos:self.pos + 4]
        self.pos += 4
        return int.from_bytes(b, 'little', signed=True)

    def read_uint(self) -> int:
        b = self.data[self.pos:self.pos + 4]
        self.pos += 4
        return int.from_bytes(b, 'little', signed=False)

    def read_size_t(self, size: int = 4) -> int:
        b = self.data[self.pos:self.pos + size]
        self.pos += size
        return int.from_bytes(b, 'little', signed=False)

    def read_double(self) -> float:
        import struct
        b = self.data[self.pos:self.pos + 8]
        self.pos += 8
        return struct.unpack('<d', b)[0]

    def read_string(self, size_t_size: int = 4) -> Optional[str]:
        sz = self.read_size_t(size_t_size)
        if sz == 0:
            return None
        s = self.data[self.pos:self.pos + sz - 1]
        self.pos += sz
        return s.decode('latin-1')

    def read_prototype(self, size_t_size: int = 4) -> Prototype:
        proto = Prototype()
        proto.source = self.read_string(size_t_size)
        proto.line_defined = self.read_int()
        proto.last_line_defined = self.read_int()
        proto.num_upvalues = self.read_byte()
        proto.num_params = self.read_byte()
        is_vararg = self.read_byte()
        proto.is_vararg = bool(is_vararg & 2)
        proto.max_stack_size = self.read_byte()

        n_inst = self.read_int()
        for _ in range(n_inst):
            raw = self.read_uint()
            proto.instructions.append(decode_instruction(raw))

        n_const = self.read_int()
        for _ in range(n_const):
            t = self.read_byte()
            if t == 0:
                proto.constants.append(Constant.nil())
            elif t == 1:
                proto.constants.append(Constant.boolean(bool(self.read_byte())))
            elif t == 3:
                proto.constants.append(Constant.number(self.read_double()))
            elif t == 4:
                s = self.read_string(size_t_size)
                proto.constants.append(Constant.string(s or ""))
            else:
                proto.constants.append(Constant.nil())

        n_protos = self.read_int()
        for _ in range(n_protos):
            proto.protos.append(self.read_prototype(size_t_size))

        n_lines = self.read_int()
        for _ in range(n_lines):
            proto.line_info.append(self.read_int())

        n_locals = self.read_int()
        for _ in range(n_locals):
            name = self.read_string(size_t_size) or ""
            start_pc = self.read_int()
            end_pc = self.read_int()
            proto.local_vars.append(LocalVar(name=name, start_pc=start_pc, end_pc=end_pc))

        n_upvals = self.read_int()
        for _ in range(n_upvals):
            name = self.read_string(size_t_size) or ""
            proto.upvalue_descs.append(UpvalueDesc(name=name))

        return proto


def load_bytecode(data: bytes) -> Optional[Prototype]:
    if len(data) < 12:
        return None
    reader = BytecodeReader(data)

    header = reader.read_byte()
    if header != 0x1B:
        return None
    sig = reader.data[reader.pos:reader.pos + 3]
    reader.pos += 3
    if sig != b'Lua':
        return None

    version = reader.read_byte()
    if version != 0x51:
        return None

    format_ver = reader.read_byte()
    endianness = reader.read_byte()
    int_size = reader.read_byte()
    size_t_size = reader.read_byte()
    inst_size = reader.read_byte()
    number_size = reader.read_byte()
    integral_flag = reader.read_byte()

    return reader.read_prototype(size_t_size)


class PrototypeCFG:
    def __init__(self, proto: Prototype):
        self.proto = proto
        self.leaders: List[int] = []
        self.blocks: Dict[int, List[int]] = {}
        self.edges: Dict[int, List[int]] = {}

    def build(self):
        leaders = {0}
        n = len(self.proto.instructions)
        for pc in range(n):
            inst = self.proto.instructions[pc]
            if inst.opcode == OpCode.JMP:
                target = pc + 1 + inst.sBx
                leaders.add(target)
                if pc + 1 < n:
                    leaders.add(pc + 1)
            elif inst.opcode in (OpCode.EQ, OpCode.LT, OpCode.LE, OpCode.TEST, OpCode.TESTSET):
                if pc + 1 < n:
                    leaders.add(pc + 1)
                if pc + 2 < n:
                    leaders.add(pc + 2)
                    jmp_inst = self.proto.instructions[pc + 1]
                    if jmp_inst.opcode == OpCode.JMP:
                        leaders.add(pc + 2 + jmp_inst.sBx)
            elif inst.opcode == OpCode.FORLOOP:
                target = pc + 1 + inst.sBx
                leaders.add(target)
                if pc + 1 < n:
                    leaders.add(pc + 1)
            elif inst.opcode == OpCode.FORPREP:
                target = pc + 1 + inst.sBx
                leaders.add(target)
            elif inst.opcode == OpCode.TFORLOOP:
                if pc + 1 < n:
                    leaders.add(pc + 1)
            elif inst.opcode == OpCode.RETURN:
                if pc + 1 < n:
                    leaders.add(pc + 1)
            elif inst.opcode == OpCode.LOADBOOL and inst.C != 0:
                if pc + 2 < n:
                    leaders.add(pc + 2)

        self.leaders = sorted(leaders)

        for i, leader in enumerate(self.leaders):
            end = self.leaders[i + 1] if i + 1 < len(self.leaders) else n
            self.blocks[leader] = list(range(leader, end))

        for leader, pcs in self.blocks.items():
            if not pcs:
                continue
            last_pc = pcs[-1]
            inst = self.proto.instructions[last_pc]
            succs = []

            if inst.opcode == OpCode.JMP:
                target = last_pc + 1 + inst.sBx
                succs.append(target)
            elif inst.opcode in (OpCode.EQ, OpCode.LT, OpCode.LE, OpCode.TEST, OpCode.TESTSET):
                if last_pc + 1 < n:
                    succs.append(last_pc + 1)
            elif inst.opcode == OpCode.FORLOOP:
                target = last_pc + 1 + inst.sBx
                succs.append(target)
                if last_pc + 1 < n:
                    succs.append(last_pc + 1)
            elif inst.opcode == OpCode.FORPREP:
                target = last_pc + 1 + inst.sBx
                succs.append(target)
            elif inst.opcode == OpCode.RETURN:
                pass
            elif inst.opcode == OpCode.LOADBOOL and inst.C != 0:
                if last_pc + 2 < n:
                    succs.append(last_pc + 2)
            else:
                fallthrough = last_pc + 1
                if fallthrough < n:
                    succs.append(fallthrough)

            self.edges[leader] = succs

    def get_block_stmts(self, leader: int) -> List[Instruction]:
        return [self.proto.instructions[pc] for pc in self.blocks.get(leader, [])]
