from __future__ import annotations
import math
from typing import Dict, Set, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum, auto
from ..core import lua_ast as ast
from ..core.cfg import CFG, BasicBlock, DominatorTree, build_cfg, compute_dominators


class LatticeKind(Enum):
    TOP = auto()
    CONST = auto()
    BOTTOM = auto()


@dataclass(frozen=True)
class LatticeValue:
    kind: LatticeKind
    value: Any = None

    @staticmethod
    def top() -> LatticeValue:
        return LatticeValue(LatticeKind.TOP)

    @staticmethod
    def const(v) -> LatticeValue:
        return LatticeValue(LatticeKind.CONST, v)

    @staticmethod
    def bottom() -> LatticeValue:
        return LatticeValue(LatticeKind.BOTTOM)

    def meet(self, other: LatticeValue) -> LatticeValue:
        if self.kind == LatticeKind.TOP:
            return other
        if other.kind == LatticeKind.TOP:
            return self
        if self.kind == LatticeKind.CONST and other.kind == LatticeKind.CONST:
            if self.value == other.value and type(self.value) == type(other.value):
                return self
            return LatticeValue.bottom()
        return LatticeValue.bottom()

    @property
    def is_const(self) -> bool:
        return self.kind == LatticeKind.CONST

    @property
    def is_top(self) -> bool:
        return self.kind == LatticeKind.TOP

    @property
    def is_bottom(self) -> bool:
        return self.kind == LatticeKind.BOTTOM

    def __repr__(self):
        if self.kind == LatticeKind.TOP:
            return "⊤"
        if self.kind == LatticeKind.BOTTOM:
            return "⊥"
        return f"Const({self.value!r})"


class TypeLattice(Enum):
    TOP = auto()
    NIL = auto()
    BOOLEAN = auto()
    NUMBER = auto()
    STRING = auto()
    TABLE = auto()
    FUNCTION = auto()
    BOTTOM = auto()

    def meet(self, other: TypeLattice) -> TypeLattice:
        if self == TypeLattice.TOP:
            return other
        if other == TypeLattice.TOP:
            return self
        if self == other:
            return self
        return TypeLattice.BOTTOM


@dataclass
class AbstractState:
    values: Dict[str, LatticeValue] = field(default_factory=dict)
    types: Dict[str, TypeLattice] = field(default_factory=dict)

    def get(self, name: str) -> LatticeValue:
        return self.values.get(name, LatticeValue.top())

    def get_type(self, name: str) -> TypeLattice:
        return self.types.get(name, TypeLattice.TOP)

    def set(self, name: str, val: LatticeValue, typ: Optional[TypeLattice] = None):
        self.values[name] = val
        if typ is not None:
            self.types[name] = typ
        elif val.is_const:
            self.types[name] = _value_type(val.value)

    def merge(self, other: AbstractState) -> bool:
        changed = False
        all_keys = set(self.values.keys()) | set(other.values.keys())
        for k in all_keys:
            old = self.values.get(k, LatticeValue.top())
            new = old.meet(other.values.get(k, LatticeValue.top()))
            if new != old:
                self.values[k] = new
                changed = True
            old_t = self.types.get(k, TypeLattice.TOP)
            new_t = old_t.meet(other.types.get(k, TypeLattice.TOP))
            if new_t != old_t:
                self.types[k] = new_t
                changed = True
        return changed

    def copy(self) -> AbstractState:
        return AbstractState(dict(self.values), dict(self.types))


def _value_type(v) -> TypeLattice:
    if v is None: return TypeLattice.NIL
    if isinstance(v, bool): return TypeLattice.BOOLEAN
    if isinstance(v, (int, float)): return TypeLattice.NUMBER
    if isinstance(v, str): return TypeLattice.STRING
    return TypeLattice.BOTTOM


