from __future__ import annotations
import json
import re
import os
import time
from typing import List, Optional, Dict, Tuple, Any, Set
from dataclasses import dataclass, field
from ..core import lua_ast as ast
from ..core.lua_parser import parse as lua_parse
from ..core.lua_emitter import emit
from ..core.sandbox import LuaSandbox, LuaError
from ..core.symbolic import SymbolicExecutor, SymEnvironment
from ..utils.dispatch_tree import DispatchTreeParser, find_dispatch_loop
from .vm_lift import VMPrototype, VMInstruction, VMConstant


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class LuraphPrototype:
    proto_id: int = 0
    proto_type: int = 0
    num_regs: int = 0
    num_params: int = 0
    is_vararg: bool = False
    opcodes: List[int] = field(default_factory=list)
    operM: List[Any] = field(default_factory=list)
    operL: List[Any] = field(default_factory=list)
    operP: List[Any] = field(default_factory=list)
    constT: List[Any] = field(default_factory=list)
    constQ: List[Any] = field(default_factory=list)
    constG: List[Any] = field(default_factory=list)
    sub_protos: List[LuraphPrototype] = field(default_factory=list)

    @property
    def num_instructions(self) -> int:
        return len(self.opcodes)


@dataclass
class OpcodeInfo:
    vm_opcode: int
    standard_op: str
    confidence: float = 0.5
    handler_body: Optional[ast.Block] = None


@dataclass
class LuraphAnalysis:
    prototypes: List[LuraphPrototype] = field(default_factory=list)
    opcode_map: Dict[int, OpcodeInfo] = field(default_factory=dict)
    constant_table: Dict[str, str] = field(default_factory=dict)
    dispatch_var: Optional[str] = None
    num_opcodes_mapped: int = 0
    num_opcodes_total: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            'num_prototypes': len(self.prototypes),
            'num_opcodes_mapped': self.num_opcodes_mapped,
            'num_opcodes_total': self.num_opcodes_total,
            'dispatch_var': self.dispatch_var,
            'opcode_map': {
                str(k): {'standard_op': v.standard_op, 'confidence': v.confidence}
                for k, v in self.opcode_map.items()
            },
            'constant_table': self.constant_table,
            'prototypes': [
                {
                    'id': p.proto_id,
                    'num_instructions': p.num_instructions,
                    'num_regs': p.num_regs,
                    'opcodes_used': sorted(set(p.opcodes)),
                }
                for p in self.prototypes
            ],
        }


# ---------------------------------------------------------------------------
# 1. Detector
# ---------------------------------------------------------------------------

class LuraphDetector:
    def is_luraph(self, source: str, tree: Optional[ast.Block] = None) -> bool:
        score = 0
        for marker in ['Luraph', 'luraph', 'LRPH']:
            if marker in source:
                score += 3
        if tree is None:
            try:
                tree = lua_parse(source)
            except Exception:
                return score >= 3

        for node in _walk(tree):
            if isinstance(node, ast.While):
                depth = self._measure_dispatch_depth(node.body)
                if depth >= 5:
                    score += 4
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Field):
                if node.func.name == 'byte':
                    score += 1
            if isinstance(node, ast.BinOp) and node.op == '*':
                if isinstance(node.right, ast.Number) and node.right.value in (256, 65536, 16777216):
                    score += 1
        return score >= 4

    def _measure_dispatch_depth(self, body: ast.Block, depth: int = 0) -> int:
        max_d = depth
        for stmt in body.stmts:
            if isinstance(stmt, ast.If):
                for test in stmt.tests:
                    if self._is_numeric_cmp(test):
                        max_d = max(max_d, depth + 1)
                        break
                for b in stmt.bodies:
                    max_d = max(max_d, self._measure_dispatch_depth(b, depth + 1))
                if stmt.else_body:
                    max_d = max(max_d, self._measure_dispatch_depth(stmt.else_body, depth + 1))
        return max_d

    def _is_numeric_cmp(self, expr: ast.Expr) -> bool:
        if isinstance(expr, ast.UnOp) and expr.op == 'not':
            return self._is_numeric_cmp(expr.operand)
        if isinstance(expr, ast.BinOp) and expr.op in ('<', '<=', '>', '>=', '==', '~='):
            return isinstance(expr.right, ast.Number) or isinstance(expr.left, ast.Number)
        return False


