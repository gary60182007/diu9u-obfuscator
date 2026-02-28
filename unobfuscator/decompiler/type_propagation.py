from __future__ import annotations
from typing import Dict, Set, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum, auto
from ..core import lua_ast as ast


class LuaType(Enum):
    NIL = auto()
    BOOLEAN = auto()
    NUMBER = auto()
    STRING = auto()
    TABLE = auto()
    FUNCTION = auto()
    USERDATA = auto()
    THREAD = auto()
    ANY = auto()

    def __repr__(self):
        return self.name.lower()


@dataclass(frozen=True)
class TypeSet:
    types: frozenset

    @staticmethod
    def single(t: LuaType) -> TypeSet:
        return TypeSet(frozenset({t}))

    @staticmethod
    def any() -> TypeSet:
        return TypeSet(frozenset({LuaType.ANY}))

    @staticmethod
    def empty() -> TypeSet:
        return TypeSet(frozenset())

    @staticmethod
    def of(*ts: LuaType) -> TypeSet:
        return TypeSet(frozenset(ts))

    def union(self, other: TypeSet) -> TypeSet:
        if LuaType.ANY in self.types or LuaType.ANY in other.types:
            return TypeSet.any()
        return TypeSet(self.types | other.types)

    def intersect(self, other: TypeSet) -> TypeSet:
        if LuaType.ANY in self.types:
            return other
        if LuaType.ANY in other.types:
            return self
        return TypeSet(self.types & other.types)

    @property
    def is_single(self) -> bool:
        return len(self.types) == 1 and LuaType.ANY not in self.types

    @property
    def single_type(self) -> Optional[LuaType]:
        if self.is_single:
            return next(iter(self.types))
        return None

    @property
    def is_any(self) -> bool:
        return LuaType.ANY in self.types

    @property
    def is_number(self) -> bool:
        return self.types == frozenset({LuaType.NUMBER})

    @property
    def is_string(self) -> bool:
        return self.types == frozenset({LuaType.STRING})

    @property
    def is_table(self) -> bool:
        return self.types == frozenset({LuaType.TABLE})

    @property
    def is_function(self) -> bool:
        return self.types == frozenset({LuaType.FUNCTION})

    @property
    def is_boolean(self) -> bool:
        return self.types == frozenset({LuaType.BOOLEAN})

    @property
    def is_nil(self) -> bool:
        return self.types == frozenset({LuaType.NIL})

    def __repr__(self):
        if self.is_any:
            return "any"
        return "|".join(t.name.lower() for t in sorted(self.types, key=lambda x: x.value))


@dataclass
class TypeInfo:
    var_types: Dict[str, TypeSet] = field(default_factory=dict)
    expr_types: Dict[int, TypeSet] = field(default_factory=dict)
    call_return_types: Dict[str, TypeSet] = field(default_factory=dict)

    def get(self, name: str) -> TypeSet:
        return self.var_types.get(name, TypeSet.any())

    def set(self, name: str, ts: TypeSet):
        if name in self.var_types:
            self.var_types[name] = self.var_types[name].union(ts)
        else:
            self.var_types[name] = ts


