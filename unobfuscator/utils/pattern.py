from __future__ import annotations
from typing import List, Optional, Dict, Tuple, Any, Callable
from dataclasses import dataclass, field
from ..core import lua_ast as ast


@dataclass
class PatternVar:
    name: str
    constraint: Optional[Callable[[ast.Node], bool]] = None


@dataclass
class MatchResult:
    matched: bool = False
    bindings: Dict[str, ast.Node] = field(default_factory=dict)

    @staticmethod
    def fail() -> MatchResult:
        return MatchResult(matched=False)

    @staticmethod
    def ok(bindings: Optional[Dict[str, ast.Node]] = None) -> MatchResult:
        return MatchResult(matched=True, bindings=bindings or {})

    def merge(self, other: MatchResult) -> MatchResult:
        if not self.matched or not other.matched:
            return MatchResult.fail()
        merged = dict(self.bindings)
        for k, v in other.bindings.items():
            if k in merged:
                if not _nodes_equal(merged[k], v):
                    return MatchResult.fail()
            else:
                merged[k] = v
        return MatchResult(matched=True, bindings=merged)


class PatternMatcher:
    def __init__(self):
        self._patterns: List[Tuple[str, Any, Callable]] = []

    def register(self, name: str, pattern: Any, callback: Callable):
        self._patterns.append((name, pattern, callback))

    def match_tree(self, tree: ast.Block) -> List[Tuple[str, MatchResult, ast.Node]]:
        results = []
        for node in _walk(tree):
            for pname, pattern, callback in self._patterns:
                m = self.match(pattern, node)
                if m.matched:
                    results.append((pname, m, node))
        return results

    def match(self, pattern: Any, node: ast.Node) -> MatchResult:
        if isinstance(pattern, PatternVar):
            if pattern.constraint is None or pattern.constraint(node):
                return MatchResult.ok({pattern.name: node})
            return MatchResult.fail()

        if isinstance(pattern, type):
            if isinstance(node, pattern):
                return MatchResult.ok()
            return MatchResult.fail()

        if isinstance(pattern, dict):
            return self._match_dict(pattern, node)

        if isinstance(pattern, (list, tuple)):
            if not isinstance(node, (list, tuple)):
                return MatchResult.fail()
            if len(pattern) != len(node):
                return MatchResult.fail()
            result = MatchResult.ok()
            for p, n in zip(pattern, node):
                m = self.match(p, n)
                result = result.merge(m)
                if not result.matched:
                    return result
            return result

        if pattern == node:
            return MatchResult.ok()
        return MatchResult.fail()

    def _match_dict(self, pattern: dict, node: ast.Node) -> MatchResult:
        if 'type' in pattern:
            if not isinstance(node, pattern['type']):
                return MatchResult.fail()

        result = MatchResult.ok()
        for key, val in pattern.items():
            if key == 'type':
                continue
            if key == '_bind':
                result = result.merge(MatchResult.ok({val: node}))
                continue
            node_val = getattr(node, key, None)
            if node_val is None:
                return MatchResult.fail()
            m = self.match(val, node_val)
            result = result.merge(m)
            if not result.matched:
                return result
        return result


def match_call(node: ast.Node, func_name: str, min_args: int = 0) -> Optional[List[ast.Expr]]:
    if not isinstance(node, ast.Call):
        return None
    if isinstance(node.func, ast.Name) and node.func.name == func_name:
        if len(node.args) >= min_args:
            return node.args
    return None


def match_method_call(node: ast.Node, method_name: str, min_args: int = 0) -> Optional[Tuple[ast.Expr, List[ast.Expr]]]:
    if isinstance(node, ast.MethodCall) and node.method == method_name:
        if len(node.args) >= min_args:
            return node.object, node.args
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Field):
        if node.func.name == method_name:
            if len(node.args) >= min_args:
                return node.func.table, node.args
    return None


def match_field_call(node: ast.Node, table_name: str, field_name: str, min_args: int = 0) -> Optional[List[ast.Expr]]:
    if not isinstance(node, ast.Call):
        return None
    if isinstance(node.func, ast.Field):
        if isinstance(node.func.table, ast.Name) and node.func.table.name == table_name:
            if node.func.name == field_name and len(node.args) >= min_args:
                return node.args
    return None


