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

            elif name == 'TEST':
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
                if wh_val is not None and wh_val not in self.opcode_map:
                    self.opcode_map[wh_val] = op_name
                    self.confidence[wh_val] = 0.8

        self._find_call_handlers(vm_code)
        self._find_closure_handler(vm_code)
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
        if 'Ih[Ah]then' in code and 'rh=zh' in code: return 'TEST'
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

    def _find_all_wh_comparisons(self, vm_code: str):
        results = []
        wh_patterns = [
            (r'Wh([<>=!~]+)\s*\(([^)]*?)\)\s*then', 2),
            (r'Wh([<>=!~]+)\s*(\d+)\s*then', 2),
            (r'Wh==\s*\(\(([^)]*?)\)\)\s*then', 1),
        ]
        for pat, grp in wh_patterns:
            for m in re.finditer(pat, vm_code):
                if grp == 1:
                    op = '=='
                    val = self._resolve_opaque(m.group(1))
                else:
                    op = m.group(1)
                    val = self._resolve_opaque(m.group(2))
                if val is not None:
                    results.append((m.start(), m.end(), op, val))
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
                self.opcode_map[wh_val] = 'TEST'
                self.confidence[wh_val] = 0.85

    def _find_move_handler(self, vm_code: str):
        for m in re.finditer(r'Ih\[Ah\]=Ih\[Qh\]end', vm_code):
            wh_val = self._find_near_wh_eq(vm_code, m.start())
            if wh_val and wh_val not in self.opcode_map:
                self.opcode_map[wh_val] = 'MOVE'
                self.confidence[wh_val] = 0.9

    def _find_concat_handler(self, vm_code: str):
        for m in re.finditer(r'Ih\[Ah\]=Ih\[Qh\]\.\.Ih\[', vm_code):
            wh_val = self._find_near_wh_eq(vm_code, m.start())
            if wh_val and wh_val not in self.opcode_map:
                self.opcode_map[wh_val] = 'CONCAT'
                self.confidence[wh_val] = 0.9

    def _find_gettable_handlers(self, vm_code: str):
        for m in re.finditer(r'Ih\[Ah\]=Ih\[Qh\]\[Ih\[Vh\]\]', vm_code):
            wh_val = self._find_near_wh_eq(vm_code, m.start())
            if wh_val and wh_val not in self.opcode_map:
                self.opcode_map[wh_val] = 'GETTABLE'
                self.confidence[wh_val] = 0.9

        for m in re.finditer(r'Ih\[Ah\]=Ih\[Qh\]\[Hh\[fh\[', vm_code):
            wh_val = self._find_near_wh_eq(vm_code, m.start())
            if wh_val and wh_val not in self.opcode_map:
                self.opcode_map[wh_val] = 'GETTABLE'
                self.confidence[wh_val] = 0.85

    def _find_settable_handlers(self, vm_code: str):
        for m in re.finditer(r'Ih\[Qh\]\[Ih\[Vh\]\]=Ih\[Ah\]', vm_code):
            wh_val = self._find_near_wh_eq(vm_code, m.start())
            if wh_val and wh_val not in self.opcode_map:
                self.opcode_map[wh_val] = 'SETTABLE'
                self.confidence[wh_val] = 0.9

        for m in re.finditer(r'Ih\[Qh\]\[Hh\[fh\[', vm_code):
            ctx = vm_code[m.start():m.start()+100]
            if ']=Ih[Ah]' in ctx:
                wh_val = self._find_near_wh_eq(vm_code, m.start())
                if wh_val and wh_val not in self.opcode_map:
                    self.opcode_map[wh_val] = 'SETTABLE'
                    self.confidence[wh_val] = 0.85

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
                wh_val = self._find_near_wh_eq(vm_code, m.start())
                if wh_val is not None and wh_val not in self.opcode_map:
                    self.opcode_map[wh_val] = 'CLOSURE'
                    self.confidence[wh_val] = 0.95

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
                 'forloop_ranges', 'declared_regs', 'proto', 'n_inst')
    def __init__(self, instructions, jump_targets, skip_labels, if_block_ends,
                 forloop_ranges, declared_regs, proto, n_inst):
        self.instructions = instructions
        self.jump_targets = jump_targets
        self.skip_labels = skip_labels
        self.if_block_ends = if_block_ends
        self.forloop_ranges = forloop_ranges
        self.declared_regs = declared_regs
        self.proto = proto
        self.n_inst = n_inst


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

        ctx = _DecompCtx(instructions, jump_targets, skip_labels, if_block_ends,
                         forloop_ranges, declared_regs, proto, n_inst)

        if 0 in jump_targets and 0 not in skip_labels:
            lines.append(f'{indent}::label_0::')

        self._emit_block(lines, ctx, 0, n_inst, indent, depth)

        if n_inst in jump_targets and n_inst not in skip_labels:
            lines.append(f'{indent}::label_{n_inst}::')

        return '\n'.join(lines)

    def _emit_block(self, lines, ctx, start_pc, end_pc, indent, depth):
        pc = start_pc
        while pc < end_pc:
            inst = ctx.instructions[pc]

            if pc in ctx.jump_targets and pc > 0 and pc not in ctx.skip_labels:
                lines.append(f'{indent}::label_{pc}::')

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

            if op_name in ('TEST', 'EQ', 'LT', 'LE') and pc in ctx.if_block_ends:
                block_end = ctx.if_block_ends[pc]
                if block_end <= end_pc:
                    A, B, C_val, D = inst.A, inst.B, inst.C, inst.D
                    sub = inst.sub or []
                    n_inst = ctx.n_inst
                    if op_name == 'TEST':
                        cond = f'not r{A}'
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
            if self._env_map and C < len(self.constants):
                val = self.constants[C].value
                if isinstance(val, str) and val in self._env_map:
                    return [f'{indent}r{A} = {self._env_map[val]}']
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
            return [f'{indent}goto label_{C}']

        elif op_name == 'EQ':
            n_inst = len(proto.instructions)
            if sub:
                target = C if C <= n_inst else D
                return [f'{indent}if r{A} == r{sub[0]} then goto label_{target} end']
            elif B > 0 and D > 0:
                target = C if C <= n_inst else D
                return [f'{indent}if r{B} == r{D} then goto label_{target} end']
            elif C <= n_inst:
                return [f'{indent}if r{A} == nil then goto label_{C} end']
            else:
                return [f'{indent}if r{A} == nil then goto label_{D} end']

        elif op_name == 'LT':
            if sub:
                cmp_reg = sub[0]
                return [f'{indent}if r{A} < r{cmp_reg} then goto label_{C} end']
            neg = '>=' if A != 0 else '<'
            return [f'{indent}if r{B} {neg} r{D} then goto label_{C} end']

        elif op_name == 'LE':
            neg = '>' if A != 0 else '<='
            return [f'{indent}if r{B} {neg} r{D} then goto label_{C} end']

        elif op_name == 'TEST':
            n_inst = len(proto.instructions)
            if C >= 0 and C <= n_inst:
                return [f'{indent}if r{A} then goto label_{C} end']
            elif D >= 0 and D <= n_inst:
                return [f'{indent}if r{A} then goto label_{D} end']
            return [f'{indent}-- TEST r{A} (jump target out of range: C={C})']

        elif op_name == 'CALL':
            nargs = B
            nrets = D
            if nargs > 0:
                args = ', '.join(f'r{A + 1 + i}' for i in range(nargs))
            else:
                args = '...'
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
                args = '...'
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
                    args = '...'
                call = f'r{A}({args})'
                if nrets == 0:
                    return [f'{indent}{call}']
                elif nrets == 1:
                    return [f'{indent}r{A} = {call}']
                else:
                    rets = ', '.join(f'r{A + i}' for i in range(nrets))
                    return [f'{indent}{rets} = {call}']
            if C == 0:
                return [f'{indent}r{A} = r{B} <op> r{D}']
            else:
                return [f'{indent}r{A} = r{B} <op> {self._rk_str(C)}']

        elif op_name == 'NOP':
            return []

        elif op_name == 'FORLOOP':
            return [f'{indent}-- FORLOOP r{A} step=r{A+2}, goto label_{C}']

        elif op_name == 'FORPREP':
            return [f'{indent}-- FORPREP r{A}, goto label_{C}']

        elif op_name == 'TFORLOOP':
            return [f'{indent}-- TFORLOOP r{A}']

        elif op_name == 'SETLIST':
            return [f'{indent}-- SETLIST r{A}']

        elif op_name == 'CLOSURE':
            if C < len(self.protos):
                child = self.protos[C]
                nparams = child.num_params
                params = ', '.join(f'p{i}' for i in range(nparams))
                lines = [f'{indent}r{A} = function({params})']
                body = self._decompile_proto(C, depth + 1)
                if body.strip():
                    lines.append(body)
                lines.append(f'{indent}end')
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
                return [f'{indent}r{A} = nil']
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
                return [f'{indent}goto label_{C}']
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
                return f'_G["{c.value}"]'
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
        return result

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

        moved = []
        i = 0
        while i < len(folded):
            if i + 1 < len(folded):
                s1 = folded[i].strip()
                s2 = folded[i + 1].strip()
                m_move = re.match(r'^(local\s+)?(r\d+)\s*=\s*(r\d+)$', s1)
                if m_move:
                    local_kw = m_move.group(1) or ''
                    dst = m_move.group(2)
                    src = m_move.group(3)
                    indent = folded[i][:len(folded[i]) - len(folded[i].lstrip())]
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
            moved.append(folded[i])
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
