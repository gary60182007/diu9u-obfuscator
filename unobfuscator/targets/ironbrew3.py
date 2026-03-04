from __future__ import annotations
from typing import List, Optional, Dict, Set, Tuple, Any
from dataclasses import dataclass, field
import struct
import re


IB3_STDLIB_PARAMS = [
    ('F', 'math.log'), ('s', 'string.unpack'), ('a', 'string.sub'),
    ('R', 'math.min'), ('x', 'math.abs'), ('Y', '_ENV'),
    ('X', 'coroutine.yield'), ('m', 'tonumber'), ('u', 'string.byte'),
    ('E', 'tostring'), ('O', 'math.cos'), ('h', 'math.sin'),
    ('I', 'string.len'), ('P', 'math.deg'), ('T', 'math.ceil'),
    ('G', 'pcall'), ('U', 'math.exp'), ('H', 'table.concat'),
    ('L', 'math.fmod'), ('r', 'math.sqrt'), ('B', 'math.max'),
    ('A', 'math.pow'), ('z', 'math.pi'), ('V', 'type'),
    ('f', 'select'), ('Q', 'math.rad'), ('W', 'table.unpack'),
    ('M', 'getfenv'), ('j', 'table.move'), ('y', 'string.char'),
    ('N', 'math.atan2'), ('K', 'pairs'), ('_', 'math.floor'),
    ('D', 'ipairs'), ('e', '_byte_table'),
]

LUA51_OPCODES = {
    'MOVE': 0, 'LOADK': 1, 'LOADBOOL': 2, 'LOADNIL': 3,
    'GETUPVAL': 4, 'GETGLOBAL': 5, 'GETTABLE': 6, 'SETGLOBAL': 7,
    'SETUPVAL': 8, 'SETTABLE': 9, 'NEWTABLE': 10, 'SELF': 11,
    'ADD': 12, 'SUB': 13, 'MUL': 14, 'DIV': 15, 'MOD': 16,
    'POW': 17, 'UNM': 18, 'NOT': 19, 'LEN': 20, 'CONCAT': 21,
    'JMP': 22, 'EQ': 23, 'LT': 24, 'LE': 25, 'TEST': 26,
    'TESTSET': 27, 'CALL': 28, 'TAILCALL': 29, 'RETURN': 30,
    'FORLOOP': 31, 'FORPREP': 32, 'TFORLOOP': 33, 'SETLIST': 34,
    'CLOSE': 35, 'CLOSURE': 36, 'VARARG': 37,
}


@dataclass
class IB3Constant:
    index: int
    value: Any
    type: str


@dataclass
class IB3Instruction:
    pc: int
    opcode: int
    A: int
    B: int
    C: int
    D: int
    sub: List[int] = field(default_factory=list)
    standard_op: Optional[str] = None


@dataclass
class IB3Proto:
    index: int
    instructions: List[IB3Instruction] = field(default_factory=list)
    num_params: int = 0
    is_vararg: bool = False
    max_stack: int = 0
    upvalue_count: int = 0
    sub_protos: List[int] = field(default_factory=list)


@dataclass
class IB3Chunk:
    hex_data: bytes = field(default_factory=bytes)
    constants: List[IB3Constant] = field(default_factory=list)
    protos: List[IB3Proto] = field(default_factory=list)
    entry_proto_index: int = 0
    stdlib_map: Dict[str, str] = field(default_factory=dict)
    param_names: List[str] = field(default_factory=list)


class IB3BufferReader:
    def __init__(self, data: bytes):
        self.data = data
        self.pos = 0

    def read_byte(self) -> int:
        b = self.data[self.pos]
        self.pos += 1
        return b

    def read_varint(self) -> int:
        result = 0
        for shift_idx in range(8):
            b = self.read_byte()
            result |= (b & 0x7F) << (shift_idx * 7)
            if (b & 0x80) == 0:
                break
        return result

    def read_int32(self) -> int:
        val = struct.unpack('<I', self.data[self.pos:self.pos + 4])[0]
        self.pos += 4
        return val

    def read_double(self) -> float:
        val = struct.unpack('<d', self.data[self.pos:self.pos + 8])[0]
        self.pos += 8
        return val

    def read_string(self, length: int) -> str:
        s = self.data[self.pos:self.pos + length].decode('utf-8', 'replace')
        self.pos += length
        return s

    @property
    def remaining(self) -> int:
        return len(self.data) - self.pos


class IB3Deserializer:
    CONST_TAG_STRING = 17
    CONST_TAG_NUMBER = 38
    CONST_TAG_TRUE = 18
    CONST_TAG_FALSE = 4
    CONST_TAG_NIL = 29

    def deserialize(self, data: bytes) -> Tuple[List[IB3Constant], List[IB3Proto]]:
        reader = IB3BufferReader(data)
        constants = self._read_constants(reader)
        protos = self._read_protos(reader)
        return constants, protos

    def _read_constants(self, reader: IB3BufferReader) -> List[IB3Constant]:
        count = reader.read_varint()
        constants = []
        for i in range(count):
            tag = reader.read_byte()
            if tag == self.CONST_TAG_STRING:
                slen = reader.read_varint()
                val = reader.read_string(slen) if slen > 0 else ''
                constants.append(IB3Constant(index=i, value=val, type='string'))
            elif tag == self.CONST_TAG_NUMBER:
                val = reader.read_double()
                constants.append(IB3Constant(index=i, value=val, type='number'))
            elif tag == self.CONST_TAG_TRUE:
                constants.append(IB3Constant(index=i, value=True, type='boolean'))
            elif tag == self.CONST_TAG_FALSE:
                constants.append(IB3Constant(index=i, value=False, type='boolean'))
            elif tag == self.CONST_TAG_NIL:
                constants.append(IB3Constant(index=i, value=None, type='nil'))
            else:
                break
        return constants

    def _read_protos(self, reader: IB3BufferReader) -> List[IB3Proto]:
        count = reader.read_varint()
        protos = []
        for pi in range(count):
            proto = self._read_proto(reader, pi)
            protos.append(proto)
        return protos

    def _read_proto(self, reader: IB3BufferReader, index: int) -> IB3Proto:
        inst_count = reader.read_varint()
        instructions = []
        for pc in range(inst_count):
            B = reader.read_int32()
            sub_count = reader.read_byte()
            sub_ops = [reader.read_varint() for _ in range(sub_count)]
            A = reader.read_int32()
            C = reader.read_int32()
            opcode = reader.read_int32()
            D = reader.read_int32()
            instructions.append(IB3Instruction(
                pc=pc, opcode=opcode, A=A, B=B, C=C, D=D, sub=sub_ops
            ))
        num_params = reader.read_byte()
        max_stack = 0
        for inst in instructions:
            if inst.A + 1 > max_stack:
                max_stack = inst.A + 1
        return IB3Proto(
            index=index,
            instructions=instructions,
            num_params=num_params,
            max_stack=max_stack,
        )


