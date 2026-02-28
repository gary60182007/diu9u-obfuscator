from __future__ import annotations
from typing import Any, Dict, List, Optional, Set, Tuple, Union
from dataclasses import dataclass, field
from enum import Enum, auto
from . import lua_ast as ast


class SymKind(Enum):
    CONST = auto()
    SYM = auto()
    BINOP = auto()
    UNOP = auto()
    CALL = auto()
    INDEX = auto()
    FIELD = auto()
    TABLE = auto()
    FUNC = auto()
    UNKNOWN = auto()
    PHI = auto()


@dataclass(frozen=True)
class SymVal:
    kind: SymKind
    data: Any = None

    @staticmethod
    def const(value) -> SymVal:
        return SymVal(SymKind.CONST, value)

    @staticmethod
    def sym(name: str) -> SymVal:
        return SymVal(SymKind.SYM, name)

    @staticmethod
    def binop(op: str, left: SymVal, right: SymVal) -> SymVal:
        return SymVal(SymKind.BINOP, (op, left, right))

    @staticmethod
    def unop(op: str, operand: SymVal) -> SymVal:
        return SymVal(SymKind.UNOP, (op, operand))

    @staticmethod
    def call(func: SymVal, args: tuple) -> SymVal:
        return SymVal(SymKind.CALL, (func, args))

    @staticmethod
    def index(table: SymVal, key: SymVal) -> SymVal:
        return SymVal(SymKind.INDEX, (table, key))

    @staticmethod
    def field_access(table: SymVal, name: str) -> SymVal:
        return SymVal(SymKind.FIELD, (table, name))

    @staticmethod
    def table(entries: tuple = ()) -> SymVal:
        return SymVal(SymKind.TABLE, entries)

    @staticmethod
    def func(name: str = "?") -> SymVal:
        return SymVal(SymKind.FUNC, name)

    @staticmethod
    def unknown() -> SymVal:
        return SymVal(SymKind.UNKNOWN)

    @staticmethod
    def phi(sources: tuple) -> SymVal:
        return SymVal(SymKind.PHI, sources)

    @property
    def is_const(self) -> bool:
        return self.kind == SymKind.CONST

    @property
    def const_value(self):
        return self.data if self.kind == SymKind.CONST else None

    def try_fold(self) -> SymVal:
        if self.kind == SymKind.BINOP:
            op, left, right = self.data
            left = left.try_fold()
            right = right.try_fold()
            if left.is_const and right.is_const:
                r = _eval_binop(op, left.const_value, right.const_value)
                if r is not None:
                    return SymVal.const(r)
            return SymVal.binop(op, left, right)
        if self.kind == SymKind.UNOP:
            op, operand = self.data
            operand = operand.try_fold()
            if operand.is_const:
                r = _eval_unop(op, operand.const_value)
                if r is not None:
                    return SymVal.const(r)
            return SymVal.unop(op, operand)
        return self

    def matches_pattern(self, pattern: SymVal, bindings: Optional[Dict[str, SymVal]] = None) -> Optional[Dict[str, SymVal]]:
        if bindings is None:
            bindings = {}
        if pattern.kind == SymKind.SYM:
            name = pattern.data
            if name in bindings:
                return bindings if bindings[name] == self else None
            bindings[name] = self
            return bindings
        if pattern.kind == SymKind.CONST:
            if self.kind == SymKind.CONST and self.data == pattern.data:
                return bindings
            return None
        if pattern.kind != self.kind:
            return None
        if pattern.kind == SymKind.BINOP:
            pop, pl, pr = pattern.data
            sop, sl, sr = self.data
            if pop != sop:
                return None
            b = sl.matches_pattern(pl, bindings)
            if b is None:
                return None
            return sr.matches_pattern(pr, b)
        if pattern.kind == SymKind.UNOP:
            pop, po = pattern.data
            sop, so = self.data
            if pop != sop:
                return None
            return so.matches_pattern(po, bindings)
        if pattern.kind == SymKind.INDEX:
            pt, pk = pattern.data
            st, sk = self.data
            b = st.matches_pattern(pt, bindings)
            if b is None:
                return None
            return sk.matches_pattern(pk, b)
        if pattern.kind == SymKind.FIELD:
            pt, pn = pattern.data
            st, sn = self.data
            if pn != sn:
                return None
            return st.matches_pattern(pt, bindings)
        return None

    def __repr__(self):
        if self.kind == SymKind.CONST:
            return f"Const({self.data!r})"
        if self.kind == SymKind.SYM:
            return f"Sym({self.data})"
        if self.kind == SymKind.BINOP:
            op, l, r = self.data
            return f"({l} {op} {r})"
        if self.kind == SymKind.UNOP:
            op, v = self.data
            return f"({op} {v})"
        if self.kind == SymKind.CALL:
            fn, args = self.data
            return f"Call({fn}, {args})"
        if self.kind == SymKind.INDEX:
            t, k = self.data
            return f"{t}[{k}]"
        if self.kind == SymKind.FIELD:
            t, n = self.data
            return f"{t}.{n}"
        if self.kind == SymKind.TABLE:
            return "Table{}"
        if self.kind == SymKind.FUNC:
            return f"Func({self.data})"
        if self.kind == SymKind.UNKNOWN:
            return "Unknown"
        if self.kind == SymKind.PHI:
            return f"Phi({self.data})"
        return f"SymVal({self.kind})"


