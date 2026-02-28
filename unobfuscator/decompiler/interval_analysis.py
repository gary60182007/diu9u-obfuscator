from __future__ import annotations
import math
from typing import Dict, Set, List, Optional, Tuple
from dataclasses import dataclass, field
from ..core import lua_ast as ast
from ..core.cfg import CFG, BasicBlock, build_cfg, compute_dominators


@dataclass(frozen=True)
class Interval:
    lo: float
    hi: float

    @staticmethod
    def top() -> Interval:
        return Interval(-math.inf, math.inf)

    @staticmethod
    def bottom() -> Interval:
        return Interval(math.inf, -math.inf)

    @staticmethod
    def const(v: float) -> Interval:
        return Interval(v, v)

    @staticmethod
    def range(lo: float, hi: float) -> Interval:
        return Interval(lo, hi)

    @property
    def is_top(self) -> bool:
        return self.lo == -math.inf and self.hi == math.inf

    @property
    def is_bottom(self) -> bool:
        return self.lo > self.hi

    @property
    def is_const(self) -> bool:
        return self.lo == self.hi and not self.is_bottom

    @property
    def const_value(self) -> Optional[float]:
        return self.lo if self.is_const else None

    def contains(self, v: float) -> bool:
        return self.lo <= v <= self.hi

    def union(self, other: Interval) -> Interval:
        if self.is_bottom:
            return other
        if other.is_bottom:
            return self
        return Interval(min(self.lo, other.lo), max(self.hi, other.hi))

    def intersect(self, other: Interval) -> Interval:
        if self.is_bottom or other.is_bottom:
            return Interval.bottom()
        lo = max(self.lo, other.lo)
        hi = min(self.hi, other.hi)
        if lo > hi:
            return Interval.bottom()
        return Interval(lo, hi)

    def widen(self, other: Interval) -> Interval:
        if self.is_bottom:
            return other
        if other.is_bottom:
            return self
        lo = self.lo if other.lo >= self.lo else -math.inf
        hi = self.hi if other.hi <= self.hi else math.inf
        return Interval(lo, hi)

    def narrow(self, other: Interval) -> Interval:
        if self.is_bottom:
            return other
        if other.is_bottom:
            return self
        lo = other.lo if self.lo == -math.inf else self.lo
        hi = other.hi if self.hi == math.inf else self.hi
        return Interval(lo, hi)

    def add(self, other: Interval) -> Interval:
        if self.is_bottom or other.is_bottom:
            return Interval.bottom()
        return Interval(self.lo + other.lo, self.hi + other.hi)

    def sub(self, other: Interval) -> Interval:
        if self.is_bottom or other.is_bottom:
            return Interval.bottom()
        return Interval(self.lo - other.hi, self.hi - other.lo)

    def mul(self, other: Interval) -> Interval:
        if self.is_bottom or other.is_bottom:
            return Interval.bottom()
        products = [
            self.lo * other.lo, self.lo * other.hi,
            self.hi * other.lo, self.hi * other.hi,
        ]
        products = [p for p in products if not math.isnan(p)]
        if not products:
            return Interval.top()
        return Interval(min(products), max(products))

    def div(self, other: Interval) -> Interval:
        if self.is_bottom or other.is_bottom:
            return Interval.bottom()
        if other.contains(0):
            return Interval.top()
        return self.mul(Interval(1.0 / other.hi, 1.0 / other.lo))

    def mod(self, other: Interval) -> Interval:
        if self.is_bottom or other.is_bottom:
            return Interval.bottom()
        if other.is_const and other.const_value != 0:
            m = abs(other.const_value)
            return Interval(0, m - 1)
        return Interval.top()

    def neg(self) -> Interval:
        if self.is_bottom:
            return Interval.bottom()
        return Interval(-self.hi, -self.lo)

    def __repr__(self):
        if self.is_bottom:
            return "⊥"
        if self.is_top:
            return "⊤"
        if self.is_const:
            return f"[{self.lo}]"
        lo_s = "-∞" if self.lo == -math.inf else str(self.lo)
        hi_s = "∞" if self.hi == math.inf else str(self.hi)
        return f"[{lo_s}, {hi_s}]"


@dataclass
class IntervalState:
    intervals: Dict[str, Interval] = field(default_factory=dict)

    def get(self, name: str) -> Interval:
        return self.intervals.get(name, Interval.top())

    def set(self, name: str, iv: Interval):
        self.intervals[name] = iv

    def copy(self) -> IntervalState:
        return IntervalState(dict(self.intervals))

    def merge(self, other: IntervalState) -> bool:
        changed = False
        all_keys = set(self.intervals.keys()) | set(other.intervals.keys())
        for k in all_keys:
            old = self.intervals.get(k, Interval.bottom())
            new = old.union(other.intervals.get(k, Interval.bottom()))
            if new != old:
                self.intervals[k] = new
                changed = True
        return changed

    def widen_merge(self, other: IntervalState) -> bool:
        changed = False
        all_keys = set(self.intervals.keys()) | set(other.intervals.keys())
        for k in all_keys:
            old = self.intervals.get(k, Interval.bottom())
            new_val = other.intervals.get(k, Interval.bottom())
            widened = old.widen(new_val)
            if widened != old:
                self.intervals[k] = widened
                changed = True
        return changed


