from __future__ import annotations
from typing import List, Optional, Tuple, Dict
from ..core import lua_ast as ast


class MBARule:
    def __init__(self, name: str, match_fn, replace_fn):
        self.name = name
        self.match = match_fn
        self.replace = replace_fn


def _is_num(e: ast.Expr) -> bool:
    return isinstance(e, ast.Number)

def _num_val(e: ast.Expr) -> Optional[float]:
    return e.value if isinstance(e, ast.Number) else None

def _is_binop(e: ast.Expr, op: str) -> bool:
    return isinstance(e, ast.BinOp) and e.op == op

def _is_unop(e: ast.Expr, op: str) -> bool:
    return isinstance(e, ast.UnOp) and e.op == op

def _exprs_equal(a: ast.Expr, b: ast.Expr) -> bool:
    if type(a) != type(b):
        return False
    if isinstance(a, ast.Name) and isinstance(b, ast.Name):
        return a.name == b.name
    if isinstance(a, ast.Number) and isinstance(b, ast.Number):
        return a.value == b.value
    if isinstance(a, ast.String) and isinstance(b, ast.String):
        return a.value == b.value
    if isinstance(a, ast.Bool) and isinstance(b, ast.Bool):
        return a.value == b.value
    if isinstance(a, ast.Nil) and isinstance(b, ast.Nil):
        return True
    if isinstance(a, ast.BinOp) and isinstance(b, ast.BinOp):
        return a.op == b.op and _exprs_equal(a.left, b.left) and _exprs_equal(a.right, b.right)
    if isinstance(a, ast.UnOp) and isinstance(b, ast.UnOp):
        return a.op == b.op and _exprs_equal(a.operand, b.operand)
    if isinstance(a, ast.Index) and isinstance(b, ast.Index):
        return _exprs_equal(a.table, b.table) and _exprs_equal(a.key, b.key)
    if isinstance(a, ast.Field) and isinstance(b, ast.Field):
        return a.name == b.name and _exprs_equal(a.table, b.table)
    return False


MBA_RULES: List[MBARule] = []

def _register_rule(name):
    def decorator(fn):
        def match_fn(e):
            return fn(e)
        MBA_RULES.append(MBARule(name, match_fn, None))
        MBA_RULES[-1].replace = lambda e, _fn=fn: _fn(e)
        return fn
    return decorator


