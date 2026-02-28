from __future__ import annotations
from typing import List, Optional, Dict, Set, Tuple, Any
from dataclasses import dataclass, field
from ..core import lua_ast as ast
from ..core.lua_parser import parse as lua_parse
from ..core.lua_emitter import emit
from ..core.sandbox import LuaSandbox, LuaError
from ..core.symbolic import SymbolicExecutor, SymVal, SymKind, SymEnvironment
from ..utils.dispatch_tree import DispatchTreeParser, find_dispatch_loop


@dataclass
class VMInstruction:
    opcode: int
    operands: List[Any] = field(default_factory=list)
    original_name: Optional[str] = None
    pc: int = 0

    def __repr__(self):
        name = self.original_name or f"OP_{self.opcode}"
        return f"{self.pc}: {name} {self.operands}"


@dataclass
class VMConstant:
    index: int
    value: Any
    type: str = "unknown"


@dataclass
class VMPrototype:
    instructions: List[VMInstruction] = field(default_factory=list)
    constants: List[VMConstant] = field(default_factory=list)
    sub_protos: List[VMPrototype] = field(default_factory=list)
    num_params: int = 0
    is_vararg: bool = False
    max_stack: int = 0
    upvalue_count: int = 0
    source_name: str = ""


@dataclass
class OpcodeMapping:
    vm_opcode: int
    standard_opcode: str
    confidence: float = 0.0
    handler_body: Optional[ast.Block] = None


