from __future__ import annotations
from typing import List, Optional, Dict, Set, Tuple, Any
from dataclasses import dataclass, field
from ..core import lua_ast as ast
from ..core.lua_parser import parse as lua_parse
from ..core.lua_emitter import emit
from ..core.sandbox import LuaSandbox, LuaError
from ..core.symbolic import SymbolicExecutor, SymVal, SymKind, SymEnvironment
from .vm_lift import VMLifter, VMPrototype, VMInstruction, OpcodeMapping, VMPatternMatcher


@dataclass
class IB2Chunk:
    bytecode_string: Optional[str] = None
    deserializer_func: Optional[ast.FunctionExpr] = None
    vm_func: Optional[ast.FunctionExpr] = None
    wrapper_call: Optional[ast.Call] = None
    constants: List[Any] = field(default_factory=list)
    instructions: List[Tuple[int, ...]] = field(default_factory=list)
    protos: List[IB2Chunk] = field(default_factory=list)
    num_params: int = 0
    is_vararg: bool = False
    max_stack: int = 0


class IronBrew2Deobfuscator:
    def __init__(self, sandbox: Optional[LuaSandbox] = None):
        self.sandbox = sandbox or LuaSandbox(op_limit=20_000_000, timeout=60.0)
        self.opcode_map: Dict[int, str] = {}
        self.handler_signatures: Dict[int, str] = {}

    def deobfuscate(self, source: str) -> Optional[ast.Block]:
        tree = lua_parse(source)
        if not self._is_ironbrew2(tree):
            return None

        chunk = self._extract_chunk(tree)
        if chunk is None:
            return None

        self._recover_opcode_map(chunk)
        proto = self._deserialize_chunk(chunk)
        if proto is None:
            return None

        stmts = self._decompile(proto)
        return ast.Block(stmts=stmts)

    def _is_ironbrew2(self, tree: ast.Block) -> bool:
        indicators = 0
        source = emit(tree)

        if 'select' in source and 'unpack' in source:
            indicators += 1

        iife_count = 0
        for node in _walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.FunctionExpr):
                iife_count += 1
            if isinstance(node, ast.While):
                for stmt in node.body.stmts:
                    if isinstance(stmt, ast.If) and len(stmt.tests) >= 10:
                        indicators += 2
            if isinstance(node, ast.LocalAssign):
                for val in node.values:
                    if isinstance(val, ast.TableConstructor):
                        fn_count = sum(1 for f in val.fields
                                       if isinstance(f.value, ast.FunctionExpr))
                        if fn_count >= 15:
                            indicators += 2

        if iife_count >= 2:
            indicators += 1

        for node in _walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Field):
                if node.func.name in ('byte', 'sub', 'char'):
                    indicators += 1
                    break

        return indicators >= 3

    def _extract_chunk(self, tree: ast.Block) -> Optional[IB2Chunk]:
        chunk = IB2Chunk()

        for node in _walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.FunctionExpr):
                body = node.func.body
                if len(body.stmts) > 10:
                    chunk.wrapper_call = node
                    self._extract_components(body, chunk)
                    break

        if chunk.vm_func is None:
            for stmt in tree.stmts:
                if isinstance(stmt, ast.ExprStmt) and isinstance(stmt.expr, ast.Call):
                    call = stmt.expr
                    if isinstance(call.func, ast.Call):
                        inner = call.func
                        if isinstance(inner.func, ast.FunctionExpr):
                            self._extract_components(inner.func.body, chunk)
                            break

        if chunk.bytecode_string is None:
            chunk.bytecode_string = self._find_bytecode_string(tree)

        return chunk if chunk.bytecode_string or chunk.vm_func else None

    def _extract_components(self, body: ast.Block, chunk: IB2Chunk):
        for stmt in body.stmts:
            if isinstance(stmt, ast.LocalAssign):
                for i, val in enumerate(stmt.values):
                    if isinstance(val, ast.String) and len(val.value) > 100:
                        chunk.bytecode_string = val.value
                    if isinstance(val, ast.FunctionExpr):
                        if self._is_deserializer(val):
                            chunk.deserializer_func = val
                        elif self._is_vm_function(val):
                            chunk.vm_func = val
            if isinstance(stmt, ast.FunctionDecl):
                if isinstance(stmt.name, ast.Name):
                    if self._is_vm_function_decl(stmt):
                        chunk.vm_func = ast.FunctionExpr(
                            params=stmt.params, body=stmt.body,
                            is_vararg=stmt.is_vararg)

    def _is_deserializer(self, func: ast.FunctionExpr) -> bool:
        score = 0
        for node in _walk(func.body):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Field):
                if node.func.name in ('byte', 'sub'):
                    score += 1
            if isinstance(node, ast.ForNumeric):
                score += 1
            if isinstance(node, ast.BinOp) and node.op == '*':
                if isinstance(node.right, ast.Number) and node.right.value == 256:
                    score += 2
        return score >= 3

    def _is_vm_function(self, func: ast.FunctionExpr) -> bool:
        score = 0
        for node in _walk(func.body):
            if isinstance(node, ast.While):
                score += 1
                for stmt in node.body.stmts:
                    if isinstance(stmt, ast.If) and len(stmt.tests) >= 5:
                        score += 3
            if isinstance(node, ast.TableConstructor):
                fn_count = sum(1 for f in node.fields if isinstance(f.value, ast.FunctionExpr))
                if fn_count >= 10:
                    score += 3
        return score >= 3

    def _is_vm_function_decl(self, decl: ast.FunctionDecl) -> bool:
        return self._is_vm_function(
            ast.FunctionExpr(params=decl.params, body=decl.body, is_vararg=decl.is_vararg))

    def _find_bytecode_string(self, tree: ast.Block) -> Optional[str]:
        for node in _walk(tree):
            if isinstance(node, ast.String) and len(node.value) > 200:
                return node.value
        return None

    def _recover_opcode_map(self, chunk: IB2Chunk):
        if chunk.vm_func is None:
            return

        body = chunk.vm_func.body
        handler_table = None

        for node in _walk(body):
            if isinstance(node, ast.LocalAssign):
                for val in node.values:
                    if isinstance(val, ast.TableConstructor):
                        fn_count = sum(1 for f in val.fields
                                       if isinstance(f.value, ast.FunctionExpr))
                        if fn_count >= 10:
                            handler_table = val
                            break
                if handler_table:
                    break

        if handler_table is None:
            for node in _walk(body):
                if isinstance(node, ast.If) and len(node.tests) >= 5:
                    self._extract_if_chain_handlers(node)
                    return

        if handler_table:
            self._extract_table_handlers(handler_table)

    def _extract_table_handlers(self, table: ast.TableConstructor):
        for i, f in enumerate(table.fields):
            if isinstance(f.value, ast.FunctionExpr):
                opcode = int(f.key.value) if f.key and isinstance(f.key, ast.Number) else i
                std_op = self._classify_ib2_handler(f.value.body)
                if std_op:
                    self.opcode_map[opcode] = std_op
                    self.handler_signatures[opcode] = std_op

    def _extract_if_chain_handlers(self, if_node: ast.If):
        for i, test in enumerate(if_node.tests):
            if isinstance(test, ast.BinOp) and test.op == '==':
                if isinstance(test.right, ast.Number) and i < len(if_node.bodies):
                    opcode = int(test.right.value)
                    std_op = self._classify_ib2_handler(if_node.bodies[i])
                    if std_op:
                        self.opcode_map[opcode] = std_op

    def _classify_ib2_handler(self, body: ast.Block) -> Optional[str]:
        se = SymbolicExecutor(max_steps=3000)
        result = se.classify_handler(body)
        if result:
            return result

        has_pc_inc = False
        has_reg_write = False
        has_call = False
        has_return = False
        has_table_new = False
        has_comparison = False
        has_concat = False

        for node in _walk(body):
            if isinstance(node, ast.Assign):
                for tgt in node.targets:
                    if isinstance(tgt, ast.Name) and 'pc' in tgt.name.lower():
                        has_pc_inc = True
                    if isinstance(tgt, ast.Index):
                        has_reg_write = True
            if isinstance(node, ast.Call):
                has_call = True
            if isinstance(node, ast.Return):
                has_return = True
            if isinstance(node, ast.TableConstructor):
                has_table_new = True
            if isinstance(node, ast.BinOp) and node.op in ('==', '<', '<=', '>', '>=', '~='):
                has_comparison = True
            if isinstance(node, ast.Concat):
                has_concat = True

        if has_pc_inc and not has_reg_write and not has_call:
            return 'JMP'
        if has_comparison and has_pc_inc:
            return 'TEST'
        if has_table_new and has_reg_write:
            return 'NEWTABLE'
        if has_concat:
            return 'CONCAT'
        if has_return:
            return 'RETURN'
        if has_call and has_reg_write:
            return 'CALL'
        if has_call and not has_reg_write:
            return 'CALL_VOID'

        return None

    def _deserialize_chunk(self, chunk: IB2Chunk) -> Optional[VMPrototype]:
        if chunk.bytecode_string is None:
            return None

        try:
            return self._try_sandbox_deserialize(chunk)
        except Exception:
            pass

        try:
            return self._manual_deserialize(chunk.bytecode_string)
        except Exception:
            pass

        return VMPrototype()

    def _try_sandbox_deserialize(self, chunk: IB2Chunk) -> Optional[VMPrototype]:
        if chunk.deserializer_func is None:
            return None

        deser_src = emit(chunk.deserializer_func)
        bc = chunk.bytecode_string.replace('\\', '\\\\').replace("'", "\\'")
        src = f"local deserialize = {deser_src}\nreturn deserialize('{bc}')"

        try:
            results = self.sandbox.execute(src)
            if results:
                return self._convert_sandbox_result(results[0])
        except LuaError:
            pass
        return None

    def _convert_sandbox_result(self, result: Any) -> VMPrototype:
        proto = VMPrototype()
        if hasattr(result, 'get'):
            proto.num_params = result.get('num_params', 0)
            proto.is_vararg = result.get('is_vararg', False)
            proto.max_stack = result.get('max_stack', 0)

            consts = result.get('constants', [])
            if isinstance(consts, list):
                from .vm_lift import VMConstant
                for i, c in enumerate(consts):
                    proto.constants.append(VMConstant(index=i, value=c))

            insts = result.get('instructions', [])
            if isinstance(insts, list):
                for pc, inst in enumerate(insts):
                    if isinstance(inst, (list, tuple)) and len(inst) >= 1:
                        proto.instructions.append(VMInstruction(
                            opcode=inst[0],
                            operands=list(inst[1:]),
                            pc=pc,
                        ))
        return proto

    def _manual_deserialize(self, data: str) -> VMPrototype:
        proto = VMPrototype()
        pos = [0]

        def read_byte():
            if pos[0] >= len(data):
                return 0
            b = ord(data[pos[0]])
            pos[0] += 1
            return b

        def read_int():
            b1 = read_byte()
            b2 = read_byte()
            b3 = read_byte()
            b4 = read_byte()
            return b1 | (b2 << 8) | (b3 << 16) | (b4 << 24)

        def read_double():
            import struct
            bs = bytes(read_byte() for _ in range(8))
            try:
                return struct.unpack('<d', bs)[0]
            except struct.error:
                return 0.0

        def read_string():
            length = read_int()
            if length == 0:
                return ""
            s = data[pos[0]:pos[0] + length]
            pos[0] += length
            return s

        try:
            n_const = read_int()
            from .vm_lift import VMConstant
            for i in range(min(n_const, 10000)):
                t = read_byte()
                if t == 0:
                    proto.constants.append(VMConstant(i, None, 'nil'))
                elif t == 1:
                    proto.constants.append(VMConstant(i, bool(read_byte()), 'boolean'))
                elif t == 2:
                    proto.constants.append(VMConstant(i, read_double(), 'number'))
                elif t == 3:
                    proto.constants.append(VMConstant(i, read_string(), 'string'))
                else:
                    break

            n_inst = read_int()
            for pc in range(min(n_inst, 100000)):
                op = read_byte()
                a = read_int()
                b = read_int()
                c = read_int()
                proto.instructions.append(VMInstruction(
                    opcode=op, operands=[a, b, c], pc=pc))

            proto.num_params = read_byte()
        except (IndexError, ValueError):
            pass

        return proto

    def _decompile(self, proto: VMPrototype) -> List[ast.Stmt]:
        stmts = []

        for inst in proto.instructions:
            std_op = self.opcode_map.get(inst.opcode)
            if std_op is None:
                continue

            decoded = self._decode_ib2_inst(std_op, inst, proto)
            if decoded:
                stmts.extend(decoded)

        return stmts

    def _decode_ib2_inst(self, std_op: str, inst: VMInstruction, proto: VMPrototype) -> List[ast.Stmt]:
        ops = inst.operands

        if std_op == 'MOVE' and len(ops) >= 2:
            return [ast.LocalAssign(names=[f"v{ops[0]}"], values=[ast.Name(name=f"v{ops[1]}")])]
        if std_op == 'LOADK' and len(ops) >= 2:
            val = self._get_const(proto, ops[1])
            return [ast.LocalAssign(names=[f"v{ops[0]}"], values=[val])]
        if std_op == 'LOADNIL' and len(ops) >= 1:
            return [ast.LocalAssign(names=[f"v{ops[0]}"], values=[ast.Nil()])]
        if std_op == 'LOADBOOL' and len(ops) >= 2:
            return [ast.LocalAssign(names=[f"v{ops[0]}"], values=[ast.Bool(value=bool(ops[1]))])]
        if std_op in ('ADD', 'SUB', 'MUL', 'DIV', 'MOD', 'POW') and len(ops) >= 3:
            sym = {
                'ADD': '+', 'SUB': '-', 'MUL': '*', 'DIV': '/',
                'MOD': '%', 'POW': '^',
            }[std_op]
            return [ast.LocalAssign(
                names=[f"v{ops[0]}"],
                values=[ast.BinOp(op=sym,
                    left=self._rk(proto, ops[1]),
                    right=self._rk(proto, ops[2]))]
            )]
        if std_op in ('UNM', 'NOT', 'LEN') and len(ops) >= 2:
            sym = {'UNM': '-', 'NOT': 'not', 'LEN': '#'}[std_op]
            return [ast.LocalAssign(
                names=[f"v{ops[0]}"],
                values=[ast.UnOp(op=sym, operand=ast.Name(name=f"v{ops[1]}"))]
            )]
        if std_op == 'CONCAT' and len(ops) >= 3:
            vals = [ast.Name(name=f"v{r}") for r in range(ops[1], ops[2] + 1)]
            return [ast.LocalAssign(
                names=[f"v{ops[0]}"],
                values=[ast.Concat(values=vals)]
            )]
        if std_op == 'NEWTABLE' and len(ops) >= 1:
            return [ast.LocalAssign(names=[f"v{ops[0]}"], values=[ast.TableConstructor(fields=[])])]
        if std_op == 'GETTABLE' and len(ops) >= 3:
            return [ast.LocalAssign(
                names=[f"v{ops[0]}"],
                values=[ast.Index(table=ast.Name(name=f"v{ops[1]}"), key=self._rk(proto, ops[2]))]
            )]
        if std_op == 'SETTABLE' and len(ops) >= 3:
            return [ast.Assign(
                targets=[ast.Index(table=ast.Name(name=f"v{ops[0]}"), key=self._rk(proto, ops[1]))],
                values=[self._rk(proto, ops[2])]
            )]
        if std_op == 'CALL' and len(ops) >= 3:
            func = ast.Name(name=f"v{ops[0]}")
            nargs = ops[1] - 1 if ops[1] != 0 else 0
            args = [ast.Name(name=f"v{ops[0] + 1 + i}") for i in range(max(0, nargs))]
            call = ast.Call(func=func, args=args)
            nresults = ops[2] - 1 if ops[2] != 0 else 0
            if nresults == 0:
                return [ast.ExprStmt(expr=call)]
            return [ast.LocalAssign(names=[f"v{ops[0]}"], values=[call])]
        if std_op == 'CALL_VOID' and len(ops) >= 2:
            func = ast.Name(name=f"v{ops[0]}")
            nargs = ops[1] - 1 if ops[1] != 0 else 0
            args = [ast.Name(name=f"v{ops[0] + 1 + i}") for i in range(max(0, nargs))]
            return [ast.ExprStmt(expr=ast.Call(func=func, args=args))]
        if std_op == 'RETURN' and len(ops) >= 1:
            nvals = ops[0] - 1 if ops[0] != 0 else 0
            vals = [ast.Name(name=f"v{ops[1] + i}") for i in range(max(0, nvals))] if len(ops) > 1 else []
            return [ast.Return(values=vals)]
        if std_op == 'JMP':
            return []
        if std_op == 'CLOSURE' and len(ops) >= 2:
            return [ast.LocalAssign(
                names=[f"v{ops[0]}"],
                values=[ast.FunctionExpr(params=[], body=ast.Block(stmts=[]))]
            )]
        if std_op == 'GETGLOBAL' and len(ops) >= 2:
            name = self._get_const_value(proto, ops[1])
            if isinstance(name, str):
                return [ast.LocalAssign(names=[f"v{ops[0]}"], values=[ast.Name(name=name)])]
        if std_op == 'SETGLOBAL' and len(ops) >= 2:
            name = self._get_const_value(proto, ops[1])
            if isinstance(name, str):
                return [ast.Assign(
                    targets=[ast.Name(name=name)],
                    values=[ast.Name(name=f"v{ops[0]}")]
                )]
        if std_op == 'SELF' and len(ops) >= 3:
            obj = ast.Name(name=f"v{ops[1]}")
            key = self._rk(proto, ops[2])
            return [
                ast.LocalAssign(names=[f"v{ops[0] + 1}"], values=[obj]),
                ast.LocalAssign(
                    names=[f"v{ops[0]}"],
                    values=[ast.Index(table=obj, key=key)]
                ),
            ]

        return []

    def _get_const(self, proto: VMPrototype, idx: int) -> ast.Expr:
        val = self._get_const_value(proto, idx)
        if val is None: return ast.Nil()
        if isinstance(val, bool): return ast.Bool(value=val)
        if isinstance(val, (int, float)): return ast.Number(value=val)
        if isinstance(val, str): return ast.String(value=val, raw='')
        return ast.Nil()

    def _get_const_value(self, proto: VMPrototype, idx: int) -> Any:
        if 0 <= idx < len(proto.constants):
            return proto.constants[idx].value
        return None

    def _rk(self, proto: VMPrototype, val: int) -> ast.Expr:
        if val >= 256:
            return self._get_const(proto, val - 256)
        return ast.Name(name=f"v{val}")


def _walk(node: ast.Node):
    yield node
    for child in node.children():
        yield from _walk(child)


def deobfuscate_ironbrew2(source: str, sandbox: Optional[LuaSandbox] = None) -> Optional[ast.Block]:
    d = IronBrew2Deobfuscator(sandbox)
    return d.deobfuscate(source)
