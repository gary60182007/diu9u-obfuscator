from __future__ import annotations
from typing import Dict, List, Optional, Set, Tuple, Any
from ..core import lua_ast as ast


class DispatchTreeParser:
    """Recursively parses deeply nested binary-search if/else dispatch trees
    used by Luraph and similar VM obfuscators.

    Luraph uses nested `if E < X then ... else ... end` patterns forming a
    binary search tree over opcode values. This parser walks the tree,
    tracking the opcode range at each level, and extracts handler bodies
    keyed by their exact opcode number.
    """

    def __init__(self):
        self.handlers: Dict[int, ast.Block] = {}
        self.dispatch_var: Optional[str] = None

    def parse(self, body: ast.Block) -> Dict[int, ast.Block]:
        self.handlers = {}
        self.dispatch_var = None
        self._detect_dispatch_var(body)
        if self.dispatch_var is None:
            self._try_flat_if_chain(body)
            if not self.handlers:
                self._try_table_dispatch(body)
            return self.handlers
        self._walk_dispatch(body, lo=0, hi=65535)
        return self.handlers

    def _detect_dispatch_var(self, body: ast.Block):
        candidates: Dict[str, int] = {}
        for node in _walk(body):
            if isinstance(node, ast.BinOp) and node.op in ('<', '<=', '>', '>=', '==', '~='):
                var_name = self._extract_var_name(node.left)
                if var_name and isinstance(node.right, ast.Number):
                    candidates[var_name] = candidates.get(var_name, 0) + 1
                var_name = self._extract_var_name(node.right)
                if var_name and isinstance(node.left, ast.Number):
                    candidates[var_name] = candidates.get(var_name, 0) + 1
        if candidates:
            best = max(candidates, key=candidates.get)
            if candidates[best] >= 5:
                self.dispatch_var = best

    def _extract_var_name(self, expr: ast.Expr) -> Optional[str]:
        if isinstance(expr, ast.Name):
            return expr.name
        return None

    def _walk_dispatch(self, body: ast.Block, lo: int, hi: int):
        for stmt in body.stmts:
            if isinstance(stmt, ast.If):
                self._process_if(stmt, lo, hi)
            elif isinstance(stmt, ast.While):
                self._walk_dispatch(stmt.body, lo, hi)
            elif isinstance(stmt, ast.Repeat):
                self._walk_dispatch(stmt.body, lo, hi)

    def _process_if(self, if_stmt: ast.If, lo: int, hi: int):
        for i, test in enumerate(if_stmt.tests):
            cmp = self._parse_comparison(test)
            if cmp is None:
                if i < len(if_stmt.bodies):
                    self._walk_dispatch(if_stmt.bodies[i], lo, hi)
                continue

            op, val, negated = cmp

            if i < len(if_stmt.bodies):
                then_body = if_stmt.bodies[i]
            else:
                continue

            if i + 1 < len(if_stmt.tests):
                else_block = ast.Block(stmts=[ast.If(
                    tests=if_stmt.tests[i+1:],
                    bodies=if_stmt.bodies[i+1:],
                    else_body=if_stmt.else_body
                )])
            elif if_stmt.else_body:
                else_block = if_stmt.else_body
            else:
                else_block = None

            if negated:
                then_body, else_block = else_block, then_body
                if then_body is None:
                    then_body = ast.Block(stmts=[])
                if else_block is None:
                    else_block = ast.Block(stmts=[])

            if op == '<':
                then_lo, then_hi = lo, min(hi, val - 1)
                else_lo, else_hi = max(lo, val), hi
            elif op == '<=':
                then_lo, then_hi = lo, min(hi, val)
                else_lo, else_hi = max(lo, val + 1), hi
            elif op == '>':
                then_lo, then_hi = max(lo, val + 1), hi
                else_lo, else_hi = lo, min(hi, val)
            elif op == '>=':
                then_lo, then_hi = max(lo, val), hi
                else_lo, else_hi = lo, min(hi, val - 1)
            elif op == '==':
                self.handlers[val] = then_body
                if else_block:
                    remaining_lo, remaining_hi = lo, hi
                    self._process_block_recursive(else_block, remaining_lo, remaining_hi, exclude={val})
                break
            elif op == '~=':
                if else_block:
                    self.handlers[val] = else_block
                remaining_lo, remaining_hi = lo, hi
                self._process_block_recursive(then_body, remaining_lo, remaining_hi, exclude={val})
                break
            else:
                continue

            if then_lo == then_hi:
                self.handlers[then_lo] = then_body
            elif then_lo < then_hi:
                self._process_block_recursive(then_body, then_lo, then_hi)
            elif then_lo > then_hi and isinstance(then_body, ast.Block) and then_body.stmts:
                pass

            if else_block:
                if else_lo == else_hi:
                    self.handlers[else_lo] = else_block
                elif else_lo < else_hi:
                    self._process_block_recursive(else_block, else_lo, else_hi)

            break

    def _process_block_recursive(self, body: ast.Block, lo: int, hi: int,
                                  exclude: Optional[Set[int]] = None):
        has_nested_dispatch = False
        for stmt in body.stmts:
            if isinstance(stmt, ast.If):
                if self._has_dispatch_comparison(stmt):
                    has_nested_dispatch = True
                    break

        if has_nested_dispatch:
            self._walk_dispatch(body, lo, hi)
        else:
            if lo == hi:
                self.handlers[lo] = body
            elif hi - lo <= 2:
                if not body.stmts:
                    return
                for v in range(lo, hi + 1):
                    if exclude and v in exclude:
                        continue
                    self.handlers[v] = body

    def _has_dispatch_comparison(self, if_stmt: ast.If) -> bool:
        for test in if_stmt.tests:
            cmp = self._parse_comparison(test)
            if cmp is not None:
                return True
        return False

    def _parse_comparison(self, expr: ast.Expr) -> Optional[Tuple[str, int, bool]]:
        negated = False
        if isinstance(expr, ast.UnOp) and expr.op == 'not':
            expr = expr.operand
            negated = True
            if isinstance(expr, ast.UnOp) and expr.op == 'not':
                expr = expr.operand

        if not isinstance(expr, ast.BinOp):
            return None
        if expr.op not in ('<', '<=', '>', '>=', '==', '~='):
            return None

        left_is_var = self._is_dispatch_var(expr.left)
        right_is_var = self._is_dispatch_var(expr.right)

        if left_is_var and isinstance(expr.right, ast.Number):
            val = int(expr.right.value)
            return (expr.op, val, negated)
        elif right_is_var and isinstance(expr.left, ast.Number):
            val = int(expr.left.value)
            flipped = {'<': '>', '<=': '>=', '>': '<', '>=': '<=', '==': '==', '~=': '~='}
            return (flipped[expr.op], val, negated)

        return None

    def _is_dispatch_var(self, expr: ast.Expr) -> bool:
        if self.dispatch_var is None:
            return False
        if isinstance(expr, ast.Name) and expr.name == self.dispatch_var:
            return True
        return False

    def _try_flat_if_chain(self, body: ast.Block):
        for stmt in body.stmts:
            if isinstance(stmt, ast.If):
                self._extract_flat_handlers(stmt)
            elif isinstance(stmt, ast.While):
                self._try_flat_if_chain(stmt.body)

    def _extract_flat_handlers(self, if_stmt: ast.If):
        for i, test in enumerate(if_stmt.tests):
            if isinstance(test, ast.BinOp) and test.op == '==':
                if isinstance(test.right, ast.Number) and i < len(if_stmt.bodies):
                    opcode = int(test.right.value)
                    self.handlers[opcode] = if_stmt.bodies[i]
                elif isinstance(test.left, ast.Number) and i < len(if_stmt.bodies):
                    opcode = int(test.left.value)
                    self.handlers[opcode] = if_stmt.bodies[i]

    def _try_table_dispatch(self, body: ast.Block):
        for node in _walk(body):
            if isinstance(node, ast.TableConstructor):
                fn_fields = [f for f in node.fields
                             if isinstance(f.value, ast.FunctionExpr)]
                if len(fn_fields) >= 10:
                    for j, f in enumerate(fn_fields):
                        if f.key and isinstance(f.key, ast.Number):
                            opcode = int(f.key.value)
                        else:
                            opcode = j
                        self.handlers[opcode] = f.value.body


