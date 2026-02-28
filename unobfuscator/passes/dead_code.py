from __future__ import annotations
from typing import Set, Dict, List, Optional
from ..core import lua_ast as ast


class UsageCollector(ast.ASTVisitor):
    def __init__(self):
        self.used: Set[str] = set()
        self.defined: Set[str] = set()
        self.assigned: Dict[str, int] = {}
        self.read: Dict[str, int] = {}
        self._in_lhs = False

    def collect(self, tree: ast.Block):
        self.visit(tree)

    def visit_Name(self, node: ast.Name):
        if self._in_lhs:
            self.defined.add(node.name)
            self.assigned[node.name] = self.assigned.get(node.name, 0) + 1
        else:
            self.used.add(node.name)
            self.read[node.name] = self.read.get(node.name, 0) + 1

    def visit_LocalAssign(self, node: ast.LocalAssign):
        for v in node.values:
            self.visit(v)
        for nm in node.names:
            self.defined.add(nm)
            self.assigned[nm] = self.assigned.get(nm, 0) + 1

    def visit_Assign(self, node: ast.Assign):
        for v in node.values:
            self.visit(v)
        old = self._in_lhs
        self._in_lhs = True
        for t in node.targets:
            self.visit(t)
        self._in_lhs = old

    def visit_ForNumeric(self, node: ast.ForNumeric):
        self.visit(node.start)
        self.visit(node.stop)
        if node.step:
            self.visit(node.step)
        self.defined.add(node.name)
        self.assigned[node.name] = self.assigned.get(node.name, 0) + 1
        self.visit(node.body)

    def visit_ForGeneric(self, node: ast.ForGeneric):
        for it in node.iterators:
            self.visit(it)
        for nm in node.names:
            self.defined.add(nm)
            self.assigned[nm] = self.assigned.get(nm, 0) + 1
        self.visit(node.body)

    def visit_FunctionDecl(self, node: ast.FunctionDecl):
        if node.is_local and isinstance(node.name, ast.Name):
            self.defined.add(node.name.name)
            self.assigned[node.name.name] = self.assigned.get(node.name.name, 0) + 1
        elif isinstance(node.name, ast.Name):
            self.defined.add(node.name.name)
            self.assigned[node.name.name] = self.assigned.get(node.name.name, 0) + 1
        if node.func:
            self.visit(node.func.body)


class DeadCodeEliminator(ast.ASTTransformer):
    def __init__(self):
        self.changes = 0
        self._used_vars: Set[str] = set()
        self._side_effect_fns: Set[str] = {'print', 'error', 'warn', 'assert',
                                            'rawset', 'rawget', 'setmetatable',
                                            'pcall', 'xpcall', 'coroutine',
                                            'io', 'os', 'debug', 'require',
                                            'loadstring', 'load', 'dofile',
                                            'collectgarbage', 'setfenv',
                                            'module', 'unpack', 'next',
                                            'game', 'workspace', 'script',
                                            'Instance', 'wait', 'spawn',
                                            'delay', 'tick', 'time'}

    def eliminate(self, tree: ast.Block) -> ast.Block:
        self.changes = 0
        self._collect_usage(tree)
        return self.transform(tree)

    def _collect_usage(self, tree: ast.Block):
        uc = UsageCollector()
        uc.collect(tree)
        self._used_vars = uc.used

    def transform_Block(self, node: ast.Block) -> ast.Block:
        new_stmts = []
        reached_return = False
        for stmt in node.stmts:
            if reached_return:
                self.changes += 1
                continue
            s = self.transform(stmt)
            if self._is_dead(s):
                self.changes += 1
                continue
            new_stmts.append(s)
            if isinstance(s, ast.Return):
                reached_return = True
        return ast.Block(stmts=new_stmts, loc=node.loc)

    def transform_If(self, node: ast.If) -> ast.Stmt:
        new_tests = []
        new_bodies = []
        for i in range(len(node.tests)):
            test = self.transform(node.tests[i])
            body = self.transform(node.bodies[i])
            cv = _const_val(test)
            if cv is not None:
                if not _truthy(cv):
                    self.changes += 1
                    continue
                else:
                    if not new_tests:
                        self.changes += 1
                        return ast.Do(body=body, loc=node.loc)
                    new_tests.append(test)
                    new_bodies.append(body)
                    return ast.If(tests=new_tests, bodies=new_bodies, else_body=None, loc=node.loc)
            new_tests.append(test)
            new_bodies.append(body)
        else_body = self.transform(node.else_body) if node.else_body else None
        if not new_tests:
            if else_body and else_body.stmts:
                self.changes += 1
                return ast.Do(body=else_body, loc=node.loc)
            self.changes += 1
            return ast.Do(body=ast.Block(stmts=[]), loc=node.loc)
        return ast.If(tests=new_tests, bodies=new_bodies, else_body=else_body, loc=node.loc)

    def transform_While(self, node: ast.While) -> ast.Stmt:
        cond = self.transform(node.condition)
        body = self.transform(node.body)
        cv = _const_val(cond)
        if cv is not None and not _truthy(cv):
            self.changes += 1
            return ast.Do(body=ast.Block(stmts=[]), loc=node.loc)
        return ast.While(condition=cond, body=body, loc=node.loc)

    def _is_dead(self, stmt: ast.Stmt) -> bool:
        if isinstance(stmt, ast.LocalAssign):
            all_unused = all(nm not in self._used_vars for nm in stmt.names)
            if all_unused and not any(self._has_side_effects(v) for v in stmt.values):
                return True
        if isinstance(stmt, ast.Do):
            if isinstance(stmt.body, ast.Block) and not stmt.body.stmts:
                return True
        if isinstance(stmt, ast.ExprStmt):
            if not self._has_side_effects(stmt.expr):
                return True
        return False

    def _has_side_effects(self, expr: ast.Expr) -> bool:
        if isinstance(expr, (ast.Nil, ast.Bool, ast.Number, ast.String, ast.Name, ast.Vararg)):
            return False
        if isinstance(expr, ast.BinOp):
            return self._has_side_effects(expr.left) or self._has_side_effects(expr.right)
        if isinstance(expr, ast.UnOp):
            return self._has_side_effects(expr.operand)
        if isinstance(expr, ast.Concat):
            return any(self._has_side_effects(v) for v in expr.values)
        if isinstance(expr, ast.TableConstructor):
            for f in expr.fields:
                if f.key and self._has_side_effects(f.key):
                    return True
                if self._has_side_effects(f.value):
                    return True
            return False
        if isinstance(expr, ast.FunctionExpr):
            return False
        if isinstance(expr, ast.Index):
            return True
        if isinstance(expr, ast.Field):
            return True
        if isinstance(expr, (ast.Call, ast.MethodCall)):
            return True
        return True


def _const_val(e: ast.Expr):
    if isinstance(e, ast.Nil): return None
    if isinstance(e, ast.Bool): return e.value
    if isinstance(e, ast.Number): return e.value
    if isinstance(e, ast.String): return e.value
    return None

def _truthy(v) -> bool:
    return v is not None and v is not False


def eliminate_dead_code(tree: ast.Block, iterations: int = 5) -> ast.Block:
    for _ in range(iterations):
        dce = DeadCodeEliminator()
        tree = dce.eliminate(tree)
        if dce.changes == 0:
            break
    return tree
