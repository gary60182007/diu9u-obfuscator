from __future__ import annotations
from typing import Set, Dict, List, Optional, Tuple
from ..core import lua_ast as ast


class JunkPatternDetector:
    def __init__(self):
        self.patterns_found: List[str] = []

    def is_junk(self, stmt: ast.Stmt) -> bool:
        for check in [
            self._is_noop_assignment,
            self._is_dead_if,
            self._is_empty_block,
            self._is_unused_local_function,
            self._is_opaque_predicate_if,
            self._is_junk_math,
            self._is_anti_deobf_trap,
            self._is_honeypot,
            self._is_dead_loop,
            self._is_unreachable_code,
        ]:
            result = check(stmt)
            if result:
                return True
        return False

    def _is_noop_assignment(self, stmt: ast.Stmt) -> bool:
        if isinstance(stmt, ast.Assign) and len(stmt.targets) == len(stmt.values):
            for tgt, val in zip(stmt.targets, stmt.values):
                if isinstance(tgt, ast.Name) and isinstance(val, ast.Name):
                    if tgt.name == val.name:
                        self.patterns_found.append("noop_self_assign")
                        return True
        if isinstance(stmt, ast.LocalAssign) and len(stmt.names) == 1 and len(stmt.values) == 1:
            if isinstance(stmt.values[0], ast.Nil):
                self.patterns_found.append("local_nil_assign")
                return True
        return False

    def _is_dead_if(self, stmt: ast.Stmt) -> bool:
        if isinstance(stmt, ast.If) and len(stmt.tests) == 1:
            test = stmt.tests[0]
            cv = _const_val(test)
            if cv is not None and not _truthy(cv):
                self.patterns_found.append("dead_if_false")
                return True
            if isinstance(test, ast.BinOp) and test.op in ('==', '~=', '<', '>', '<=', '>='):
                lv = _const_val(test.left)
                rv = _const_val(test.right)
                if lv is not None and rv is not None:
                    result = _eval_comparison(test.op, lv, rv)
                    if result is False:
                        self.patterns_found.append("dead_if_const_compare")
                        return True
        return False

    def _is_empty_block(self, stmt: ast.Stmt) -> bool:
        if isinstance(stmt, ast.Do):
            if isinstance(stmt.body, ast.Block) and not stmt.body.stmts:
                self.patterns_found.append("empty_do_block")
                return True
        if isinstance(stmt, ast.While):
            cv = _const_val(stmt.condition)
            if cv is not None and not _truthy(cv):
                self.patterns_found.append("dead_while")
                return True
        return False

    def _is_unused_local_function(self, stmt: ast.Stmt) -> bool:
        return False

    def _is_opaque_predicate_if(self, stmt: ast.Stmt) -> bool:
        if not isinstance(stmt, ast.If):
            return False
        for test in stmt.tests:
            if self._is_opaque_predicate(test):
                self.patterns_found.append("opaque_predicate")
                return True
        return False

    def _is_opaque_predicate(self, expr: ast.Expr) -> bool:
        if isinstance(expr, ast.BinOp):
            if expr.op == '==' and isinstance(expr.left, ast.BinOp) and isinstance(expr.right, ast.Number):
                if expr.left.op == '%' and isinstance(expr.left.right, ast.Number):
                    mod = expr.left.right.value
                    target = expr.right.value
                    if isinstance(mod, (int, float)) and isinstance(target, (int, float)):
                        if int(mod) == 2 and int(target) not in (0, 1):
                            return True
                        if int(mod) == 1 and int(target) != 0:
                            return True
            if expr.op == '>' and isinstance(expr.left, ast.Call):
                if isinstance(expr.left.func, ast.Name) and expr.left.func.name == 'type':
                    return True
            if expr.op in ('==', '~='):
                if isinstance(expr.left, ast.Call) and isinstance(expr.left.func, ast.Name):
                    if expr.left.func.name == 'type' and isinstance(expr.right, ast.String):
                        if expr.right.value in ('userdata', 'thread'):
                            return True
        if isinstance(expr, ast.Call) and isinstance(expr.func, ast.Name):
            if expr.func.name in ('pcall', 'xpcall') and len(expr.args) >= 1:
                if isinstance(expr.args[0], ast.FunctionExpr):
                    body = expr.args[0].body
                    if body.stmts and isinstance(body.stmts[0], ast.ExprStmt):
                        inner = body.stmts[0].expr
                        if isinstance(inner, ast.Call) and isinstance(inner.func, ast.Name):
                            if inner.func.name == 'error':
                                return True
        return False

    def _is_junk_math(self, stmt: ast.Stmt) -> bool:
        if isinstance(stmt, ast.LocalAssign) and len(stmt.values) == 1:
            val = stmt.values[0]
            if isinstance(val, ast.BinOp) and _all_const_arithmetic(val):
                self.patterns_found.append("junk_const_math")
                return True
        if isinstance(stmt, ast.ExprStmt) and isinstance(stmt.expr, ast.Name):
            self.patterns_found.append("standalone_name")
            return True
        return False

    def _is_anti_deobf_trap(self, stmt: ast.Stmt) -> bool:
        if isinstance(stmt, ast.If):
            for test in stmt.tests:
                if self._is_debug_check(test):
                    self.patterns_found.append("anti_deobf_debug_check")
                    return True
                if self._is_timing_check(test):
                    self.patterns_found.append("anti_deobf_timing")
                    return True
        return False

    def _is_debug_check(self, expr: ast.Expr) -> bool:
        for node in _walk(expr):
            if isinstance(node, ast.Field):
                if isinstance(node.table, ast.Name) and node.table.name == 'debug':
                    return True
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Field):
                if isinstance(node.func.table, ast.Name) and node.func.table.name == 'debug':
                    return True
        return False

    def _is_timing_check(self, expr: ast.Expr) -> bool:
        for node in _walk(expr):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.name in ('os.clock', 'tick', 'os.time'):
                    return True
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Field):
                if isinstance(node.func.table, ast.Name) and node.func.table.name == 'os':
                    if node.func.name in ('clock', 'time'):
                        return True
        return False

    def _is_honeypot(self, stmt: ast.Stmt) -> bool:
        if isinstance(stmt, ast.If):
            for body in stmt.bodies:
                if isinstance(body, ast.Block):
                    for s in body.stmts:
                        if isinstance(s, ast.ExprStmt) and isinstance(s.expr, ast.Call):
                            if isinstance(s.expr.func, ast.Name) and s.expr.func.name == 'error':
                                if len(s.expr.args) >= 1 and isinstance(s.expr.args[0], ast.String):
                                    msg = s.expr.args[0].value.lower()
                                    if any(kw in msg for kw in ['deobfusc', 'tamper', 'modif', 'cheat', 'hack', 'detect']):
                                        self.patterns_found.append("honeypot")
                                        return True
        return False

    def _is_dead_loop(self, stmt: ast.Stmt) -> bool:
        if isinstance(stmt, ast.ForNumeric):
            sv = _const_val(stmt.start)
            ev = _const_val(stmt.stop)
            if sv is not None and ev is not None:
                step = _const_val(stmt.step) if stmt.step else 1
                if step is not None:
                    if (isinstance(step, (int, float)) and isinstance(sv, (int, float)) and
                        isinstance(ev, (int, float))):
                        if step > 0 and sv > ev:
                            self.patterns_found.append("dead_for_never_executes")
                            return True
                        if step < 0 and sv < ev:
                            self.patterns_found.append("dead_for_never_executes")
                            return True
                        if step == 0:
                            self.patterns_found.append("dead_for_zero_step")
                            return True
        return False

    def _is_unreachable_code(self, stmt: ast.Stmt) -> bool:
        return False