class IntervalAnalyzer:
    def __init__(self, max_iterations: int = 50):
        self.max_iterations = max_iterations
        self.state = IntervalState()

    def analyze(self, tree: ast.Block) -> IntervalState:
        for _ in range(self.max_iterations):
            old = dict(self.state.intervals)
            self._analyze_block(tree)
            if self.state.intervals == old:
                break
        return self.state

    def _analyze_block(self, block: ast.Block):
        for stmt in block.stmts:
            self._analyze_stmt(stmt)

    def _analyze_stmt(self, stmt: ast.Stmt):
        if isinstance(stmt, ast.LocalAssign):
            for i, name in enumerate(stmt.names):
                if i < len(stmt.values):
                    iv = self._eval_interval(stmt.values[i])
                else:
                    iv = Interval.const(0)
                self.state.set(name, iv)
        elif isinstance(stmt, ast.Assign):
            for i, tgt in enumerate(stmt.targets):
                if isinstance(tgt, ast.Name) and i < len(stmt.values):
                    iv = self._eval_interval(stmt.values[i])
                    self.state.set(tgt.name, iv)
        elif isinstance(stmt, ast.ForNumeric):
            start = self._eval_interval(stmt.start)
            stop = self._eval_interval(stmt.stop)
            step_iv = self._eval_interval(stmt.step) if stmt.step else Interval.const(1)
            loop_range = start.union(stop)
            self.state.set(stmt.name, loop_range)
            self._analyze_block(stmt.body)
        elif isinstance(stmt, ast.ForGeneric):
            for nm in stmt.names:
                self.state.set(nm, Interval.top())
            self._analyze_block(stmt.body)
        elif isinstance(stmt, ast.If):
            for i in range(len(stmt.tests)):
                self._refine_from_condition(stmt.tests[i], True)
                self._analyze_block(stmt.bodies[i])
            if stmt.else_body:
                self._analyze_block(stmt.else_body)
        elif isinstance(stmt, ast.While):
            self._analyze_block(stmt.body)
        elif isinstance(stmt, ast.Do):
            self._analyze_block(stmt.body)
        elif isinstance(stmt, ast.Repeat):
            self._analyze_block(stmt.body)
        elif isinstance(stmt, ast.FunctionDecl):
            self._analyze_block(stmt.body)

    def _eval_interval(self, expr: ast.Expr) -> Interval:
        if isinstance(expr, ast.Number):
            return Interval.const(expr.value)
        if isinstance(expr, ast.Name):
            return self.state.get(expr.name)
        if isinstance(expr, ast.BinOp):
            l = self._eval_interval(expr.left)
            r = self._eval_interval(expr.right)
            if expr.op == '+': return l.add(r)
            if expr.op == '-': return l.sub(r)
            if expr.op == '*': return l.mul(r)
            if expr.op == '/': return l.div(r)
            if expr.op == '%': return l.mod(r)
            if expr.op == '^':
                if l.is_const and r.is_const:
                    try:
                        return Interval.const(l.const_value ** r.const_value)
                    except (OverflowError, ValueError):
                        pass
                return Interval.top()
            return Interval.top()
        if isinstance(expr, ast.UnOp):
            v = self._eval_interval(expr.operand)
            if expr.op == '-': return v.neg()
            if expr.op == '#': return Interval.range(0, math.inf)
            return Interval.top()
        if isinstance(expr, ast.Call):
            return self._eval_call_interval(expr)
        return Interval.top()

    def _eval_call_interval(self, expr: ast.Call) -> Interval:
        if isinstance(expr.func, ast.Field) and isinstance(expr.func.table, ast.Name):
            tbl = expr.func.table.name
            name = expr.func.name
            if tbl == 'math':
                if name == 'abs' and len(expr.args) >= 1:
                    v = self._eval_interval(expr.args[0])
                    if not v.is_bottom:
                        lo = 0 if v.lo <= 0 <= v.hi else min(abs(v.lo), abs(v.hi))
                        hi = max(abs(v.lo), abs(v.hi)) if not v.is_top else math.inf
                        return Interval(lo, hi)
                if name == 'floor' and len(expr.args) >= 1:
                    v = self._eval_interval(expr.args[0])
                    return Interval(math.floor(v.lo) if v.lo != -math.inf else -math.inf,
                                    math.floor(v.hi) if v.hi != math.inf else math.inf)
                if name == 'ceil' and len(expr.args) >= 1:
                    v = self._eval_interval(expr.args[0])
                    return Interval(math.ceil(v.lo) if v.lo != -math.inf else -math.inf,
                                    math.ceil(v.hi) if v.hi != math.inf else math.inf)
                if name == 'max' and len(expr.args) >= 2:
                    ivs = [self._eval_interval(a) for a in expr.args]
                    lo = max(iv.lo for iv in ivs)
                    hi = max(iv.hi for iv in ivs)
                    return Interval(lo, hi)
                if name == 'min' and len(expr.args) >= 2:
                    ivs = [self._eval_interval(a) for a in expr.args]
                    lo = min(iv.lo for iv in ivs)
                    hi = min(iv.hi for iv in ivs)
                    return Interval(lo, hi)
                if name == 'random':
                    if len(expr.args) == 0:
                        return Interval(0, 1)
                    if len(expr.args) == 1:
                        return Interval(1, self._eval_interval(expr.args[0]).hi)
                    if len(expr.args) >= 2:
                        lo = self._eval_interval(expr.args[0])
                        hi = self._eval_interval(expr.args[1])
                        return Interval(lo.lo, hi.hi)
                if name in ('sin', 'cos'):
                    return Interval(-1, 1)
                if name == 'sqrt' and len(expr.args) >= 1:
                    v = self._eval_interval(expr.args[0])
                    lo = math.sqrt(max(0, v.lo)) if v.lo != -math.inf else 0
                    hi = math.sqrt(v.hi) if v.hi != math.inf and v.hi >= 0 else math.inf
                    return Interval(lo, hi)
            if tbl == 'string':
                if name in ('byte', 'len'):
                    return Interval(0, math.inf)
            if tbl in ('bit32', 'bit'):
                return Interval(0, 0xFFFFFFFF)
        if isinstance(expr.func, ast.Name):
            if expr.func.name == 'tonumber':
                return Interval.top()
        return Interval.top()

    def _refine_from_condition(self, cond: ast.Expr, is_true: bool):
        if isinstance(cond, ast.BinOp):
            if cond.op in ('<', '<=', '>', '>=', '==') and isinstance(cond.left, ast.Name):
                name = cond.left.name
                rhs = self._eval_interval(cond.right)
                cur = self.state.get(name)
                if is_true:
                    if cond.op == '<' and rhs.is_const:
                        self.state.set(name, cur.intersect(Interval(-math.inf, rhs.const_value - 1)))
                    elif cond.op == '<=' and rhs.is_const:
                        self.state.set(name, cur.intersect(Interval(-math.inf, rhs.const_value)))
                    elif cond.op == '>' and rhs.is_const:
                        self.state.set(name, cur.intersect(Interval(rhs.const_value + 1, math.inf)))
                    elif cond.op == '>=' and rhs.is_const:
                        self.state.set(name, cur.intersect(Interval(rhs.const_value, math.inf)))
                    elif cond.op == '==' and rhs.is_const:
                        self.state.set(name, Interval.const(rhs.const_value))