class AbstractInterpreter:
    def __init__(self, cfg: CFG):
        self.cfg = cfg
        self.block_states: Dict[int, AbstractState] = {}
        self.out_states: Dict[int, AbstractState] = {}
        self._max_iterations = 100

    def run(self) -> Dict[str, LatticeValue]:
        for bid in self.cfg.blocks:
            self.block_states[bid] = AbstractState()
            self.out_states[bid] = AbstractState()

        worklist = list(self.cfg.rpo())
        iterations = 0

        while worklist and iterations < self._max_iterations:
            iterations += 1
            bid = worklist.pop(0)
            bb = self.cfg.blocks[bid]

            in_state = AbstractState()
            for pred in bb.preds:
                in_state.merge(self.out_states.get(pred, AbstractState()))

            out_state = in_state.copy()
            self._transfer_block(bb, out_state)

            old = self.out_states[bid]
            if self._states_differ(old, out_state):
                self.out_states[bid] = out_state
                self.block_states[bid] = in_state
                for succ in bb.succs:
                    if succ not in worklist:
                        worklist.append(succ)

        result = {}
        for bid, state in self.out_states.items():
            for k, v in state.values.items():
                if k in result:
                    result[k] = result[k].meet(v)
                else:
                    result[k] = v
        return result

    def _transfer_block(self, bb: BasicBlock, state: AbstractState):
        for stmt in bb.stmts:
            self._transfer_stmt(stmt, state)

    def _transfer_stmt(self, stmt: ast.Stmt, state: AbstractState):
        if isinstance(stmt, ast.LocalAssign):
            vals = [self._eval_expr(v, state) for v in stmt.values]
            for i, nm in enumerate(stmt.names):
                if i < len(vals):
                    state.set(nm, vals[i])
                else:
                    state.set(nm, LatticeValue.const(None), TypeLattice.NIL)
        elif isinstance(stmt, ast.Assign):
            vals = [self._eval_expr(v, state) for v in stmt.values]
            for i, tgt in enumerate(stmt.targets):
                if isinstance(tgt, ast.Name):
                    if i < len(vals):
                        state.set(tgt.name, vals[i])
                    else:
                        state.set(tgt.name, LatticeValue.const(None))
        elif isinstance(stmt, ast.FunctionDecl):
            if stmt.is_local and isinstance(stmt.name, ast.Name):
                state.set(stmt.name.name, LatticeValue.bottom(), TypeLattice.FUNCTION)
            elif isinstance(stmt.name, ast.Name):
                state.set(stmt.name.name, LatticeValue.bottom(), TypeLattice.FUNCTION)

    def _eval_expr(self, expr: ast.Expr, state: AbstractState) -> LatticeValue:
        if isinstance(expr, ast.Nil):
            return LatticeValue.const(None)
        if isinstance(expr, ast.Bool):
            return LatticeValue.const(expr.value)
        if isinstance(expr, ast.Number):
            return LatticeValue.const(expr.value)
        if isinstance(expr, ast.String):
            return LatticeValue.const(expr.value)
        if isinstance(expr, ast.Name):
            return state.get(expr.name)
        if isinstance(expr, ast.BinOp):
            return self._eval_binop(expr, state)
        if isinstance(expr, ast.UnOp):
            return self._eval_unop(expr, state)
        if isinstance(expr, ast.Concat):
            vals = [self._eval_expr(v, state) for v in expr.values]
            if all(v.is_const for v in vals):
                try:
                    return LatticeValue.const(''.join(_tostr(v.value) for v in vals))
                except Exception:
                    return LatticeValue.bottom()
            return LatticeValue.bottom()
        return LatticeValue.bottom()

    def _eval_binop(self, expr: ast.BinOp, state: AbstractState) -> LatticeValue:
        l = self._eval_expr(expr.left, state)
        r = self._eval_expr(expr.right, state)

        if expr.op == 'and':
            if l.is_const:
                return r if _truthy(l.value) else l
            return LatticeValue.bottom()
        if expr.op == 'or':
            if l.is_const:
                return l if _truthy(l.value) else r
            return LatticeValue.bottom()

        if l.is_const and r.is_const:
            result = _do_binop(expr.op, l.value, r.value)
            if result is not None:
                return LatticeValue.const(result)
        if l.is_top or r.is_top:
            return LatticeValue.top()
        return LatticeValue.bottom()

    def _eval_unop(self, expr: ast.UnOp, state: AbstractState) -> LatticeValue:
        v = self._eval_expr(expr.operand, state)
        if v.is_const:
            result = _do_unop(expr.op, v.value)
            if result is not None:
                return LatticeValue.const(result)
        if v.is_top:
            return LatticeValue.top()
        return LatticeValue.bottom()

    def _states_differ(self, a: AbstractState, b: AbstractState) -> bool:
        all_keys = set(a.values.keys()) | set(b.values.keys())
        for k in all_keys:
            av = a.values.get(k, LatticeValue.top())
            bv = b.values.get(k, LatticeValue.top())
            if av != bv:
                return True
        return False


