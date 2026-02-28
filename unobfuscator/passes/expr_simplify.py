from __future__ import annotations
import math
from typing import Optional, List
from ..core import lua_ast as ast


class ExprSimplifier(ast.ASTTransformer):
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
        result = self._simplify_binop(node)
        if result is not None:
            self.changes += 1
            return result
        return node

    def transform_UnOp(self, node: ast.UnOp) -> ast.Expr:
        node = ast.UnOp(
            op=node.op,
            operand=self.transform(node.operand),
            loc=node.loc,
        )
        result = self._simplify_unop(node)
        if result is not None:
            self.changes += 1
            return result
        return node

    def transform_Call(self, node: ast.Call) -> ast.Expr:
        node = ast.Call(
            func=self.transform(node.func),
            args=[self.transform(a) for a in node.args],
            loc=node.loc,
        )
        result = self._simplify_call(node)
        if result is not None:
            self.changes += 1
            return result
        return node

    def transform_If(self, node: ast.If) -> ast.Stmt:
        new_tests = []
        new_bodies = []
        for i in range(len(node.tests)):
            test = self.transform(node.tests[i])
            body = self.transform(node.bodies[i])
            simplified = self._simplify_condition(test)
            if simplified is not None:
                test = simplified
                self.changes += 1
            new_tests.append(test)
            new_bodies.append(body)
        else_body = self.transform(node.else_body) if node.else_body else None
        return ast.If(tests=new_tests, bodies=new_bodies, else_body=else_body, loc=node.loc)

    def transform_While(self, node: ast.While) -> ast.Stmt:
        cond = self.transform(node.condition)
        body = self.transform(node.body)
        simplified = self._simplify_condition(cond)
        if simplified is not None:
            cond = simplified
            self.changes += 1
        return ast.While(condition=cond, body=body, loc=node.loc)

    def _simplify_binop(self, e: ast.BinOp) -> Optional[ast.Expr]:
        lv = _const_val(e.left)
        rv = _const_val(e.right)
        if lv is not None and rv is not None:
            result = _eval_binop(e.op, lv, rv)
            if result is not None:
                return _to_ast(result, e.loc)

        op = e.op

        if op == '+':
            if rv == 0: return e.left
            if lv == 0: return e.right
            if isinstance(e.right, ast.UnOp) and e.right.op == '-':
                return ast.BinOp(op='-', left=e.left, right=e.right.operand, loc=e.loc)
        elif op == '-':
            if rv == 0: return e.left
            if _exprs_eq(e.left, e.right):
                return ast.Number(value=0, loc=e.loc)
            if isinstance(e.right, ast.UnOp) and e.right.op == '-':
                return ast.BinOp(op='+', left=e.left, right=e.right.operand, loc=e.loc)
        elif op == '*':
            if rv == 1: return e.left
            if lv == 1: return e.right
            if rv == 0 or lv == 0: return ast.Number(value=0, loc=e.loc)
            if rv == -1: return ast.UnOp(op='-', operand=e.left, loc=e.loc)
            if lv == -1: return ast.UnOp(op='-', operand=e.right, loc=e.loc)
            if rv == 2: return ast.BinOp(op='+', left=e.left, right=e.left, loc=e.loc)
            if lv == 2: return ast.BinOp(op='+', left=e.right, right=e.right, loc=e.loc)
        elif op == '/':
            if rv == 1: return e.left
            if rv == -1: return ast.UnOp(op='-', operand=e.left, loc=e.loc)
            if _exprs_eq(e.left, e.right): return ast.Number(value=1, loc=e.loc)
        elif op == '%':
            if rv == 1: return ast.Number(value=0, loc=e.loc)
        elif op == '^':
            if rv == 0: return ast.Number(value=1, loc=e.loc)
            if rv == 1: return e.left
            if rv == 2: return ast.BinOp(op='*', left=e.left, right=e.left, loc=e.loc)
            if lv == 1: return ast.Number(value=1, loc=e.loc)
        elif op == '..':
            if lv == '': return e.right
            if rv == '': return e.left
        elif op == '==':
            if _exprs_eq(e.left, e.right): return ast.Bool(value=True, loc=e.loc)
        elif op == '~=':
            if _exprs_eq(e.left, e.right): return ast.Bool(value=False, loc=e.loc)
        elif op == 'and':
            if lv is not None:
                return e.right if _truthy(lv) else e.left
        elif op == 'or':
            if lv is not None:
                return e.left if _truthy(lv) else e.right

        return None

    def _simplify_unop(self, e: ast.UnOp) -> Optional[ast.Expr]:
        v = _const_val(e.operand)
        if v is not None:
            result = _eval_unop(e.op, v)
            if result is not None:
                return _to_ast(result, e.loc)

        if e.op == 'not':
            if isinstance(e.operand, ast.UnOp) and e.operand.op == 'not':
                return e.operand.operand
            if isinstance(e.operand, ast.BinOp):
                neg_op = {'==': '~=', '~=': '==', '<': '>=', '>': '<=', '<=': '>', '>=': '<'}
                if e.operand.op in neg_op:
                    return ast.BinOp(op=neg_op[e.operand.op], left=e.operand.left, right=e.operand.right, loc=e.loc)
        if e.op == '-':
            if isinstance(e.operand, ast.UnOp) and e.operand.op == '-':
                return e.operand.operand
        if e.op == '#':
            if isinstance(e.operand, ast.String):
                return ast.Number(value=len(e.operand.value), loc=e.loc)
            if isinstance(e.operand, ast.TableConstructor):
                seq_count = sum(1 for f in e.operand.fields if f.key is None)
                if seq_count == len(e.operand.fields):
                    return ast.Number(value=seq_count, loc=e.loc)
        return None

    def _simplify_call(self, node: ast.Call) -> Optional[ast.Expr]:
        if isinstance(node.func, ast.Name):
            name = node.func.name
            if name == 'tostring' and len(node.args) == 1:
                arg = node.args[0]
                if isinstance(arg, ast.String):
                    return arg
                if isinstance(arg, ast.Number):
                    return ast.String(value=_num_tostr(arg.value), raw='', loc=node.loc)
                if isinstance(arg, ast.Bool):
                    return ast.String(value='true' if arg.value else 'false', raw='', loc=node.loc)
                if isinstance(arg, ast.Nil):
                    return ast.String(value='nil', raw='', loc=node.loc)
            if name == 'tonumber' and len(node.args) == 1:
                arg = node.args[0]
                if isinstance(arg, ast.Number):
                    return arg
                if isinstance(arg, ast.String):
                    try:
                        v = int(arg.value) if '.' not in arg.value else float(arg.value)
                        return ast.Number(value=v, loc=node.loc)
                    except ValueError:
                        pass
            if name == 'type' and len(node.args) == 1:
                arg = node.args[0]
                type_map = {ast.Nil: 'nil', ast.Bool: 'boolean', ast.Number: 'number', ast.String: 'string'}
                if type(arg) in type_map:
                    return ast.String(value=type_map[type(arg)], raw='', loc=node.loc)
                if isinstance(arg, ast.TableConstructor):
                    return ast.String(value='table', raw='', loc=node.loc)
                if isinstance(arg, ast.FunctionExpr):
                    return ast.String(value='function', raw='', loc=node.loc)
            if name == 'select' and len(node.args) >= 2:
                if isinstance(node.args[0], ast.Number):
                    idx = int(node.args[0].value)
                    if 1 <= idx < len(node.args):
                        return node.args[idx]
                if isinstance(node.args[0], ast.String) and node.args[0].value == '#':
                    return ast.Number(value=len(node.args) - 1, loc=node.loc)

        if isinstance(node.func, ast.Field):
            tbl = node.func.table
            name = node.func.name
            if isinstance(tbl, ast.Name) and tbl.name == 'string':
                return self._simplify_string_call(name, node.args, node.loc)
            if isinstance(tbl, ast.Name) and tbl.name == 'math':
                return self._simplify_math_call(name, node.args, node.loc)
        return None

    def _simplify_string_call(self, name: str, args: list, loc) -> Optional[ast.Expr]:
        if name == 'len' and len(args) >= 1 and isinstance(args[0], ast.String):
            return ast.Number(value=len(args[0].value), loc=loc)
        if name == 'byte' and len(args) >= 1 and isinstance(args[0], ast.String):
            s = args[0].value
            i = int(args[1].value) if len(args) > 1 and isinstance(args[1], ast.Number) else 1
            if i < 0: i = len(s) + i + 1
            if 1 <= i <= len(s):
                return ast.Number(value=ord(s[i - 1]), loc=loc)
        if name == 'char' and all(isinstance(a, ast.Number) for a in args):
            try:
                return ast.String(value=''.join(chr(int(a.value)) for a in args), raw='', loc=loc)
            except (ValueError, OverflowError):
                pass
        if name == 'sub' and len(args) >= 2 and isinstance(args[0], ast.String) and isinstance(args[1], ast.Number):
            s = args[0].value
            i = int(args[1].value)
            j = int(args[2].value) if len(args) > 2 and isinstance(args[2], ast.Number) else -1
            if i < 0: i = max(len(s) + i + 1, 1)
            if j < 0: j = len(s) + j + 1
            if i < 1: i = 1
            return ast.String(value=s[i - 1:j], raw='', loc=loc)
        if name == 'rep' and len(args) >= 2 and isinstance(args[0], ast.String) and isinstance(args[1], ast.Number):
            n = int(args[1].value)
            if n <= 100:
                return ast.String(value=args[0].value * max(0, n), raw='', loc=loc)
        if name == 'reverse' and len(args) >= 1 and isinstance(args[0], ast.String):
            return ast.String(value=args[0].value[::-1], raw='', loc=loc)
        if name == 'lower' and len(args) >= 1 and isinstance(args[0], ast.String):
            return ast.String(value=args[0].value.lower(), raw='', loc=loc)
        if name == 'upper' and len(args) >= 1 and isinstance(args[0], ast.String):
            return ast.String(value=args[0].value.upper(), raw='', loc=loc)
        if name == 'format' and len(args) >= 1 and isinstance(args[0], ast.String):
            if all(isinstance(a, (ast.Number, ast.String, ast.Bool, ast.Nil)) for a in args[1:]):
                try:
                    return self._eval_string_format(args[0].value, args[1:], loc)
                except Exception:
                    pass
        return None

    def _simplify_math_call(self, name: str, args: list, loc) -> Optional[ast.Expr]:
        if not args or not all(isinstance(a, ast.Number) for a in args):
            return None
        vals = [a.value for a in args]
        try:
            if name == 'abs' and len(vals) >= 1: return ast.Number(value=abs(vals[0]), loc=loc)
            if name == 'ceil' and len(vals) >= 1: return ast.Number(value=math.ceil(vals[0]), loc=loc)
            if name == 'floor' and len(vals) >= 1: return ast.Number(value=math.floor(vals[0]), loc=loc)
            if name == 'sqrt' and len(vals) >= 1 and vals[0] >= 0: return ast.Number(value=math.sqrt(vals[0]), loc=loc)
            if name == 'max' and vals: return ast.Number(value=max(vals), loc=loc)
            if name == 'min' and vals: return ast.Number(value=min(vals), loc=loc)
            if name == 'fmod' and len(vals) >= 2 and vals[1] != 0: return ast.Number(value=math.fmod(vals[0], vals[1]), loc=loc)
            if name == 'pow' and len(vals) >= 2: return ast.Number(value=vals[0] ** vals[1], loc=loc)
        except (ValueError, OverflowError):
            pass
        return None

    def _eval_string_format(self, fmt: str, args: list, loc) -> Optional[ast.Expr]:
        result = []
        ai = 0
        i = 0
        while i < len(fmt):
            if fmt[i] == '%' and i + 1 < len(fmt):
                i += 1
                if fmt[i] == '%':
                    result.append('%')
                    i += 1
                    continue
                start = i - 1
                while i < len(fmt) and fmt[i] in '-+ #0':
                    i += 1
                while i < len(fmt) and fmt[i].isdigit():
                    i += 1
                if i < len(fmt) and fmt[i] == '.':
                    i += 1
                    while i < len(fmt) and fmt[i].isdigit():
                        i += 1
                if i >= len(fmt) or ai >= len(args):
                    return None
                conv = fmt[i]
                i += 1
                arg = args[ai]
                ai += 1
                spec = fmt[start:i]
                if conv in ('d', 'i'):
                    if isinstance(arg, ast.Number):
                        result.append(str(int(arg.value)))
                    else:
                        return None
                elif conv in ('f', 'F', 'e', 'E', 'g', 'G'):
                    if isinstance(arg, ast.Number):
                        result.append(spec % float(arg.value))
                    else:
                        return None
                elif conv == 's':
                    if isinstance(arg, ast.String):
                        result.append(arg.value)
                    elif isinstance(arg, ast.Number):
                        result.append(_num_tostr(arg.value))
                    else:
                        return None
                elif conv in ('x', 'X'):
                    if isinstance(arg, ast.Number):
                        result.append(format(int(arg.value) & 0xFFFFFFFF, 'x' if conv == 'x' else 'X'))
                    else:
                        return None
                elif conv == 'c':
                    if isinstance(arg, ast.Number):
                        result.append(chr(int(arg.value) & 0xFF))
                    else:
                        return None
                else:
                    return None
            else:
                result.append(fmt[i])
                i += 1
        return ast.String(value=''.join(result), raw='', loc=loc)

    def _simplify_condition(self, cond: ast.Expr) -> Optional[ast.Expr]:
        if isinstance(cond, ast.UnOp) and cond.op == 'not':
            if isinstance(cond.operand, ast.UnOp) and cond.operand.op == 'not':
                return cond.operand.operand
        if isinstance(cond, ast.BinOp) and cond.op in ('==', '~='):
            if isinstance(cond.right, ast.Bool):
                if cond.op == '==' and cond.right.value is True:
                    return cond.left
                if cond.op == '==' and cond.right.value is False:
                    return ast.UnOp(op='not', operand=cond.left, loc=cond.loc)
                if cond.op == '~=' and cond.right.value is True:
                    return ast.UnOp(op='not', operand=cond.left, loc=cond.loc)
                if cond.op == '~=' and cond.right.value is False:
                    return cond.left
            if isinstance(cond.left, ast.Bool):
                if cond.op == '==' and cond.left.value is True:
                    return cond.right
                if cond.op == '==' and cond.left.value is False:
                    return ast.UnOp(op='not', operand=cond.right, loc=cond.loc)
                if cond.op == '~=' and cond.left.value is True:
                    return ast.UnOp(op='not', operand=cond.right, loc=cond.loc)
                if cond.op == '~=' and cond.left.value is False:
                    return cond.right
            if isinstance(cond.right, ast.Nil):
                if cond.op == '~=':
                    return cond.left
                if cond.op == '==':
                    return ast.UnOp(op='not', operand=cond.left, loc=cond.loc)
        return None