class VMLifter:
    def __init__(self, sandbox: Optional[LuaSandbox] = None):
        self.sandbox = sandbox or LuaSandbox(op_limit=10_000_000, timeout=30.0)
        self.opcode_mappings: Dict[int, OpcodeMapping] = {}
        self.vm_protos: List[VMPrototype] = []

    def lift(self, source: str) -> Optional[ast.Block]:
        tree = lua_parse(source)
        vm_info = self._detect_vm_structure(tree)
        if vm_info is None:
            return None

        dispatch_table, proto_data = vm_info
        self._analyze_handlers(dispatch_table)
        self._extract_prototypes(proto_data)

        if not self.vm_protos:
            return None

        result_stmts = []
        for proto in self.vm_protos:
            stmts = self._decompile_proto(proto)
            result_stmts.extend(stmts)

        return ast.Block(stmts=result_stmts)

    def _detect_vm_structure(self, tree: ast.Block) -> Optional[Tuple[Dict, Any]]:
        for pattern_fn in [
            self._detect_table_dispatch,
            self._detect_if_chain_dispatch,
            self._detect_closure_dispatch,
        ]:
            result = pattern_fn(tree)
            if result is not None:
                return result
        return None

    def _detect_table_dispatch(self, tree: ast.Block) -> Optional[Tuple[Dict, Any]]:
        dispatch = {}
        proto_data = None

        for node in _walk(tree):
            if isinstance(node, ast.While):
                body = node.body
                for stmt in body.stmts:
                    if isinstance(stmt, ast.LocalAssign):
                        for val in stmt.values:
                            if isinstance(val, ast.Index):
                                pass
                    if isinstance(stmt, ast.ExprStmt) and isinstance(stmt.expr, ast.Call):
                        call = stmt.expr
                        if isinstance(call.func, ast.Index):
                            dispatch['type'] = 'table_dispatch'

            if isinstance(node, ast.LocalAssign):
                for val in node.values:
                    if isinstance(val, ast.Call) and isinstance(val.func, ast.FunctionExpr):
                        iife_body = val.func.body
                        tables = self._find_handler_tables(iife_body)
                        if tables:
                            dispatch.update(tables)
                            proto_data = self._find_proto_data(iife_body)

        if dispatch:
            return dispatch, proto_data
        return None

    def _detect_if_chain_dispatch(self, tree: ast.Block) -> Optional[Tuple[Dict, Any]]:
        dispatch_body = find_dispatch_loop(tree)
        if dispatch_body is None:
            return None
        parser = DispatchTreeParser()
        handler_map = parser.parse(dispatch_body)
        if len(handler_map) >= 3:
            dispatch = {
                'handlers': handler_map,
                'type': 'dispatch_tree',
            }
            return dispatch, None
        return None

    def _detect_closure_dispatch(self, tree: ast.Block) -> Optional[Tuple[Dict, Any]]:
        for node in _walk(tree):
            if isinstance(node, ast.LocalAssign):
                for val in node.values:
                    if isinstance(val, ast.TableConstructor):
                        fn_count = sum(1 for f in val.fields
                                       if isinstance(f.value, ast.FunctionExpr))
                        if fn_count >= 10:
                            dispatch = {'type': 'closure_table', 'table': val}
                            return dispatch, None
        return None

    def _find_handler_tables(self, body: ast.Block) -> Dict:
        result = {}
        for stmt in body.stmts:
            if isinstance(stmt, ast.LocalAssign):
                for i, val in enumerate(stmt.values):
                    if isinstance(val, ast.TableConstructor):
                        fn_fields = [f for f in val.fields if isinstance(f.value, ast.FunctionExpr)]
                        if len(fn_fields) >= 5:
                            handlers = {}
                            for j, f in enumerate(fn_fields):
                                if f.key and isinstance(f.key, ast.Number):
                                    handlers[int(f.key.value)] = f.value.body
                                else:
                                    handlers[j] = f.value.body if isinstance(f.value, ast.FunctionExpr) else None
                            result['handlers'] = handlers
        return result

    def _find_proto_data(self, body: ast.Block) -> Any:
        for stmt in body.stmts:
            if isinstance(stmt, ast.LocalAssign):
                for val in stmt.values:
                    if isinstance(val, ast.Call):
                        return val
        return None

    def _analyze_handlers(self, dispatch: Dict):
        handlers = dispatch.get('handlers', {})
        for opcode, handler_body in handlers.items():
            if handler_body is None:
                continue
            mapping = self._classify_handler(opcode, handler_body)
            if mapping:
                self.opcode_mappings[opcode] = mapping

    def _classify_handler(self, opcode: int, body: ast.Block) -> Optional[OpcodeMapping]:
        se = SymbolicExecutor(max_steps=5000)
        env = SymEnvironment()
        env.set('R', SymVal.sym('R'))
        env.set('I', SymVal.sym('I'))
        env.set('K', SymVal.sym('K'))
        env.set('PC', SymVal.sym('PC'))

        try:
            se.analyze_block(body, env)
        except Exception:
            pass

        std_op = self._match_writes_to_opcode(se.writes, se.calls)
        if std_op:
            return OpcodeMapping(
                vm_opcode=opcode,
                standard_opcode=std_op,
                confidence=0.8,
                handler_body=body,
            )
        return None

    def _match_writes_to_opcode(self, writes, calls) -> Optional[str]:
        has_reg_write = False
        has_reg_read = False
        has_const_read = False
        has_pc_modify = False
        has_call = len(calls) > 0
        write_val_kinds = set()

        for w in writes:
            tgt, val = w.target, w.value
            if tgt.kind == SymKind.INDEX:
                t, k = tgt.data
                if t.kind == SymKind.SYM and t.data == 'R':
                    has_reg_write = True
                    write_val_kinds.add(val.kind)
                    if val.kind == SymKind.INDEX:
                        vt = val.data[0]
                        if vt.kind == SymKind.SYM:
                            if vt.data == 'R': has_reg_read = True
                            if vt.data == 'K': has_const_read = True
            if tgt.kind == SymKind.SYM and tgt.data == 'PC':
                has_pc_modify = True

        if has_reg_write and has_reg_read and not has_const_read and not has_pc_modify and not has_call:
            if SymKind.INDEX in write_val_kinds:
                return 'MOVE'
        if has_reg_write and has_const_read and not has_pc_modify:
            return 'LOADK'
        if has_reg_write and SymKind.CONST in write_val_kinds:
            for w in writes:
                if w.value.is_const:
                    v = w.value.const_value
                    if v is None: return 'LOADNIL'
                    if isinstance(v, bool): return 'LOADBOOL'
        if has_reg_write and SymKind.BINOP in write_val_kinds:
            for w in writes:
                if w.value.kind == SymKind.BINOP:
                    op = w.value.data[0]
                    op_map = {'+': 'ADD', '-': 'SUB', '*': 'MUL', '/': 'DIV',
                              '%': 'MOD', '^': 'POW', '..': 'CONCAT',
                              '&': 'BAND', '|': 'BOR', '~': 'BXOR'}
                    if op in op_map: return op_map[op]
        if has_reg_write and SymKind.UNOP in write_val_kinds:
            for w in writes:
                if w.value.kind == SymKind.UNOP:
                    op = w.value.data[0]
                    if op == '-': return 'UNM'
                    if op == 'not': return 'NOT'
                    if op == '#': return 'LEN'
        if has_reg_write and SymKind.TABLE in write_val_kinds:
            return 'NEWTABLE'
        if has_reg_write and SymKind.FUNC in write_val_kinds:
            return 'CLOSURE'
        if has_pc_modify and not has_reg_write:
            return 'JMP'
        if has_call and not has_reg_write:
            return 'CALL_VOID'
        if has_call and has_reg_write:
            return 'CALL'

        return None

    def _extract_prototypes(self, proto_data: Any):
        if proto_data is None:
            self.vm_protos = [VMPrototype()]
            return

        try:
            src = emit(proto_data) if isinstance(proto_data, ast.Node) else str(proto_data)
            self.sandbox.execute(src)
        except (LuaError, Exception):
            self.vm_protos = [VMPrototype()]

    def _decompile_proto(self, proto: VMPrototype) -> List[ast.Stmt]:
        stmts = []
        for inst in proto.instructions:
            mapping = self.opcode_mappings.get(inst.opcode)
            if mapping is None:
                continue
            decoded = self._decode_instruction(mapping, inst)
            if decoded:
                stmts.extend(decoded)
        return stmts

    def _decode_instruction(self, mapping: OpcodeMapping, inst: VMInstruction) -> List[ast.Stmt]:
        op = mapping.standard_opcode
        ops = inst.operands

        if op == 'MOVE' and len(ops) >= 2:
            return [ast.LocalAssign(
                names=[f"v{ops[0]}"],
                values=[ast.Name(name=f"v{ops[1]}")]
            )]
        if op == 'LOADK' and len(ops) >= 2:
            return [ast.LocalAssign(
                names=[f"v{ops[0]}"],
                values=[self._const_to_ast(ops[1])]
            )]
        if op == 'LOADNIL' and len(ops) >= 1:
            return [ast.LocalAssign(
                names=[f"v{ops[0]}"],
                values=[ast.Nil()]
            )]
        if op == 'LOADBOOL' and len(ops) >= 2:
            return [ast.LocalAssign(
                names=[f"v{ops[0]}"],
                values=[ast.Bool(value=bool(ops[1]))]
            )]
        if op in ('ADD', 'SUB', 'MUL', 'DIV', 'MOD', 'POW') and len(ops) >= 3:
            op_sym = {
                'ADD': '+', 'SUB': '-', 'MUL': '*', 'DIV': '/',
                'MOD': '%', 'POW': '^',
            }[op]
            return [ast.LocalAssign(
                names=[f"v{ops[0]}"],
                values=[ast.BinOp(op=op_sym,
                    left=ast.Name(name=f"v{ops[1]}"),
                    right=ast.Name(name=f"v{ops[2]}"))]
            )]
        if op in ('UNM', 'NOT', 'LEN') and len(ops) >= 2:
            op_sym = {'UNM': '-', 'NOT': 'not', 'LEN': '#'}[op]
            return [ast.LocalAssign(
                names=[f"v{ops[0]}"],
                values=[ast.UnOp(op=op_sym, operand=ast.Name(name=f"v{ops[1]}"))]
            )]
        if op == 'NEWTABLE' and len(ops) >= 1:
            return [ast.LocalAssign(
                names=[f"v{ops[0]}"],
                values=[ast.TableConstructor(fields=[])]
            )]
        if op == 'JMP':
            return []
        if op == 'CALL' and len(ops) >= 3:
            func = ast.Name(name=f"v{ops[0]}")
            nargs = ops[1]
            args = [ast.Name(name=f"v{ops[0] + 1 + i}") for i in range(max(0, nargs))]
            call = ast.Call(func=func, args=args)
            nresults = ops[2]
            if nresults == 0:
                return [ast.ExprStmt(expr=call)]
            return [ast.LocalAssign(names=[f"v{ops[0]}"], values=[call])]
        if op == 'RETURN' and len(ops) >= 1:
            nvals = ops[0] if ops else 0
            vals = [ast.Name(name=f"v{ops[1] + i}") for i in range(nvals)] if len(ops) > 1 else []
            return [ast.Return(values=vals)]

        return []

    def _const_to_ast(self, val: Any) -> ast.Expr:
        if val is None: return ast.Nil()
        if isinstance(val, bool): return ast.Bool(value=val)
        if isinstance(val, (int, float)): return ast.Number(value=val)
        if isinstance(val, str): return ast.String(value=val, raw='')
        return ast.Nil()


