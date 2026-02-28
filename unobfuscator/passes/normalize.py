from __future__ import annotations
from typing import List, Optional, Set, Dict
from ..core import lua_ast as ast
from ..core.lua_emitter import emit


class Normalizer(ast.ASTTransformer):
    def __init__(self):
        self.changes = 0

    def normalize(self, tree: ast.Block) -> ast.Block:
        self.changes = 0
        result = self.transform(tree)
        return result

    def transform_BinOp(self, node: ast.BinOp) -> ast.Expr:
        node = ast.BinOp(
            op=node.op,
            left=self.transform(node.left),
            right=self.transform(node.right),
            loc=node.loc,
        )
        folded = self._try_const_fold_binop(node)
        if folded is not None:
            self.changes += 1
            return folded
        simplified = self._simplify_binop(node)
        if simplified is not node:
            self.changes += 1
            return simplified
        return node

    def transform_UnOp(self, node: ast.UnOp) -> ast.Expr:
        node = ast.UnOp(
            op=node.op,
            operand=self.transform(node.operand),
            loc=node.loc,
        )
        folded = self._try_const_fold_unop(node)
        if folded is not None:
            self.changes += 1
            return folded
        if node.op == 'not' and isinstance(node.operand, ast.UnOp) and node.operand.op == 'not':
            self.changes += 1
            return node.operand.operand
        if node.op == '-' and isinstance(node.operand, ast.UnOp) and node.operand.op == '-':
            self.changes += 1
            return node.operand.operand
        return node

    def transform_Concat(self, node: ast.Concat) -> ast.Expr:
        new_vals = [self.transform(v) for v in node.values]
        merged = []
        for v in new_vals:
            if isinstance(v, ast.Concat):
                merged.extend(v.values)
            else:
                merged.append(v)
        folded = []
        for v in merged:
            if folded and isinstance(folded[-1], ast.String) and isinstance(v, ast.String):
                folded[-1] = ast.String(value=folded[-1].value + v.value, raw='', loc=folded[-1].loc)
                self.changes += 1
            elif isinstance(v, ast.Number):
                sv = _num_to_str(v.value)
                if folded and isinstance(folded[-1], ast.String):
                    folded[-1] = ast.String(value=folded[-1].value + sv, raw='', loc=folded[-1].loc)
                    self.changes += 1
                else:
                    folded.append(v)
            else:
                folded.append(v)
        if len(folded) == 1:
            return folded[0]
        return ast.Concat(values=folded, loc=node.loc)

    def transform_If(self, node: ast.If) -> ast.Stmt:
        new_tests = []
        new_bodies = []
        for i in range(len(node.tests)):
            test = self.transform(node.tests[i])
            body = self.transform(node.bodies[i])
            cv = _const_val(test)
            if cv is not None:
                if _truthy(cv):
                    if not new_tests:
                        self.changes += 1
                        return ast.Do(body=body, loc=node.loc)
                    new_tests.append(test)
                    new_bodies.append(body)
                    self.changes += 1
                    return ast.If(tests=new_tests, bodies=new_bodies, else_body=None, loc=node.loc)
                else:
                    self.changes += 1
                    continue
            new_tests.append(test)
            new_bodies.append(body)

        else_body = self.transform(node.else_body) if node.else_body else None

        if not new_tests:
            self.changes += 1
            if else_body:
                return ast.Do(body=else_body, loc=node.loc)
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

    def transform_Block(self, node: ast.Block) -> ast.Block:
        new_stmts = []
        for stmt in node.stmts:
            s = self.transform(stmt)
            if isinstance(s, ast.Do) and isinstance(s.body, ast.Block) and not s.body.stmts:
                self.changes += 1
                continue
            new_stmts.append(s)
        return ast.Block(stmts=new_stmts, loc=node.loc)

    def _try_const_fold_binop(self, node: ast.BinOp) -> Optional[ast.Expr]:
        lv = _const_val(node.left)
        rv = _const_val(node.right)
        if lv is None or rv is None:
            if node.op == 'and':
                if lv is not None:
                    return node.right if _truthy(lv) else node.left
            if node.op == 'or':
                if lv is not None:
                    return node.left if _truthy(lv) else node.right
            return None
        result = _eval_binop(node.op, lv, rv)
        if result is not None:
            return _val_to_ast(result, node.loc)
        return None

    def _try_const_fold_unop(self, node: ast.UnOp) -> Optional[ast.Expr]:
        v = _const_val(node.operand)
        if v is None:
            return None
        result = _eval_unop(node.op, v)
        if result is not None:
            return _val_to_ast(result, node.loc)
        return None

    def _simplify_binop(self, node: ast.BinOp) -> ast.Expr:
        op = node.op
        rv = _const_val(node.right)
        lv = _const_val(node.left)

        if op == '+':
            if rv == 0: return node.left
            if lv == 0: return node.right
        elif op == '-':
            if rv == 0: return node.left
        elif op == '*':
            if rv == 1: return node.left
            if lv == 1: return node.right
            if rv == 0 or lv == 0:
                return ast.Number(value=0, loc=node.loc)
        elif op == '/':
            if rv == 1: return node.left
        elif op == '^':
            if rv == 1: return node.left
            if rv == 0: return ast.Number(value=1, loc=node.loc)
        elif op == '..':
            if lv == '': return node.right
            if rv == '': return node.left

        return node