def match_binop(node: ast.Node, op: str) -> Optional[Tuple[ast.Expr, ast.Expr]]:
    if isinstance(node, ast.BinOp) and node.op == op:
        return node.left, node.right
    return None


def match_unop(node: ast.Node, op: str) -> Optional[ast.Expr]:
    if isinstance(node, ast.UnOp) and node.op == op:
        return node.operand
    return None


def match_local_assign(stmt: ast.Stmt) -> Optional[Tuple[List[str], List[ast.Expr]]]:
    if isinstance(stmt, ast.LocalAssign):
        return stmt.names, stmt.values
    return None


def match_assign(stmt: ast.Stmt) -> Optional[Tuple[List[ast.Expr], List[ast.Expr]]]:
    if isinstance(stmt, ast.Assign):
        return stmt.targets, stmt.values
    return None


def match_iife(node: ast.Node) -> Optional[Tuple[ast.FunctionExpr, List[ast.Expr]]]:
    if isinstance(node, ast.Call) and isinstance(node.func, ast.FunctionExpr):
        return node.func, node.args
    return None


def match_loadstring(node: ast.Node) -> Optional[ast.Expr]:
    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name) and node.func.name in ('loadstring', 'load'):
            if len(node.args) >= 1:
                return node.args[0]
        if isinstance(node.func, ast.Call):
            inner = match_loadstring(node.func)
            if inner is not None:
                return inner
    return None


def match_string_concat(node: ast.Node) -> Optional[List[ast.Expr]]:
    if isinstance(node, ast.Concat):
        return node.values
    if isinstance(node, ast.BinOp) and node.op == '..':
        parts = []
        _collect_concat_parts(node, parts)
        return parts
    return None


def _collect_concat_parts(node: ast.Expr, parts: List[ast.Expr]):
    if isinstance(node, ast.BinOp) and node.op == '..':
        _collect_concat_parts(node.left, parts)
        _collect_concat_parts(node.right, parts)
    else:
        parts.append(node)


def match_table_constructor(node: ast.Node) -> Optional[List[ast.TableField]]:
    if isinstance(node, ast.TableConstructor):
        return node.fields
    return None


def match_for_numeric(stmt: ast.Stmt) -> Optional[Tuple[str, ast.Expr, ast.Expr, Optional[ast.Expr], ast.Block]]:
    if isinstance(stmt, ast.ForNumeric):
        return stmt.name, stmt.start, stmt.stop, stmt.step, stmt.body
    return None


def match_while_true(stmt: ast.Stmt) -> Optional[ast.Block]:
    if isinstance(stmt, ast.While):
        if isinstance(stmt.condition, ast.Bool) and stmt.condition.value is True:
            return stmt.body
        if isinstance(stmt.condition, ast.Number) and stmt.condition.value != 0:
            return stmt.body
    return None


def find_pattern(tree: ast.Block, predicate: Callable[[ast.Node], bool]) -> List[ast.Node]:
    results = []
    for node in _walk(tree):
        if predicate(node):
            results.append(node)
    return results


def find_calls_to(tree: ast.Block, func_name: str) -> List[ast.Call]:
    results = []
    for node in _walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.name == func_name:
                results.append(node)
    return results


def find_string_literals(tree: ast.Block) -> List[ast.String]:
    return [n for n in _walk(tree) if isinstance(n, ast.String)]


def find_number_literals(tree: ast.Block) -> List[ast.Number]:
    return [n for n in _walk(tree) if isinstance(n, ast.Number)]


def find_function_decls(tree: ast.Block) -> List[ast.FunctionDecl]:
    return [n for n in _walk(tree) if isinstance(n, ast.FunctionDecl)]


def count_nodes(tree: ast.Block) -> int:
    return sum(1 for _ in _walk(tree))


def _nodes_equal(a: ast.Node, b: ast.Node) -> bool:
    if type(a) != type(b):
        return False
    if isinstance(a, ast.Name):
        return a.name == b.name
    if isinstance(a, ast.Number):
        return a.value == b.value
    if isinstance(a, ast.String):
        return a.value == b.value
    if isinstance(a, ast.Bool):
        return a.value == b.value
    if isinstance(a, ast.Nil):
        return True
    return False


def _walk(node):
    if node is None:
        return
    yield node
    if isinstance(node, ast.Node):
        for child in node.children():
            yield from _walk(child)
    elif isinstance(node, list):
        for item in node:
            yield from _walk(item)