# ---------------------------------------------------------------------------
# 2. Bytecode Extractor (lupa-based dynamic extraction)
# ---------------------------------------------------------------------------

class LuraphBytecodeExtractor:
    def __init__(self, op_limit: int = 100_000_000, timeout: float = 120.0):
        self.op_limit = op_limit
        self.timeout = timeout

    def extract(self, source: str) -> List[LuraphPrototype]:
        try:
            from ..utils.lua_runtime import LuaRuntimeWrapper, LuaRuntimeError
        except ImportError:
            return []

        runtime = LuaRuntimeWrapper(op_limit=self.op_limit, timeout=self.timeout)
        try:
            runtime._init_runtime()
        except Exception:
            return []

        modified = runtime.inject_bytecode_dumper(source)
        modified = runtime.suppress_vm_errors(modified)

        try:
            runtime.execute(modified)
        except Exception:
            pass

        raw_protos = runtime.extract_prototypes()
        if not raw_protos:
            return []

        result = []
        for rp in raw_protos:
            if rp.get('is_v14'):
                raw = rp.get('raw_fields', {})
                lp = LuraphPrototype(
                    proto_id=rp.get('id', 0),
                )
                lp._raw_fields = raw
                for fi, val in raw.items():
                    if isinstance(val, list):
                        if not lp.opcodes and len(val) > 0 and all(isinstance(v, (int, float)) for v in val[:10] if v is not None):
                            if fi not in lp._assigned_arrays:
                                lp._assigned_arrays = getattr(lp, '_assigned_arrays', set())
                                lp._assigned_arrays.add(fi)
                result.append(lp)
            else:
                lp = LuraphPrototype(
                    proto_id=rp.get('id', 0),
                    proto_type=rp.get('type', 0),
                    num_regs=rp.get('numregs', 0),
                    opcodes=rp.get('opcodes', []),
                    operM=rp.get('operM', []),
                    operL=rp.get('operL', []),
                    operP=rp.get('operP', []),
                    constT=rp.get('constT', []),
                    constQ=rp.get('constQ', []),
                    constG=rp.get('constG', []),
                )
                result.append(lp)
        return result


# ---------------------------------------------------------------------------
# 3. Opcode Mapper (static dispatch tree analysis)
# ---------------------------------------------------------------------------

class LuraphOpcodeMapper:
    def __init__(self):
        self.opcode_map: Dict[int, OpcodeInfo] = {}

    def map_from_tree(self, tree: ast.Block) -> Dict[int, OpcodeInfo]:
        dispatch_body = find_dispatch_loop(tree)
        if dispatch_body is None:
            return {}

        parser = DispatchTreeParser()
        handlers = parser.parse(dispatch_body)

        for opcode, handler_body in handlers.items():
            se = SymbolicExecutor(max_steps=5000)
            std_op = se.classify_handler(handler_body)
            if std_op:
                self.opcode_map[opcode] = OpcodeInfo(
                    vm_opcode=opcode,
                    standard_op=std_op,
                    confidence=0.7,
                    handler_body=handler_body,
                )
            else:
                fallback = self._heuristic_classify(handler_body)
                if fallback:
                    self.opcode_map[opcode] = OpcodeInfo(
                        vm_opcode=opcode,
                        standard_op=fallback,
                        confidence=0.4,
                        handler_body=handler_body,
                    )

        return self.opcode_map

    def map_from_prototypes(self, protos: List[LuraphPrototype]) -> Set[int]:
        used_opcodes: Set[int] = set()
        for p in protos:
            used_opcodes.update(p.opcodes)
        return used_opcodes

    def _heuristic_classify(self, body: ast.Block) -> Optional[str]:
        if not body.stmts:
            return "NOP"
        for node in _walk(body):
            if isinstance(node, ast.BinOp):
                arith = {'+': 'ADD', '-': 'SUB', '*': 'MUL', '/': 'DIV',
                         '%': 'MOD', '^': 'POW', '..': 'CONCAT',
                         '//': 'IDIV', '&': 'BAND', '|': 'BOR', '~': 'BXOR'}
                if node.op in arith:
                    return arith[node.op]
            if isinstance(node, ast.UnOp):
                if node.op == '-': return 'UNM'
                if node.op == 'not': return 'NOT'
                if node.op == '#': return 'LEN'
            if isinstance(node, ast.TableConstructor) and not node.fields:
                return 'NEWTABLE'
            if isinstance(node, ast.Return):
                return 'RETURN'
            if isinstance(node, ast.FunctionExpr):
                return 'CLOSURE'
        return None