class ConstantPropagator(ast.ASTTransformer):
    def __init__(self, constants: Dict[str, LatticeValue]):
        self.constants = constants
        self.changes = 0

    def propagate(self, tree: ast.Block) -> ast.Block:
        self.changes = 0
        return self.transform(tree)

    def transform_Name(self, node: ast.Name) -> ast.Expr:
        val = self.constants.get(node.name)
        if val and val.is_const:
            v = val.value
            if isinstance(v, (int, float)):
                self.changes += 1
                return ast.Number(value=v, loc=node.loc)
            if isinstance(v, str):
                self.changes += 1
                return ast.String(value=v, raw='', loc=node.loc)
            if isinstance(v, bool):
                self.changes += 1
                return ast.Bool(value=v, loc=node.loc)
            if v is None:
                self.changes += 1
                return ast.Nil(loc=node.loc)
        return node


def _truthy(v) -> bool:
    return v is not None and v is not False


def _tostr(v) -> str:
    if v is None: return "nil"
    if isinstance(v, bool): return "true" if v else "false"
    if isinstance(v, float):
        if v == int(v) and not math.isinf(v): return str(int(v))
        return str(v)
    return str(v)


def _do_binop(op, a, b):
    try:
        if op == '+' and isinstance(a, (int, float)) and isinstance(b, (int, float)): return a + b
        if op == '-' and isinstance(a, (int, float)) and isinstance(b, (int, float)): return a - b
        if op == '*' and isinstance(a, (int, float)) and isinstance(b, (int, float)): return a * b
        if op == '/' and isinstance(a, (int, float)) and isinstance(b, (int, float)) and b != 0: return a / b
        if op == '%' and isinstance(a, (int, float)) and isinstance(b, (int, float)) and b != 0: return a % b
        if op == '^' and isinstance(a, (int, float)) and isinstance(b, (int, float)): return a ** b
        if op == '//' and isinstance(a, (int, float)) and isinstance(b, (int, float)) and b != 0: return a // b
        if op == '..' and isinstance(a, str) and isinstance(b, str): return a + b
        if op == '==': return a == b
        if op == '~=': return a != b
        if op == '<' and type(a) == type(b): return a < b
        if op == '>' and type(a) == type(b): return a > b
        if op == '<=' and type(a) == type(b): return a <= b
        if op == '>=' and type(a) == type(b): return a >= b
        if op == '&' and isinstance(a, (int, float)) and isinstance(b, (int, float)): return int(a) & int(b)
        if op == '|' and isinstance(a, (int, float)) and isinstance(b, (int, float)): return int(a) | int(b)
        if op == '~' and isinstance(a, (int, float)) and isinstance(b, (int, float)): return int(a) ^ int(b)
    except Exception:
        pass
    return None


def _do_unop(op, v):
    try:
        if op == '-' and isinstance(v, (int, float)): return -v
        if op == '#' and isinstance(v, str): return len(v)
        if op == 'not': return not _truthy(v)
        if op == '~' and isinstance(v, (int, float)): return (~int(v)) & 0xFFFFFFFF
    except Exception:
        pass
    return None


def constant_propagation(tree: ast.Block) -> ast.Block:
    cfg = build_cfg(tree)
    dom = compute_dominators(cfg)
    ai = AbstractInterpreter(cfg)
    constants = ai.run()
    cp = ConstantPropagator(constants)
    return cp.propagate(tree)
