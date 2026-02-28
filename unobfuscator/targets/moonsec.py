from __future__ import annotations
from typing import List, Optional, Dict, Tuple, Any
from dataclasses import dataclass, field
from ..core import lua_ast as ast
from ..core.lua_parser import parse as lua_parse
from ..core.lua_emitter import emit
from ..core.sandbox import LuaSandbox, LuaError
from ..core.symbolic import SymbolicExecutor, SymEnvironment
from .vm_lift import VMPrototype, VMInstruction, VMConstant


@dataclass
class MoonsecChunk:
    bytecode_data: Optional[str] = None
    vm_body: Optional[ast.Block] = None
    handler_table: Optional[ast.TableConstructor] = None
    deserializer: Optional[ast.FunctionExpr] = None
    encryption_key: Optional[int] = None
    constants: List[Any] = field(default_factory=list)
    instructions: List[Tuple] = field(default_factory=list)
    sub_protos: List[MoonsecChunk] = field(default_factory=list)
    num_params: int = 0
    max_stack: int = 0


class MoonsecV3Deobfuscator:
    def __init__(self, sandbox: Optional[LuaSandbox] = None):
        self.sandbox = sandbox or LuaSandbox(op_limit=20_000_000, timeout=60.0)
        self.opcode_map: Dict[int, str] = {}

    def deobfuscate(self, source: str) -> Optional[ast.Block]:
        tree = lua_parse(source)
        if not self._is_moonsec(tree):
            return None

        chunk = self._extract_chunk(tree)
        if chunk is None:
            return None

        self._recover_opcodes(chunk)
        proto = self._build_prototype(chunk)
        stmts = self._decompile(proto)
        return ast.Block(stmts=stmts)

    def _is_moonsec(self, tree: ast.Block) -> bool:
        score = 0
        source = emit(tree)

        for marker in ['MoonSec', 'moonsec', 'MSEC', 'v3']:
            if marker in source:
                score += 1

        for node in _walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.FunctionExpr):
                body = node.func.body
                if self._has_moonsec_patterns(body):
                    score += 3

            if isinstance(node, ast.BinOp) and node.op == '~':
                score += 1

            if isinstance(node, ast.LocalAssign):
                for val in node.values:
                    if isinstance(val, ast.String) and len(val.value) > 1000:
                        has_xor_decode = False
                        for sibling in _walk(tree):
                            if isinstance(sibling, ast.BinOp) and sibling.op == '~':
                                has_xor_decode = True
                                break
                        if has_xor_decode:
                            score += 2

        return score >= 3

    def _has_moonsec_patterns(self, body: ast.Block) -> bool:
        has_multi_layer = False
        has_xor = False
        has_dispatch = False
        has_string_table = False

        for node in _walk(body):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.name in ('loadstring', 'load'):
                    has_multi_layer = True
            if isinstance(node, ast.BinOp) and node.op in ('~', '&', '|'):
                has_xor = True
            if isinstance(node, ast.While):
                for stmt in node.body.stmts:
                    if isinstance(stmt, ast.If) and len(stmt.tests) >= 5:
                        has_dispatch = True
            if isinstance(node, ast.TableConstructor):
                str_count = sum(1 for f in node.fields if isinstance(f.value, ast.String))
                if str_count >= 5:
                    has_string_table = True

        return sum([has_multi_layer, has_xor, has_dispatch, has_string_table]) >= 2

    def _extract_chunk(self, tree: ast.Block) -> Optional[MoonsecChunk]:
        chunk = MoonsecChunk()

        for node in _walk(tree):
            if isinstance(node, ast.String) and len(node.value) > 500:
                if chunk.bytecode_data is None:
                    chunk.bytecode_data = node.value

        for node in _walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.FunctionExpr):
                body = node.func.body
                self._find_vm_components(body, chunk)
                if chunk.vm_body:
                    break

        if chunk.vm_body is None:
            for stmt in tree.stmts:
                if isinstance(stmt, ast.ExprStmt) and isinstance(stmt.expr, ast.Call):
                    call = stmt.expr
                    if isinstance(call.func, ast.Call) and isinstance(call.func.func, ast.FunctionExpr):
                        self._find_vm_components(call.func.func.body, chunk)

        key = self._find_encryption_key(tree)
        if key is not None:
            chunk.encryption_key = key

        return chunk if (chunk.bytecode_data or chunk.vm_body) else None

    def _find_vm_components(self, body: ast.Block, chunk: MoonsecChunk):
        for stmt in body.stmts:
            if isinstance(stmt, ast.LocalAssign):
                for val in stmt.values:
                    if isinstance(val, ast.FunctionExpr):
                        if self._is_deserializer(val):
                            chunk.deserializer = val
                        elif self._is_vm_func(val):
                            chunk.vm_body = val.body
            if isinstance(stmt, ast.While):
                for s in stmt.body.stmts:
                    if isinstance(s, ast.If) and len(s.tests) >= 5:
                        chunk.vm_body = stmt.body
                        break
            if isinstance(stmt, ast.FunctionDecl):
                if self._is_vm_func_body(stmt.body):
                    chunk.vm_body = stmt.body

    def _is_deserializer(self, func: ast.FunctionExpr) -> bool:
        score = 0
        for node in _walk(func.body):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Field):
                if node.func.name in ('byte', 'sub', 'char'):
                    score += 1
            if isinstance(node, ast.BinOp) and node.op == '*':
                if isinstance(node.right, ast.Number) and node.right.value in (256, 65536, 16777216):
                    score += 2
        return score >= 3

    def _is_vm_func(self, func: ast.FunctionExpr) -> bool:
        return self._is_vm_func_body(func.body)

    def _is_vm_func_body(self, body: ast.Block) -> bool:
        for node in _walk(body):
            if isinstance(node, ast.While):
                for stmt in node.body.stmts:
                    if isinstance(stmt, ast.If) and len(stmt.tests) >= 5:
                        return True
        return False

    def _find_encryption_key(self, tree: ast.Block) -> Optional[int]:
        for node in _walk(tree):
            if isinstance(node, ast.BinOp) and node.op == '~':
                if isinstance(node.right, ast.Number):
                    return int(node.right.value)
                if isinstance(node.left, ast.Number):
                    return int(node.left.value)
        return None

    def _recover_opcodes(self, chunk: MoonsecChunk):
        if chunk.vm_body is None:
            return
        self._scan_if_chains(chunk.vm_body)

    def _scan_if_chains(self, body: ast.Block):
        for stmt in body.stmts:
            if isinstance(stmt, ast.If):
                for i, test in enumerate(stmt.tests):
                    if isinstance(test, ast.BinOp) and test.op == '==':
                        if isinstance(test.right, ast.Number) and i < len(stmt.bodies):
                            opcode = int(test.right.value)
                            std = self._classify_handler(stmt.bodies[i])
                            if std:
                                self.opcode_map[opcode] = std
            if isinstance(stmt, ast.While):
                self._scan_if_chains(stmt.body)
            if isinstance(stmt, ast.Do):
                self._scan_if_chains(stmt.body)

    def _classify_handler(self, body: ast.Block) -> Optional[str]:
        se = SymbolicExecutor(max_steps=3000)
        result = se.classify_handler(body)
        if result:
            return result

        for node in _walk(body):
            if isinstance(node, ast.BinOp):
                arith = {'+': 'ADD', '-': 'SUB', '*': 'MUL', '/': 'DIV',
                         '%': 'MOD', '^': 'POW', '..': 'CONCAT'}
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
        return None

    def _build_prototype(self, chunk: MoonsecChunk) -> VMPrototype:
        proto = VMPrototype()
        proto.num_params = chunk.num_params
        proto.max_stack = chunk.max_stack
        for i, c in enumerate(chunk.constants):
            t = 'nil'
            if isinstance(c, bool): t = 'boolean'
            elif isinstance(c, (int, float)): t = 'number'
            elif isinstance(c, str): t = 'string'
            proto.constants.append(VMConstant(i, c, t))
        for pc, inst_data in enumerate(chunk.instructions):
            if isinstance(inst_data, (list, tuple)) and inst_data:
                proto.instructions.append(VMInstruction(
                    opcode=inst_data[0], operands=list(inst_data[1:]), pc=pc))
        return proto

    def _decompile(self, proto: VMPrototype) -> List[ast.Stmt]:
        stmts = []
        for inst in proto.instructions:
            std_op = self.opcode_map.get(inst.opcode)
            if std_op is None:
                continue
            decoded = self._decode_inst(std_op, inst, proto)
            if decoded:
                stmts.extend(decoded)
        return stmts

    def _decode_inst(self, std_op: str, inst: VMInstruction, proto: VMPrototype) -> List[ast.Stmt]:
        ops = inst.operands
        if std_op == 'MOVE' and len(ops) >= 2:
            return [ast.LocalAssign(names=[f"v{ops[0]}"], values=[ast.Name(name=f"v{ops[1]}")])]
        if std_op == 'LOADK' and len(ops) >= 2:
            return [ast.LocalAssign(names=[f"v{ops[0]}"], values=[self._const_ast(proto, ops[1])])]
        if std_op == 'LOADNIL' and len(ops) >= 1:
            return [ast.LocalAssign(names=[f"v{ops[0]}"], values=[ast.Nil()])]
        if std_op == 'LOADBOOL' and len(ops) >= 2:
            return [ast.LocalAssign(names=[f"v{ops[0]}"], values=[ast.Bool(value=bool(ops[1]))])]
        if std_op in ('ADD', 'SUB', 'MUL', 'DIV', 'MOD', 'POW') and len(ops) >= 3:
            sym = {'ADD': '+', 'SUB': '-', 'MUL': '*', 'DIV': '/', 'MOD': '%', 'POW': '^'}[std_op]
            return [ast.LocalAssign(names=[f"v{ops[0]}"],
                values=[ast.BinOp(op=sym, left=self._rk(proto, ops[1]), right=self._rk(proto, ops[2]))])]
        if std_op in ('UNM', 'NOT', 'LEN') and len(ops) >= 2:
            sym = {'UNM': '-', 'NOT': 'not', 'LEN': '#'}[std_op]
            return [ast.LocalAssign(names=[f"v{ops[0]}"],
                values=[ast.UnOp(op=sym, operand=ast.Name(name=f"v{ops[1]}"))])]
        if std_op == 'CONCAT' and len(ops) >= 3:
            vals = [ast.Name(name=f"v{r}") for r in range(ops[1], ops[2] + 1)]
            return [ast.LocalAssign(names=[f"v{ops[0]}"], values=[ast.Concat(values=vals)])]
        if std_op == 'NEWTABLE' and len(ops) >= 1:
            return [ast.LocalAssign(names=[f"v{ops[0]}"], values=[ast.TableConstructor(fields=[])])]
        if std_op == 'GETTABLE' and len(ops) >= 3:
            return [ast.LocalAssign(names=[f"v{ops[0]}"],
                values=[ast.Index(table=ast.Name(name=f"v{ops[1]}"), key=self._rk(proto, ops[2]))])]
        if std_op == 'SETTABLE' and len(ops) >= 3:
            return [ast.Assign(
                targets=[ast.Index(table=ast.Name(name=f"v{ops[0]}"), key=self._rk(proto, ops[1]))],
                values=[self._rk(proto, ops[2])])]
        if std_op == 'CALL' and len(ops) >= 3:
            func = ast.Name(name=f"v{ops[0]}")
            nargs = max(0, ops[1] - 1) if ops[1] != 0 else 0
            args = [ast.Name(name=f"v{ops[0] + 1 + i}") for i in range(nargs)]
            call = ast.Call(func=func, args=args)
            nresults = ops[2] - 1 if ops[2] != 0 else 0
            if nresults == 0:
                return [ast.ExprStmt(expr=call)]
            return [ast.LocalAssign(names=[f"v{ops[0]}"], values=[call])]
        if std_op == 'RETURN' and len(ops) >= 1:
            nvals = max(0, ops[0] - 1) if ops[0] != 0 else 0
            vals = [ast.Name(name=f"v{i}") for i in range(nvals)]
            return [ast.Return(values=vals)]
        if std_op == 'JMP':
            return []
        if std_op == 'GETGLOBAL' and len(ops) >= 2:
            name = self._const_value(proto, ops[1])
            if isinstance(name, str):
                return [ast.LocalAssign(names=[f"v{ops[0]}"], values=[ast.Name(name=name)])]
        if std_op == 'SETGLOBAL' and len(ops) >= 2:
            name = self._const_value(proto, ops[1])
            if isinstance(name, str):
                return [ast.Assign(targets=[ast.Name(name=name)], values=[ast.Name(name=f"v{ops[0]}")])]
        return []

    def _const_ast(self, proto: VMPrototype, idx: int) -> ast.Expr:
        v = self._const_value(proto, idx)
        if v is None: return ast.Nil()
        if isinstance(v, bool): return ast.Bool(value=v)
        if isinstance(v, (int, float)): return ast.Number(value=v)
        if isinstance(v, str): return ast.String(value=v, raw='')
        return ast.Nil()

    def _const_value(self, proto: VMPrototype, idx: int) -> Any:
        if 0 <= idx < len(proto.constants):
            return proto.constants[idx].value
        return None

    def _rk(self, proto: VMPrototype, val: int) -> ast.Expr:
        if val >= 256:
            return self._const_ast(proto, val - 256)
        return ast.Name(name=f"v{val}")


def _walk(node: ast.Node):
    yield node
    for child in node.children():
        yield from _walk(child)


def deobfuscate_moonsec(source: str, sandbox: Optional[LuaSandbox] = None) -> Optional[ast.Block]:
    d = MoonsecV3Deobfuscator(sandbox)
    return d.deobfuscate(source)