def _const_val(e: ast.Expr):
    if isinstance(e, ast.Nil): return None
    if isinstance(e, ast.Bool): return e.value
    if isinstance(e, ast.Number): return e.value
    if isinstance(e, ast.String): return e.value
    return None

def _truthy(v) -> bool:
    return v is not None and v is not False

def _exprs_eq(a: ast.Expr, b: ast.Expr) -> bool:
    if type(a) != type(b): return False
    if isinstance(a, ast.Name): return a.name == b.name
    if isinstance(a, ast.Number): return a.value == b.value
    if isinstance(a, ast.String): return a.value == b.value
    if isinstance(a, ast.Bool): return a.value == b.value
    if isinstance(a, ast.Nil): return True
    return False

def _num_tostr(v) -> str:
    if isinstance(v, float):
        if v == int(v) and not math.isinf(v): return str(int(v))
        return f"{v:g}"
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
    except Exception:
        pass
    return None

def _eval_unop(op, v):
    try:
        if op == '-' and isinstance(v, (int, float)): return -v
        if op == '#' and isinstance(v, str): return len(v)
        if op == 'not': return not _truthy(v)
    except Exception:
        pass
    return None

def _to_ast(v, loc=None) -> ast.Expr:
    if v is None: return ast.Nil(loc=loc)
    if isinstance(v, bool): return ast.Bool(value=v, loc=loc)
    if isinstance(v, (int, float)): return ast.Number(value=v, loc=loc)
    if isinstance(v, str): return ast.String(value=v, raw='', loc=loc)
    return ast.Nil(loc=loc)


def simplify_exprs(tree: ast.Block, iterations: int = 10) -> ast.Block:
    for _ in range(iterations):
        s = ExprSimplifier()
        tree = s.simplify(tree)
        if s.changes == 0:
            break
    return tree