class VMPatternMatcher:
    def __init__(self):
        self.patterns: List[Tuple[str, Any]] = []

    def is_vm_obfuscated(self, tree: ast.Block) -> bool:
        score = 0
        for node in _walk(tree):
            if isinstance(node, ast.While):
                body = node.body
                if self._has_dispatch_pattern(body):
                    score += 3
            if isinstance(node, ast.TableConstructor):
                fn_count = sum(1 for f in node.fields if isinstance(f.value, ast.FunctionExpr))
                if fn_count >= 10:
                    score += 2
            if isinstance(node, ast.LocalAssign):
                for val in node.values:
                    if isinstance(val, ast.Call) and isinstance(val.func, ast.FunctionExpr):
                        if len(val.func.body.stmts) > 20:
                            score += 1
        return score >= 3

    def _has_dispatch_pattern(self, body: ast.Block) -> bool:
        for stmt in body.stmts:
            if isinstance(stmt, ast.If) and len(stmt.tests) >= 5:
                return True
            if isinstance(stmt, ast.ExprStmt) and isinstance(stmt.expr, ast.Call):
                if isinstance(stmt.expr.func, ast.Index):
                    return True
        return False

    def detect_vm_type(self, tree: ast.Block) -> Optional[str]:
        source = emit(tree)
        indicators = {
            'ironbrew': ['Synapse', 'IBRW', 'IB2'],
            'psu': ['PSU', 'psu_'],
            'moonsec': ['MoonSec', 'moonsec'],
            'luraph': ['Luraph', 'luraph'],
        }
        for vm_type, keywords in indicators.items():
            for kw in keywords:
                if kw in source:
                    return vm_type
        if self.is_vm_obfuscated(tree):
            return 'generic_vm'
        return None


def _walk(node: ast.Node):
    yield node
    for child in node.children():
        yield from _walk(child)


def lift_vm(source: str, sandbox: Optional[LuaSandbox] = None) -> Optional[ast.Block]:
    lifter = VMLifter(sandbox)
    return lifter.lift(source)