class MBASimplifier(ast.ASTTransformer):
    def __init__(self):
        self.changes = 0

    def simplify(self, tree: ast.Block) -> ast.Block:
        self.changes = 0
        return self.transform(tree)

    def transform_BinOp(self, node: ast.BinOp) -> ast.Expr:
        node = ast.BinOp(
            op=node.op,
            left=self.transform(node.left),
            right=self.transform(node.right),
            loc=node.loc,
        )
        result = self._try_simplify(node)
        if result is not None and not _exprs_equal(result, node):
            self.changes += 1
            return result
        return node

    def transform_UnOp(self, node: ast.UnOp) -> ast.Expr:
        node = ast.UnOp(
            op=node.op,
            operand=self.transform(node.operand),
            loc=node.loc,
        )
        result = self._try_simplify(node)
        if result is not None and not _exprs_equal(result, node):
            self.changes += 1
            return result
        return node

    def _try_simplify(self, expr: ast.Expr) -> Optional[ast.Expr]:
        for rule_fn in [
            self._rule_xor_self,
            self._rule_and_self,
            self._rule_or_self,
            self._rule_xor_neg1,
            self._rule_and_neg1,
            self._rule_or_zero,
            self._rule_and_zero,
            self._rule_double_neg,
            self._rule_double_bnot,
            self._rule_xor_xor,
            self._rule_add_neg,
            self._rule_sub_neg,
            self._rule_mul_neg1,
            self._rule_linear_mba,
            self._rule_bitwise_identity,
            self._rule_de_morgan,
            self._rule_distribute,
            self._rule_xor_to_arith,
        ]:
            result = rule_fn(expr)
            if result is not None:
                return result
        return None

    def _rule_xor_self(self, e: ast.Expr) -> Optional[ast.Expr]:
        if _is_binop(e, '~') and _exprs_equal(e.left, e.right):
            return ast.Number(value=0, loc=e.loc)
        return None

    def _rule_and_self(self, e: ast.Expr) -> Optional[ast.Expr]:
        if _is_binop(e, '&') and _exprs_equal(e.left, e.right):
            return e.left
        return None

    def _rule_or_self(self, e: ast.Expr) -> Optional[ast.Expr]:
        if _is_binop(e, '|') and _exprs_equal(e.left, e.right):
            return e.left
        return None

    def _rule_xor_neg1(self, e: ast.Expr) -> Optional[ast.Expr]:
        if _is_binop(e, '~'):
            if _num_val(e.right) == 0xFFFFFFFF or _num_val(e.right) == -1:
                return ast.UnOp(op='~', operand=e.left, loc=e.loc)
            if _num_val(e.left) == 0xFFFFFFFF or _num_val(e.left) == -1:
                return ast.UnOp(op='~', operand=e.right, loc=e.loc)
        return None

    def _rule_and_neg1(self, e: ast.Expr) -> Optional[ast.Expr]:
        if _is_binop(e, '&'):
            if _num_val(e.right) == 0xFFFFFFFF or _num_val(e.right) == -1:
                return e.left
            if _num_val(e.left) == 0xFFFFFFFF or _num_val(e.left) == -1:
                return e.right
        return None

    def _rule_or_zero(self, e: ast.Expr) -> Optional[ast.Expr]:
        if _is_binop(e, '|'):
            if _num_val(e.right) == 0: return e.left
            if _num_val(e.left) == 0: return e.right
        return None

    def _rule_and_zero(self, e: ast.Expr) -> Optional[ast.Expr]:
        if _is_binop(e, '&'):
            if _num_val(e.right) == 0 or _num_val(e.left) == 0:
                return ast.Number(value=0, loc=e.loc)
        return None

    def _rule_double_neg(self, e: ast.Expr) -> Optional[ast.Expr]:
        if _is_unop(e, '-') and _is_unop(e.operand, '-'):
            return e.operand.operand
        return None

    def _rule_double_bnot(self, e: ast.Expr) -> Optional[ast.Expr]:
        if _is_unop(e, '~') and _is_unop(e.operand, '~'):
            return e.operand.operand
        return None

    def _rule_xor_xor(self, e: ast.Expr) -> Optional[ast.Expr]:
        if _is_binop(e, '~') and _is_binop(e.left, '~'):
            if _exprs_equal(e.left.right, e.right):
                return e.left.left
            if _exprs_equal(e.left.left, e.right):
                return e.left.right
        return None

    def _rule_add_neg(self, e: ast.Expr) -> Optional[ast.Expr]:
        if _is_binop(e, '+') and _is_unop(e.right, '-'):
            return ast.BinOp(op='-', left=e.left, right=e.right.operand, loc=e.loc)
        if _is_binop(e, '+') and _is_unop(e.left, '-'):
            return ast.BinOp(op='-', left=e.right, right=e.left.operand, loc=e.loc)
        return None

    def _rule_sub_neg(self, e: ast.Expr) -> Optional[ast.Expr]:
        if _is_binop(e, '-') and _is_unop(e.right, '-'):
            return ast.BinOp(op='+', left=e.left, right=e.right.operand, loc=e.loc)
        return None

    def _rule_mul_neg1(self, e: ast.Expr) -> Optional[ast.Expr]:
        if _is_binop(e, '*'):
            if _num_val(e.right) == -1:
                return ast.UnOp(op='-', operand=e.left, loc=e.loc)
            if _num_val(e.left) == -1:
                return ast.UnOp(op='-', operand=e.right, loc=e.loc)
        return None

    def _rule_linear_mba(self, e: ast.Expr) -> Optional[ast.Expr]:
        if not isinstance(e, ast.BinOp):
            return None
        terms = self._collect_linear_terms(e)
        if terms is None or len(terms) < 2:
            return None
        all_const = all(isinstance(t, (int, float)) for t in terms.values())
        if not all_const:
            return None
        simplified = self._try_truth_table_simplify(terms)
        return simplified

    def _collect_linear_terms(self, e: ast.Expr) -> Optional[Dict[str, float]]:
        return None

    def _try_truth_table_simplify(self, terms) -> Optional[ast.Expr]:
        return None

    def _rule_bitwise_identity(self, e: ast.Expr) -> Optional[ast.Expr]:
        if _is_binop(e, '&') and _is_unop(e.right, '~'):
            if _exprs_equal(e.left, e.right.operand):
                return ast.Number(value=0, loc=e.loc)
        if _is_binop(e, '|') and _is_unop(e.right, '~'):
            if _exprs_equal(e.left, e.right.operand):
                return ast.Number(value=0xFFFFFFFF, loc=e.loc)
        if _is_binop(e, '~') and _is_unop(e.right, '~'):
            if _exprs_equal(e.left, e.right.operand):
                return ast.Number(value=0xFFFFFFFF, loc=e.loc)
        if _is_binop(e, '+'):
            if _is_binop(e.left, '&') and _is_binop(e.right, '|'):
                if ((_exprs_equal(e.left.left, e.right.left) and _exprs_equal(e.left.right, e.right.right)) or
                    (_exprs_equal(e.left.left, e.right.right) and _exprs_equal(e.left.right, e.right.left))):
                    return ast.BinOp(op='+', left=e.left.left, right=e.left.right, loc=e.loc)
        return None

    def _rule_de_morgan(self, e: ast.Expr) -> Optional[ast.Expr]:
        if _is_unop(e, '~') and _is_binop(e.operand, '&'):
            return ast.BinOp(
                op='|',
                left=ast.UnOp(op='~', operand=e.operand.left, loc=e.loc),
                right=ast.UnOp(op='~', operand=e.operand.right, loc=e.loc),
                loc=e.loc,
            )
        if _is_unop(e, '~') and _is_binop(e.operand, '|'):
            return ast.BinOp(
                op='&',
                left=ast.UnOp(op='~', operand=e.operand.left, loc=e.loc),
                right=ast.UnOp(op='~', operand=e.operand.right, loc=e.loc),
                loc=e.loc,
            )
        return None

    def _rule_distribute(self, e: ast.Expr) -> Optional[ast.Expr]:
        if _is_binop(e, '&') and _is_binop(e.left, '|'):
            if _exprs_equal(e.left.left, e.right):
                return e.right
            if _exprs_equal(e.left.right, e.right):
                return e.right
        if _is_binop(e, '|') and _is_binop(e.left, '&'):
            if _exprs_equal(e.left.left, e.right):
                return e.right
            if _exprs_equal(e.left.right, e.right):
                return e.right
        return None

    def _rule_xor_to_arith(self, e: ast.Expr) -> Optional[ast.Expr]:
        if not _is_binop(e, '+'):
            return None
        if (_is_binop(e.left, '&') and _is_binop(e.right, '&') and
            _is_unop(e.left.left, '~') and _is_unop(e.right.right, '~')):
            if (_exprs_equal(e.left.left.operand, e.right.left) and
                _exprs_equal(e.left.right, e.right.right.operand)):
                return ast.BinOp(op='~', left=e.right.left, right=e.left.right, loc=e.loc)
        if (_is_binop(e.left, '-') and _is_binop(e.right, '*') and
            _num_val(e.right.left) == -2):
            if _is_binop(e.right.right, '&'):
                if ((_exprs_equal(e.left.left, e.right.right.left) and _exprs_equal(e.left.right, e.right.right.right)) or
                    (_exprs_equal(e.left.left, e.right.right.right) and _exprs_equal(e.left.right, e.right.right.left))):
                    return ast.BinOp(op='~', left=e.left.left, right=e.left.right, loc=e.loc)
        return None


def simplify_mba(tree: ast.Block, iterations: int = 10) -> ast.Block:
    for _ in range(iterations):
        s = MBASimplifier()
        tree = s.simplify(tree)
        if s.changes == 0:
            break
    return tree