class JunkRemover(ast.ASTTransformer):
    def __init__(self):
        self.changes = 0
        self._detector = JunkPatternDetector()

    def remove(self, tree: ast.Block) -> ast.Block:
        self.changes = 0
        return self.transform(tree)

    def transform_Block(self, node: ast.Block) -> ast.Block:
        new_stmts = []
        for stmt in node.stmts:
            s = self.transform(stmt)
            if self._detector.is_junk(s):
                self.changes += 1
                continue
            new_stmts.append(s)
        return ast.Block(stmts=new_stmts, loc=node.loc)

    def transform_If(self, node: ast.If) -> ast.Stmt:
        new_tests = []
        new_bodies = []
        for i in range(len(node.tests)):
            test = self.transform(node.tests[i])
            body = self.transform(node.bodies[i])
            if self._detector._is_opaque_predicate(test):
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


def _walk(node: ast.Node):
    yield node
    for child in node.children():
        yield from _walk(child)

def _const_val(e: ast.Expr):
    if isinstance(e, ast.Nil): return None
    if isinstance(e, ast.Bool): return e.value
    if isinstance(e, ast.Number): return e.value
    if isinstance(e, ast.String): return e.value
    return None

def _truthy(v) -> bool:
    return v is not None and v is not False

def _eval_comparison(op, a, b):
    try:
        if op == '==': return a == b
        if op == '~=': return a != b
        if op == '<' and type(a) == type(b): return a < b
        if op == '>' and type(a) == type(b): return a > b
        if op == '<=' and type(a) == type(b): return a <= b
        if op == '>=' and type(a) == type(b): return a >= b
    except Exception:
        pass
    return None

def _all_const_arithmetic(expr: ast.Expr) -> bool:
    if isinstance(expr, (ast.Number, ast.String, ast.Bool, ast.Nil)):
        return True
    if isinstance(expr, ast.BinOp):
        return _all_const_arithmetic(expr.left) and _all_const_arithmetic(expr.right)
    if isinstance(expr, ast.UnOp):
        return _all_const_arithmetic(expr.operand)
    return False


def remove_junk(tree: ast.Block, iterations: int = 5) -> ast.Block:
    for _ in range(iterations):
        jr = JunkRemover()
        tree = jr.remove(tree)
        if jr.changes == 0:
            break
    return tree