class IntervalSimplifier(ast.ASTTransformer):
    def __init__(self, state: IntervalState):
        self.state = state
        self.changes = 0

    def simplify(self, tree: ast.Block) -> ast.Block:
        self.changes = 0
        return self.transform(tree)

    def transform_If(self, node: ast.If) -> ast.Stmt:
        new_tests = []
        new_bodies = []
        for i in range(len(node.tests)):
            test = self.transform(node.tests[i])
            body = self.transform(node.bodies[i])
            result = self._try_resolve_condition(test)
            if result is True:
                if not new_tests:
                    self.changes += 1
                    return ast.Do(body=body, loc=node.loc)
            elif result is False:
                self.changes += 1
                continue
            new_tests.append(test)
            new_bodies.append(body)
        else_body = self.transform(node.else_body) if node.else_body else None
        if not new_tests:
            if else_body and else_body.stmts:
                return ast.Do(body=else_body, loc=node.loc)
            return ast.Do(body=ast.Block(stmts=[]), loc=node.loc)
        return ast.If(tests=new_tests, bodies=new_bodies, else_body=else_body, loc=node.loc)

    def _try_resolve_condition(self, cond: ast.Expr) -> Optional[bool]:
        if isinstance(cond, ast.BinOp) and isinstance(cond.left, ast.Name):
            iv = self.state.get(cond.left.name)
            if isinstance(cond.right, ast.Number):
                rhs = cond.right.value
                if cond.op == '<' and iv.hi < rhs: return True
                if cond.op == '<' and iv.lo >= rhs: return False
                if cond.op == '<=' and iv.hi <= rhs: return True
                if cond.op == '<=' and iv.lo > rhs: return False
                if cond.op == '>' and iv.lo > rhs: return True
                if cond.op == '>' and iv.hi <= rhs: return False
                if cond.op == '>=' and iv.lo >= rhs: return True
                if cond.op == '>=' and iv.hi < rhs: return False
                if cond.op == '==' and iv.is_const and iv.const_value == rhs: return True
                if cond.op == '==' and (iv.hi < rhs or iv.lo > rhs): return False
                if cond.op == '~=' and iv.is_const and iv.const_value == rhs: return False
                if cond.op == '~=' and (iv.hi < rhs or iv.lo > rhs): return True
        return None


def analyze_intervals(tree: ast.Block) -> Tuple[ast.Block, IntervalState]:
    ia = IntervalAnalyzer()
    state = ia.analyze(tree)
    ism = IntervalSimplifier(state)
    tree = ism.simplify(tree)
    return tree, state