def _eval_binop(op: str, a, b):
    try:
        if op == '+' and isinstance(a, (int, float)) and isinstance(b, (int, float)):
            return a + b
        if op == '-' and isinstance(a, (int, float)) and isinstance(b, (int, float)):
            return a - b
        if op == '*' and isinstance(a, (int, float)) and isinstance(b, (int, float)):
            return a * b
        if op == '/' and isinstance(a, (int, float)) and isinstance(b, (int, float)):
            return a / b if b != 0 else None
        if op == '%' and isinstance(a, (int, float)) and isinstance(b, (int, float)):
            return a % b if b != 0 else None
        if op == '^' and isinstance(a, (int, float)) and isinstance(b, (int, float)):
            return a ** b
        if op == '//' and isinstance(a, (int, float)) and isinstance(b, (int, float)):
            return a // b if b != 0 else None
        if op == '..' and isinstance(a, str) and isinstance(b, str):
            return a + b
        if op == '==' : return a == b
        if op == '~=' : return a != b
        if op == '<' and isinstance(a, (int, float, str)) and isinstance(b, type(a)):
            return a < b
        if op == '>' and isinstance(a, (int, float, str)) and isinstance(b, type(a)):
            return a > b
        if op == '<=' and isinstance(a, (int, float, str)) and isinstance(b, type(a)):
            return a <= b
        if op == '>=' and isinstance(a, (int, float, str)) and isinstance(b, type(a)):
            return a >= b
        if op == '&' and isinstance(a, (int, float)) and isinstance(b, (int, float)):
            return int(a) & int(b)
        if op == '|' and isinstance(a, (int, float)) and isinstance(b, (int, float)):
            return int(a) | int(b)
        if op == '~' and isinstance(a, (int, float)) and isinstance(b, (int, float)):
            return int(a) ^ int(b)
        if op == '<<' and isinstance(a, (int, float)) and isinstance(b, (int, float)):
            return (int(a) << int(b)) & 0xFFFFFFFF
        if op == '>>' and isinstance(a, (int, float)) and isinstance(b, (int, float)):
            return (int(a) >> int(b)) & 0xFFFFFFFF
    except Exception:
        pass
    return None


def _eval_unop(op: str, a):
    try:
        if op == '-' and isinstance(a, (int, float)):
            return -a
        if op == '#' and isinstance(a, str):
            return len(a)
        if op == 'not':
            return not (a is not None and a is not False)
        if op == '~' and isinstance(a, (int, float)):
            return (~int(a)) & 0xFFFFFFFF
    except Exception:
        pass
    return None