class TypePropagator(ast.ASTVisitor):
    def __init__(self):
        self.info = TypeInfo()
        self._max_iterations = 20

    def propagate(self, tree: ast.Block) -> TypeInfo:
        for _ in range(self._max_iterations):
            old = dict(self.info.var_types)
            self.visit(tree)
            if self.info.var_types == old:
                break
        return self.info

    def visit_LocalAssign(self, node: ast.LocalAssign):
        for i, name in enumerate(node.names):
            if i < len(node.values):
                ts = self._infer_expr(node.values[i])
            else:
                ts = TypeSet.single(LuaType.NIL)
            self.info.set(name, ts)
        for v in node.values:
            self.visit(v)

    def visit_Assign(self, node: ast.Assign):
        for i, tgt in enumerate(node.targets):
            if isinstance(tgt, ast.Name) and i < len(node.values):
                ts = self._infer_expr(node.values[i])
                self.info.set(tgt.name, ts)
        for v in node.values:
            self.visit(v)

    def visit_ForNumeric(self, node: ast.ForNumeric):
        self.info.set(node.name, TypeSet.single(LuaType.NUMBER))
        self.visit(node.body)

    def visit_ForGeneric(self, node: ast.ForGeneric):
        for nm in node.names:
            self.info.set(nm, TypeSet.any())
        for it in node.iterators:
            self.visit(it)
        self.visit(node.body)

    def visit_FunctionDecl(self, node: ast.FunctionDecl):
        if isinstance(node.name, ast.Name):
            self.info.set(node.name.name, TypeSet.single(LuaType.FUNCTION))
        for p in node.params:
            self.info.set(p, TypeSet.any())
        self.visit(node.body)

    def _infer_expr(self, expr: ast.Expr) -> TypeSet:
        if isinstance(expr, ast.Nil):
            return TypeSet.single(LuaType.NIL)
        if isinstance(expr, ast.Bool):
            return TypeSet.single(LuaType.BOOLEAN)
        if isinstance(expr, ast.Number):
            return TypeSet.single(LuaType.NUMBER)
        if isinstance(expr, ast.String):
            return TypeSet.single(LuaType.STRING)
        if isinstance(expr, ast.Name):
            return self.info.get(expr.name)
        if isinstance(expr, ast.TableConstructor):
            return TypeSet.single(LuaType.TABLE)
        if isinstance(expr, ast.FunctionExpr):
            return TypeSet.single(LuaType.FUNCTION)
        if isinstance(expr, ast.BinOp):
            return self._infer_binop(expr)
        if isinstance(expr, ast.UnOp):
            return self._infer_unop(expr)
        if isinstance(expr, ast.Concat):
            return TypeSet.single(LuaType.STRING)
        if isinstance(expr, ast.Call):
            return self._infer_call(expr)
        if isinstance(expr, ast.MethodCall):
            return TypeSet.any()
        if isinstance(expr, (ast.Index, ast.Field)):
            return TypeSet.any()
        return TypeSet.any()

    def _infer_binop(self, expr: ast.BinOp) -> TypeSet:
        if expr.op in ('+', '-', '*', '/', '%', '^', '//'):
            return TypeSet.single(LuaType.NUMBER)
        if expr.op in ('==', '~=', '<', '>', '<=', '>='):
            return TypeSet.single(LuaType.BOOLEAN)
        if expr.op == '..':
            return TypeSet.single(LuaType.STRING)
        if expr.op in ('&', '|', '~', '<<', '>>'):
            return TypeSet.single(LuaType.NUMBER)
        if expr.op == 'and':
            lt = self._infer_expr(expr.left)
            rt = self._infer_expr(expr.right)
            return lt.union(rt)
        if expr.op == 'or':
            lt = self._infer_expr(expr.left)
            rt = self._infer_expr(expr.right)
            return lt.union(rt)
        return TypeSet.any()

    def _infer_unop(self, expr: ast.UnOp) -> TypeSet:
        if expr.op == '-':
            return TypeSet.single(LuaType.NUMBER)
        if expr.op == '#':
            return TypeSet.single(LuaType.NUMBER)
        if expr.op == 'not':
            return TypeSet.single(LuaType.BOOLEAN)
        if expr.op == '~':
            return TypeSet.single(LuaType.NUMBER)
        return TypeSet.any()

    def _infer_call(self, expr: ast.Call) -> TypeSet:
        if isinstance(expr.func, ast.Name):
            name = expr.func.name
            known = {
                'type': TypeSet.single(LuaType.STRING),
                'tostring': TypeSet.single(LuaType.STRING),
                'tonumber': TypeSet.of(LuaType.NUMBER, LuaType.NIL),
                'pairs': TypeSet.single(LuaType.FUNCTION),
                'ipairs': TypeSet.single(LuaType.FUNCTION),
                'next': TypeSet.any(),
                'select': TypeSet.any(),
                'pcall': TypeSet.single(LuaType.BOOLEAN),
                'xpcall': TypeSet.single(LuaType.BOOLEAN),
                'setmetatable': TypeSet.single(LuaType.TABLE),
                'getmetatable': TypeSet.of(LuaType.TABLE, LuaType.NIL),
                'rawget': TypeSet.any(),
                'rawset': TypeSet.single(LuaType.TABLE),
                'rawlen': TypeSet.single(LuaType.NUMBER),
                'rawequal': TypeSet.single(LuaType.BOOLEAN),
                'require': TypeSet.any(),
                'loadstring': TypeSet.of(LuaType.FUNCTION, LuaType.NIL),
                'load': TypeSet.of(LuaType.FUNCTION, LuaType.NIL),
                'unpack': TypeSet.any(),
                'error': TypeSet.single(LuaType.NIL),
                'assert': TypeSet.any(),
            }
            if name in known:
                return known[name]
        if isinstance(expr.func, ast.Field):
            tbl = expr.func.table
            name = expr.func.name
            if isinstance(tbl, ast.Name):
                if tbl.name == 'string':
                    str_fns = {
                        'byte': TypeSet.single(LuaType.NUMBER),
                        'char': TypeSet.single(LuaType.STRING),
                        'sub': TypeSet.single(LuaType.STRING),
                        'rep': TypeSet.single(LuaType.STRING),
                        'reverse': TypeSet.single(LuaType.STRING),
                        'upper': TypeSet.single(LuaType.STRING),
                        'lower': TypeSet.single(LuaType.STRING),
                        'len': TypeSet.single(LuaType.NUMBER),
                        'format': TypeSet.single(LuaType.STRING),
                        'find': TypeSet.of(LuaType.NUMBER, LuaType.NIL),
                        'match': TypeSet.of(LuaType.STRING, LuaType.NIL),
                        'gsub': TypeSet.single(LuaType.STRING),
                        'gmatch': TypeSet.single(LuaType.FUNCTION),
                        'dump': TypeSet.single(LuaType.STRING),
                    }
                    if name in str_fns:
                        return str_fns[name]
                if tbl.name == 'math':
                    math_fns = {'abs', 'ceil', 'floor', 'sqrt', 'sin', 'cos', 'tan',
                                'asin', 'acos', 'atan', 'atan2', 'exp', 'log', 'log10',
                                'max', 'min', 'fmod', 'pow', 'random', 'deg', 'rad',
                                'frexp', 'ldexp', 'modf'}
                    if name in math_fns:
                        return TypeSet.single(LuaType.NUMBER)
                    if name == 'randomseed':
                        return TypeSet.single(LuaType.NIL)
                if tbl.name == 'table':
                    table_fns = {
                        'insert': TypeSet.single(LuaType.NIL),
                        'remove': TypeSet.any(),
                        'sort': TypeSet.single(LuaType.NIL),
                        'concat': TypeSet.single(LuaType.STRING),
                        'getn': TypeSet.single(LuaType.NUMBER),
                        'maxn': TypeSet.single(LuaType.NUMBER),
                    }
                    if name in table_fns:
                        return table_fns[name]
                if tbl.name in ('bit32', 'bit'):
                    return TypeSet.single(LuaType.NUMBER)
                if tbl.name == 'os':
                    if name in ('clock', 'time', 'difftime'):
                        return TypeSet.single(LuaType.NUMBER)
                    if name == 'date':
                        return TypeSet.of(LuaType.STRING, LuaType.TABLE)
        return TypeSet.any()