def parse_dispatch_tree(body: ast.Block) -> Dict[int, ast.Block]:
    parser = DispatchTreeParser()
    return parser.parse(body)


def find_dispatch_loop(tree: ast.Block) -> Optional[ast.Block]:
    best_body: Optional[ast.Block] = None
    best_count = 0
    for node in _walk(tree):
        if isinstance(node, ast.While):
            count = _count_dispatch_comparisons(node.body)
            if count > best_count:
                best_count = count
                best_body = node.body
    return best_body


def _count_dispatch_comparisons(body: ast.Block) -> int:
    count = 0
    for node in _walk(body):
        if isinstance(node, ast.BinOp) and node.op in ('<', '<=', '>', '>=', '==', '~='):
            if isinstance(node.right, ast.Number) or isinstance(node.left, ast.Number):
                count += 1
    return count


def _is_numeric_comparison(expr: ast.Expr) -> bool:
    if isinstance(expr, ast.UnOp) and expr.op == 'not':
        return _is_numeric_comparison(expr.operand)
    if isinstance(expr, ast.BinOp) and expr.op in ('<', '<=', '>', '>=', '==', '~='):
        if isinstance(expr.right, ast.Number) or isinstance(expr.left, ast.Number):
            return True
    return False


def _walk(node: ast.Node):
    yield node
    for child in node.children():
        yield from _walk(child)