# ---------------------------------------------------------------------------
# 4. Constant Decoder
# ---------------------------------------------------------------------------

class LuraphConstantDecoder:
    def decode_constant_table(self, protos: List[LuraphPrototype]) -> Dict[str, str]:
        if not protos:
            return {}
        ct: Dict[str, str] = {}
        p1 = protos[0]
        for idx in range(p1.num_instructions):
            g = p1.constG[idx] if idx < len(p1.constG) else None
            t = p1.constT[idx] if idx < len(p1.constT) else None
            if g is not None and t is not None:
                ct[str(g)] = str(t)
        return ct


# ---------------------------------------------------------------------------
# 5. Decompiler (prototype → AST)
# ---------------------------------------------------------------------------

class LuraphDecompiler:
    def __init__(self, opcode_map: Dict[int, OpcodeInfo],
                 constant_table: Dict[str, str]):
        self.opcode_map = opcode_map
        self.constant_table = constant_table

    def decompile_all(self, protos: List[LuraphPrototype]) -> ast.Block:
        stmts: List[ast.Stmt] = []
        if len(protos) >= 2:
            main_stmts = self._decompile_proto(protos[1])
            stmts.extend(main_stmts)
        for i, proto in enumerate(protos):
            if i <= 1:
                continue
            fn_stmts = self._decompile_proto(proto)
            func_expr = ast.FunctionExpr(
                params=[f"arg{j}" for j in range(proto.num_params)],
                has_vararg=proto.is_vararg,
                body=ast.Block(stmts=fn_stmts),
            )
            stmts.append(ast.LocalAssign(
                names=[f"proto_{i+1}"],
                values=[func_expr],
            ))
        return ast.Block(stmts=stmts)

    def _decompile_proto(self, proto: LuraphPrototype) -> List[ast.Stmt]:
        stmts: List[ast.Stmt] = []
        n = proto.num_instructions
        for idx in range(n):
            op = proto.opcodes[idx]
            info = self.opcode_map.get(op)
            if info is None:
                continue

            m = self._num(proto.operM, idx)
            l = self._num(proto.operL, idx)
            p = self._num(proto.operP, idx)
            t = proto.constT[idx] if idx < len(proto.constT) else None
            q = proto.constQ[idx] if idx < len(proto.constQ) else None
            g = proto.constG[idx] if idx < len(proto.constG) else None

            decoded = self._emit_instruction(info.standard_op, m, l, p, t, q, g)
            if decoded:
                stmts.extend(decoded)

        return stmts

    def _emit_instruction(self, std_op: str, m: int, l: int, p: int,
                           t: Any, q: Any, g: Any) -> List[ast.Stmt]:
        R = lambda x: ast.Name(name=f"r{x}")
        N = lambda x: ast.Number(value=x) if isinstance(x, (int, float)) else ast.String(value=str(x), raw='')

        def resolve_key(v):
            if v is None:
                return ast.Nil()
            k = str(v)
            resolved = self.constant_table.get(k, k)
            if resolved and isinstance(resolved, str):
                try:
                    fv = float(resolved)
                    if fv == int(fv):
                        return ast.Number(value=int(fv))
                    return ast.Number(value=fv)
                except (ValueError, TypeError):
                    pass
                return ast.String(value=resolved, raw='')
            return N(v)

        if std_op == 'MOVE':
            return [ast.Assign(targets=[R(m)], values=[R(p)])]
        if std_op == 'LOADK':
            return [ast.Assign(targets=[R(m)], values=[resolve_key(q)])]
        if std_op == 'LOADNIL':
            return [ast.Assign(targets=[R(p)], values=[ast.Nil()])]
        if std_op == 'LOADBOOL':
            return [ast.Assign(targets=[R(m)], values=[ast.Bool(value=bool(q))])]
        if std_op in ('ADD', 'SUB', 'MUL', 'DIV', 'MOD', 'POW', 'IDIV',
                       'BAND', 'BOR', 'BXOR', 'CONCAT'):
            sym_map = {'ADD': '+', 'SUB': '-', 'MUL': '*', 'DIV': '/',
                       'MOD': '%', 'POW': '^', 'IDIV': '//', 'BAND': '&',
                       'BOR': '|', 'BXOR': '~', 'CONCAT': '..'}
            return [ast.Assign(targets=[R(m)], values=[
                ast.BinOp(op=sym_map[std_op], left=R(l), right=R(p))])]
        if std_op in ('UNM', 'NOT', 'LEN'):
            sym_map = {'UNM': '-', 'NOT': 'not', 'LEN': '#'}
            return [ast.Assign(targets=[R(m)], values=[
                ast.UnOp(op=sym_map[std_op], operand=R(l))])]
        if std_op == 'NEWTABLE':
            return [ast.Assign(targets=[R(m)], values=[ast.TableConstructor(fields=[])])]
        if std_op == 'GETTABLE':
            return [ast.Assign(targets=[R(p)], values=[
                ast.Index(table=R(m), key=resolve_key(q))])]
        if std_op == 'SETTABLE':
            return [ast.Assign(
                targets=[ast.Index(table=R(p), key=resolve_key(t))],
                values=[R(l)])]
        if std_op == 'CALL':
            func = R(m)
            nargs = max(0, l - 1)
            args = [R(m + 1 + i) for i in range(nargs)]
            call = ast.Call(func=func, args=args)
            return [ast.ExprStmt(expr=call)]
        if std_op == 'RETURN':
            return [ast.Return(values=[R(m)])]
        if std_op == 'CLOSURE':
            return [ast.Assign(targets=[R(m)], values=[
                ast.FunctionExpr(params=[], body=ast.Block(stmts=[]))])]
        if std_op == 'JMP':
            return []
        if std_op in ('TEST', 'EQ', 'LT', 'LE'):
            return []
        if std_op in ('FORPREP', 'FORLOOP', 'TFORLOOP'):
            return []
        if std_op == 'NOP':
            return []
        if std_op == 'SELF':
            return [ast.Assign(targets=[R(p+1)], values=[R(m)]),
                    ast.Assign(targets=[R(p)], values=[
                        ast.Index(table=R(m), key=resolve_key(q))])]
        return []

    def _num(self, arr: List[Any], idx: int) -> int:
        if idx < len(arr) and arr[idx] is not None:
            try:
                return int(arr[idx])
            except (TypeError, ValueError):
                return 0
        return 0


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