class IB3OpcodeClassifier:
    def __init__(self):
        self.opcode_map: Dict[int, str] = {}
        self.confidence: Dict[int, float] = {}

    def classify_from_source(self, source: str, protos: List[IB3Proto],
                              constants: List[IB3Constant]) -> Dict[int, str]:
        self._classify_from_dispatch_text(source)
        self._classify_from_bytecode_patterns(protos, constants)
        self._classify_remaining(protos, constants)
        return self.opcode_map

    def _classify_remaining(self, protos: List[IB3Proto],
                            constants: List[IB3Constant]):
        from collections import Counter
        nconst = len(constants)
        all_insts = [i for p in protos for i in p.instructions]
        op_counts = Counter(i.opcode for i in all_insts)
        max_pc = max((len(p.instructions) for p in protos), default=0)

        self._fix_misclassifications(all_insts, nconst, max_pc, protos)

        for op, cnt in op_counts.items():
            if op in self.opcode_map:
                continue
            examples = [i for i in all_insts if i.opcode == op]
            all_zero = all(e.A == 0 and e.B == 0 and e.C == 0 and e.D == 0
                          and not e.sub for e in examples)
            mostly_zero = sum(1 for e in examples
                              if e.A == 0 and e.B == 0 and e.C == 0
                              and e.D == 0) / cnt > 0.7
            if cnt >= 10 and mostly_zero:
                self.opcode_map[op] = 'SUPEROP'
                self.confidence[op] = 0.5
            elif all_zero and cnt <= 5:
                self.opcode_map[op] = 'NOP'
                self.confidence[op] = 0.3
            elif cnt >= 3:
                b_vals = [e.B for e in examples]
                d_vals = [e.D for e in examples]
                c_zero = sum(1 for e in examples if e.C == 0) / cnt
                has_sub = sum(1 for e in examples if e.sub)
                if has_sub > cnt * 0.3 and c_zero < 0.5:
                    self.opcode_map[op] = 'EQ'
                    self.confidence[op] = 0.4
                elif c_zero > 0.7 and max(b_vals) > 0 and max(d_vals) > 0:
                    self.opcode_map[op] = 'ARITH'
                    self.confidence[op] = 0.3
            if op not in self.opcode_map and cnt <= 3:
                has_mixed = len(set((e.B > 0, e.C > 0, e.D > 0, bool(e.sub))
                                    for e in examples)) > 1
                if has_mixed:
                    self.opcode_map[op] = 'SUPEROP'
                    self.confidence[op] = 0.3
                else:
                    b0 = all(e.B == 0 for e in examples)
                    c_valid = all(0 <= e.C < nconst for e in examples)
                    if b0 and c_valid:
                        self.opcode_map[op] = 'GETGLOBAL'
                        self.confidence[op] = 0.3
                    elif b0 and all(e.D > 0 for e in examples):
                        self.opcode_map[op] = 'CONCAT'
                        self.confidence[op] = 0.3
                    else:
                        self.opcode_map[op] = 'SUPEROP'
                        self.confidence[op] = 0.2

    def _fix_misclassifications(self, all_insts, nconst, max_pc, protos=None):
        from collections import Counter
        by_op = {}
        for i in all_insts:
            by_op.setdefault(i.opcode, []).append(i)

        for op, name in list(self.opcode_map.items()):
            examples = by_op.get(op, [])
            if not examples:
                continue
            cnt = len(examples)

            if name == 'GETTABLE':
                no_sub = sum(1 for e in examples if not e.sub)
                if no_sub == cnt:
                    b_zero = sum(1 for e in examples if e.B == 0) / cnt
                    if b_zero > 0.9:
                        c_vals = [e.C for e in examples]
                        if all(0 <= c < nconst for c in c_vals):
                            self.opcode_map[op] = 'GETGLOBAL'
                            self.confidence[op] = 0.7
                        elif all(c <= max_pc for c in c_vals):
                            self.opcode_map[op] = 'FORPREP'
                            self.confidence[op] = 0.6
                        else:
                            del self.opcode_map[op]
                            del self.confidence[op]

            elif name == 'MOVE':
                has_sub = sum(1 for e in examples if e.sub)
                no_sub = cnt - has_sub
                if has_sub > 0 and no_sub > 0:
                    self.opcode_map[op] = 'SUPEROP'
                    self.confidence[op] = 0.4
                elif has_sub == cnt:
                    self.opcode_map[op] = 'GETTABLE'
                    self.confidence[op] = 0.5
                elif no_sub == cnt:
                    b_zero = sum(1 for e in examples if e.B == 0)
                    if b_zero == cnt:
                        c_zero = sum(1 for e in examples if e.C == 0)
                        if c_zero == cnt:
                            self.opcode_map[op] = 'NEWTABLE'
                            self.confidence[op] = 0.5

            elif name in ('TEST', 'TEST_NOT'):
                c_vals = [e.C for e in examples]
                non_jmp = sum(1 for c in c_vals if c > max_pc * 2)
                if non_jmp > 0:
                    self.opcode_map[op] = 'LOADI'
                    self.confidence[op] = 0.6

            elif name == 'LOADNIL':
                b_vals = [e.B for e in examples]
                if all(b == 0 for b in b_vals) and all(e.C == 0 and e.D == 0 for e in examples):
                    a_vals = [e.A for e in examples]
                    if all(a == 0 for a in a_vals) and cnt <= 10:
                        self.opcode_map[op] = 'NEWTABLE'
                        self.confidence[op] = 0.45

        if protos:
            self._fix_forloop_from_forprep(protos, by_op)
            self._fix_superop_reclassify(protos, by_op, nconst, max_pc)

    def _fix_forloop_from_forprep(self, protos, by_op):
        from collections import Counter
        forprep_ops = [op for op, name in self.opcode_map.items() if name == 'FORPREP']
        if not forprep_ops:
            return
        target_opcodes = Counter()
        for proto in protos:
            insts = proto.instructions
            for inst in insts:
                if inst.opcode in forprep_ops:
                    target_pc = inst.C
                    if 0 <= target_pc < len(insts):
                        target_opcodes[insts[target_pc].opcode] += 1
        if not target_opcodes:
            return
        forloop_op, count = target_opcodes.most_common(1)[0]
        if count >= 3 and self.opcode_map.get(forloop_op) != 'FORLOOP':
            self.opcode_map[forloop_op] = 'FORLOOP'
            self.confidence[forloop_op] = 0.95

    def _fix_superop_reclassify(self, protos, by_op, nconst, max_pc):
        for op, name in list(self.opcode_map.items()):
            if name != 'SUPEROP':
                continue
            examples = by_op.get(op, [])
            if not examples:
                continue
            cnt = len(examples)
            non_zero = [e for e in examples if e.A != 0 or e.B != 0 or e.C != 0 or e.D != 0]
            if not non_zero:
                continue
            c_vals = [e.C for e in non_zero]
            if c_vals and all(0 < c <= max_pc for c in c_vals) and all(e.B == 0 for e in non_zero):
                if all(e.D == 0 for e in non_zero):
                    self.opcode_map[op] = 'TFORLOOP'
                    self.confidence[op] = 0.6
                    continue
            if cnt <= 10:
                has_sub = sum(1 for e in examples if e.sub)
                if has_sub > cnt * 0.3:
                    sub_sizes = [len(e.sub) for e in examples if e.sub]
                    if sub_sizes and max(sub_sizes) >= 2:
                        self.opcode_map[op] = 'SELF'
                        self.confidence[op] = 0.5

    def _resolve_opaque(self, expr: str) -> Optional[int]:
        expr = expr.strip()
        if re.match(r'^\d+$', expr):
            return int(expr)
        result = self._try_eval_opaque(expr)
        if result is not None:
            return result
        m = re.search(r'and\s*\(?(\d+)', expr)
        if m:
            return int(m.group(1))
        m = re.match(r'r\((\d+)\*(\d+)\)', expr)
        if m:
            import math
            return int(math.sqrt(int(m.group(1)) * int(m.group(2))))
        m = re.match(r'x\((\d+)\)', expr)
        if m:
            return int(m.group(1))
        m = re.search(r'(\d+)\*[A-Za-z]\(', expr)
        if m:
            return int(m.group(1))
        return None

    def _try_eval_opaque(self, expr: str) -> Optional[int]:
        s = expr
        s = re.sub(r"V\([^)]*\)==['\"][^'\"]*['\"]", 'true', s)
        s = re.sub(r"V\(function\(\)end\)==['\"][^'\"]*['\"]", 'true', s)
        s = re.sub(r'\bnot\s+not\s+true\b', 'true', s)
        s = re.sub(r"a\('[^']*',\d+,\d+\)==['\"][^'\"]*['\"]", 'true', s)
        s = re.sub(r'\(-?\d+\)\^2==\d+', 'true', s)
        s = re.sub(r'-?\d+\^2==\d+', 'true', s)
        for _ in range(5):
            s = re.sub(r'true\s+and\s+(\d+)\s+or\s+\d+', r'\1', s)
            s = re.sub(r'\(true\)\s*and\s*(\d+)\s+or\s+\d+', r'\1', s)
            s = re.sub(r'\(true\)\s*and\s*\((\d+)\)\s*or\s*\d+', r'\1', s)
        s = re.sub(r'#\{\}', '0', s)
        s = re.sub(r"#'([^']*)'", lambda m: str(len(m.group(1))), s)
        s = re.sub(r'[A-Za-z_]\w*\([^)]*\)', '0', s)
        s = re.sub(r'\b[A-Za-z_]\w*\b', '0', s)
        s = s.replace('^', '**')
        s = re.sub(r'[^0-9+\-*/(). ]', '', s)
        s = s.strip()
        if not s or not re.match(r'^[\d+\-*/(). ]+$', s):
            return None
        try:
            result = eval(s)
            if isinstance(result, (int, float)) and result >= 0 and result == int(result) and result < 10000:
                return int(result)
        except:
            pass
        return None

    def _classify_from_dispatch_text(self, source: str):
        vm_start = source.find('Ph=function(c,Rh,mh)')
        if vm_start < 0:
            return
        vm_code = source[vm_start:vm_start + 50000]

        comparisons = self._find_all_wh_comparisons(vm_code)
        for pos, end, comp_op, comp_val in comparisons:
            handler = vm_code[end:end + 500]
            for breaker in ['else do if Wh', 'end end end end end else',
                           'else do if Wh<=', 'else do if Wh>=',
                           'end else do if Wh']:
                bp = handler.find(breaker)
                if 0 < bp < len(handler):
                    handler = handler[:bp]

            cls = self._classify_handler_text(handler)
            if cls and comp_op == '==':
                if comp_val not in self.opcode_map:
                    self.opcode_map[comp_val] = cls
                    self.confidence[comp_val] = 0.9

        handler_patterns = [
            ('Ih[Ah]=Ih[Qh]+Ih[', 'ADD'),
            ('Ih[Ah]=Ih[Qh]-Ih[', 'SUB'),
            ('Ih[Ah]=Ih[Qh]*Ih[', 'MUL'),
            ('Ih[Ah]=Ih[Qh]/Ih[', 'DIV'),
            ('Ih[Ah]=Ih[Qh]%Ih[', 'MOD'),
            ('Ih[Ah]=Ih[Qh]^Ih[', 'POW'),
            ('Ih[Ah]=-Ih[', 'UNM'),
            ('Ih[Ah]=not Ih[', 'NOT'),
            ('Ih[Ah]=#Ih[', 'LEN'),
            ('Ih[Ah]={}', 'NEWTABLE'),
            ('Ih[Ah]=Hh[zh]', 'LOADK'),
            ('Ih[Ah]=Y[Hh[zh]]', 'GETGLOBAL'),
            ('Y[Hh[zh]]=Ih[Ah]', 'SETGLOBAL'),
            ('Ih[Ah]=nil', 'LOADNIL'),
            ('Ih[Ah]=zh', 'LOADBOOL'),
            ('Ih[Ah]=true', 'LOADBOOL'),
            ('Ih[Ah]=false', 'LOADBOOL'),
            ('Ih[Ah]=M[', 'GETUPVAL'),
            ('return W(Ih', 'RETURN'),
            ('j(Ih', 'SETLIST'),
        ]

        for pattern, op_name in handler_patterns:
            for pm in re.finditer(re.escape(pattern), vm_code):
                wh_val = self._find_near_wh_eq(vm_code, pm.start())
                if wh_val is None:
                    wh_val = self._find_implicit_wh(vm_code, pm.start())
                if wh_val is not None and wh_val not in self.opcode_map:
                    self.opcode_map[wh_val] = op_name
                    self.confidence[wh_val] = 0.8

        self._find_call_handlers(vm_code)
        self._find_closure_handler(vm_code)
        self._find_getupval_mh_handler(vm_code)
        self._find_test_handlers(vm_code)
        self._find_move_handler(vm_code)
        self._find_concat_handler(vm_code)
        self._find_gettable_handlers(vm_code)
        self._find_settable_handlers(vm_code)
        self._find_self_handler(vm_code)
        self._find_forloop_handler(vm_code)
        self._find_jmp_handler(vm_code)
        self._find_comparison_handlers(vm_code)
        self._find_field_env_handlers(vm_code)
        self._find_superop_handlers(vm_code)
        self._find_patch_handlers(vm_code)
        self._find_forloop_ib3(vm_code)
        self._find_setupval_handlers(vm_code)
        self._find_return_handlers(vm_code)
        self._find_arith_handlers(vm_code)

    def _classify_handler_text(self, code: str) -> Optional[str]:
        if 'Ih[Ah]=Ih[Qh]+Ih[' in code: return 'ADD'
        if 'Ih[Ah]=Ih[Qh]-Ih[' in code: return 'SUB'
        if 'Ih[Ah]=Ih[Qh]*Ih[' in code: return 'MUL'
        if 'Ih[Ah]=Ih[Qh]/Ih[' in code: return 'DIV'
        if 'Ih[Ah]=Ih[Qh]%Ih[' in code: return 'MOD'
        if 'Ih[Ah]=Ih[Qh]^Ih[' in code: return 'POW'
        if 'Ih[Ah]=-Ih[' in code: return 'UNM'
        if 'Ih[Ah]=not Ih[' in code: return 'NOT'
        if 'Ih[Ah]=#Ih[' in code: return 'LEN'
        if 'Ih[Ah]={}' in code: return 'NEWTABLE'
        if 'Ih[Ah]=Hh[zh]' in code: return 'LOADK'
        if 'Ih[Ah]=Y[Hh[zh]]' in code: return 'GETGLOBAL'
        if 'Y[Hh[zh]]=Ih[Ah]' in code: return 'SETGLOBAL'
        if 'Ih[Ah]=nil' in code and len(code) < 200: return 'LOADNIL'
        if 'Ih[Ah]=zh' in code and len(code) < 150: return 'LOADBOOL'
        if 'return W(Ih' in code: return 'RETURN'
        if 'Ih[Ah]=M[' in code: return 'GETUPVAL'
        if 'M[' in code and ']=Ih[Ah]' in code: return 'SETUPVAL'
        if 'Ih[Ah]=Ih[Qh][Hh[' in code: return 'GETTABLE'
        if 'Ih[Ah]=Ih[Qh][Ih[' in code: return 'GETTABLE'
        if 'Ih[Qh][Ih[Vh]]=Ih[Ah]' in code: return 'SETTABLE'
        if 'Ih[Qh][Hh[' in code and ']=Ih[Ah]' in code: return 'SETTABLE'
        if 'Ih[Ah]=Ih[Qh]..' in code: return 'CONCAT'
        if 'Ih[Ah]then' in code and 'rh=zh' in code:
            if 'then else do rh=zh' in code or 'then else do rh' in code:
                return 'TEST_NOT'
            return 'TEST'
        if 'Ih[Ah](W(Ih' in code: return 'CALL'
        if 'Y[Hh[fh[' in code: return 'GETFIELD_ENV'
        if 'hh(' in code or 'hh(Ih' in code: return 'CLOSURE'
        if 'j(Ih' in code: return 'SETLIST'
        if 'Bh=Gh[rh]' in code: return 'SUPEROP'
        if 'rh=rh-1' in code and 'c[31]=' in code: return 'PATCH_OP'
        if 'do rh=zh' in code and 'Ih[' not in code: return 'JMP'
        if 'Ih[Ah]=Ih[Qh]' in code:
            after = code[code.find('Ih[Ah]=Ih[Qh]') + 14:]
            if not after or after[0] not in '[+\\-*/%^.':
                return 'MOVE'
        return None

    def _find_near_wh_eq(self, vm_code: str, pattern_pos: int) -> Optional[int]:
        best = None
        best_dist = 300
        wh_patterns = [
            r'Wh==\s*\(([^)]*?)\)',
            r'Wh==\s*(\d+)',
            r'Wh==\s*\(\(([^)]*?)\)\)',
        ]
        for pat in wh_patterns:
            for m in re.finditer(pat, vm_code[:pattern_pos + 5]):
                val = self._resolve_opaque(m.group(1))
                if val is not None:
                    dist = pattern_pos - m.end()
                    if 0 < dist < best_dist:
                        best_dist = dist
                        best = val
        return best

    @staticmethod
    def _extract_balanced(text: str, start: int) -> Optional[str]:
        if start >= len(text) or text[start] != '(':
            return None
        depth = 0
        for i in range(start, min(start + 200, len(text))):
            if text[i] == '(':
                depth += 1
            elif text[i] == ')':
                depth -= 1
                if depth == 0:
                    return text[start + 1:i]
        return None

    def _find_wh_comparisons_in(self, text: str):
        results = []
        for m in re.finditer(r'Wh\s*([><=!~]+)\s*', text):
            op = m.group(1)
            after = text[m.end():]
            num_m = re.match(r'(\d+)', after)
            if num_m:
                expr = num_m.group(1)
                end_pos = m.end() + num_m.end()
            elif after and after[0] == '(':
                expr = self._extract_balanced(text, m.end())
                if expr is None:
                    continue
                end_pos = m.end() + len(expr) + 2
            else:
                continue
            v = self._resolve_opaque(expr)
            if v is not None:
                results.append((m.start(), end_pos, op, v))
        return results

    def _find_implicit_wh(self, vm_code: str, pattern_pos: int) -> Optional[int]:
        best = None
        best_dist = 300
        search_start = max(0, pattern_pos - 250)
        search_back = vm_code[search_start:pattern_pos]

        for pat in [r'Wh==\s*\(([^)]*?)\)', r'Wh==\s*(\d+)', r'Wh==\s*\(\(([^)]*?)\)\)']:
            for m in re.finditer(pat, vm_code[:pattern_pos + 5]):
                v = self._resolve_opaque(m.group(1))
                if v is not None:
                    dist = pattern_pos - m.end()
                    if 0 < dist < best_dist:
                        best_dist = dist
                        best = v

        for start_pos, end_pos, op, v in self._find_wh_comparisons_in(search_back):
            between = search_back[end_pos:]
            dist = len(search_back) - end_pos
            if op == '==' and dist < best_dist:
                best_dist = dist
                best = v
            elif op in ('>', '>='):
                if 'else' in between:
                    if dist < best_dist:
                        best_dist = dist
                        best = v
                elif 'then' in between:
                    after_then = between[between.find('then') + 4:]
                    if 'Wh' not in after_then and 'else' not in after_then:
                        if dist < best_dist:
                            best_dist = dist
                            best = v + 1
            elif op == '<':
                if 'else' in between:
                    if dist < best_dist:
                        best_dist = dist
                        best = v
                elif 'then' in between:
                    after_then = between[between.find('then') + 4:]
                    if 'Wh' not in after_then and 'else' not in after_then:
                        if dist < best_dist:
                            best_dist = dist
                            best = v - 1
            elif op == '<=' and dist < best_dist:
                best_dist = dist
                best = v
        return best

    def _find_all_wh_comparisons(self, vm_code: str):
        results = []
        for m in re.finditer(r'Wh\s*([><=!~]+)\s*', vm_code):
            op = m.group(1)
            after = vm_code[m.end():]
            num_m = re.match(r'(\d+)', after)
            if num_m:
                expr = num_m.group(1)
                end_pos = m.end() + num_m.end()
            elif after and after[0] == '(':
                expr = self._extract_balanced(vm_code, m.end())
                if expr is None:
                    continue
                end_pos = m.end() + len(expr) + 2
            else:
                continue
            rest = vm_code[end_pos:end_pos + 10]
            if not re.match(r'\s*then', rest):
                continue
            then_m = re.match(r'\s*then', rest)
            end_pos += then_m.end()
            v = self._resolve_opaque(expr)
            if v is not None:
                results.append((m.start(), end_pos, op, v))
        results.sort(key=lambda x: x[0])
        seen = set()
        deduped = []
        for r in results:
            if r[0] not in seen:
                seen.add(r[0])
                deduped.append(r)
        return deduped

    def _find_call_handlers(self, vm_code: str):
        for m in re.finditer(r'Ih\[Ah\]\(W\(Ih', vm_code):
            context = vm_code[max(0, m.start()-200):m.start()+400]
            wh_val = self._find_near_wh_eq(vm_code, m.start())
            if 'return' in context[200:] and 'W(Ih' in context:
                if wh_val and wh_val not in self.opcode_map:
                    self.opcode_map[wh_val] = 'TAILCALL'
                    self.confidence[wh_val] = 0.8

        for m in re.finditer(r'Z\(Ih\[Ah\]\(W\(Ih', vm_code):
            context = vm_code[max(0, m.start()-400):m.start()+600]
            if 'Qh==0' in context or 'Uh=' in context:
                for wm in re.finditer(r'Wh([<>=]+)\s*\(([^)]*?)\)', context[:400]):
                    val = self._resolve_opaque(wm.group(2))
                    if val and val not in self.opcode_map:
                        self.opcode_map[val] = 'CALL'
                        self.confidence[val] = 0.7

    def _find_test_handlers(self, vm_code: str):
        for m in re.finditer(r'if Ih\[Ah\]then do rh=zh', vm_code):
            wh_val = self._find_near_wh_eq(vm_code, m.start())
            if wh_val and wh_val not in self.opcode_map:
                self.opcode_map[wh_val] = 'TEST'
                self.confidence[wh_val] = 0.9

        for m in re.finditer(r'if Ih\[Ah\]then else do rh=zh', vm_code):
            wh_val = self._find_near_wh_eq(vm_code, m.start())
            if wh_val and wh_val not in self.opcode_map:
                self.opcode_map[wh_val] = 'TEST_NOT'
                self.confidence[wh_val] = 0.85

    def _find_move_handler(self, vm_code: str):
        for m in re.finditer(r'Ih\[Ah\]=Ih\[Qh\]end', vm_code):
            wh_val = self._find_near_wh_eq(vm_code, m.start())
            if wh_val and wh_val not in self.opcode_map:
                self.opcode_map[wh_val] = 'MOVE'
                self.confidence[wh_val] = 0.9

    def _find_concat_handler(self, vm_code: str):
        for m in re.finditer(r'Ih\[Ah\]=Ih\[Qh\]\.\.Ih\[', vm_code):
            wh_val = self._find_implicit_wh(vm_code, m.start())
            if wh_val is not None:
                existing_conf = self.confidence.get(wh_val, 0)
                if wh_val not in self.opcode_map or existing_conf < 0.9:
                    self.opcode_map[wh_val] = 'CONCAT'
                    self.confidence[wh_val] = 0.9

    def _find_gettable_handlers(self, vm_code: str):
        for m in re.finditer(r'Ih\[Ah\]=Ih\[Qh\]\[Ih\[Vh\]\]', vm_code):
            wh_val = self._find_implicit_wh(vm_code, m.start())
            if wh_val is not None:
                existing_conf = self.confidence.get(wh_val, 0)
                if wh_val not in self.opcode_map or existing_conf < 0.9:
                    self.opcode_map[wh_val] = 'GETTABLE'
                    self.confidence[wh_val] = 0.9

        for m in re.finditer(r'Ih\[Ah\]=Ih\[Qh\]\[Hh\[fh\[', vm_code):
            wh_val = self._find_implicit_wh(vm_code, m.start())
            if wh_val is not None:
                existing_conf = self.confidence.get(wh_val, 0)
                if wh_val not in self.opcode_map or existing_conf < 0.85:
                    self.opcode_map[wh_val] = 'GETTABLE'
                    self.confidence[wh_val] = 0.85

    def _find_settable_handlers(self, vm_code: str):
        for m in re.finditer(r'Ih\[Qh\]\[Ih\[Vh\]\]=Ih\[Ah\]', vm_code):
            wh_val = self._find_implicit_wh(vm_code, m.start())
            if wh_val is not None:
                existing_conf = self.confidence.get(wh_val, 0)
                if wh_val not in self.opcode_map or existing_conf < 0.92:
                    self.opcode_map[wh_val] = 'SETTABLE'
                    self.confidence[wh_val] = 0.92

        for m in re.finditer(r'Ih\[Qh\]\[Hh\[fh\[', vm_code):
            ctx = vm_code[m.start():m.start()+100]
            if ']=Ih[Ah]' in ctx:
                wh_val = self._find_implicit_wh(vm_code, m.start())
                if wh_val is not None:
                    existing_conf = self.confidence.get(wh_val, 0)
                    if wh_val not in self.opcode_map or existing_conf < 0.92:
                        self.opcode_map[wh_val] = 'SETTABLE'
                        self.confidence[wh_val] = 0.92

    def _find_self_handler(self, vm_code: str):
        for m in re.finditer(r'Ih\[Ah\+1\]=Ih\[Qh\]', vm_code):
            ctx = vm_code[m.start():m.start()+200]
            if 'Ih[Ah]=Ih[Qh][Hh[' in ctx:
                wh_val = self._find_near_wh_eq(vm_code, m.start())
                if wh_val and wh_val not in self.opcode_map:
                    self.opcode_map[wh_val] = 'SELF'
                    self.confidence[wh_val] = 0.9

    def _find_closure_handler(self, vm_code: str):
        for m in re.finditer(r'c\[5\]\[zh\]', vm_code):
            ctx = vm_code[m.start():m.start()+300]
            if 'Ph(' in ctx:
                wh_val = self._find_implicit_wh(vm_code, m.start())
                if wh_val is not None:
                    existing_conf = self.confidence.get(wh_val, 0)
                    if wh_val not in self.opcode_map or existing_conf < 0.95:
                        self.opcode_map[wh_val] = 'CLOSURE'
                        self.confidence[wh_val] = 0.95

    def _find_getupval_mh_handler(self, vm_code: str):
        for m in re.finditer(r'mh\[Qh\]', vm_code):
            ctx = vm_code[m.start():m.start()+80]
            if '[39]' in ctx and '[37]' in ctx and 'Ih[Ah]=' in vm_code[max(0,m.start()-20):m.start()+80]:
                wh_val = self._find_implicit_wh(vm_code, m.start())
                if wh_val is not None:
                    existing_conf = self.confidence.get(wh_val, 0)
                    if wh_val not in self.opcode_map or existing_conf < 0.90:
                        self.opcode_map[wh_val] = 'GETUPVAL'
                        self.confidence[wh_val] = 0.90

    def _find_forloop_handler(self, vm_code: str):
        for m in re.finditer(r'Ih\[Ah\+2\]=Ih\[Ah\+3\]', vm_code):
            ctx = vm_code[m.start():m.start()+100]
            if 'rh=zh' in ctx:
                wh_val = self._find_near_wh_eq(vm_code, m.start())
                if wh_val and wh_val not in self.opcode_map:
                    self.opcode_map[wh_val] = 'FORLOOP'
                    self.confidence[wh_val] = 0.85

        for m in re.finditer(r'Ih\[Ah\]=Ih\[Ah\]-Ih\[Ah\+2\]', vm_code):
            wh_val = self._find_near_wh_eq(vm_code, m.start())
            if wh_val and wh_val not in self.opcode_map:
                self.opcode_map[wh_val] = 'FORPREP'
                self.confidence[wh_val] = 0.9

    def _find_jmp_handler(self, vm_code: str):
        for m in re.finditer(r'do rh=zh;?end', vm_code):
            ctx = vm_code[max(0, m.start()-60):m.start()]
            if 'Ih[' not in ctx or 'then' in ctx:
                continue
            wh_val = self._find_near_wh_eq(vm_code, m.start())
            if wh_val and wh_val not in self.opcode_map:
                self.opcode_map[wh_val] = 'JMP'
                self.confidence[wh_val] = 0.85

    def _find_comparison_handlers(self, vm_code: str):
        for m in re.finditer(r'Ih\[Qh\]==Ih\[Vh\]', vm_code):
            ctx = vm_code[m.start():m.start()+200]
            if 'rh=zh' in ctx:
                wh_val = self._find_near_wh_eq(vm_code, m.start())
                if wh_val and wh_val not in self.opcode_map:
                    self.opcode_map[wh_val] = 'EQ'
                    self.confidence[wh_val] = 0.8

        for m in re.finditer(r'Ih\[Qh\]<Ih\[Vh\]', vm_code):
            ctx = vm_code[m.start()-5:m.start()+200]
            if '<=' not in ctx[:10] and 'rh=zh' in ctx:
                wh_val = self._find_near_wh_eq(vm_code, m.start())
                if wh_val and wh_val not in self.opcode_map:
                    self.opcode_map[wh_val] = 'LT'
                    self.confidence[wh_val] = 0.8

        for m in re.finditer(r'Ih\[Qh\]<=Ih\[Vh\]', vm_code):
            ctx = vm_code[m.start():m.start()+200]
            if 'rh=zh' in ctx:
                wh_val = self._find_near_wh_eq(vm_code, m.start())
                if wh_val and wh_val not in self.opcode_map:
                    self.opcode_map[wh_val] = 'LE'
                    self.confidence[wh_val] = 0.8

        for m in re.finditer(r'Ih\[Ah\]<Ih\[fh\[', vm_code):
            ctx = vm_code[m.start():m.start()+200]
            if 'rh=zh' in ctx:
                wh_val = self._find_near_wh_eq(vm_code, m.start())
                if wh_val and wh_val not in self.opcode_map:
                    self.opcode_map[wh_val] = 'LT'
                    self.confidence[wh_val] = 0.7

    def _find_field_env_handlers(self, vm_code: str):
        for m in re.finditer(r'Ih\[Ah\]=Y\[Hh\[fh\[1\]\]\]\[Hh\[fh\[', vm_code):
            ctx = vm_code[m.start():m.start()+100]
            depth = ctx.count('][Hh[fh[')
            wh_val = self._find_near_wh_eq(vm_code, m.start())
            if wh_val and wh_val not in self.opcode_map:
                self.opcode_map[wh_val] = f'GETFIELD_ENV{depth+1}'
                self.confidence[wh_val] = 0.85

    def _find_superop_handlers(self, vm_code: str):
        for m in re.finditer(r'Bh=Gh\[rh\]', vm_code):
            wh_val = self._find_near_wh_eq(vm_code, m.start())
            if wh_val and wh_val not in self.opcode_map:
                self.opcode_map[wh_val] = 'SUPEROP'
                self.confidence[wh_val] = 0.7

    def _find_patch_handlers(self, vm_code: str):
        for m in re.finditer(r'rh=rh-1.*?c\[31\]=(\d+)', vm_code):
            patched_to = int(m.group(1))
            wh_val = self._find_near_wh_eq(vm_code, m.start())
            if wh_val and wh_val not in self.opcode_map:
                self.opcode_map[wh_val] = f'PATCH_{patched_to}'
                self.confidence[wh_val] = 0.9

    def _find_forloop_ib3(self, vm_code: str):
        for m in re.finditer(r'Ih\[Ah\+2\]=yh', vm_code):
            ctx = vm_code[max(0, m.start()-100):m.start()+200]
            if 'jh>0' in ctx or 'jh<0' in ctx or 'yh<=Mh' in ctx or 'yh>=Mh' in ctx:
                wh_val = self._find_near_wh_eq(vm_code, m.start())
                if wh_val and wh_val not in self.opcode_map:
                    self.opcode_map[wh_val] = 'FORLOOP'
                    self.confidence[wh_val] = 0.85

        for m in re.finditer(r'Ih\[Ah\]\[Ih\[Ah\+2\]\]', vm_code):
            wh_val = self._find_near_wh_eq(vm_code, m.start())
            if wh_val and wh_val not in self.opcode_map:
                self.opcode_map[wh_val] = 'TFORLOOP'
                self.confidence[wh_val] = 0.8

    def _find_setupval_handlers(self, vm_code: str):
        for m in re.finditer(r'M\[zh\]=Ih\[Ah\]', vm_code):
            wh_val = self._find_near_wh_eq(vm_code, m.start())
            if wh_val and wh_val not in self.opcode_map:
                self.opcode_map[wh_val] = 'SETUPVAL'
                self.confidence[wh_val] = 0.85
        for m in re.finditer(r'M\[Qh\]=Ih\[Ah\]', vm_code):
            wh_val = self._find_near_wh_eq(vm_code, m.start())
            if wh_val and wh_val not in self.opcode_map:
                self.opcode_map[wh_val] = 'SETUPVAL'
                self.confidence[wh_val] = 0.85

    def _find_return_handlers(self, vm_code: str):
        for m in re.finditer(r'return\s+W\(Ih', vm_code):
            wh_val = self._find_near_wh_eq(vm_code, m.start())
            if wh_val and wh_val not in self.opcode_map:
                self.opcode_map[wh_val] = 'RETURN'
                self.confidence[wh_val] = 0.85
        for m in re.finditer(r'return\s*;?\s*$', vm_code):
            pass

    def _find_arith_handlers(self, vm_code: str):
        arith_pats = [
            (r'Ih\[Ah\]\s*=\s*Ih\[\w+\]\s*\+\s*(?:Ih|Hh)\[', 'ADD'),
            (r'Ih\[Ah\]\s*=\s*Ih\[\w+\]\s*\-\s*(?:Ih|Hh)\[', 'SUB'),
            (r'Ih\[Ah\]\s*=\s*Ih\[\w+\]\s*\*\s*(?:Ih|Hh)\[', 'MUL'),
            (r'Ih\[Ah\]\s*=\s*Ih\[\w+\]\s*/\s*(?:Ih|Hh)\[', 'DIV'),
            (r'Ih\[Ah\]\s*=\s*Ih\[\w+\]\s*%\s*(?:Ih|Hh)\[', 'MOD'),
        ]
        for pat, name in arith_pats:
            for m in re.finditer(pat, vm_code):
                pos = m.start()
                before = vm_code[max(0, pos - 600):pos]
                wh_eq = list(re.finditer(r'Wh==\(?(\d+)\)?', before))
                if wh_eq:
                    wh_val = int(wh_eq[-1].group(1))
                    if wh_val not in self.opcode_map:
                        self.opcode_map[wh_val] = name
                        self.confidence[wh_val] = 0.85
                        continue
                wh_gt = list(re.finditer(r'Wh>\s*\(?.*?(\d{1,3})\s*(?:or\s+\d+)?\)?', before))
                if wh_gt:
                    try:
                        val = int(wh_gt[-1].group(1))
                        candidate = val + 1
                        if candidate not in self.opcode_map:
                            self.opcode_map[candidate] = name
                            self.confidence[candidate] = 0.7
                    except (ValueError, IndexError):
                        pass

    def _classify_from_bytecode_patterns(self, protos: List[IB3Proto],
                                          constants: List[IB3Constant]):
        from collections import defaultdict, Counter
        nconst = len(constants)
        max_inst = max((len(p.instructions) for p in protos), default=0)

        stats = defaultdict(lambda: {
            'count': 0, 'A': [], 'B': [], 'C': [], 'D': [],
            'has_sub': 0, 'sub_counts': []
        })
        for p in protos:
            for inst in p.instructions:
                s = stats[inst.opcode]
                s['count'] += 1
                s['A'].append(inst.A)
                s['B'].append(inst.B)
                s['C'].append(inst.C)
                s['D'].append(inst.D)
                if inst.sub:
                    s['has_sub'] += 1
                    s['sub_counts'].append(len(inst.sub))

        def ratio(lst, pred):
            if not lst: return 0.0
            return sum(1 for x in lst if pred(x)) / len(lst)

        for op, s in stats.items():
            if op in self.opcode_map:
                continue
            count = s['count']
            if count == 0:
                continue

            sub_ratio = s['has_sub'] / count
            sub_sizes = s['sub_counts']
            b_zero = ratio(s['B'], lambda x: x == 0)
            c_zero = ratio(s['C'], lambda x: x == 0)
            d_zero = ratio(s['D'], lambda x: x == 0)
            max_a = max(s['A']) if s['A'] else 0
            max_b = max(s['B']) if s['B'] else 0
            max_c = max(s['C']) if s['C'] else 0
            max_d = max(s['D']) if s['D'] else 0

            if sub_ratio > 0.9:
                common_sc = Counter(sub_sizes).most_common(1)[0][0] if sub_sizes else 0
                if common_sc == 1:
                    self.opcode_map[op] = 'GETTABLE'
                    self.confidence[op] = 0.6
                elif common_sc == 2:
                    self.opcode_map[op] = 'GETFIELD_ENV2'
                    self.confidence[op] = 0.6
                elif common_sc == 3:
                    self.opcode_map[op] = 'GETFIELD_ENV3'
                    self.confidence[op] = 0.6
                else:
                    self.opcode_map[op] = 'FIELD_OP'
                    self.confidence[op] = 0.5
                continue

            if c_zero > 0.95 and max_b <= 10 and max_b > 0 and max_d <= 5:
                b_vals = set(s['B'])
                d_vals = set(s['D'])
                if len(b_vals) > 2 and len(d_vals) <= 5:
                    self.opcode_map[op] = 'CALL'
                    self.confidence[op] = 0.6
                    continue

            if c_zero > 0.95 and d_zero > 0.95 and max_b == 0 and max_a > 0:
                self.opcode_map[op] = 'LOADNIL'
                self.confidence[op] = 0.5
                continue

            if b_zero > 0.95 and d_zero > 0.95 and max_c > max_inst * 0.3:
                a_vals = set(s['A'])
                if len(a_vals) > 1:
                    self.opcode_map[op] = 'TEST'
                    self.confidence[op] = 0.5
                elif len(a_vals) == 1 and 0 in a_vals:
                    self.opcode_map[op] = 'JMP'
                    self.confidence[op] = 0.5
                continue

            if b_zero > 0.95 and max_c > 50 and max_c <= nconst + 10:
                self.opcode_map[op] = 'LOADK'
                self.confidence[op] = 0.5
                continue

            if c_zero > 0.95 and d_zero > 0.95 and max_b > 0:
                b_vals = Counter(s['B'])
                if len(b_vals) <= 4 and max_b <= 3:
                    self.opcode_map[op] = 'RETURN'
                    self.confidence[op] = 0.45
                elif max_b <= max_a + 2:
                    self.opcode_map[op] = 'MOVE'
                    self.confidence[op] = 0.4
                continue

            if c_zero > 0.95 and max_b > 0 and max_d > 0:
                if max_b <= max_a + 5 and max_d <= max_a + 5:
                    self.opcode_map[op] = 'ARITH'
                    self.confidence[op] = 0.35
                continue