class SymEnvironment:
    def __init__(self, parent: Optional[SymEnvironment] = None):
        self.vars: Dict[str, SymVal] = {}
        self.parent = parent

    def get(self, name: str) -> SymVal:
        if name in self.vars:
            return self.vars[name]
        if self.parent:
            return self.parent.get(name)
        return SymVal.sym(name)

    def set(self, name: str, val: SymVal):
        self.vars[name] = val

    def set_existing(self, name: str, val: SymVal) -> bool:
        if name in self.vars:
            self.vars[name] = val
            return True
        if self.parent:
            return self.parent.set_existing(name, val)
        return False

    def child(self) -> SymEnvironment:
        return SymEnvironment(self)


@dataclass
class PathConstraint:
    condition: SymVal
    is_true: bool
    location: Optional[ast.SourceLocation] = None


@dataclass
class SymWrite:
    target: SymVal
    value: SymVal
    location: Optional[ast.SourceLocation] = None


class SymbolicExecutor:
    def __init__(self, max_steps: int = 50000):
        self.max_steps = max_steps
        self.steps = 0
        self.constraints: List[PathConstraint] = []
        self.writes: List[SymWrite] = []
        self.calls: List[Tuple[SymVal, Tuple[SymVal, ...]]] = []
        self.returns: List[Tuple[SymVal, ...]] = []

    def analyze_block(self, block: ast.Block, env: Optional[SymEnvironment] = None) -> SymEnvironment:
        if env is None:
            env = SymEnvironment()
        for stmt in block.stmts:
            self._step()
            self._analyze_stmt(stmt, env)
        return env

    def analyze_expr(self, expr: ast.Expr, env: Optional[SymEnvironment] = None) -> SymVal:
        if env is None:
            env = SymEnvironment()
        return self._eval(expr, env)

    def prove_always_true(self, expr: ast.Expr, env: Optional[SymEnvironment] = None) -> Optional[bool]:
        val = self.analyze_expr(expr, env)
        folded = val.try_fold()
        if folded.is_const:
            v = folded.const_value
            if v is None or v is False:
                return False
            return True
        return None

    def prove_always_false(self, expr: ast.Expr, env: Optional[SymEnvironment] = None) -> Optional[bool]:
        r = self.prove_always_true(expr, env)
        if r is None:
            return None
        return not r

    def classify_handler(self, body: ast.Block, reg_sym: str = "R", inst_sym: str = "I") -> Optional[str]:
        env = SymEnvironment()
        env.set(reg_sym, SymVal.sym(reg_sym))
        env.set(inst_sym, SymVal.sym(inst_sym))
        self.writes.clear()
        self.calls.clear()
        self.returns.clear()

        try:
            self.analyze_block(body, env)
        except _StepLimit:
            pass

        return self._match_opcode_pattern()

    def _step(self):
        self.steps += 1
        if self.steps > self.max_steps:
            raise _StepLimit()

    def _analyze_stmt(self, stmt: ast.Stmt, env: SymEnvironment):
        if isinstance(stmt, ast.LocalAssign):
            vals = [self._eval(v, env) for v in stmt.values]
            for i, nm in enumerate(stmt.names):
                env.set(nm, vals[i] if i < len(vals) else SymVal.const(None))
        elif isinstance(stmt, ast.Assign):
            vals = [self._eval(v, env) for v in stmt.values]
            for i, tgt in enumerate(stmt.targets):
                val = vals[i] if i < len(vals) else SymVal.const(None)
                self._assign(tgt, val, env)
        elif isinstance(stmt, ast.ExprStmt):
            self._eval(stmt.expr, env)
        elif isinstance(stmt, ast.If):
            for idx in range(len(stmt.tests)):
                cond = self._eval(stmt.tests[idx], env)
                self.constraints.append(PathConstraint(cond, True, stmt.loc))
                child = env.child()
                self.analyze_block(stmt.bodies[idx], child)
            if stmt.else_body:
                child = env.child()
                self.analyze_block(stmt.else_body, child)
        elif isinstance(stmt, ast.While):
            cond = self._eval(stmt.condition, env)
            self.constraints.append(PathConstraint(cond, True, stmt.loc))
            child = env.child()
            self.analyze_block(stmt.body, child)
        elif isinstance(stmt, ast.ForNumeric):
            child = env.child()
            child.set(stmt.name, SymVal.sym(stmt.name))
            self.analyze_block(stmt.body, child)
        elif isinstance(stmt, ast.ForGeneric):
            child = env.child()
            for nm in stmt.names:
                child.set(nm, SymVal.sym(nm))
            self.analyze_block(stmt.body, child)
        elif isinstance(stmt, ast.Do):
            self.analyze_block(stmt.body, env.child())
        elif isinstance(stmt, ast.Return):
            vals = tuple(self._eval(v, env) for v in stmt.values)
            self.returns.append(vals)
        elif isinstance(stmt, ast.FunctionDecl):
            fn_val = SymVal.func(self._name_str(stmt.name) if stmt.name else "?")
            if stmt.is_local and isinstance(stmt.name, ast.Name):
                env.set(stmt.name.name, fn_val)
            else:
                self._assign(stmt.name, fn_val, env)
        elif isinstance(stmt, ast.Repeat):
            child = env.child()
            self.analyze_block(stmt.body, child)

    def _assign(self, tgt: ast.Expr, val: SymVal, env: SymEnvironment):
        if isinstance(tgt, ast.Name):
            if not env.set_existing(tgt.name, val):
                env.set(tgt.name, val)
            self.writes.append(SymWrite(SymVal.sym(tgt.name), val, tgt.loc))
        elif isinstance(tgt, ast.Index):
            t = self._eval(tgt.table, env)
            k = self._eval(tgt.key, env)
            self.writes.append(SymWrite(SymVal.index(t, k), val, tgt.loc))
        elif isinstance(tgt, ast.Field):
            t = self._eval(tgt.table, env)
            self.writes.append(SymWrite(SymVal.field_access(t, tgt.name), val, tgt.loc))

    def _eval(self, expr: ast.Expr, env: SymEnvironment) -> SymVal:
        self._step()
        if isinstance(expr, ast.Nil):
            return SymVal.const(None)
        if isinstance(expr, ast.Bool):
            return SymVal.const(expr.value)
        if isinstance(expr, ast.Number):
            return SymVal.const(expr.value)
        if isinstance(expr, ast.String):
            return SymVal.const(expr.value)
        if isinstance(expr, ast.Name):
            return env.get(expr.name)
        if isinstance(expr, ast.Vararg):
            return SymVal.sym('...')
        if isinstance(expr, ast.BinOp):
            l = self._eval(expr.left, env)
            r = self._eval(expr.right, env)
            result = SymVal.binop(expr.op, l, r)
            return result.try_fold()
        if isinstance(expr, ast.UnOp):
            v = self._eval(expr.operand, env)
            result = SymVal.unop(expr.op, v)
            return result.try_fold()
        if isinstance(expr, ast.Concat):
            vals = [self._eval(v, env) for v in expr.values]
            if all(v.is_const and isinstance(v.const_value, str) for v in vals):
                return SymVal.const(''.join(v.const_value for v in vals))
            result = vals[0]
            for v in vals[1:]:
                result = SymVal.binop('..', result, v)
            return result
        if isinstance(expr, ast.Call):
            fn = self._eval(expr.func, env)
            args = tuple(self._eval(a, env) for a in expr.args)
            self.calls.append((fn, args))
            result = SymVal.call(fn, args)
            return self._try_builtin_call(fn, args) or result
        if isinstance(expr, ast.MethodCall):
            obj = self._eval(expr.object, env)
            args = (obj,) + tuple(self._eval(a, env) for a in expr.args)
            fn = SymVal.field_access(obj, expr.method)
            self.calls.append((fn, args))
            return SymVal.call(fn, args)
        if isinstance(expr, ast.Index):
            t = self._eval(expr.table, env)
            k = self._eval(expr.key, env)
            return SymVal.index(t, k)
        if isinstance(expr, ast.Field):
            t = self._eval(expr.table, env)
            return SymVal.field_access(t, expr.name)
        if isinstance(expr, ast.FunctionExpr):
            return SymVal.func("lambda")
        if isinstance(expr, ast.TableConstructor):
            return SymVal.table()
        return SymVal.unknown()

    def _try_builtin_call(self, fn: SymVal, args: tuple) -> Optional[SymVal]:
        if fn.kind == SymKind.FIELD:
            tbl, name = fn.data
            if tbl.kind == SymKind.SYM and tbl.data == 'string':
                if name == 'byte' and len(args) >= 1 and args[0].is_const and isinstance(args[0].const_value, str):
                    s = args[0].const_value
                    i = args[1].const_value if len(args) > 1 and args[1].is_const else 1
                    if isinstance(i, (int, float)) and 1 <= int(i) <= len(s):
                        return SymVal.const(ord(s[int(i) - 1]))
                if name == 'char' and all(a.is_const and isinstance(a.const_value, (int, float)) for a in args):
                    try:
                        return SymVal.const(''.join(chr(int(a.const_value)) for a in args))
                    except (ValueError, OverflowError):
                        pass
                if name == 'sub' and len(args) >= 2:
                    if args[0].is_const and isinstance(args[0].const_value, str) and args[1].is_const:
                        s = args[0].const_value
                        i = int(args[1].const_value)
                        j = int(args[2].const_value) if len(args) > 2 and args[2].is_const else -1
                        if i < 0: i = max(len(s) + i + 1, 1)
                        if j < 0: j = len(s) + j + 1
                        return SymVal.const(s[i-1:j])
                if name == 'len' and len(args) >= 1 and args[0].is_const and isinstance(args[0].const_value, str):
                    return SymVal.const(len(args[0].const_value))
                if name == 'rep' and len(args) >= 2 and args[0].is_const and args[1].is_const:
                    return SymVal.const(str(args[0].const_value) * int(args[1].const_value))
                if name == 'reverse' and len(args) >= 1 and args[0].is_const and isinstance(args[0].const_value, str):
                    return SymVal.const(args[0].const_value[::-1])
                if name == 'lower' and len(args) >= 1 and args[0].is_const and isinstance(args[0].const_value, str):
                    return SymVal.const(args[0].const_value.lower())
                if name == 'upper' and len(args) >= 1 and args[0].is_const and isinstance(args[0].const_value, str):
                    return SymVal.const(args[0].const_value.upper())

            if tbl.kind == SymKind.SYM and tbl.data == 'math':
                import math as _m
                one_arg_fns = {'abs': abs, 'ceil': _m.ceil, 'floor': _m.floor, 'sqrt': _m.sqrt,
                               'sin': _m.sin, 'cos': _m.cos, 'tan': _m.tan, 'exp': _m.exp, 'log': _m.log}
                if name in one_arg_fns and len(args) >= 1 and args[0].is_const and isinstance(args[0].const_value, (int, float)):
                    try:
                        return SymVal.const(one_arg_fns[name](args[0].const_value))
                    except (ValueError, OverflowError):
                        pass

            if tbl.kind == SymKind.SYM and tbl.data in ('bit32', 'bit'):
                if name == 'band' and all(a.is_const and isinstance(a.const_value, (int, float)) for a in args):
                    r = 0xFFFFFFFF
                    for a in args:
                        r &= int(a.const_value) & 0xFFFFFFFF
                    return SymVal.const(r)
                if name == 'bor' and all(a.is_const and isinstance(a.const_value, (int, float)) for a in args):
                    r = 0
                    for a in args:
                        r |= int(a.const_value) & 0xFFFFFFFF
                    return SymVal.const(r)
                if name == 'bxor' and all(a.is_const and isinstance(a.const_value, (int, float)) for a in args):
                    r = 0
                    for a in args:
                        r ^= int(a.const_value) & 0xFFFFFFFF
                    return SymVal.const(r)
                if name == 'bnot' and len(args) >= 1 and args[0].is_const and isinstance(args[0].const_value, (int, float)):
                    return SymVal.const((~int(args[0].const_value)) & 0xFFFFFFFF)
                if name == 'lshift' and len(args) >= 2 and args[0].is_const and args[1].is_const:
                    return SymVal.const((int(args[0].const_value) << int(args[1].const_value)) & 0xFFFFFFFF)
                if name == 'rshift' and len(args) >= 2 and args[0].is_const and args[1].is_const:
                    return SymVal.const((int(args[0].const_value) & 0xFFFFFFFF) >> int(args[1].const_value))

        if fn.kind == SymKind.SYM:
            if fn.data == 'type' and len(args) >= 1 and args[0].is_const:
                v = args[0].const_value
                if v is None: return SymVal.const("nil")
                if isinstance(v, bool): return SymVal.const("boolean")
                if isinstance(v, (int, float)): return SymVal.const("number")
                if isinstance(v, str): return SymVal.const("string")
            if fn.data == 'tostring' and len(args) >= 1 and args[0].is_const:
                v = args[0].const_value
                if isinstance(v, (int, float, str, bool)) or v is None:
                    if v is None: return SymVal.const("nil")
                    if isinstance(v, bool): return SymVal.const("true" if v else "false")
                    if isinstance(v, float):
                        if v == int(v): return SymVal.const(str(int(v)))
                        return SymVal.const(str(v))
                    return SymVal.const(str(v))
            if fn.data == 'tonumber' and len(args) >= 1 and args[0].is_const:
                v = args[0].const_value
                if isinstance(v, (int, float)):
                    return SymVal.const(v)
                if isinstance(v, str):
                    try:
                        return SymVal.const(int(v) if '.' not in v else float(v))
                    except ValueError:
                        return SymVal.const(None)
        return None

    def _match_opcode_pattern(self) -> Optional[str]:
        has_reg_write = False
        has_reg_read = False
        has_const_read = False
        has_pc_modify = False
        has_call = len(self.calls) > 0
        has_return = len(self.returns) > 0
        has_upval_read = False
        has_upval_write = False
        has_table_write = False
        has_nil_range = False
        write_val_kinds: Set[SymKind] = set()
        write_ops: Set[str] = set()
        call_count = len(self.calls)
        write_count = len(self.writes)
        reg_write_count = 0

        for w in self.writes:
            tgt, val = w.target, w.value
            if _is_reg_write(tgt):
                has_reg_write = True
                reg_write_count += 1
                write_val_kinds.add(val.kind)
                if val.kind == SymKind.INDEX:
                    vt = val.data[0]
                    if _is_sym(vt, 'R'):
                        has_reg_read = True
                    elif _is_sym(vt, 'K'):
                        has_const_read = True
                    elif _is_upval_table(vt):
                        has_upval_read = True
                elif val.kind == SymKind.BINOP:
                    write_ops.add(val.data[0])
                    for operand in (val.data[1], val.data[2]):
                        if operand.kind == SymKind.INDEX:
                            ot = operand.data[0]
                            if _is_sym(ot, 'R'):
                                has_reg_read = True
                            elif _is_sym(ot, 'K'):
                                has_const_read = True
            elif _is_pc_write(tgt):
                has_pc_modify = True
            elif _is_table_element_write(tgt):
                has_table_write = True
                vt = tgt.data[0]
                if _is_upval_table(vt):
                    has_upval_write = True
            elif tgt.kind == SymKind.SYM and tgt.data == 'V':
                has_pc_modify = True

        if not self.writes and not self.calls and not self.returns:
            return "NOP"

        if has_return and not has_reg_write and not has_call:
            return "RETURN"

        if has_return and has_pc_modify:
            return "TFORLOOP"

        if has_pc_modify and not has_reg_write and not has_call:
            return "JMP"

        if has_pc_modify and has_reg_write and not has_call:
            if write_ops:
                return "FORPREP" if '-' in write_ops else "FORLOOP"
            cmp_ops = write_ops & {'<', '<=', '>', '>=', '==', '~='}
            if cmp_ops:
                return "TEST"

        if has_pc_modify and not has_reg_write:
            for c in self.constraints:
                if c.condition.kind == SymKind.BINOP:
                    op = c.condition.data[0]
                    if op in ('<', '<=', '>', '>='):
                        return "LT"
                    if op in ('==', '~='):
                        return "EQ"
            return "TEST"

        if has_reg_write and not has_call and not has_pc_modify:
            if write_val_kinds == {SymKind.CONST}:
                for w in self.writes:
                    if _is_reg_write(w.target) and w.value.is_const:
                        v = w.value.const_value
                        if v is None:
                            return "LOADNIL"
                        if isinstance(v, bool):
                            return "LOADBOOL"
                return "LOADK"

            if SymKind.BINOP in write_val_kinds:
                op_map = {'+': 'ADD', '-': 'SUB', '*': 'MUL', '/': 'DIV',
                          '%': 'MOD', '^': 'POW', '//': 'IDIV',
                          '&': 'BAND', '|': 'BOR', '~': 'BXOR',
                          '<<': 'SHL', '>>': 'SHR', '..': 'CONCAT',
                          '<': 'LT', '<=': 'LE', '>': 'GT', '>=': 'GE',
                          '==': 'EQ_BOOL', '~=': 'NE_BOOL'}
                for op in write_ops:
                    if op in op_map:
                        return op_map[op]

            if SymKind.UNOP in write_val_kinds:
                for w in self.writes:
                    if w.value.kind == SymKind.UNOP:
                        op = w.value.data[0]
                        if op == '-': return "UNM"
                        if op == 'not': return "NOT"
                        if op == '#': return "LEN"

            if SymKind.TABLE in write_val_kinds:
                return "NEWTABLE"
            if SymKind.FUNC in write_val_kinds:
                return "CLOSURE"

            if has_reg_read and not has_const_read and SymKind.INDEX in write_val_kinds:
                if reg_write_count == 1:
                    return "MOVE"
                if reg_write_count == 2:
                    return "SELF"

            if has_const_read:
                return "LOADK"
            if has_upval_read:
                return "GETUPVAL"
            if SymKind.INDEX in write_val_kinds and has_reg_read:
                return "GETTABLE"
            if SymKind.FIELD in write_val_kinds:
                return "GETFIELD"

        if has_table_write and not has_reg_write and not has_call:
            if has_upval_write:
                return "SETUPVAL"
            return "SETTABLE"

        if has_call and has_reg_write:
            if call_count == 1 and reg_write_count >= 1:
                return "CALL"
            return "CALL"
        if has_call and not has_reg_write:
            if has_return:
                return "TAILCALL"
            return "CALL_VOID"

        if has_reg_write:
            return "MOVE"

        return None

    def _name_str(self, n: ast.Expr) -> str:
        if isinstance(n, ast.Name): return n.name
        if isinstance(n, ast.Field): return self._name_str(n.table) + '.' + n.name
        return "?"