class TypeAnnotator(ast.ASTTransformer):
    def __init__(self, info: TypeInfo):
        self.info = info
        self.changes = 0

    def annotate(self, tree: ast.Block) -> ast.Block:
        self.changes = 0
        return self.transform(tree)

    def transform_If(self, node: ast.If) -> ast.Stmt:
        new_tests = []
        new_bodies = []
        for i in range(len(node.tests)):
            test = self.transform(node.tests[i])
            body = self.transform(node.bodies[i])
            test = self._simplify_type_check(test)
            new_tests.append(test)
            new_bodies.append(body)
        else_body = self.transform(node.else_body) if node.else_body else None
        return ast.If(tests=new_tests, bodies=new_bodies, else_body=else_body, loc=node.loc)

    def _simplify_type_check(self, expr: ast.Expr) -> ast.Expr:
        if isinstance(expr, ast.BinOp) and expr.op in ('==', '~='):
            if isinstance(expr.left, ast.Call) and isinstance(expr.left.func, ast.Name):
                if expr.left.func.name == 'type' and isinstance(expr.right, ast.String):
                    if len(expr.left.args) == 1 and isinstance(expr.left.args[0], ast.Name):
                        var_name = expr.left.args[0].name
                        expected_type = expr.right.value
                        actual = self.info.get(var_name)
                        type_map = {
                            'nil': LuaType.NIL, 'boolean': LuaType.BOOLEAN,
                            'number': LuaType.NUMBER, 'string': LuaType.STRING,
                            'table': LuaType.TABLE, 'function': LuaType.FUNCTION,
                        }
                        if expected_type in type_map and actual.is_single:
                            actual_type = actual.single_type
                            if expr.op == '==':
                                result = actual_type == type_map[expected_type]
                                self.changes += 1
                                return ast.Bool(value=result, loc=expr.loc)
                            else:
                                result = actual_type != type_map[expected_type]
                                self.changes += 1
                                return ast.Bool(value=result, loc=expr.loc)
        return expr


def propagate_types(tree: ast.Block) -> Tuple[ast.Block, TypeInfo]:
    tp = TypePropagator()
    info = tp.propagate(tree)
    ta = TypeAnnotator(info)
    tree = ta.annotate(tree)
    return tree, info
