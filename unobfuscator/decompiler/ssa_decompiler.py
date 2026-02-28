from __future__ import annotations
from typing import List, Optional, Dict, Set, Tuple, Any
from dataclasses import dataclass, field
from ..core import lua_ast as ast
from .bytecode import Prototype, Instruction, OpCode, Constant, PrototypeCFG


@dataclass
class SSAReg:
    base: int
    version: int = 0

    @property
    def name(self) -> str:
        return f"r{self.base}_{self.version}"

    def __hash__(self):
        return hash((self.base, self.version))

    def __eq__(self, other):
        return isinstance(other, SSAReg) and self.base == other.base and self.version == other.version


@dataclass
class PhiNode:
    dest: SSAReg
    sources: List[Tuple[int, SSAReg]] = field(default_factory=list)


class SSABuilder:
    def __init__(self, proto: Prototype, cfg: PrototypeCFG):
        self.proto = proto
        self.cfg = cfg
        self.versions: Dict[int, int] = {}
        self.phi_nodes: Dict[int, List[PhiNode]] = {}
        self.reg_defs: Dict[int, Dict[int, SSAReg]] = {}

    def build(self):
        for leader in self.cfg.leaders:
            self.reg_defs[leader] = {}
            self.phi_nodes[leader] = []

        for leader in self.cfg.leaders:
            for pc in self.cfg.blocks.get(leader, []):
                inst = self.proto.instructions[pc]
                defs = self._get_defs(inst)
                for reg in defs:
                    ver = self._next_version(reg)
                    self.reg_defs[leader][reg] = SSAReg(reg, ver)

    def _next_version(self, reg: int) -> int:
        v = self.versions.get(reg, 0)
        self.versions[reg] = v + 1
        return v

    def _get_defs(self, inst: Instruction) -> List[int]:
        op = inst.opcode
        if op in (OpCode.MOVE, OpCode.LOADK, OpCode.LOADBOOL, OpCode.GETUPVAL,
                  OpCode.GETGLOBAL, OpCode.GETTABLE, OpCode.NEWTABLE,
                  OpCode.ADD, OpCode.SUB, OpCode.MUL, OpCode.DIV,
                  OpCode.MOD, OpCode.POW, OpCode.UNM, OpCode.NOT,
                  OpCode.LEN, OpCode.CONCAT, OpCode.CLOSURE):
            return [inst.A]
        if op == OpCode.SELF:
            return [inst.A, inst.A + 1]
        if op == OpCode.LOADNIL:
            return list(range(inst.A, inst.B + 1))
        if op == OpCode.CALL:
            if inst.C == 0:
                return [inst.A]
            return list(range(inst.A, inst.A + inst.C - 1))
        if op == OpCode.VARARG:
            if inst.B == 0:
                return [inst.A]
            return list(range(inst.A, inst.A + inst.B - 1))
        if op == OpCode.FORPREP:
            return [inst.A]
        if op == OpCode.FORLOOP:
            return [inst.A, inst.A + 3]
        if op == OpCode.TFORLOOP:
            return list(range(inst.A + 3, inst.A + 3 + inst.C))
        if op == OpCode.TESTSET:
            return [inst.A]
        return []