class LuraphDeobfuscator:
    def __init__(self, sandbox: Optional[LuaSandbox] = None,
                 op_limit: int = 100_000_000, timeout: float = 120.0,
                 inspect_path: Optional[str] = None):
        self.sandbox = sandbox or LuaSandbox(op_limit=20_000_000, timeout=60.0)
        self.op_limit = op_limit
        self.timeout = timeout
        self.inspect_path = inspect_path
        self.analysis: Optional[LuraphAnalysis] = None

    def deobfuscate(self, source: str) -> Optional[ast.Block]:
        detector = LuraphDetector()
        if not detector.is_luraph(source):
            return None

        analysis = LuraphAnalysis()

        extractor = LuraphBytecodeExtractor(
            op_limit=self.op_limit, timeout=self.timeout)
        protos = extractor.extract(source)
        analysis.prototypes = protos

        mapper = LuraphOpcodeMapper()
        try:
            tree = lua_parse(source)
            opcode_map = mapper.map_from_tree(tree)
        except Exception:
            opcode_map = {}
        analysis.opcode_map = opcode_map
        analysis.num_opcodes_mapped = len(opcode_map)

        used_opcodes = mapper.map_from_prototypes(protos) if protos else set()
        analysis.num_opcodes_total = len(used_opcodes)

        decoder = LuraphConstantDecoder()
        ct = decoder.decode_constant_table(protos)
        analysis.constant_table = ct

        self.analysis = analysis

        if self.inspect_path:
            try:
                with open(self.inspect_path, 'w', encoding='utf-8') as f:
                    json.dump(analysis.to_dict(), f, indent=2, default=str)
            except Exception:
                pass

        if not protos:
            return None

        decompiler = LuraphDecompiler(opcode_map, ct)
        return decompiler.decompile_all(protos)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _walk(node: ast.Node):
    yield node
    for child in node.children():
        yield from _walk(child)


def deobfuscate_luraph(source: str, sandbox: Optional[LuaSandbox] = None,
                       inspect_path: Optional[str] = None) -> Optional[ast.Block]:
    d = LuraphDeobfuscator(sandbox, inspect_path=inspect_path)
    return d.deobfuscate(source)