class VariableInliner(ast.ASTTransformer):
    def __init__(self):
        self.changes = 0
        self._single_use_vars: Dict[str, ast.Expr] = {}
        self._usage_counts: Dict[str, int] = {}
        self._def_order: List[str] = []

    def inline(self, tree: ast.Block) -> ast.Block:
        self._count_usages(tree)
        self._find_single_defs(tree)
        result = self.transform(tree)
        return result

    def _count_usages(self, node: ast.Node):
        if isinstance(node, ast.Name):
            self._usage_counts[node.name] = self._usage_counts.get(node.name, 0) + 1
        for child in node.children():
            self._count_usages(child)

    def _find_single_defs(self, block: ast.Block):
        defs: Dict[str, int] = {}
        for stmt in block.stmts:
            if isinstance(stmt, ast.LocalAssign) and len(stmt.names) == 1 and len(stmt.values) == 1:
                name = stmt.names[0]
                defs[name] = defs.get(name, 0) + 1
                if defs[name] == 1 and self._usage_counts.get(name, 0) == 1:
                    val = stmt.values[0]
                    if self._is_safe_to_inline(val):
                        self._single_use_vars[name] = val

    def _is_safe_to_inline(self, expr: ast.Expr) -> bool:
        if isinstance(expr, (ast.Nil, ast.Bool, ast.Number, ast.String, ast.Name)):
            return True
        if isinstance(expr, ast.BinOp):
            return self._is_safe_to_inline(expr.left) and self._is_safe_to_inline(expr.right)
        if isinstance(expr, ast.UnOp):
            return self._is_safe_to_inline(expr.operand)
        if isinstance(expr, ast.Index):
            return self._is_safe_to_inline(expr.table) and self._is_safe_to_inline(expr.key)
        if isinstance(expr, ast.Field):
            return self._is_safe_to_inline(expr.table)
        return False

    def transform_Name(self, node: ast.Name) -> ast.Expr:
        if node.name in self._single_use_vars:
            self.changes += 1
            return self._single_use_vars[node.name]
        return node

    def transform_Block(self, node: ast.Block) -> ast.Block:
        new_stmts = []
        for stmt in node.stmts:
            if isinstance(stmt, ast.LocalAssign) and len(stmt.names) == 1:
                if stmt.names[0] in self._single_use_vars:
                    self.changes += 1
                    continue
            new_stmts.append(self.transform(stmt))
        return ast.Block(stmts=new_stmts, loc=node.loc)


def _const_val(node: ast.Expr):
    if isinstance(node, ast.Nil): return None
    if isinstance(node, ast.Bool): return node.value
    if isinstance(node, ast.Number): return node.value
    if isinstance(node, ast.String): return node.value
    return None


def _truthy(v) -> bool:
    return v is not None and v is not False


def _num_to_str(v) -> str:
    if isinstance(v, float):
        if v == int(v):
            return str(int(v))
        return str(v)
    return str(v)


def _eval_binop(op, a, b):
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
        if op == '<<' and isinstance(a, (int, float)) and isinstance(b, (int, float)): return (int(a) << int(b)) & 0xFFFFFFFF
        if op == '>>' and isinstance(a, (int, float)) and isinstance(b, (int, float)): return (int(a) >> int(b)) & 0xFFFFFFFF
        if op == 'and': return b if _truthy(a) else a
        if op == 'or': return a if _truthy(a) else b
    except Exception:
        pass
    return None


def _eval_unop(op, v):
    try:
        if op == '-' and isinstance(v, (int, float)): return -v
        if op == '#' and isinstance(v, str): return len(v)
        if op == 'not': return not _truthy(v)
        if op == '~' and isinstance(v, (int, float)): return (~int(v)) & 0xFFFFFFFF
    except Exception:
        pass
    return None


def _val_to_ast(v, loc=None) -> ast.Expr:
    if v is None:
        return ast.Nil(loc=loc)
    if isinstance(v, bool):
        return ast.Bool(value=v, loc=loc)
    if isinstance(v, (int, float)):
        return ast.Number(value=v, loc=loc)
    if isinstance(v, str):
        return ast.String(value=v, raw='', loc=loc)
    return ast.Nil(loc=loc)


def normalize(tree: ast.Block, iterations: int = 10) -> ast.Block:
    for _ in range(iterations):
        n = Normalizer()
        tree = n.normalize(tree)
        if n.changes == 0:
            break
    return tree