class _DecompCtx:
    __slots__ = ('instructions', 'jump_targets', 'skip_labels', 'if_block_ends',
                 'forloop_ranges', 'tforloop_ranges', 'closure_skip',
                 'declared_regs', 'proto', 'n_inst', 'proto_index')
    def __init__(self, instructions, jump_targets, skip_labels, if_block_ends,
                 forloop_ranges, tforloop_ranges, closure_skip,
                 declared_regs, proto, n_inst, proto_index=0):
        self.instructions = instructions
        self.jump_targets = jump_targets
        self.skip_labels = skip_labels
        self.if_block_ends = if_block_ends
        self.forloop_ranges = forloop_ranges
        self.tforloop_ranges = tforloop_ranges
        self.closure_skip = closure_skip
        self.declared_regs = declared_regs
        self.proto = proto
        self.n_inst = n_inst
        self.proto_index = proto_index


class IB3Decompiler:
    def __init__(self, constants: List[IB3Constant], protos: List[IB3Proto],
                 opcode_map: Dict[int, str], stdlib_map: Dict[str, str],
                 entry_proto_index: Optional[int] = None,
                 env_map: Optional[Dict[str, str]] = None):
        self.constants = constants
        self.protos = protos
        self.opcode_map = opcode_map
        self.stdlib_map = stdlib_map
        self._entry_proto_index = entry_proto_index
        self._env_map = env_map or {}
        self._patch_map: Dict[int, int] = {}
        for op, name in opcode_map.items():
            if name.startswith('PATCH_'):
                try:
                    self._patch_map[op] = int(name.split('_')[1])
                except (ValueError, IndexError):
                    pass
        self._decompiled_protos: Dict[int, str] = {}

    def decompile_all(self) -> str:
        self._apply_patches()
        lines = []
        lines.append(f'-- IronBrew 3 Deobfuscated Output')
        lines.append(f'-- Constants: {len(self.constants)}, Protos: {len(self.protos)}')
        total_inst = sum(len(p.instructions) for p in self.protos)
        lines.append(f'-- Instructions: {total_inst}, Opcodes: {len(self.opcode_map)}')
        lines.append('')

        closure_children = set()
        for proto in self.protos:
            for inst in proto.instructions:
                if self.opcode_map.get(inst.opcode) == 'CLOSURE':
                    if 0 <= inst.C < len(self.protos):
                        closure_children.add(inst.C)

        entry = self._find_entry_proto()

        for pi, proto in enumerate(self.protos):
            proto_lines = self._decompile_proto(pi, depth=0)
            self._decompiled_protos[pi] = proto_lines

        for pi in range(len(self.protos)):
            if pi == entry or pi in closure_children:
                continue
            if pi in self._decompiled_protos:
                content = self._decompiled_protos[pi].strip()
                if content and content != 'end':
                    nparams = self.protos[pi].num_params
                    params = ', '.join(f'p{i}' for i in range(nparams))
                    lines.append(f'local function proto_{pi}({params})')
                    lines.append(content)
                    lines.append('end')
                    lines.append('')

        if entry in self._decompiled_protos:
            lines.append(f'-- Entry point (proto {entry})')
            lines.append(self._decompiled_protos[entry])
        return self._cleanup_output('\n'.join(lines))

    def _apply_patches(self):
        for proto in self.protos:
            for inst in proto.instructions:
                if inst.opcode in self._patch_map:
                    inst.opcode = self._patch_map[inst.opcode]

    def _find_entry_proto(self) -> int:
        if self._entry_proto_index is not None and 0 <= self._entry_proto_index < len(self.protos):
            return self._entry_proto_index
        max_inst = 0
        entry = 0
        for i, p in enumerate(self.protos):
            if len(p.instructions) > max_inst:
                max_inst = len(p.instructions)
                entry = i
        return entry

    def _decompile_proto(self, proto_index: int, depth: int = 0) -> str:
        self._current_proto_index = proto_index
        proto = self.protos[proto_index]
        lines: List[str] = []
        indent = '  ' * depth
        instructions = proto.instructions
        n_inst = len(instructions)
        jump_targets = self._find_jump_targets(instructions)
        declared_regs: Set[int] = set()
        for i in range(proto.num_params):
            declared_regs.add(i)

        forloop_ranges = {}
        for pc_i, inst in enumerate(instructions):
            if self.opcode_map.get(inst.opcode) == 'FORPREP':
                forloop_pc = inst.C
                if 0 <= forloop_pc < n_inst:
                    forloop_ranges[pc_i] = forloop_pc

        tforloop_ranges = {}
        for pc_i, inst in enumerate(instructions):
            if self.opcode_map.get(inst.opcode) == 'TFORLOOP':
                exit_pc = inst.C
                if exit_pc > pc_i and exit_pc <= n_inst:
                    tforloop_ranges[pc_i] = exit_pc

        closure_skip = set()
        for pc_i, inst in enumerate(instructions):
            if self.opcode_map.get(inst.opcode) == 'CLOSURE':
                num_uv = inst.sub[0] if inst.sub else 0
                for skip_i in range(1, num_uv + 1):
                    if pc_i + skip_i < n_inst:
                        closure_skip.add(pc_i + skip_i)

        if_block_ends = {}
        for pc_i, inst in enumerate(instructions):
            op = self.opcode_map.get(inst.opcode, '')
            if op in ('TEST', 'EQ', 'LT', 'LE'):
                target = inst.C if 0 <= inst.C <= n_inst else (inst.D if 0 <= inst.D <= n_inst else -1)
                if target > pc_i:
                    if_block_ends[pc_i] = target

        skip_labels = set()
        for prep_pc, loop_pc in forloop_ranges.items():
            skip_labels.add(loop_pc)
        for tfor_pc, exit_pc in tforloop_ranges.items():
            if exit_pc - 1 > tfor_pc and exit_pc - 1 < n_inst:
                back_jmp = instructions[exit_pc - 1]
                if self.opcode_map.get(back_jmp.opcode) == 'JMP':
                    skip_labels.add(exit_pc - 1)

        ctx = _DecompCtx(instructions, jump_targets, skip_labels, if_block_ends,
                         forloop_ranges, tforloop_ranges, closure_skip,
                         declared_regs, proto, n_inst, proto_index)

        lp = f'p{proto_index}_'
        if 0 in jump_targets and 0 not in skip_labels:
            lines.append(f'{indent}::{lp}label_0::')

        self._emit_block(lines, ctx, 0, n_inst, indent, depth)

        if n_inst in jump_targets and n_inst not in skip_labels:
            lines.append(f'{indent}::{lp}label_{n_inst}::')

        return '\n'.join(lines)

    def _emit_block(self, lines, ctx, start_pc, end_pc, indent, depth):
        pc = start_pc
        while pc < end_pc:
            inst = ctx.instructions[pc]

            lp = f'p{ctx.proto_index}_'
            if pc in ctx.jump_targets and pc > 0 and pc not in ctx.skip_labels:
                lines.append(f'{indent}::{lp}label_{pc}::')

            op_name = self.opcode_map.get(inst.opcode)
            if op_name is None:
                lines.append(f'{indent}-- UNKNOWN op={inst.opcode} A={inst.A} B={inst.B} C={inst.C} D={inst.D}')
                pc += 1
                continue

            if op_name == 'FORPREP' and pc in ctx.forloop_ranges:
                forloop_pc = ctx.forloop_ranges[pc]
                A = inst.A
                lines.append(f'{indent}for r{A} = r{A}, r{A+1}, r{A+2} do')
                self._emit_block(lines, ctx, pc + 1, forloop_pc, indent + '  ', depth + 1)
                lines.append(f'{indent}end')
                pc = forloop_pc + 1
                continue

            if op_name == 'FORLOOP':
                pc += 1
                continue

            if op_name == 'TFORLOOP' and pc in ctx.tforloop_ranges:
                exit_pc = ctx.tforloop_ranges[pc]
                A = inst.A
                body_end = exit_pc
                if exit_pc - 1 > pc and exit_pc - 1 < ctx.n_inst:
                    back_jmp = ctx.instructions[exit_pc - 1]
                    if self.opcode_map.get(back_jmp.opcode) == 'JMP':
                        body_end = exit_pc - 1
                lines.append(f'{indent}for r{A+3}, r{A+4} in r{A}, r{A+1}, r{A+2} do')
                ctx.declared_regs.add(A + 3)
                ctx.declared_regs.add(A + 4)
                self._emit_block(lines, ctx, pc + 1, body_end, indent + '  ', depth + 1)
                lines.append(f'{indent}end')
                pc = exit_pc
                continue

            if pc in ctx.closure_skip:
                pc += 1
                continue

            if op_name == 'LOADBOOL' and inst.D != 0:
                val = 'true' if inst.C != 0 else 'false'
                result = [f'{indent}r{inst.A} = {val}']
                if inst.A not in ctx.declared_regs:
                    result = [f'{indent}local r{inst.A} = {val}']
                    ctx.declared_regs.add(inst.A)
                lines.extend(result)
                pc += 2
                continue

            if op_name == 'SELF':
                next_pc = pc + 1
                if next_pc < end_pc and next_pc < ctx.n_inst:
                    next_inst = ctx.instructions[next_pc]
                    next_op = self.opcode_map.get(next_inst.opcode, '')
                    if next_op == 'CALL' and next_inst.A == inst.A:
                        if inst.sub:
                            method = self._get_const_val_str(inst.sub[0])
                        else:
                            method = self._rk_str(inst.C)
                        nargs = next_inst.B
                        nrets = next_inst.D
                        if nargs > 0:
                            extra_args = ', '.join(f'r{inst.A + 2 + i}' for i in range(nargs - 1))
                            args_str = extra_args if extra_args else ''
                        else:
                            args_str = '...'
                        if re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', method):
                            call = f'r{inst.B}:{method}({args_str})'
                        else:
                            call = f'r{inst.B}[{method}]({args_str})'
                        if nrets == 0:
                            result = [f'{indent}{call}']
                        elif nrets == 1:
                            result = [f'{indent}r{inst.A} = {call}']
                        else:
                            rets = ', '.join(f'r{inst.A + i}' for i in range(nrets))
                            result = [f'{indent}{rets} = {call}']
                        if next_pc in ctx.jump_targets and next_pc not in ctx.skip_labels:
                            lines.append(f'{indent}::{lp}label_{next_pc}::')
                        lines.extend(result)
                        pc = next_pc + 1
                        continue

            if op_name in ('TEST', 'TEST_NOT', 'EQ', 'LT', 'LE') and pc in ctx.if_block_ends:
                block_end = ctx.if_block_ends[pc]
                if block_end <= end_pc:
                    A, B, C_val, D = inst.A, inst.B, inst.C, inst.D
                    sub = inst.sub or []
                    n_inst = ctx.n_inst
                    if op_name == 'TEST':
                        cond = f'not r{A}'
                    elif op_name == 'TEST_NOT':
                        cond = f'r{A}'
                    elif op_name == 'EQ':
                        if sub:
                            cond = f'r{A} ~= r{sub[0]}'
                        elif B > 0 and D > 0:
                            cond = f'r{B} ~= r{D}'
                        else:
                            cond = f'r{A} ~= nil'
                    elif op_name == 'LT':
                        if sub:
                            cond = f'r{A} >= r{sub[0]}'
                        else:
                            cond = f'r{B} >= r{D}' if A == 0 else f'r{B} < r{D}'
                    elif op_name == 'LE':
                        cond = f'r{B} > r{D}' if A == 0 else f'r{B} <= r{D}'
                    else:
                        cond = f'not r{A}'
                    lines.append(f'{indent}if {cond} then')
                    self._emit_block(lines, ctx, pc + 1, block_end, indent + '  ', depth + 1)
                    lines.append(f'{indent}end')
                    pc = block_end
                    continue

            result = self._emit_with_local(op_name, inst, ctx.proto, pc, indent, depth, ctx.declared_regs)
            lines.extend(result)
            pc += 1

    def _emit_with_local(self, op_name, inst, proto, pc, indent, depth, declared_regs):
        result = self._emit_instruction(op_name, inst, proto, pc, indent, depth)
        A = inst.A
        if op_name in ('LOADK', 'LOADBOOL', 'LOADI', 'LOADNIL', 'GETGLOBAL',
                       'GETTABLE', 'GETFIELD_ENV2', 'GETFIELD_ENV3',
                       'NEWTABLE', 'MOVE', 'ADD', 'SUB', 'MUL', 'DIV', 'MOD', 'POW',
                       'UNM', 'NOT', 'LEN', 'CONCAT', 'ARITH', 'CLOSURE',
                       'VARARG', 'GETUPVAL') or op_name.startswith('GETFIELD_ENV'):
            if A not in declared_regs and result:
                for i, line in enumerate(result):
                    stripped = line.lstrip()
                    if stripped.startswith(f'r{A} = ') or stripped.startswith(f'r{A},'):
                        result[i] = line.replace(f'r{A} = ', f'local r{A} = ', 1)
                        declared_regs.add(A)
                        break
        if op_name == 'CALL' and inst.D > 0:
            for ret_r in range(A, A + inst.D):
                if ret_r not in declared_regs and result:
                    for i, line in enumerate(result):
                        stripped = line.lstrip()
                        if stripped.startswith(f'r{ret_r}') and '=' in stripped:
                            result[i] = line.replace(f'r{ret_r}', f'local r{ret_r}', 1)
                            declared_regs.add(ret_r)
                            break
        return result

    def _find_jump_targets(self, instructions: List[IB3Instruction]) -> Set[int]:
        targets = set()
        for inst in instructions:
            op = self.opcode_map.get(inst.opcode, '')
            if op in ('JMP', 'FORLOOP', 'FORPREP', 'TEST', 'EQ', 'LT', 'LE',
                       'SUPEROP') or op.startswith('PATCH_'):
                if inst.C >= 0 and inst.C <= len(instructions):
                    targets.add(inst.C)
                if inst.D >= 0 and inst.D <= len(instructions):
                    targets.add(inst.D)
        return targets

    def _emit_instruction(self, op_name: str, inst: IB3Instruction,
                           proto: IB3Proto, pc: int, indent: str, depth: int) -> List[str]:
        A, B, C, D = inst.A, inst.B, inst.C, inst.D
        sub = inst.sub

        if op_name == 'MOVE':
            return [f'{indent}r{A} = r{B}']

        elif op_name == 'LOADK':
            return [f'{indent}r{A} = {self._const_str(C)}']

        elif op_name == 'LOADBOOL':
            val = 'true' if C != 0 else 'false'
            line = f'{indent}r{A} = {val}'
            if D != 0:
                line += f'  -- skip next'
            return [line]

        elif op_name == 'LOADI':
            if C > 0x7FFFFFFF:
                val = C - 0x100000000
            else:
                val = C
            return [f'{indent}r{A} = {val}']

        elif op_name == 'LOADNIL':
            regs = ', '.join(f'r{i}' for i in range(A, A + B + 1))
            return [f'{indent}{regs} = nil']

        elif op_name == 'GETGLOBAL':
            name = self._get_const_name(C)
            return [f'{indent}r{A} = {name}']

        elif op_name == 'SETGLOBAL':
            name = self._get_const_name(C)
            return [f'{indent}{name} = r{A}']

        elif op_name == 'GETTABLE':
            if sub:
                raw_key = self._get_const_val_str(sub[0])
                display_key = self._env_map.get(raw_key, raw_key) if self._env_map else raw_key
                if re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', display_key):
                    return [f'{indent}r{A} = r{B}.{display_key}']
                else:
                    return [f'{indent}r{A} = r{B}[{self._const_str(sub[0])}]']
            return [f'{indent}r{A} = r{B}[{self._rk_str(C)}]']

        elif op_name in ('GETFIELD_ENV2', 'GETFIELD_ENV3') or op_name.startswith('GETFIELD_ENV'):
            if len(sub) >= 2:
                parts = []
                for si, s in enumerate(sub):
                    raw = self._get_const_val_str(s)
                    if si == 0 and self._env_map:
                        raw = self._env_map.get(raw, raw)
                    parts.append(raw)
                chain = self._build_dot_chain(parts)
                return [f'{indent}r{A} = {chain}']
            elif len(sub) == 1:
                raw = self._get_const_val_str(sub[0])
                if self._env_map:
                    raw = self._env_map.get(raw, raw)
                return [f'{indent}r{A} = {raw}']
            return [f'{indent}r{A} = _G']

        elif op_name == 'SETTABLE':
            if sub:
                raw_key = self._get_const_val_str(sub[0])
                if re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', raw_key):
                    return [f'{indent}r{B}.{raw_key} = r{A}']
                else:
                    return [f'{indent}r{B}[{self._const_str(sub[0])}] = r{A}']
            return [f'{indent}r{B}[{self._rk_str(D)}] = r{A}']

        elif op_name == 'NEWTABLE':
            return [f'{indent}r{A} = {{}}']

        elif op_name == 'SELF':
            if sub:
                method = self._const_str(sub[0])
            else:
                method = self._rk_str(C)
            return [
                f'{indent}r{A + 1} = r{B}',
                f'{indent}r{A} = r{B}[{method}]'
            ]

        elif op_name in ('ADD', 'SUB', 'MUL', 'DIV', 'MOD', 'POW'):
            ops = {'ADD': '+', 'SUB': '-', 'MUL': '*', 'DIV': '/', 'MOD': '%', 'POW': '^'}
            return [f'{indent}r{A} = r{B} {ops[op_name]} r{D}']

        elif op_name == 'UNM':
            return [f'{indent}r{A} = -r{B}']
        elif op_name == 'NOT':
            return [f'{indent}r{A} = not r{B}']
        elif op_name == 'LEN':
            return [f'{indent}r{A} = #r{B}']

        elif op_name == 'CONCAT':
            end = D if D > B else B + 1
            regs = ' .. '.join(f'r{i}' for i in range(B, end + 1))
            return [f'{indent}r{A} = {regs}']

        elif op_name == 'CLOSE':
            return []

        elif op_name == 'JMP':
            lp = f'p{self._current_proto_index}_'
            return [f'{indent}goto {lp}label_{C}']

        elif op_name == 'EQ':
            lp = f'p{self._current_proto_index}_'
            n_inst = len(proto.instructions)
            if sub:
                target = C if C <= n_inst else D
                return [f'{indent}if r{A} == r{sub[0]} then goto {lp}label_{target} end']
            elif B > 0 and D > 0:
                target = C if C <= n_inst else D
                return [f'{indent}if r{B} == r{D} then goto {lp}label_{target} end']
            elif C <= n_inst:
                return [f'{indent}if r{A} == nil then goto {lp}label_{C} end']
            else:
                return [f'{indent}if r{A} == nil then goto {lp}label_{D} end']

        elif op_name == 'LT':
            lp = f'p{self._current_proto_index}_'
            if sub:
                cmp_reg = sub[0]
                return [f'{indent}if r{A} < r{cmp_reg} then goto {lp}label_{C} end']
            neg = '>=' if A != 0 else '<'
            return [f'{indent}if r{B} {neg} r{D} then goto {lp}label_{C} end']

        elif op_name == 'LE':
            lp = f'p{self._current_proto_index}_'
            neg = '>' if A != 0 else '<='
            return [f'{indent}if r{B} {neg} r{D} then goto {lp}label_{C} end']

        elif op_name == 'TEST':
            lp = f'p{self._current_proto_index}_'
            n_inst = len(proto.instructions)
            if C >= 0 and C <= n_inst:
                return [f'{indent}if r{A} then goto {lp}label_{C} end']
            elif D >= 0 and D <= n_inst:
                return [f'{indent}if r{A} then goto {lp}label_{D} end']
            return [f'{indent}-- TEST r{A} (jump target out of range: C={C})']

        elif op_name == 'TEST_NOT':
            lp = f'p{self._current_proto_index}_'
            n_inst = len(proto.instructions)
            if C >= 0 and C <= n_inst:
                return [f'{indent}if not r{A} then goto {lp}label_{C} end']
            elif D >= 0 and D <= n_inst:
                return [f'{indent}if not r{A} then goto {lp}label_{D} end']
            return [f'{indent}-- TEST_NOT r{A} (jump target out of range: C={C})']

        elif op_name == 'CALL':
            nargs = B
            nrets = D
            if nargs > 0:
                args = ', '.join(f'r{A + 1 + i}' for i in range(nargs))
            else:
                args = ''
            call = f'r{A}({args})'
            if nrets == 0:
                return [f'{indent}{call}']
            elif nrets == 1:
                return [f'{indent}r{A} = {call}']
            else:
                rets = ', '.join(f'r{A + i}' for i in range(nrets))
                return [f'{indent}{rets} = {call}']

        elif op_name == 'TAILCALL':
            nargs = B
            if nargs > 0:
                args = ', '.join(f'r{A + 1 + i}' for i in range(nargs))
            else:
                args = ''
            return [f'{indent}return r{A}({args})']

        elif op_name == 'RETURN':
            nret = B
            if nret == 0:
                return [f'{indent}return']
            vals = ', '.join(f'r{A + i}' for i in range(nret))
            return [f'{indent}return {vals}']

        elif op_name == 'ARITH':
            if B == A + 1 and D < A:
                return [f'{indent}r{A} = r{B}(r{D})']
            if B == A + 1 and D == A + 2:
                return [f'{indent}r{A} = r{B}(r{D})']
            if B <= 5 and D <= 3 and (B + D) > 0:
                nargs = B
                nrets = D
                if nargs > 0:
                    args = ', '.join(f'r{A + 1 + i}' for i in range(nargs))
                else:
                    args = ''
                call = f'r{A}({args})'
                if nrets == 0:
                    return [f'{indent}{call}']
                elif nrets == 1:
                    return [f'{indent}r{A} = {call}']
                else:
                    rets = ', '.join(f'r{A + i}' for i in range(nrets))
                    return [f'{indent}{rets} = {call}']
            if A == B and A == D:
                return [f'{indent}r{A} = r{A} * r{A}']
            if C == 0:
                return [f'{indent}r{A} = r{B} % r{D}']
            else:
                return [f'{indent}r{A} = r{B} % {self._rk_str(C)}']

        elif op_name == 'NOP':
            return []

        elif op_name == 'FORLOOP':
            lp = f'p{self._current_proto_index}_'
            return [f'{indent}-- FORLOOP r{A} step=r{A+2}, goto {lp}label_{C}']

        elif op_name == 'FORPREP':
            lp = f'p{self._current_proto_index}_'
            return [f'{indent}-- FORPREP r{A}, goto {lp}label_{C}']

        elif op_name == 'TFORLOOP':
            return [f'{indent}-- TFORLOOP r{A}']

        elif op_name == 'SETLIST':
            count = B
            if count > 0:
                vals = ', '.join(f'r{A + i}' for i in range(1, count + 1))
                return [f'{indent}r{A} = {{{vals}}}']
            return [f'{indent}-- SETLIST r{A} (variable length)']

        elif op_name == 'CLOSURE':
            if C < len(self.protos) and depth < 50:
                if not hasattr(self, '_decompiling'):
                    self._decompiling = set()
                if C not in self._decompiling:
                    self._decompiling.add(C)
                    child = self.protos[C]
                    nparams = child.num_params
                    params = ', '.join(f'p{i}' for i in range(nparams))
                    lines = [f'{indent}r{A} = function({params})']
                    body = self._decompile_proto(C, depth + 1)
                    if body.strip():
                        lines.append(body)
                    lines.append(f'{indent}end')
                    self._decompiling.discard(C)
                    return lines
            return [f'{indent}r{A} = function() end -- proto_{C}']

        elif op_name == 'VARARG':
            return [f'{indent}r{A} = ...']

        elif op_name == 'GETUPVAL':
            return [f'{indent}r{A} = upval_{B}']

        elif op_name == 'SETUPVAL':
            return [f'{indent}upval_{B} = r{A}']

        elif op_name == 'SUPEROP':
            if sub and B > 0:
                key = self._get_const_val_str(sub[0])
                if self._env_map:
                    key = self._env_map.get(key, key)
                if re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', key):
                    return [f'{indent}r{A} = r{B}.{key}']
                return [f'{indent}r{A} = r{B}[{self._const_str(sub[0])}]']
            if sub and B == 0:
                key = self._get_const_val_str(sub[0])
                if self._env_map:
                    key = self._env_map.get(key, key)
                return [f'{indent}r{A} = {key}']
            if B == 0 and C == 0 and D == 0:
                return []
            if B == 0 and not sub and C > 0 and C < len(self.constants) and D == 0:
                if self._env_map and C < len(self.constants):
                    val = self.constants[C].value
                    if isinstance(val, str) and val in self._env_map:
                        return [f'{indent}r{A} = {self._env_map[val]}']
                return [f'{indent}r{A} = {self._const_str(C)}']
            if B > 0 and C == 0 and D == 0 and not sub:
                if B == A + 1:
                    return [f'{indent}r{A}(r{B})']
                elif B > A:
                    args = ', '.join(f'r{i}' for i in range(A + 1, B + 1))
                    return [f'{indent}r{A}({args})']
                else:
                    return [f'{indent}r{A} = r{B}']
            if C > 0 and C < len(proto.instructions) and D == 0:
                lp = f'p{self._current_proto_index}_'
                return [f'{indent}goto {lp}label_{C}']
            return [f'{indent}-- SUPEROP_{inst.opcode} A={A} B={B} C={C} D={D}']

        elif op_name == 'FIELD_OP':
            if sub:
                keys = ', '.join(str(s) for s in sub)
                return [f'{indent}-- FIELD_OP r{A} sub=[{keys}]']
            return [f'{indent}-- FIELD_OP r{A}']

        return [f'{indent}-- {op_name} A={A} B={B} C={C} D={D}']

    def _const_str(self, idx: int) -> str:
        if 0 <= idx < len(self.constants):
            c = self.constants[idx]
            if c.type == 'string':
                escaped = c.value.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n').replace('\r', '\\r')
                return f'"{escaped}"'
            elif c.type == 'number':
                if c.value == int(c.value):
                    return str(int(c.value))
                return str(c.value)
            elif c.type == 'boolean':
                return 'true' if c.value else 'false'
            elif c.type == 'nil':
                return 'nil'
        return f'K[{idx}]'

    def _get_const_name(self, idx: int) -> str:
        if 0 <= idx < len(self.constants):
            c = self.constants[idx]
            if c.type == 'string':
                if re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', c.value):
                    return c.value
                escaped = c.value.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
                return f'_G["{escaped}"]'
            return self._const_str(idx)
        return f'_G[{idx}]'

    def _get_const_val_str(self, idx: int) -> str:
        if 0 <= idx < len(self.constants):
            c = self.constants[idx]
            if c.type == 'string':
                return c.value
        return f'K[{idx}]'

    def _rk_str(self, val: int) -> str:
        if val >= 256:
            return self._const_str(val - 256)
        return f'r{val}'

    def _build_dot_chain(self, parts: List[str]) -> str:
        if not parts:
            return '_G'
        result = parts[0]
        for p in parts[1:]:
            if re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', p):
                result += f'.{p}'
            else:
                escaped = p.replace('\\', '\\\\').replace('"', '\\"')
                result += f'["{escaped}"]'
        return result


    def _cleanup_output(self, source: str) -> str:
        prev = None
        result = source
        for _ in range(3):
            result = self._cleanup_pass(result)
            if result == prev:
                break
            prev = result
        prev = None
        for _ in range(4):
            result = self._expression_propagation(result)
            result = self._call_chain_fusion(result)
            result = self._multi_use_propagation(result)
            result = self._dead_init_removal(result)
            result = self._opaque_predicate_removal(result)
            result = self._cleanup_pass(result)
            if result == prev:
                break
            prev = result
        result = self._rename_registers(result)
        result = self._ssa_split_registers(result)
        result = self._rename_remaining_registers(result)
        result = self._add_local_declarations(result)
        result = self._rename_functions(result)
        result = self._goto_to_structured(result)
        prev = None
        for _ in range(3):
            result = self._expression_propagation(result)
            result = self._call_chain_fusion(result)
            result = self._multi_use_propagation(result)
            result = self._dead_init_removal(result)
            result = self._cleanup_pass(result)
            if result == prev:
                break
            prev = result
        result = self._remove_dead_locals(result)
        result = self._fix_block_structure(result)
        return result

    def _expression_propagation(self, source: str) -> str:
        lines = source.split('\n')
        changed = True
        iterations = 0
        while changed and iterations < 80:
            changed = False
            iterations += 1
            i = 0
            while i < len(lines):
                s = lines[i].strip()
                if not s:
                    i += 1
                    continue
                m = re.match(r'^(?:local\s+)?(r\d+)\s*=\s*(.+)$', s)
                if not m:
                    i += 1
                    continue
                reg = m.group(1)
                expr = m.group(2).strip()
                has_call = '(' in expr or ':' in expr
                is_const = (expr in ('nil', 'true', 'false', '...')
                            or bool(re.match(r'^-?\d+(\.\d+)?$', expr))
                            or expr.startswith('"'))
                if is_const and not has_call:
                    i += 1
                    continue
                window = 5 if has_call else 30
                reg_pat = r'\b' + re.escape(reg) + r'\b'
                expr_regs = set(re.findall(r'\br\d+\b', expr))
                uses = []
                safe = True
                intervening_calls = 0
                for j in range(i + 1, min(i + window, len(lines))):
                    sj = lines[j].strip()
                    if not sj:
                        continue
                    if sj.startswith('::') or sj in ('end', 'else', 'elseif') or sj.startswith('goto '):
                        break
                    if has_call and ('(' in sj or ':' in sj):
                        intervening_calls += 1
                        if intervening_calls > 1:
                            safe = False
                            break
                    for ereg in expr_regs:
                        if re.match(r'^(?:local\s+)?' + re.escape(ereg) + r'\s*=', sj):
                            safe = False
                            break
                    if not safe:
                        break
                    if re.search(reg_pat, sj):
                        m_reassign = re.match(r'^(?:local\s+)?' + re.escape(reg) + r'\s*=', sj)
                        if m_reassign:
                            rhs = sj[m_reassign.end():]
                            if re.search(reg_pat, rhs):
                                uses.append(j)
                            break
                        else:
                            uses.append(j)
                if safe and len(uses) == 1:
                    use_idx = uses[0]
                    use_line = lines[use_idx]
                    use_s = use_line.strip()
                    use_indent = use_line[:len(use_line) - len(use_line.lstrip())]
                    count_on_use = len(re.findall(reg_pat, use_s))
                    if count_on_use == 1:
                        eq_pos = use_s.find('=')
                        is_assign = (eq_pos > 0
                                     and use_s[eq_pos:eq_pos+2] != '=='
                                     and use_s[max(0,eq_pos-1):eq_pos+1] not in ('~=', '<=', '>='))
                        if is_assign:
                            lhs = use_s[:eq_pos]
                            rhs_part = use_s[eq_pos:]
                        else:
                            lhs = ''
                            rhs_part = use_s
                        if re.search(reg_pat, rhs_part) and not re.search(reg_pat, lhs):
                            callee_pat = re.escape(reg) + r'\s*\('
                            is_non_callable = bool(re.match(r'^(".*"|-?\d+(\.\d+)?|true|false|nil)$', expr))
                            if is_non_callable and re.search(callee_pat, use_s):
                                pass
                            else:
                                if has_call and len(expr) > 35 and re.search(r'\b' + re.escape(reg) + r'\s*\.', use_s):
                                    pass
                                elif has_call and re.search(r'\b' + re.escape(reg) + r'\s*\[', use_s):
                                    pass
                                else:
                                    inline_expr = expr
                                    if has_call and re.search(callee_pat, use_s):
                                        inline_expr = f'({expr})'
                                    new_rhs = re.sub(reg_pat, inline_expr, rhs_part)
                                    lines[use_idx] = f'{use_indent}{lhs}{new_rhs}'
                                    lines[i] = ''
                                    changed = True
                i += 1
            if changed:
                lines = [l for l in lines if l != '']
        return '\n'.join(lines)

    def _call_chain_fusion(self, source: str) -> str:
        lines = source.split('\n')
        changed = True
        while changed:
            changed = False
            i = 0
            while i < len(lines) - 1:
                s = lines[i].strip()
                m = re.match(r'^(?:local\s+)?(r\d+)\s*=\s*(.+)$', s)
                if not m:
                    i += 1
                    continue
                reg = m.group(1)
                expr = m.group(2).strip()
                j = i + 1
                while j < len(lines) and not lines[j].strip():
                    j += 1
                if j >= len(lines):
                    i += 1
                    continue
                nxt = lines[j].strip()
                nxt_indent = lines[j][:len(lines[j]) - len(lines[j].lstrip())]
                call_m = re.match(r'^' + re.escape(reg) + r'\((.*)$', nxt)
                if call_m:
                    is_non_callable = bool(re.match(r'^(".*"|-?\d+(\.\d+)?|true|false|nil)$', expr))
                    if not is_non_callable:
                        if '(' in expr or ':' in expr:
                            lines[j] = f'{nxt_indent}({expr})({call_m.group(1)}'
                        else:
                            lines[j] = f'{nxt_indent}{expr}({call_m.group(1)}'
                        lines[i] = ''
                        changed = True
                        i = j + 1
                        continue
                call_m = re.match(r'^' + re.escape(reg) + r':(\w+)\((.*)$', nxt)
                if call_m:
                    method = call_m.group(1)
                    rest = call_m.group(2)
                    if '(' in expr or ':' in expr:
                        lines[j] = f'{nxt_indent}({expr}):{method}({rest}'
                    else:
                        lines[j] = f'{nxt_indent}{expr}:{method}({rest}'
                    lines[i] = ''
                    changed = True
                    i = j + 1
                    continue
                i += 1
            if changed:
                lines = [l for l in lines if l != '']
        return '\n'.join(lines)

    def _multi_use_propagation(self, source: str) -> str:
        lines = source.split('\n')
        changed = True
        iterations = 0
        while changed and iterations < 20:
            changed = False
            iterations += 1
            i = 0
            while i < len(lines):
                s = lines[i].strip()
                m = re.match(r'^(?:local\s+)?(r\d+)\s*=\s*(.+)$', s)
                if not m:
                    i += 1
                    continue
                reg = m.group(1)
                expr = m.group(2).strip()
                if expr in ('nil', 'true', 'false', '...'):
                    i += 1
                    continue
                is_simple_field = bool(re.match(r'^[A-Za-z_]\w*(?:\.\w+)*$', expr))
                is_simple_str = bool(re.match(r'^"\w+"$', expr))
                if not (is_simple_str or is_simple_field):
                    i += 1
                    continue
                reg_pat = r'\b' + re.escape(reg) + r'\b'
                uses = []
                safe = True
                for j in range(i + 1, min(i + 20, len(lines))):
                    sj = lines[j].strip()
                    if not sj:
                        continue
                    if sj.startswith('::') or sj in ('end', 'else', 'elseif') or sj.startswith('goto '):
                        break
                    m_reassign = re.match(r'^(?:local\s+)?' + re.escape(reg) + r'\s*=', sj)
                    if m_reassign:
                        rhs = sj[m_reassign.end():]
                        if not re.search(reg_pat, rhs):
                            break
                    if re.search(reg_pat, sj):
                        uses.append(j)
                if safe and 1 <= len(uses) <= 5:
                    all_ok = True
                    for use_idx in uses:
                        use_s = lines[use_idx].strip()
                        callee_pat = re.escape(reg) + r'\s*[(]'
                        is_non_callable = bool(re.match(r'^(".*"|-?\d+(\.\d+)?|true|false|nil)$', expr))
                        if is_non_callable and re.search(callee_pat, use_s):
                            all_ok = False
                            break
                        m_lhs = re.match(r'^(?:local\s+)?' + re.escape(reg) + r'\s*=', use_s)
                        if m_lhs:
                            all_ok = False
                            break
                    if all_ok:
                        for use_idx in reversed(uses):
                            use_line = lines[use_idx]
                            use_indent = use_line[:len(use_line) - len(use_line.lstrip())]
                            use_s = use_line.strip()
                            eq_pos = use_s.find('=')
                            is_assign = (eq_pos > 0
                                         and use_s[eq_pos:eq_pos+2] != '=='
                                         and use_s[max(0,eq_pos-1):eq_pos+1] not in ('~=', '<=', '>='))
                            if is_assign:
                                lhs_part = use_s[:eq_pos+1]
                                rhs_part = use_s[eq_pos+1:]
                                new_rhs = re.sub(reg_pat, expr, rhs_part)
                                lines[use_idx] = f'{use_indent}{lhs_part}{new_rhs}'
                            else:
                                new_line = re.sub(reg_pat, expr, use_s)
                                lines[use_idx] = f'{use_indent}{new_line}'
                        lines[i] = ''
                        changed = True
                i += 1
            if changed:
                lines = [l for l in lines if l != '']
        return '\n'.join(lines)

    def _opaque_predicate_removal(self, source: str) -> str:
        lines = source.split('\n')

        def _find_const(reg, start):
            for k in range(start - 1, max(start - 20, -1), -1):
                sk = lines[k].strip()
                if sk.startswith('local function ') or sk == 'end':
                    return None
                m = re.match(r'^(?:local\s+)?' + re.escape(reg) + r'\s*=\s*(-?\d+(?:\.\d+)?)\s*$', sk)
                if m:
                    return m.group(1)
                if re.match(r'^(?:local\s+)?' + re.escape(reg) + r'\s*=', sk):
                    return None
            return None

        for i, line in enumerate(lines):
            s = line.strip()
            m = re.match(r'^if\s+(r\d+)\s+then\s+goto\s+(\w+)\s+end$', s)
            if m:
                val = _find_const(m.group(1), i)
                if val is not None:
                    indent = line[:len(line) - len(line.lstrip())]
                    lines[i] = f'{indent}goto {m.group(2)}'
                    continue
            m = re.match(r'^if\s+not\s+(r\d+)\s+then\s+goto\s+(\w+)\s+end$', s)
            if m:
                val = _find_const(m.group(1), i)
                if val is not None:
                    lines[i] = ''
                    continue
            m = re.match(r'^if\s+(r\d+)\s*([=~<>]+)\s*(r\d+)\s+then\s+goto\s+(\w+)\s+end$', s)
            if m:
                va = _find_const(m.group(1), i)
                vb = _find_const(m.group(3), i)
                if va is not None and vb is not None:
                    try:
                        a, b, op = float(va), float(vb), m.group(2)
                        result_val = None
                        if op == '==': result_val = (a == b)
                        elif op == '~=': result_val = (a != b)
                        elif op == '<': result_val = (a < b)
                        elif op == '>': result_val = (a > b)
                        elif op == '<=': result_val = (a <= b)
                        elif op == '>=': result_val = (a >= b)
                        if result_val is True:
                            indent = line[:len(line) - len(line.lstrip())]
                            lines[i] = f'{indent}goto {m.group(4)}'
                        elif result_val is False:
                            lines[i] = ''
                    except ValueError:
                        pass
        lines = [l for l in lines if l != '']
        result = []
        i = 0
        while i < len(lines):
            s = lines[i].strip()
            m = re.match(r'^if\s+(-?\d+(?:\.\d+)?)\s+then\s+goto\s+(\w+)\s+end$', s)
            if m:
                i += 1
                continue
            m = re.match(r'^if\s+not\s+(-?\d+(?:\.\d+)?)\s+then\s+goto\s+(\w+)\s+end$', s)
            if m:
                indent = lines[i][:len(lines[i]) - len(lines[i].lstrip())]
                result.append(f'{indent}goto {m.group(2)}')
                i += 1
                continue
            m = re.match(r'^if\s+"[^"]*"\s+then\s+goto\s+(\w+)\s+end$', s)
            if m:
                i += 1
                continue
            m = re.match(r'^if\s+(-?\d+(?:\.\d+)?)\s*([=~<>]+)\s*(-?\d+(?:\.\d+)?)\s+then\s+goto\s+(\w+)\s+end$', s)
            if m:
                try:
                    a, op, b = float(m.group(1)), m.group(2), float(m.group(3))
                    always_true = False
                    always_false = False
                    if op == '==' and a == b:
                        always_true = True
                    elif op == '==' and a != b:
                        always_false = True
                    elif op == '~=' and a != b:
                        always_true = True
                    elif op == '~=' and a == b:
                        always_false = True
                    elif op == '<' and a < b:
                        always_true = True
                    elif op == '<' and a >= b:
                        always_false = True
                    elif op == '>' and a > b:
                        always_true = True
                    elif op == '>' and a >= b:
                        always_false = True
                    elif op == '<=' and a <= b:
                        always_true = True
                    elif op == '<=' and a > b:
                        always_false = True
                    elif op == '>=' and a >= b:
                        always_true = True
                    elif op == '>=' and a < b:
                        always_false = True
                    if always_false:
                        i += 1
                        continue
                    elif always_true:
                        indent = lines[i][:len(lines[i]) - len(lines[i].lstrip())]
                        result.append(f'{indent}goto {m.group(4)}')
                        i += 1
                        continue
                except ValueError:
                    pass
            result.append(lines[i])
            i += 1
        return '\n'.join(result)

    def _dead_init_removal(self, source: str) -> str:
        lines = source.split('\n')
        result = []
        for i, line in enumerate(lines):
            s = line.strip()
            m = re.match(r'^(?:local\s+)?(r\d+)\s*=\s*nil\s*$', s)
            if m:
                reg = m.group(1)
                for j in range(i + 1, min(i + 5, len(lines))):
                    nj = lines[j].strip()
                    if not nj:
                        continue
                    if re.match(r'^(?:local\s+)?' + re.escape(reg) + r'\s*=\s*', nj):
                        line = ''
                        break
                    if re.search(r'\b' + re.escape(reg) + r'\b', nj):
                        break
                    break
            if not line:
                continue
            m = re.match(r'^(?:local\s+)?(r\d+)\s*=\s*(-?\d+(?:\.\d+)?|"[^"]*")\s*$', s)
            if m:
                reg = m.group(1)
                reg_pat = r'\b' + re.escape(reg) + r'\b'
                used = False
                for j in range(i + 1, min(i + 30, len(lines))):
                    nj = lines[j].strip()
                    if nj.startswith('local function ') or nj == 'end':
                        break
                    if re.match(r'^(?:local\s+)?' + re.escape(reg) + r'\s*=', nj):
                        break
                    if re.search(reg_pat, nj):
                        used = True
                        break
                if not used:
                    continue
            result.append(line)
        return '\n'.join(result)

    @staticmethod
    def _find_func_ranges(lines):
        stack = []
        func_ranges = []
        for i, line in enumerate(lines):
            s = line.strip()
            if s.startswith('local function ') or (s.startswith('function ') and s.endswith(')')):
                stack.append(('func', i))
            elif s.startswith('if ') and s.endswith(' then'):
                stack.append(('if', i))
            elif re.match(r'^for\s+.+\s+do$', s):
                stack.append(('for', i))
            elif s.startswith('while ') and s.endswith(' do'):
                stack.append(('while', i))
            elif s == 'repeat':
                stack.append(('repeat', i))
            elif s.startswith('until ') and stack and stack[-1][0] == 'repeat':
                stack.pop()
            elif s == 'end' and stack:
                tag, start = stack.pop()
                if tag == 'func':
                    func_ranges.append((start, i))
        return func_ranges

    _SKIP_FIELD_NAMES = {
        'GetService', 'FindFirstChild', 'WaitForChild', 'Clone', 'Destroy',
        'new', 'connect', 'Connect', 'Value', 'Name', 'Parent', 'Position',
        'CFrame', 'Size', 'wait', 'Wait', 'Touched', 'Fire', 'Invoke',
    }

    def _derive_var_name(self, expr):
        m = re.match(r'.*:GetService\("(\w+)"\)', expr)
        if m:
            return m.group(1)
        m = re.match(r'.*\.(\w+)$', expr)
        if m:
            n = m.group(1)
            if (n[0].isalpha() or n[0] == '_') and n not in self._SKIP_FIELD_NAMES:
                return n
        m = re.match(r'^"(\w+)"$', expr)
        if m and len(m.group(1)) > 1 and m.group(1).isidentifier():
            return m.group(1)
        if expr == 'game':
            return None
        if expr in ('nil', 'true', 'false', '...') or re.match(r'^-?\d+(\.\d+)?$', expr):
            return None
        if expr == '{}':
            return 'tbl'
        m = re.match(r'^(\w+)\(', expr)
        if m and not re.match(r'^r\d+$', m.group(1)):
            return m.group(1) + '_result'
        return None

    def _rename_registers(self, source: str) -> str:
        lines = source.split('\n')
        func_ranges = self._find_func_ranges(lines)
        result = list(lines)
        for func_start, func_end in func_ranges:
            reg_assigns = {}
            for j in range(func_start, func_end + 1):
                s = result[j].strip()
                m = re.match(r'^(?:local\s+)?(r\d+)\s*=\s*(.+)$', s)
                if m:
                    reg = m.group(1)
                    expr = m.group(2).strip()
                    if reg not in reg_assigns:
                        reg_assigns[reg] = []
                    reg_assigns[reg].append(expr)
            rename_map = {}
            used_names = set()
            sorted_regs = sorted(reg_assigns.keys(), key=lambda r: int(r[1:]))
            for reg in sorted_regs:
                exprs = reg_assigns[reg]
                if len(exprs) == 1:
                    name = self._derive_var_name(exprs[0])
                else:
                    from collections import Counter
                    derived = Counter()
                    for expr in exprs:
                        n = self._derive_var_name(expr)
                        if n:
                            derived[n] += 1
                    if derived:
                        best_name, best_count = derived.most_common(1)[0]
                        if best_count >= max(1, (len(exprs) + 2) // 3):
                            name = best_name
                        else:
                            name = None
                    else:
                        name = None
                if not name:
                    continue
                if name in used_names or name in ('game', 'end', 'do', 'then', 'else',
                    'if', 'for', 'while', 'repeat', 'until', 'return', 'local',
                    'function', 'not', 'and', 'or', 'in', 'nil', 'true', 'false',
                    'break', 'goto', 'elseif'):
                    base = name
                    for k in range(2, 100):
                        candidate = f'{base}_{k}'
                        if candidate not in used_names:
                            name = candidate
                            break
                used_names.add(name)
                rename_map[reg] = name
            for reg, name in rename_map.items():
                pat = r'\b' + re.escape(reg) + r'\b'
                for j in range(func_start, func_end + 1):
                    new_line = re.sub(pat, name, result[j])
                    result[j] = new_line
        return '\n'.join(result)

    def _ssa_split_registers(self, source: str) -> str:
        lines = source.split('\n')
        result = list(lines)
        func_ranges = self._find_func_ranges(result)
        for func_start, func_end in func_ranges:
            reg_assign_sites = {}
            for j in range(func_start, func_end + 1):
                s = result[j].strip()
                m = re.match(r'^(?:local\s+)?(r\d+)\s*=\s*(.+)$', s)
                if m:
                    reg = m.group(1)
                    expr = m.group(2).strip()
                    if reg not in reg_assign_sites:
                        reg_assign_sites[reg] = []
                    reg_assign_sites[reg].append((j, expr))
            used_names = set()
            for j in range(func_start, func_end + 1):
                for m in re.finditer(r'\b([A-Za-z_]\w+)\b', result[j]):
                    used_names.add(m.group(1))
            for reg, sites in sorted(reg_assign_sites.items(), key=lambda x: int(x[0][1:])):
                if len(sites) < 2 or len(sites) > 6:
                    continue
                site_names = []
                for line_idx, expr in sites:
                    name = self._derive_var_name(expr)
                    if name and re.match(r'^"', expr):
                        name = None
                    if name and name.endswith('_result'):
                        name = None
                    site_names.append((line_idx, expr, name))
                unique_names = set(n for _, _, n in site_names if n)
                if len(unique_names) < 2:
                    continue
                for site_idx, (line_idx, expr, name) in enumerate(site_names):
                    if not name:
                        continue
                    actual_name = name
                    if actual_name in used_names:
                        for k in range(2, 100):
                            candidate = f'{actual_name}_{k}'
                            if candidate not in used_names:
                                actual_name = candidate
                                break
                    used_names.add(actual_name)
                    next_line = func_end + 1
                    for future_idx in range(site_idx + 1, len(site_names)):
                        next_line = site_names[future_idx][0]
                        break
                    reg_pat = r'\b' + re.escape(reg) + r'\b'
                    for j in range(line_idx, min(next_line, func_end + 1)):
                        result[j] = re.sub(reg_pat, actual_name, result[j])
        return '\n'.join(result)

    def _rename_remaining_registers(self, source: str) -> str:
        lines = source.split('\n')
        result = list(lines)
        func_ranges = self._find_func_ranges(result)
        LUA_KEYWORDS = {'game', 'end', 'do', 'then', 'else', 'if', 'for', 'while',
                        'repeat', 'until', 'return', 'local', 'function', 'not', 'and',
                        'or', 'in', 'nil', 'true', 'false', 'break', 'goto', 'elseif',
                        'self', 'task', 'setreadonly', 'len', 'select', 'type', 'error',
                        'print', 'pairs', 'ipairs', 'next', 'tostring', 'tonumber',
                        'table', 'string', 'math', 'pcall', 'xpcall', 'require',
                        'setmetatable', 'getmetatable', 'rawget', 'rawset', 'unpack'}
        LOOP_VARS = ['i', 'j', 'k', 'n', 'idx']

        covered = set()
        for fs, fe in func_ranges:
            for j in range(fs, fe + 1):
                covered.add(j)
        toplevel_lines = [i for i in range(len(result)) if i not in covered]
        if toplevel_lines:
            has_rN = any(re.search(r'\br\d+\b', result[j]) for j in toplevel_lines)
            if has_rN:
                func_ranges = list(func_ranges) + [(toplevel_lines[0], toplevel_lines[-1])]

        for func_start, func_end in func_ranges:
            existing_names = set()
            for j in range(func_start, func_end + 1):
                for m in re.finditer(r'\b([A-Za-z_]\w*)\b', result[j]):
                    n = m.group(1)
                    if not re.match(r'^r\d+$', n):
                        existing_names.add(n)

            remaining_regs = set()
            for j in range(func_start, func_end + 1):
                for m in re.finditer(r'\b(r\d+)\b', result[j]):
                    remaining_regs.add(m.group(1))
            if not remaining_regs:
                continue

            param_m = re.match(r'^(?:local\s+)?function\s+\w*\((.*?)\)', result[func_start].strip())
            param_regs = set()
            if param_m and param_m.group(1):
                for p in param_m.group(1).split(','):
                    p = p.strip()
                    if re.match(r'^r\d+$', p):
                        param_regs.add(p)

            for_loop_regs = set()
            for j in range(func_start, func_end + 1):
                fm = re.match(r'^\s*for\s+(r\d+)\s*=', result[j].strip())
                if fm:
                    for_loop_regs.add(fm.group(1))

            reg_usage = {}
            for reg in remaining_regs:
                reg_pat = r'\b' + re.escape(reg) + r'\b'
                usage = set()
                for j in range(func_start, func_end + 1):
                    s = result[j]
                    if not re.search(reg_pat, s):
                        continue
                    stripped = s.strip()
                    if re.search(re.escape(reg) + r'\s*\(', stripped):
                        am = re.match(r'^(?:local\s+)?' + re.escape(reg) + r'\s*=', stripped)
                        if not am:
                            usage.add('callee')
                    if re.search(re.escape(reg) + r'\s*:\w+\s*\(', stripped):
                        usage.add('method_target')
                    if re.search(re.escape(reg) + r'\s*\.', stripped):
                        usage.add('field_access')
                    if re.search(re.escape(reg) + r'\s*\[', stripped):
                        usage.add('table_access')
                reg_usage[reg] = usage

            rename_map = {}
            used_names = set(existing_names)
            loop_var_idx = 0

            def _pick_unique(base):
                if base not in used_names and base not in LUA_KEYWORDS:
                    used_names.add(base)
                    return base
                for suffix in range(2, 200):
                    candidate = f'{base}_{suffix}'
                    if candidate not in used_names:
                        used_names.add(candidate)
                        return candidate
                return base

            sorted_regs = sorted(remaining_regs, key=lambda r: int(r[1:]))
            for reg in sorted_regs:
                usage = reg_usage.get(reg, set())
                if reg in param_regs:
                    name = _pick_unique(f'p{reg[1:]}')
                elif reg in for_loop_regs:
                    if loop_var_idx < len(LOOP_VARS):
                        name = _pick_unique(LOOP_VARS[loop_var_idx])
                    else:
                        name = _pick_unique(f'idx_{loop_var_idx}')
                    loop_var_idx += 1
                elif 'callee' in usage and 'field_access' not in usage and 'method_target' not in usage:
                    name = _pick_unique('fn')
                elif 'method_target' in usage or ('field_access' in usage and 'callee' in usage):
                    name = _pick_unique('obj')
                elif 'field_access' in usage or 'table_access' in usage:
                    name = _pick_unique('tbl')
                elif 'callee' in usage:
                    name = _pick_unique('fn')
                else:
                    name = _pick_unique('v')
                rename_map[reg] = name

            for reg, name in rename_map.items():
                pat = r'\b' + re.escape(reg) + r'\b'
                for j in range(func_start, func_end + 1):
                    result[j] = re.sub(pat, name, result[j])
        return '\n'.join(result)

    @staticmethod
    def _negate_condition(cond):
        cond = cond.strip()
        if cond.startswith('not '):
            inner = cond[4:].strip()
            if inner.startswith('(') and inner.endswith(')'):
                return inner[1:-1]
            return inner
        m = re.match(r'^(.+?)\s*(==|~=|<|>|<=|>=)\s*(.+)$', cond)
        if m:
            lhs, op, rhs = m.group(1), m.group(2), m.group(3)
            neg = {'==': '~=', '~=': '==', '<': '>=', '>': '<=', '<=': '>', '>=': '<'}
            return f'{lhs} {neg[op]} {rhs}'
        return f'not {cond}'

    def _goto_to_structured(self, source: str) -> str:
        lines = source.split('\n')

        for _iteration in range(200):
            changed = False

            func_ranges = self._find_func_ranges(lines)

            def _scope_of(idx):
                best = None
                for fs, fe in func_ranges:
                    if fs <= idx <= fe:
                        if best is None or (fe - fs) < (best[1] - best[0]):
                            best = (fs, fe)
                return best

            all_labels = []
            for i, l in enumerate(lines):
                m = re.match(r'^\s*::(\w+)::\s*$', l)
                if m:
                    all_labels.append((i, m.group(1)))

            def _find_label(goto_line, label_name):
                scope = _scope_of(goto_line)
                for li, ln in all_labels:
                    if ln != label_name:
                        continue
                    ls = _scope_of(li)
                    if scope == ls:
                        return li
                return None

            gotos = []
            for i, l in enumerate(lines):
                s = l.strip()
                m = re.match(r'^goto\s+(\w+)$', s)
                if m:
                    lbl = _find_label(i, m.group(1))
                    if lbl is not None:
                        gotos.append((i, 'uncond', m.group(1), None, lbl))
                    continue
                m = re.match(r'^if\s+(.+)\s+then\s+goto\s+(\w+)\s+end$', s)
                if m:
                    lbl = _find_label(i, m.group(2))
                    if lbl is not None:
                        gotos.append((i, 'cond', m.group(2), m.group(1), lbl))

            best_loop = None
            best_span = float('inf')
            for goto_idx, gtype, target, cond, lbl in gotos:
                if gtype != 'uncond':
                    continue
                if lbl < goto_idx:
                    span = goto_idx - lbl
                    if span < best_span:
                        best_span = span
                        best_loop = (lbl, goto_idx, target)

            if best_loop:
                lbl_line, goto_line, target = best_loop
                indent = lines[lbl_line][:len(lines[lbl_line]) - len(lines[lbl_line].lstrip())]
                other_refs = sum(1 for gi, gt, tgt, cd, lb in gotos if tgt == target and gi != goto_line and lb == lbl_line)

                new_lines = lines[:lbl_line]
                if other_refs > 0:
                    new_lines.append(lines[lbl_line])
                new_lines.append(f'{indent}while true do')
                for j in range(lbl_line + 1, goto_line):
                    if lines[j].strip():
                        new_lines.append(f'  {lines[j]}')
                    else:
                        new_lines.append(lines[j])
                new_lines.append(f'{indent}end')
                new_lines.extend(lines[goto_line + 1:])
                lines = new_lines
                changed = True

            if not changed:
                block_stack = []
                while_ranges = []
                for i, l in enumerate(lines):
                    s = l.strip()
                    if s == 'while true do':
                        block_stack.append(('while', i))
                    elif s.startswith('if ') and s.endswith(' then') and 'goto' not in s:
                        block_stack.append(('if', i))
                    elif re.match(r'^for\s+.+\s+do$', s):
                        block_stack.append(('for', i))
                    elif s.startswith('local function ') or (s.startswith('function ') and s.endswith(')')):
                        block_stack.append(('func', i))
                    elif s == 'end' and block_stack:
                        tag, start = block_stack.pop()
                        if tag == 'while':
                            while_ranges.append((start, i))

                for wr_start, wr_end in while_ranges:
                    loop_label = None
                    for k in range(wr_start - 1, max(wr_start - 3, -1), -1):
                        m = re.match(r'^\s*::(\w+)::\s*$', lines[k])
                        if m:
                            loop_label = m.group(1)
                            break
                        if lines[k].strip():
                            break

                    end_label = None
                    for k in range(wr_end + 1, min(wr_end + 3, len(lines))):
                        m = re.match(r'^\s*::(\w+)::\s*$', lines[k])
                        if m:
                            end_label = m.group(1)
                            break
                        if lines[k].strip():
                            break

                    inner_loops = set()
                    stk = []
                    for k in range(wr_start + 1, wr_end):
                        s = lines[k].strip()
                        if s == 'while true do' or re.match(r'^for\s+.+\s+do$', s):
                            stk.append(k)
                        elif s == 'end' and stk:
                            inner_start = stk.pop()
                            for q in range(inner_start, k + 1):
                                inner_loops.add(q)

                    for k in range(wr_start + 1, wr_end):
                        if k in inner_loops:
                            continue
                        s = lines[k].strip()
                        if end_label:
                            m = re.match(r'^goto\s+(\w+)$', s)
                            if m and m.group(1) == end_label:
                                indent_k = lines[k][:len(lines[k]) - len(lines[k].lstrip())]
                                lines[k] = f'{indent_k}break'
                                changed = True
                                continue
                            m = re.match(r'^if\s+(.+)\s+then\s+goto\s+(\w+)\s+end$', s)
                            if m and m.group(2) == end_label:
                                indent_k = lines[k][:len(lines[k]) - len(lines[k].lstrip())]
                                lines[k] = f'{indent_k}if {m.group(1)} then break end'
                                changed = True
                                continue
                        if loop_label:
                            m = re.match(r'^if\s+(.+)\s+then\s+goto\s+(\w+)\s+end$', s)
                            if m and m.group(2) == loop_label:
                                indent_k = lines[k][:len(lines[k]) - len(lines[k].lstrip())]
                                lines[k] = f'{indent_k}if {m.group(1)} then continue end'
                                changed = True
                                continue
                            m2 = re.match(r'^goto\s+(\w+)$', s)
                            if m2 and m2.group(1) == loop_label:
                                indent_k = lines[k][:len(lines[k]) - len(lines[k].lstrip())]
                                lines[k] = f'{indent_k}continue'
                                changed = True
                                continue

            if not changed:
                fwd_conds = [(goto_idx, gtype, target, cond, lbl)
                             for goto_idx, gtype, target, cond, lbl in gotos
                             if gtype == 'cond' and lbl > goto_idx]
                fwd_conds.sort(key=lambda x: x[4] - x[0])

                for goto_idx, gtype, target, cond, lbl in fwd_conds:
                    same_scope_refs = sum(1 for gi, gt, tgt, cd, lb in gotos if lb == lbl and gi != goto_idx)
                    range_has_same_target = any(gi != goto_idx and lb == lbl and goto_idx < gi < lbl
                                                for gi, gt, tgt, cd, lb in gotos)
                    if range_has_same_target:
                        continue

                    has_external = False
                    for j in range(goto_idx + 1, lbl):
                        m2 = re.match(r'^\s*::(\w+)::\s*$', lines[j])
                        if m2:
                            inner_lbl = m2.group(1)
                            for gi, gt, tgt, cd, lb in gotos:
                                if tgt == inner_lbl and (gi < goto_idx or gi > lbl):
                                    has_external = True
                                    break
                        if has_external:
                            break
                    if has_external:
                        continue

                    indent = lines[goto_idx][:len(lines[goto_idx]) - len(lines[goto_idx].lstrip())]
                    neg = self._negate_condition(cond)
                    new_lines = lines[:goto_idx]
                    new_lines.append(f'{indent}if {neg} then')
                    for j in range(goto_idx + 1, lbl):
                        if lines[j].strip():
                            new_lines.append(f'  {lines[j]}')
                        else:
                            new_lines.append(lines[j])
                    new_lines.append(f'{indent}end')
                    if same_scope_refs > 0:
                        new_lines.append(lines[lbl])
                    new_lines.extend(lines[lbl + 1:])
                    lines = new_lines
                    changed = True
                    break

            if not changed:
                for goto_idx, gtype, target, cond, lbl in gotos:
                    if gtype != 'uncond' or lbl <= goto_idx:
                        continue
                    if lbl - goto_idx <= 5:
                        same_refs = sum(1 for gi, gt, tgt, cd, lb in gotos if lb == lbl and gi != goto_idx)
                        if same_refs == 0:
                            indent = lines[goto_idx][:len(lines[goto_idx]) - len(lines[goto_idx].lstrip())]
                            new_lines = lines[:goto_idx]
                            for j in range(goto_idx + 1, lbl):
                                new_lines.append(lines[j])
                            new_lines.extend(lines[lbl + 1:])
                            lines = new_lines
                            changed = True
                            break

            if not changed:
                break

        label_pos = {}
        for i, l in enumerate(lines):
            m = re.match(r'^\s*::(\w+)::\s*$', l)
            if m:
                label_pos[m.group(1)] = i

        for i in range(len(lines)):
            s = lines[i].strip()
            target = None
            cond = None
            m = re.match(r'^goto\s+(\w+)$', s)
            if m:
                target = m.group(1)
            m = re.match(r'^if\s+(.+)\s+then\s+goto\s+(\w+)\s+end$', s)
            if m:
                target = m.group(2)
                cond = m.group(1)
            if target is None or target not in label_pos:
                continue
            lbl = label_pos[target]
            if lbl <= i:
                continue
            only_ends = True
            for k in range(lbl + 1, min(lbl + 10, len(lines))):
                sk = lines[k].strip()
                if not sk:
                    continue
                if sk == 'end':
                    continue
                if sk.startswith('local function ') or sk.startswith('function '):
                    break
                only_ends = False
                break
            if only_ends:
                indent = lines[i][:len(lines[i]) - len(lines[i].lstrip())]
                if cond:
                    lines[i] = f'{indent}if {cond} then return end'
                else:
                    lines[i] = f'{indent}return'

        cleaned = []
        skip = False
        for i, l in enumerate(lines):
            s = l.strip()
            if skip:
                if not s:
                    continue
                if s == 'end' or s.startswith('::') or s.startswith('local function ') or s.startswith('else'):
                    skip = False
                    cleaned.append(l)
                    continue
                continue
            cleaned.append(l)
            if re.match(r'^\s*return\b', s) and not s.startswith('return ') and not re.match(r'^\s*if\s+', s):
                skip = True
        lines = cleaned

        for i in range(len(lines)):
            l = lines[i]
            l = re.sub(r'"[^"]*"\s*(:GetService\b)', r'game\1', l)
            l = re.sub(r'"[^"]*"\s*(\.Text:GetService\b)', r'game\1', l)
            l = re.sub(r'"[^"]*"\s*(\[)', r'game\1', l)
            l = re.sub(r'"[^"]*"\s*(\.CreateWindow\b)', r'game\1', l)
            l = re.sub(r'"[^"]*"\s*(\.gInt\b)', r'game\1', l)
            l = re.sub(r'"[^"]*"\s*(\.ActionText\b)', r'game\1', l)
            lines[i] = l

        for i in range(len(lines)):
            s = lines[i].strip()
            target = None
            cond = None
            m = re.match(r'^if\s+(.+)\s+then\s+goto\s+(\w+)\s+end$', s)
            if m:
                target = m.group(2)
                cond = m.group(1)
            if target is None or target not in label_pos:
                continue
            lbl = label_pos[target]
            if lbl <= i:
                continue
            same_target = [j for j in range(len(lines)) if j != i and
                           re.search(r'\bgoto\s+' + re.escape(target) + r'\b', lines[j])]
            if same_target:
                continue
            ends_between = 0
            for k in range(i + 1, lbl):
                if lines[k].strip() == 'end':
                    ends_between += 1
            if ends_between == 0:
                continue
            indent = lines[i][:len(lines[i]) - len(lines[i].lstrip())]
            lines[i] = f'{indent}if {cond} then'
            skip_lines = []
            for k in range(i + 1, lbl):
                sk = lines[k].strip()
                if sk == 'end':
                    ends_between -= 1
                    if ends_between == 0:
                        skip_lines.append(k)
                        break
                skip_lines.append(k)
            for k in skip_lines:
                if lines[k].strip():
                    lines[k] = '  ' + lines[k]

        existing_labels = set()
        for l in lines:
            m = re.match(r'^\s*::(\w+)::\s*$', l)
            if m:
                existing_labels.add(m.group(1))

        cleaned = []
        for l in lines:
            s = l.strip()
            m = re.match(r'^goto\s+(\w+)$', s)
            if m and m.group(1) not in existing_labels:
                continue
            m = re.match(r'^if\s+.+\s+then\s+goto\s+(\w+)\s+end$', s)
            if m and m.group(1) not in existing_labels:
                continue
            cleaned.append(l)
        lines = cleaned

        used_labels = set()
        for l in lines:
            for m in re.finditer(r'\bgoto\s+(\w+)', l):
                used_labels.add(m.group(1))
        result = []
        for l in lines:
            m = re.match(r'^\s*::(\w+)::\s*$', l)
            if m and m.group(1) not in used_labels:
                continue
            result.append(l)
        lines = result

        balanced = []
        depth = 0
        for l in lines:
            s = l.strip()
            if not s or s.startswith('--'):
                balanced.append(l)
                continue
            is_open = False
            is_close = False
            if s.startswith('local function ') or (s.startswith('function ') and '(' in s and s.endswith(')')):
                is_open = True
            elif s == 'while true do' or s == 'repeat':
                is_open = True
            elif re.match(r'^for\s+.+\s+do$', s):
                is_open = True
            elif 'if ' in s and re.search(r'\bthen\s*$', s):
                if not (s.endswith(' end') or s.endswith(' end)')):
                    is_open = True
            if s == 'end':
                is_close = True
            elif s.startswith('until '):
                is_close = True
            if is_close and not is_open and depth <= 0:
                continue
            if is_open:
                depth += 1
            if is_close:
                depth -= 1
            balanced.append(l)
        lines = balanced

        for _ in range(3):
            prev_len = len(lines)
            cleaned = []
            skip = False
            for l in lines:
                s = l.strip()
                if skip:
                    if not s:
                        continue
                    if s == 'end' or s.startswith('::') or s.startswith('local function ') or s.startswith('else'):
                        skip = False
                        cleaned.append(l)
                        continue
                    continue
                cleaned.append(l)
                if s == 'return' and not re.match(r'^\s*if\s+', l.strip()):
                    skip = True
            lines = cleaned

            cleaned = []
            i = 0
            while i < len(lines):
                s = lines[i].strip()
                if i + 1 < len(lines) and re.search(r'\bthen\s*$', s) and lines[i+1].strip() == 'end':
                    i += 2
                    continue
                cleaned.append(lines[i])
                i += 1
            lines = cleaned
            if len(lines) == prev_len:
                break

        for _ in range(3):
            merged = []
            changed = False
            i = 0
            while i < len(lines):
                s = lines[i].strip()
                if i + 2 < len(lines) and re.search(r'\bthen\s*$', s) and re.search(r'\bthen\s*$', lines[i+1].strip()):
                    inner_if = lines[i+1].strip()
                    m_outer = re.match(r'^if\s+(.+)\s+then$', s)
                    m_inner = re.match(r'^if\s+(.+)\s+then$', inner_if)
                    if m_outer and m_inner:
                        depth_check = 1
                        inner_end = -1
                        outer_end = -1
                        for j in range(i + 2, len(lines)):
                            sj = lines[j].strip()
                            if re.search(r'\bthen\s*$', sj) and not (sj.endswith(' end') or sj.endswith(' end)')):
                                depth_check += 1
                            elif sj.startswith('for ') and sj.endswith(' do'):
                                depth_check += 1
                            elif sj == 'while true do':
                                depth_check += 1
                            elif sj.startswith('local function ') or (sj.startswith('function ') and sj.endswith(')')):
                                depth_check += 1
                            elif sj == 'end':
                                depth_check -= 1
                                if depth_check == 1 and inner_end < 0:
                                    inner_end = j
                                elif depth_check == 0:
                                    outer_end = j
                                    break
                        if inner_end >= 0 and outer_end >= 0 and outer_end == inner_end + 1:
                            has_else = any('else' in lines[k].strip() or lines[k].strip().startswith('elseif')
                                          for k in range(i+2, inner_end))
                            if not has_else:
                                cond = f'{m_outer.group(1)} and {m_inner.group(1)}'
                                merged.append(f'if {cond} then')
                                for k in range(i + 2, inner_end):
                                    merged.append(lines[k])
                                merged.append('end')
                                i = outer_end + 1
                                changed = True
                                continue
                merged.append(lines[i])
                i += 1
            lines = merged
            if not changed:
                break

        for _ in range(3):
            folded = []
            changed = False
            i = 0
            while i < len(lines):
                s = lines[i].strip()
                if (i + 2 < len(lines) and re.search(r'\bthen\s*$', s) and
                    lines[i+2].strip() == 'end' and lines[i+1].strip() and
                    not re.search(r'\bthen\s*$', lines[i+1].strip()) and
                    lines[i+1].strip() != 'end' and
                    'else' not in lines[i+1].strip()):
                    stmt = lines[i+1].strip()
                    if len(s) + len(stmt) + 5 < 120:
                        folded.append(f'{s} {stmt} end')
                        i += 3
                        changed = True
                        continue
                folded.append(lines[i])
                i += 1
            lines = folded
            if not changed:
                break

        balanced2 = []
        depth = 0
        for l in lines:
            s = l.strip()
            if not s or s.startswith('--'):
                balanced2.append(l)
                continue
            is_open = is_close = False
            if s.startswith('local function ') or (s.startswith('function ') and '(' in s and s.endswith(')')):
                is_open = True
            elif s == 'while true do' or s == 'repeat':
                is_open = True
            elif re.match(r'^for\s+.+\s+do$', s):
                is_open = True
            elif 'if ' in s and re.search(r'\bthen\s*$', s):
                if not (s.endswith(' end') or s.endswith(' end)')):
                    is_open = True
            if s == 'end':
                is_close = True
            elif s.startswith('until '):
                is_close = True
            if is_close and not is_open and depth <= 0:
                continue
            if is_open: depth += 1
            if is_close: depth -= 1
            balanced2.append(l)
        lines = balanced2

        reindented = []
        depth = 0
        for l in lines:
            s = l.strip()
            if not s:
                reindented.append('')
                continue
            if s.startswith('--'):
                reindented.append('  ' * depth + s)
                continue
            is_open = False
            is_close = False
            if s.startswith('local function ') or (s.startswith('function ') and '(' in s and s.endswith(')')):
                is_open = True
            elif s == 'while true do' or s == 'repeat':
                is_open = True
            elif re.match(r'^for\s+.+\s+do$', s):
                is_open = True
            elif 'if ' in s and re.search(r'\bthen\s*$', s):
                if not (s.endswith(' end') or s.endswith(' end)')):
                    is_open = True
            if s == 'end':
                is_close = True
            elif s.startswith('until '):
                is_close = True
            elif s == 'else' or s.startswith('elseif '):
                is_close = True
                is_open = True
            if is_close and not is_open:
                depth = max(0, depth - 1)
            reindented.append('  ' * depth + s)
            if is_open and not is_close:
                depth += 1
            elif is_open and is_close:
                pass

        return '\n'.join(reindented)

    def _remove_dead_locals(self, source: str) -> str:
        lines = source.split('\n')
        result = []

        funcs = []
        i = 0
        while i < len(lines):
            s = lines[i].strip()
            if s.startswith('local function ') or (s.startswith('function ') and '(' in s and s.endswith(')')):
                start = i
                depth = 1
                j = i + 1
                while j < len(lines) and depth > 0:
                    sj = lines[j].strip()
                    if sj.startswith('local function ') or (sj.startswith('function ') and sj.endswith(')')):
                        depth += 1
                    elif sj == 'end':
                        depth -= 1
                    j += 1
                funcs.append((start, j - 1))
            i += 1

        remove_lines = set()

        def _is_side_effect_free(val):
            if val in ('nil', 'true', 'false'):
                return True
            if re.match(r'^[\d.]+$', val):
                return True
            if re.match(r'^"[^"]*"$', val):
                return True
            if re.match(r'^[\w.]+$', val) and '(' not in val and ':' not in val:
                return True
            return False

        for fstart, fend in funcs:
            for k in range(fstart + 1, fend):
                s = lines[k].strip()
                m = re.match(r'^local\s+(\w+)\s*=\s*(.+)$', s)
                if not m:
                    continue
                var = m.group(1)
                val = m.group(2).strip()
                if not _is_side_effect_free(val):
                    continue
                used = False
                inner_depth = 0
                for q in range(k + 1, fend):
                    sq = lines[q].strip()
                    if sq.startswith('local function ') or (sq.startswith('function ') and sq.endswith(')')):
                        inner_depth += 1
                    elif sq == 'end':
                        if inner_depth > 0:
                            inner_depth -= 1
                    if inner_depth == 0 and re.search(r'\b' + re.escape(var) + r'\b', lines[q]):
                        if not re.match(r'^local\s+' + re.escape(var) + r'\b', sq):
                            used = True
                            break
                if not used:
                    remove_lines.add(k)

            if fend > 0 and lines[fend - 1].strip() == 'return':
                remove_lines.add(fend - 1)

        for i in range(len(lines)):
            s = lines[i].strip()
            if s == 'return' or (s.startswith('return') and not s.startswith('return ')):
                j = i - 1
                while j >= 0:
                    sj = lines[j].strip()
                    if not sj:
                        j -= 1
                        continue
                    m = re.match(r'^(?:local\s+)?(\w+)\s*=\s*(.+)$', sj)
                    if m:
                        val = m.group(2).strip()
                        if '(' not in val and ':' not in val:
                            remove_lines.add(j)
                            j -= 1
                            continue
                    break

        for i, l in enumerate(lines):
            if i not in remove_lines:
                result.append(l)

        return '\n'.join(result)

    def _fix_block_structure(self, source: str) -> str:
        lines = source.split('\n')

        for _ in range(3):
            prev_len = len(lines)
            cleaned = []
            skip = False
            for l in lines:
                s = l.strip()
                if skip:
                    if not s:
                        continue
                    if s == 'end' or s.startswith('::') or s.startswith('local function ') or s.startswith('else'):
                        skip = False
                        cleaned.append(l)
                        continue
                    continue
                cleaned.append(l)
                if s == 'return' and not re.match(r'^\s*if\s+', l.strip()):
                    skip = True
            lines = cleaned

            cleaned = []
            i = 0
            while i < len(lines):
                s = lines[i].strip()
                if i + 1 < len(lines) and re.search(r'\bthen\s*$', s) and lines[i+1].strip() == 'end':
                    i += 2
                    continue
                cleaned.append(lines[i])
                i += 1
            lines = cleaned
            if len(lines) == prev_len:
                break

        balanced = []
        depth = 0
        for l in lines:
            s = l.strip()
            if not s or s.startswith('--'):
                balanced.append(l)
                continue
            is_open = is_close = False
            if s.startswith('local function ') or (s.startswith('function ') and '(' in s and s.endswith(')')):
                is_open = True
            elif s == 'while true do' or s == 'repeat':
                is_open = True
            elif re.match(r'^for\s+.+\s+do$', s):
                is_open = True
            elif 'if ' in s and re.search(r'\bthen\s*$', s):
                if not (s.endswith(' end') or s.endswith(' end)')):
                    is_open = True
            if s == 'end':
                is_close = True
            elif s.startswith('until '):
                is_close = True
            if is_close and not is_open and depth <= 0:
                continue
            if is_open: depth += 1
            if is_close: depth -= 1
            balanced.append(l)
        lines = balanced

        reindented = []
        depth = 0
        for l in lines:
            s = l.strip()
            if not s:
                reindented.append('')
                continue
            if s.startswith('--'):
                reindented.append('  ' * depth + s)
                continue
            is_open = is_close = False
            if s.startswith('local function ') or (s.startswith('function ') and '(' in s and s.endswith(')')):
                is_open = True
            elif s == 'while true do' or s == 'repeat':
                is_open = True
            elif re.match(r'^for\s+.+\s+do$', s):
                is_open = True
            elif 'if ' in s and re.search(r'\bthen\s*$', s):
                if not (s.endswith(' end') or s.endswith(' end)')):
                    is_open = True
            if s == 'end':
                is_close = True
            elif s.startswith('until '):
                is_close = True
            elif s == 'else' or s.startswith('elseif '):
                is_close = True
                is_open = True
            if is_close and not is_open:
                depth = max(0, depth - 1)
            reindented.append('  ' * depth + s)
            if is_open and not is_close:
                depth += 1
        return '\n'.join(reindented)

    def _rename_functions(self, source: str) -> str:
        lines = source.split('\n')
        result = list(lines)
        func_names = {}
        COMMON_FIELDS = {'Unlock', 'Character', 'CollectionService', 'Stable',
                         'ToggleCabinet', 'GetService', 'AddLabel', 'Value',
                         'Enabled', 'Frame', 'Position', 'CFrame', 'Name',
                         'Parent', 'Text'}
        COMMON_STRINGS = {'settings', 'equipmentType', 'CollectionService',
                          'Value', 'Pick', 'Fix', 'Chunk', 'gSizet', 'tostring',
                          'center', 'find', 'select', 'codes', 'menuItem'}
        for i, line in enumerate(result):
            m = re.match(r'^local function (proto_\d+)\((.*?)\)', line)
            if not m:
                continue
            func_name = m.group(1)
            services = set()
            fields = []
            strings = set()
            method_calls = set()
            body_lines = 0
            has_for = False
            has_return = False
            for j in range(i + 1, min(i + 200, len(result))):
                s = result[j].strip()
                body_lines += 1
                if s == 'end' and body_lines > 1:
                    break
                if s.startswith('for '):
                    has_for = True
                if s.startswith('return'):
                    has_return = True
                for sm in re.finditer(r'GetService\("(\w+)"\)', s):
                    services.add(sm.group(1))
                for sm in re.finditer(r':(\w+)\(', s):
                    method_calls.add(sm.group(1))
                for sm in re.finditer(r'\.(\w+)', s):
                    f = sm.group(1)
                    if f[0].isupper() and len(f) > 3 and f not in COMMON_FIELDS:
                        if f not in fields:
                            fields.append(f)
                for sm in re.finditer(r'"(\w{4,})"', s):
                    v = sm.group(1)
                    if v not in COMMON_STRINGS and v[0].islower():
                        strings.add(v)
            name = None
            method_calls -= {'GetService', 'rawget', 'rawset', 'task', 'wait'}
            if method_calls:
                mc = sorted(method_calls)[0]
                name = mc
            elif fields:
                name = fields[0][0].lower() + fields[0][1:]
            elif services - {'CollectionService'}:
                svc = sorted(services - {'CollectionService'})[0]
                name = svc[0].lower() + svc[1:]
            elif strings:
                name = sorted(strings)[0]
            elif services:
                svc = sorted(services)[0]
                name = svc[0].lower() + svc[1:]
            if name:
                suffix = '_loop' if has_for else ('_get' if has_return and body_lines < 15 else '_fn')
                name = name + suffix
                if name in func_names.values():
                    for k in range(2, 100):
                        candidate = f'{name[:-len(suffix)]}_{k}{suffix}'
                        if candidate not in func_names.values():
                            name = candidate
                            break
                func_names[func_name] = name
        for old_name, new_name in func_names.items():
            pat = r'\b' + re.escape(old_name) + r'\b'
            for i in range(len(result)):
                result[i] = re.sub(pat, new_name, result[i])
        return '\n'.join(result)

    def _add_local_declarations(self, source: str) -> str:
        lines = source.split('\n')
        result = list(lines)
        keywords = {'game', 'end', 'do', 'then', 'else', 'if', 'for', 'while',
                     'repeat', 'until', 'return', 'local', 'function', 'not',
                     'and', 'or', 'in', 'nil', 'true', 'false', 'break', 'goto',
                     'elseif', 'setreadonly', 'select', 'type', 'tostring',
                     'tonumber', 'pcall', 'xpcall', 'error', 'print', 'pairs',
                     'ipairs', 'next', 'rawget', 'rawset', 'require', 'assert',
                     'unpack', 'table', 'string', 'math', 'coroutine', 'debug',
                     'WorldPivot', 'len', 'topLabel', 'workspace'}
        declared = set()
        nesting = 0
        in_func = False
        for i, line in enumerate(result):
            s = line.strip()
            if s.startswith('local function ') or (s.startswith('function ') and s.endswith(')')):
                if not in_func:
                    in_func = True
                    nesting = 1
                    declared = set()
                    m = re.search(r'\((.*?)\)', s)
                    if m and m.group(1):
                        for p in m.group(1).split(','):
                            declared.add(p.strip())
                else:
                    nesting += 1
                continue
            if s == 'end' and in_func:
                nesting -= 1
                if nesting <= 0:
                    in_func = False
                    declared = set()
                continue
            if not in_func:
                continue
            if (s.startswith('if ') and s.endswith(' then')) or \
               (s.startswith('for ') and s.endswith(' do')) or \
               (s.startswith('while ') and s.endswith(' do')):
                nesting += 1
            if s.startswith('local '):
                m = re.match(r'^local\s+(\w+)', s)
                if m:
                    declared.add(m.group(1))
                continue
            if s.startswith('for ') and ' do' in s:
                m = re.match(r'^for\s+(\w+)', s)
                if m:
                    declared.add(m.group(1))
                continue
            m = re.match(r'^(\w+)\s*=\s*', s)
            if m:
                var = m.group(1)
                if var not in keywords and var not in declared:
                    indent = line[:len(line) - len(line.lstrip())]
                    result[i] = f'{indent}local {s}'
                    declared.add(var)
            m_multi = re.match(r'^(\w+(?:\s*,\s*\w+)+)\s*=\s*', s)
            if m_multi:
                vars_str = m_multi.group(1)
                for v in re.findall(r'\w+', vars_str):
                    if v not in keywords and v not in declared:
                        declared.add(v)
        return '\n'.join(result)

    def _cleanup_pass(self, source: str) -> str:
        lines = source.split('\n')

        goto_targets = set()
        for line in lines:
            stripped = line.strip()
            if stripped.startswith('goto '):
                goto_targets.add(stripped[5:].strip())
            elif stripped.startswith('if ') and 'goto ' in stripped:
                idx = stripped.index('goto ')
                target = stripped[idx+5:].strip().rstrip(' end').strip()
                goto_targets.add(target)

        cleaned = []
        i = 0
        while i < len(lines):
            stripped = lines[i].strip()
            if stripped.startswith('::') and stripped.endswith('::'):
                label_name = stripped[2:-2]
                if label_name not in goto_targets:
                    i += 1
                    continue

            if stripped.startswith('goto '):
                target = stripped[5:].strip()
                if i + 1 < len(lines):
                    next_stripped = lines[i + 1].strip()
                    if next_stripped == f'::{target}::':
                        i += 1
                        continue

            if stripped.startswith('-- NOP') or stripped == '-- FORPREP' or stripped.startswith('-- TFORLOOP'):
                i += 1
                continue

            cleaned.append(lines[i])
            i += 1

        dce = []
        skip_until_reachable = False
        skip_indent = -1
        for line in cleaned:
            stripped = line.strip()
            if not stripped:
                if not skip_until_reachable:
                    dce.append(line)
                continue
            indent_level = len(line) - len(line.lstrip())
            if skip_until_reachable:
                if stripped.startswith('::') and stripped.endswith('::'):
                    skip_until_reachable = False
                elif indent_level < skip_indent:
                    skip_until_reachable = False
                elif stripped in ('end', 'else', 'elseif') and indent_level <= skip_indent:
                    skip_until_reachable = False
                else:
                    continue
            dce.append(line)
            if stripped == 'return' or stripped.startswith('return '):
                skip_until_reachable = True
                skip_indent = indent_level
            elif stripped.startswith('goto '):
                skip_until_reachable = True
                skip_indent = indent_level

        folded = []
        i = 0
        while i < len(dce):
            if i + 1 < len(dce):
                s1 = dce[i].strip()
                s2 = dce[i + 1].strip()
                m1 = re.match(r'^(local\s+)?(r(\d+))\s*=\s*(r(\d+))\.(\w+)$', s1)
                if m1:
                    local_kw = m1.group(1) or ''
                    dst = m1.group(2)
                    dst_n = int(m1.group(3))
                    obj = m1.group(4)
                    obj_n = int(m1.group(5))
                    method = m1.group(6)
                    indent = dce[i][:len(dce[i]) - len(dce[i].lstrip())]
                    if dst == obj:
                        m2 = re.match(r'^' + re.escape(dst) + r'\s*=\s*' + re.escape(dst) + r'\((r(\d+)(?:,\s*.+)?)\)$', s2)
                        if m2:
                            all_args = m2.group(1)
                            first_n = int(m2.group(2))
                            if first_n == dst_n + 1:
                                parts = [a.strip() for a in all_args.split(',')]
                                self_ref = parts[0]
                                rest_args = ', '.join(parts[1:])
                                folded.append(f'{indent}{local_kw}{dst} = {self_ref}:{method}({rest_args})')
                                i += 2
                                continue
                        m3 = re.match(r'^' + re.escape(dst) + r'\((r(\d+)(?:,\s*.+)?)\)$', s2)
                        if m3:
                            all_args = m3.group(1)
                            first_n = int(m3.group(2))
                            if first_n == dst_n + 1:
                                parts = [a.strip() for a in all_args.split(',')]
                                self_ref = parts[0]
                                rest_args = ', '.join(parts[1:])
                                folded.append(f'{indent}{self_ref}:{method}({rest_args})')
                                i += 2
                                continue
                    else:
                        m2 = re.match(r'^' + re.escape(dst) + r'\s*=\s*' + re.escape(dst) + r'\((' + re.escape(obj) + r'(?:,\s*.+)?)\)$', s2)
                        if m2:
                            all_args = m2.group(1)
                            parts = [a.strip() for a in all_args.split(',')]
                            if parts and parts[0] == obj:
                                rest_args = ', '.join(parts[1:])
                                folded.append(f'{indent}{local_kw}{dst} = {obj}:{method}({rest_args})')
                                i += 2
                                continue
                        m3 = re.match(r'^' + re.escape(dst) + r'\((.*)\)$', s2)
                        if m3:
                            args = m3.group(1)
                            parts = [a.strip() for a in args.split(',')] if args else []
                            if parts and parts[0] == obj:
                                rest_args = ', '.join(parts[1:])
                                folded.append(f'{indent}{obj}:{method}({rest_args})')
                                i += 2
                                continue
            folded.append(dce[i])
            i += 1

        no_empty = []
        i = 0
        while i < len(folded):
            if i + 1 < len(folded):
                s1 = folded[i].strip()
                s2 = folded[i + 1].strip()
                if s1.startswith('if ') and s1.endswith(' then') and s2 == 'end':
                    i += 2
                    continue
            no_empty.append(folded[i])
            i += 1

        deduped = []
        i = 0
        while i < len(no_empty):
            if i + 1 < len(no_empty):
                s1 = no_empty[i].strip()
                s2 = no_empty[i + 1].strip()
                m1 = re.match(r'^(?:local\s+)?(r\d+)\s*=\s*(.+)$', s1)
                m2 = re.match(r'^(?:local\s+)?(r\d+)\s*=', s2)
                if m1 and m2 and m1.group(1) == m2.group(1):
                    reg = m1.group(1)
                    val = m1.group(2)
                    reg_n = int(reg[1:])
                    has_local = s1.startswith('local ')
                    next_reg = f'r{reg_n + 1}'
                    if '(' not in val and ':' not in val:
                        if re.search(r'\b' + re.escape(next_reg) + r':', s2):
                            local_kw = 'local ' if has_local else ''
                            indent = no_empty[i][:len(no_empty[i]) - len(no_empty[i].lstrip())]
                            merged = re.sub(r'\b' + re.escape(next_reg) + r'\b', val, s2)
                            merged = re.sub(r'^local\s+', '', merged)
                            deduped.append(f'{indent}{local_kw}{merged}')
                            i += 2
                            continue
                    if not has_local and '(' not in val and ':' not in val and not val.startswith('r' + str(reg_n) + ' '):
                        i += 1
                        continue
            deduped.append(no_empty[i])
            i += 1

        moved = []
        i = 0
        while i < len(deduped):
            if i + 1 < len(deduped):
                s1 = deduped[i].strip()
                s2 = deduped[i + 1].strip()
                m_move = re.match(r'^(local\s+)?(r\d+)\s*=\s*(r\d+)$', s1)
                if m_move:
                    local_kw = m_move.group(1) or ''
                    dst = m_move.group(2)
                    src = m_move.group(3)
                    indent = deduped[i][:len(deduped[i]) - len(deduped[i].lstrip())]
                    m_sc = re.match(r'^' + re.escape(dst) + r'\s*=\s*' + re.escape(dst) + r'\((.+)\)$', s2)
                    if m_sc:
                        moved.append(f'{indent}{local_kw}{dst} = {src}({m_sc.group(1)})')
                        i += 2
                        continue
                    m_vc = re.match(r'^' + re.escape(dst) + r'\((.+)\)$', s2)
                    if m_vc:
                        moved.append(f'{indent}{src}({m_vc.group(1)})')
                        i += 2
                        continue
            moved.append(deduped[i])
            i += 1

        inlined = []
        i = 0
        while i < len(moved):
            if i + 1 < len(moved):
                s1 = moved[i].strip()
                m_const = re.match(r'^(?:local\s+)?(r\d+)\s*=\s*("(?:[^"\\]|\\.)*"|game|true|false|nil|-?\d+(?:\.\d+)?)\s*$', s1)
                if m_const:
                    reg = m_const.group(1)
                    val = m_const.group(2)
                    s2 = moved[i + 1].strip()
                    reg_pat = r'\b' + re.escape(reg) + r'\b'
                    eq_pos = s2.find('=')
                    is_assign = (eq_pos > 0
                                 and s2[eq_pos:eq_pos+2] != '=='
                                 and s2[max(0,eq_pos-1):eq_pos+1] not in ('~=', '<=', '>='))
                    if is_assign:
                        lhs = s2[:eq_pos]
                        rhs = s2[eq_pos:]
                    else:
                        lhs = ''
                        rhs = s2
                    if re.search(reg_pat, rhs) and not re.search(reg_pat, lhs):
                        callee_pat = re.escape(reg) + r'\s*\('
                        is_non_callable = bool(re.match(r'^(".*"|-?\d+(\.\d+)?|true|false|nil)$', val))
                        if is_non_callable and re.search(callee_pat, s2):
                            pass
                        else:
                            remaining_uses = 0
                            for j in range(i + 2, min(i + 20, len(moved))):
                                sj = moved[j].strip()
                                if re.search(reg_pat, sj):
                                    remaining_uses += 1
                                if sj.startswith('::') or sj in ('end', 'else') or sj.startswith('for ') or sj.startswith('if '):
                                    break
                            if remaining_uses == 0:
                                indent = moved[i + 1][:len(moved[i + 1]) - len(moved[i + 1].lstrip())]
                                new_rhs = re.sub(reg_pat, val, rhs)
                                inlined.append(f'{indent}{lhs}{new_rhs}')
                                i += 2
                                continue
            inlined.append(moved[i])
            i += 1

        final = []
        prev_blank = False
        for line in inlined:
            is_blank = line.strip() == ''
            if is_blank and prev_blank:
                continue
            final.append(line)
            prev_blank = is_blank

        return '\n'.join(final)


class IronBrew3Deobfuscator:
    def __init__(self):
        self.chunk: Optional[IB3Chunk] = None
        self.deserializer = IB3Deserializer()
        self.classifier = IB3OpcodeClassifier()

    @staticmethod
    def detect(source: str) -> bool:
        return source.strip().startswith('--ironbrew3')

    def deobfuscate(self, source: str) -> Optional[str]:
        self.chunk = self._extract_chunk(source)
        if self.chunk is None:
            return None

        constants, protos = self.deserializer.deserialize(self.chunk.hex_data)
        self.chunk.constants = constants
        self.chunk.protos = protos

        self.classifier.classify_from_source(source, protos, constants)

        env_map = self._build_env_map(constants, protos, self.classifier.opcode_map)

        decompiler = IB3Decompiler(
            constants=constants,
            protos=protos,
            opcode_map=self.classifier.opcode_map,
            stdlib_map=self.chunk.stdlib_map,
            entry_proto_index=self.chunk.entry_proto_index,
            env_map=env_map,
        )

        return decompiler.decompile_all()

    def repackage(self, source: str) -> Optional[str]:
        self.chunk = self._extract_chunk(source)
        if self.chunk is None:
            return None

        constants, protos = self.deserializer.deserialize(self.chunk.hex_data)
        self.chunk.constants = constants
        self.chunk.protos = protos

        self.classifier.classify_from_source(source, protos, constants)

        from .ib3_vm_repack import IB3VMRepackager
        repackager = IB3VMRepackager(
            constants=constants,
            protos=protos,
            opcode_map=self.classifier.opcode_map,
            stdlib_map=self.chunk.stdlib_map,
            entry_proto_index=self.chunk.entry_proto_index,
        )
        return repackager.repackage()

    def _build_env_map(self, constants, protos, opcode_map):
        env_map = {}
        from collections import Counter
        KNOWN_SERVICES = {
            'RunService', 'Players', 'Workspace', 'ReplicatedStorage',
            'ServerStorage', 'ServerScriptService', 'StarterGui',
            'StarterPack', 'Lighting', 'SoundService', 'TweenService',
            'UserInputService', 'HttpService', 'MarketplaceService',
            'CollectionService', 'PhysicsService', 'TextService',
            'Chat', 'Teams', 'BadgeService', 'DataStoreService',
            'MessagingService', 'PolicyService', 'LocalizationService',
        }
        env_root_counter = Counter()
        env_root_services = {}
        for proto in protos:
            for inst in proto.instructions:
                op_name = opcode_map.get(inst.opcode, '')
                if op_name in ('GETFIELD_ENV2', 'GETFIELD_ENV3') or op_name.startswith('GETFIELD_ENV'):
                    if inst.sub and len(inst.sub) >= 1:
                        root = constants[inst.sub[0]].value if 0 <= inst.sub[0] < len(constants) else None
                        if root and isinstance(root, str):
                            env_root_counter[root] += 1
                            if len(inst.sub) >= 2:
                                field = constants[inst.sub[1]].value if 0 <= inst.sub[1] < len(constants) else None
                                if isinstance(field, str) and field in KNOWN_SERVICES:
                                    env_root_services.setdefault(root, set()).add(field)
        for root_name, cnt in env_root_counter.most_common():
            if root_name in env_root_services:
                env_map[root_name] = 'game'
        base_method_counter = Counter()
        for proto in protos:
            insts = proto.instructions
            for j in range(len(insts)):
                inst = insts[j]
                op_name = opcode_map.get(inst.opcode, '')
                if op_name == 'GETTABLE' and inst.sub:
                    method_const = constants[inst.sub[0]].value if 0 <= inst.sub[0] < len(constants) else None
                    if not method_const:
                        continue
                    base_reg = inst.B
                    for k in range(j - 1, max(j - 5, -1), -1):
                        prev = insts[k]
                        if opcode_map.get(prev.opcode) == 'LOADK' and prev.A == base_reg:
                            base_const = constants[prev.C].value if 0 <= prev.C < len(constants) else None
                            if base_const and isinstance(base_const, str) and base_const in env_map:
                                base_method_counter[method_const] += 1
                            break
                        if prev.A == base_reg:
                            break
        for method, cnt in base_method_counter.most_common(3):
            if cnt >= 5 and method not in env_map:
                env_map[method] = 'GetService'
        KNOWN_FIELDS = {
            'wait': 'task', 'spawn': 'task', 'delay': 'task', 'defer': 'task',
            'cancel': 'task',
        }
        env_root_fields = {}
        for proto in protos:
            for inst in proto.instructions:
                op_name = opcode_map.get(inst.opcode, '')
                if (op_name in ('GETFIELD_ENV2', 'GETFIELD_ENV3') or op_name.startswith('GETFIELD_ENV')):
                    if inst.sub and len(inst.sub) >= 2:
                        root = constants[inst.sub[0]].value if 0 <= inst.sub[0] < len(constants) else None
                        field = constants[inst.sub[1]].value if 0 <= inst.sub[1] < len(constants) else None
                        if root and isinstance(root, str) and field and isinstance(field, str):
                            if root not in env_map:
                                env_root_fields.setdefault(root, []).append(field)
        for root, fields in env_root_fields.items():
            for f in fields:
                if f in KNOWN_FIELDS and root not in env_map:
                    env_map[root] = KNOWN_FIELDS[f]
                    break
        return env_map

    def _extract_chunk(self, source: str) -> Optional[IB3Chunk]:
        chunk = IB3Chunk()

        hex_match = re.search(r'i\("([0-9A-Fa-f]+)"', source)
        if hex_match:
            hex_str = hex_match.group(1)
            try:
                chunk.hex_data = bytes.fromhex(hex_str)
            except ValueError:
                return None
        else:
            long_hex = re.search(r'"([0-9A-Fa-f]{200,})"', source)
            if long_hex:
                try:
                    chunk.hex_data = bytes.fromhex(long_hex.group(1))
                except ValueError:
                    return None
            else:
                return None

        func_match = re.search(r'function\(([A-Za-z_,]+),\.\.\.\)', source)
        if func_match:
            params = func_match.group(1).split(',')
            chunk.param_names = params
            for i, (expected_name, stdlib_func) in enumerate(IB3_STDLIB_PARAMS):
                if i < len(params):
                    chunk.stdlib_map[params[i]] = stdlib_func

        entry_match = re.search(r'mh\[5\]\[(\d+)\]', source)
        if entry_match:
            chunk.entry_proto_index = int(entry_match.group(1)) - 1

        return chunk

    def get_summary(self) -> str:
        if self.chunk is None:
            return "No chunk extracted"
        lines = [
            f"IronBrew 3 Deobfuscation Summary",
            f"  Constants: {len(self.chunk.constants)}",
            f"  Protos: {len(self.chunk.protos)}",
            f"  Total instructions: {sum(len(p.instructions) for p in self.chunk.protos)}",
            f"  Unique opcodes: {len(set(i.opcode for p in self.chunk.protos for i in p.instructions))}",
            f"  Classified opcodes: {len(self.classifier.opcode_map)}",
            f"  Entry proto: {self.chunk.entry_proto_index}",
        ]
        if self.classifier.opcode_map:
            lines.append(f"  Opcode map:")
            for op, name in sorted(self.classifier.opcode_map.items()):
                conf = self.classifier.confidence.get(op, 0)
                lines.append(f"    {op:3d} -> {name} ({conf:.0%})")
        return '\n'.join(lines)