class Decompiler:
    def __init__(self, proto: Prototype):
        self.proto = proto
        self.cfg = PrototypeCFG(proto)
        self.cfg.build()
        self._local_names: Dict[int, str] = {}
        self._init_local_names()

    def _init_local_names(self):
        for lv in self.proto.local_vars:
            self._local_names[lv.start_pc] = lv.name

    def decompile(self) -> ast.Block:
        stmts = self._decompile_range(0, len(self.proto.instructions))
        return ast.Block(stmts=stmts)

    def _decompile_range(self, start: int, end: int) -> List[ast.Stmt]:
        stmts = []
        pc = start
        while pc < end:
            inst = self.proto.instructions[pc]
            result = self._decompile_inst(pc, inst)
            if result:
                stmts.extend(result)
            pc += 1
            if inst.opcode in (OpCode.EQ, OpCode.LT, OpCode.LE, OpCode.TEST, OpCode.TESTSET):
                pc += 1
        return stmts

    def _decompile_inst(self, pc: int, inst: Instruction) -> List[ast.Stmt]:
        op = inst.opcode

        if op == OpCode.MOVE:
            return [self._assign_reg(inst.A, self._reg(inst.B))]

        if op == OpCode.LOADK:
            return [self._assign_reg(inst.A, self._const_expr(inst.Bx))]

        if op == OpCode.LOADBOOL:
            stmts = [self._assign_reg(inst.A, ast.Bool(value=bool(inst.B)))]
            return stmts

        if op == OpCode.LOADNIL:
            stmts = []
            for r in range(inst.A, inst.B + 1):
                stmts.append(self._assign_reg(r, ast.Nil()))
            return stmts

        if op == OpCode.GETUPVAL:
            return [self._assign_reg(inst.A, self._upval(inst.B))]

        if op == OpCode.GETGLOBAL:
            name = self.proto.get_constant(inst.Bx)
            if isinstance(name, str):
                return [self._assign_reg(inst.A, ast.Name(name=name))]
            return [self._assign_reg(inst.A, ast.Name(name=f"_G[{name!r}]"))]

        if op == OpCode.GETTABLE:
            return [self._assign_reg(inst.A,
                ast.Index(table=self._reg(inst.B), key=self._rk(inst.C)))]

        if op == OpCode.SETGLOBAL:
            name = self.proto.get_constant(inst.Bx)
            return [ast.Assign(
                targets=[ast.Name(name=name if isinstance(name, str) else f"_G[{name!r}]")],
                values=[self._reg(inst.A)],
            )]

        if op == OpCode.SETUPVAL:
            return [ast.Assign(
                targets=[self._upval(inst.B)],
                values=[self._reg(inst.A)],
            )]

        if op == OpCode.SETTABLE:
            return [ast.Assign(
                targets=[ast.Index(table=self._reg(inst.A), key=self._rk(inst.B))],
                values=[self._rk(inst.C)],
            )]

        if op == OpCode.NEWTABLE:
            return [self._assign_reg(inst.A, ast.TableConstructor(fields=[]))]

        if op == OpCode.SELF:
            obj = self._reg(inst.B)
            key = self._rk(inst.C)
            return [
                self._assign_reg(inst.A + 1, obj),
                self._assign_reg(inst.A, ast.Index(table=obj, key=key)),
            ]

        if op in (OpCode.ADD, OpCode.SUB, OpCode.MUL, OpCode.DIV,
                  OpCode.MOD, OpCode.POW):
            op_map = {
                OpCode.ADD: '+', OpCode.SUB: '-', OpCode.MUL: '*',
                OpCode.DIV: '/', OpCode.MOD: '%', OpCode.POW: '^',
            }
            return [self._assign_reg(inst.A,
                ast.BinOp(op=op_map[op], left=self._rk(inst.B), right=self._rk(inst.C)))]

        if op == OpCode.UNM:
            return [self._assign_reg(inst.A, ast.UnOp(op='-', operand=self._reg(inst.B)))]

        if op == OpCode.NOT:
            return [self._assign_reg(inst.A, ast.UnOp(op='not', operand=self._reg(inst.B)))]

        if op == OpCode.LEN:
            return [self._assign_reg(inst.A, ast.UnOp(op='#', operand=self._reg(inst.B)))]

        if op == OpCode.CONCAT:
            vals = [self._reg(r) for r in range(inst.B, inst.C + 1)]
            return [self._assign_reg(inst.A, ast.Concat(values=vals))]

        if op == OpCode.JMP:
            return []

        if op in (OpCode.EQ, OpCode.LT, OpCode.LE):
            cmp_ops = {OpCode.EQ: '==', OpCode.LT: '<', OpCode.LE: '<='}
            cmp = ast.BinOp(op=cmp_ops[op], left=self._rk(inst.B), right=self._rk(inst.C))
            if inst.A != 0:
                cmp = ast.UnOp(op='not', operand=cmp)
            return [ast.ExprStmt(expr=cmp)]

        if op == OpCode.TEST:
            return []

        if op == OpCode.TESTSET:
            return [self._assign_reg(inst.A, self._reg(inst.B))]

        if op == OpCode.CALL:
            func = self._reg(inst.A)
            nargs = inst.B - 1 if inst.B != 0 else -1
            if nargs >= 0:
                args = [self._reg(inst.A + 1 + i) for i in range(nargs)]
            else:
                args = [self._reg(inst.A + 1)]
            call = ast.Call(func=func, args=args)
            nresults = inst.C - 1 if inst.C != 0 else -1
            if nresults == 0:
                return [ast.ExprStmt(expr=call)]
            if nresults >= 1:
                return [self._assign_reg(inst.A, call)]
            return [self._assign_reg(inst.A, call)]

        if op == OpCode.TAILCALL:
            func = self._reg(inst.A)
            nargs = inst.B - 1 if inst.B != 0 else 0
            args = [self._reg(inst.A + 1 + i) for i in range(nargs)]
            return [ast.Return(values=[ast.Call(func=func, args=args)])]

        if op == OpCode.RETURN:
            nvals = inst.B - 1 if inst.B != 0 else 0
            if nvals == 0 and inst.B == 1:
                return [ast.Return(values=[])]
            vals = [self._reg(inst.A + i) for i in range(max(nvals, 0))]
            return [ast.Return(values=vals)]

        if op == OpCode.FORLOOP:
            return []

        if op == OpCode.FORPREP:
            return []

        if op == OpCode.TFORLOOP:
            return []

        if op == OpCode.SETLIST:
            return []

        if op == OpCode.CLOSE:
            return []

        if op == OpCode.CLOSURE:
            child = self.proto.protos[inst.Bx] if inst.Bx < len(self.proto.protos) else None
            if child:
                sub = Decompiler(child)
                body = sub.decompile()
                params = [f"a{i}" for i in range(child.num_params)]
                return [self._assign_reg(inst.A,
                    ast.FunctionExpr(params=params, body=body, is_vararg=child.is_vararg))]
            return [self._assign_reg(inst.A, ast.FunctionExpr(params=[], body=ast.Block(stmts=[])))]

        if op == OpCode.VARARG:
            return [self._assign_reg(inst.A, ast.Vararg())]

        return []

    def _reg(self, idx: int) -> ast.Expr:
        for lv in self.proto.local_vars:
            if lv.start_pc <= idx <= lv.end_pc:
                pass
        name = self._reg_name(idx)
        return ast.Name(name=name)

    def _reg_name(self, idx: int) -> str:
        for lv in self.proto.local_vars:
            if lv.name and lv.name != '(for generator)':
                return lv.name
        return f"v{idx}"

    def _upval(self, idx: int) -> ast.Name:
        if idx < len(self.proto.upvalue_descs):
            name = self.proto.upvalue_descs[idx].name
            if name:
                return ast.Name(name=name)
        return ast.Name(name=f"upval{idx}")

    def _rk(self, val: int) -> ast.Expr:
        is_k, idx = self.proto.rk(val)
        if is_k:
            return self._const_expr(idx)
        return self._reg(idx)

    def _const_expr(self, idx: int) -> ast.Expr:
        if idx >= len(self.proto.constants):
            return ast.Nil()
        c = self.proto.constants[idx]
        if c.type == 'nil':
            return ast.Nil()
        if c.type == 'boolean':
            return ast.Bool(value=c.value)
        if c.type == 'number':
            return ast.Number(value=c.value)
        if c.type == 'string':
            return ast.String(value=c.value, raw='')
        return ast.Nil()

    def _assign_reg(self, reg: int, value: ast.Expr) -> ast.Stmt:
        name = self._reg_name(reg)
        return ast.LocalAssign(names=[name], values=[value])


def decompile_prototype(proto: Prototype) -> ast.Block:
    d = Decompiler(proto)
    return d.decompile()