class _StepLimit(Exception):
    pass


def _is_sym(val: SymVal, name: str) -> bool:
    return val.kind == SymKind.SYM and val.data == name


def _is_reg_write(tgt: SymVal) -> bool:
    if tgt.kind == SymKind.INDEX:
        tbl = tgt.data[0]
        if _is_sym(tbl, 'R') or _is_sym(tbl, 'p'):
            return True
    return False


def _is_pc_write(tgt: SymVal) -> bool:
    if tgt.kind == SymKind.SYM and tgt.data in ('PC', 'V', 'pc'):
        return True
    return False


def _is_upval_table(val: SymVal) -> bool:
    if val.kind == SymKind.SYM and val.data in ('U', 'I', 'upvals'):
        return True
    if val.kind == SymKind.INDEX:
        tbl = val.data[0]
        if _is_sym(tbl, 'I') or _is_sym(tbl, 'U'):
            return True
    return False


def _is_table_element_write(tgt: SymVal) -> bool:
    if tgt.kind == SymKind.INDEX:
        tbl = tgt.data[0]
        if not _is_sym(tbl, 'R') and not _is_sym(tbl, 'p'):
            return True
    if tgt.kind == SymKind.FIELD:
        return True
    return False


def symbolic_eval(expr: ast.Expr, env: Optional[SymEnvironment] = None) -> SymVal:
    se = SymbolicExecutor()
    return se.analyze_expr(expr, env)


def prove_const(expr: ast.Expr, env: Optional[SymEnvironment] = None) -> Optional[Any]:
    val = symbolic_eval(expr, env)
    folded = val.try_fold()
    if folded.is_const:
        return folded.const_value
    return None
