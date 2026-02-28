from __future__ import annotations
from typing import List, Optional, Tuple
from ..core import lua_ast as ast
from ..core.lua_parser import parse as lua_parse
from ..core.lua_emitter import emit
from ..core.sandbox import LuaSandbox, LuaError


class LoadstringUnwrapper:
    def __init__(self, sandbox: Optional[LuaSandbox] = None, max_layers: int = 50):
        self.sandbox = sandbox or LuaSandbox(op_limit=10_000_000, timeout=30.0)
        self.max_layers = max_layers
        self.layers_unwrapped = 0
        self.intermediate_sources: List[str] = []

    def unwrap(self, source: str) -> str:
        for _ in range(self.max_layers):
            tree = lua_parse(source)
            unwrapped = self._try_unwrap_ast(tree)
            if unwrapped is None:
                unwrapped = self._try_unwrap_sandbox(source)
            if unwrapped is None:
                break
            self.layers_unwrapped += 1
            self.intermediate_sources.append(unwrapped)
            source = unwrapped
        return source

    def _try_unwrap_ast(self, tree: ast.Block) -> Optional[str]:
        for pattern_fn in [
            self._pattern_loadstring_call,
            self._pattern_load_call,
            self._pattern_iife_loadstring,
            self._pattern_select_loadstring,
            self._pattern_nested_loadstring,
        ]:
            result = pattern_fn(tree)
            if result is not None:
                return result
        return None

    def _pattern_loadstring_call(self, tree: ast.Block) -> Optional[str]:
        if len(tree.stmts) != 1:
            return None
        stmt = tree.stmts[0]
        if not isinstance(stmt, ast.ExprStmt):
            return None
        call = stmt.expr
        if not isinstance(call, ast.Call):
            return None
        inner = call.func
        if isinstance(inner, ast.Call):
            if isinstance(inner.func, ast.Name) and inner.func.name in ('loadstring', 'load'):
                if len(inner.args) >= 1:
                    return self._eval_string_arg(inner.args[0], tree)
        return None

    def _pattern_load_call(self, tree: ast.Block) -> Optional[str]:
        if len(tree.stmts) != 1:
            return None
        stmt = tree.stmts[0]
        if not isinstance(stmt, ast.ExprStmt):
            return None
        call = stmt.expr
        if isinstance(call, ast.Call) and isinstance(call.func, ast.Name):
            if call.func.name in ('loadstring', 'load') and len(call.args) >= 1:
                return self._eval_string_arg(call.args[0], tree)
        return None

    def _pattern_iife_loadstring(self, tree: ast.Block) -> Optional[str]:
        if len(tree.stmts) < 1:
            return None
        stmt = tree.stmts[-1]
        if not isinstance(stmt, ast.ExprStmt):
            return None
        expr = stmt.expr
        if isinstance(expr, ast.Call) and isinstance(expr.func, ast.FunctionExpr):
            body = expr.func.body
            for s in body.stmts:
                inner_src = self._find_loadstring_in_stmt(s)
                if inner_src is not None:
                    return inner_src
            full_src = emit(tree)
            return self._try_sandbox_intercept(full_src)
        return None

    def _pattern_select_loadstring(self, tree: ast.Block) -> Optional[str]:
        if len(tree.stmts) != 1:
            return None
        stmt = tree.stmts[0]
        if not isinstance(stmt, ast.ExprStmt):
            return None
        expr = stmt.expr
        if isinstance(expr, ast.Call) and isinstance(expr.func, ast.Name):
            if expr.func.name == 'select':
                for arg in expr.args:
                    if isinstance(arg, ast.Call):
                        if isinstance(arg.func, ast.Name) and arg.func.name in ('loadstring', 'load'):
                            if len(arg.args) >= 1:
                                return self._eval_string_arg(arg.args[0], tree)
        return None

    def _pattern_nested_loadstring(self, tree: ast.Block) -> Optional[str]:
        for node in _walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Call):
                inner = node.func
                if isinstance(inner.func, ast.Name) and inner.func.name in ('loadstring', 'load'):
                    if len(inner.args) >= 1:
                        result = self._eval_string_arg(inner.args[0], tree)
                        if result is not None:
                            return result
        return None

    def _find_loadstring_in_stmt(self, stmt: ast.Stmt) -> Optional[str]:
        for node in _walk(stmt):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.name in ('loadstring', 'load'):
                    if len(node.args) >= 1 and isinstance(node.args[0], ast.String):
                        return node.args[0].value
        return None

    def _eval_string_arg(self, expr: ast.Expr, tree: ast.Block) -> Optional[str]:
        if isinstance(expr, ast.String):
            return expr.value
        src = emit(tree)
        return self._try_sandbox_intercept(src)

    def _try_unwrap_sandbox(self, source: str) -> Optional[str]:
        return self._try_sandbox_intercept(source)

    def _try_sandbox_intercept(self, source: str) -> Optional[str]:
        self.sandbox.intercepted_loads.clear()
        try:
            self.sandbox.execute(source)
        except LuaError:
            pass
        if self.sandbox.intercepted_loads:
            longest = max(self.sandbox.intercepted_loads, key=len)
            if len(longest) > 10:
                return longest
        return None


class MultiLayerUnwrapper:
    def __init__(self, sandbox: Optional[LuaSandbox] = None, max_layers: int = 50):
        self.sandbox = sandbox or LuaSandbox(op_limit=10_000_000, timeout=30.0)
        self.max_layers = max_layers
        self.all_layers: List[str] = []

    def unwrap(self, source: str) -> str:
        seen = {source}
        for _ in range(self.max_layers):
            self.sandbox.intercepted_loads.clear()
            try:
                self.sandbox.execute(source)
            except LuaError:
                pass
            if not self.sandbox.intercepted_loads:
                break
            longest = max(self.sandbox.intercepted_loads, key=len)
            if len(longest) <= 10 or longest in seen:
                break
            seen.add(longest)
            self.all_layers.append(longest)
            source = longest
        return source


def _walk(node: ast.Node):
    yield node
    for child in node.children():
        yield from _walk(child)


def unwrap_loadstrings(source: str, sandbox: Optional[LuaSandbox] = None, max_layers: int = 50) -> str:
    uw = LoadstringUnwrapper(sandbox, max_layers)
    result = uw.unwrap(source)
    if uw.layers_unwrapped == 0:
        ml = MultiLayerUnwrapper(sandbox or LuaSandbox(op_limit=10_000_000, timeout=30.0), max_layers)
        result = ml.unwrap(source)
    return result
