from __future__ import annotations
from typing import List, Optional, Dict, Tuple, Any
from ..core import lua_ast as ast
from ..core.sandbox import LuaSandbox, LuaError
from ..core.lua_emitter import emit


class StringDecryptor(ast.ASTTransformer):
    def __init__(self, sandbox: Optional[LuaSandbox] = None):
        self.sandbox = sandbox or LuaSandbox(op_limit=5_000_000, timeout=10.0)
        self.changes = 0
        self.decrypted: List[Tuple[str, str]] = []
        self._known_decoders: Dict[str, ast.Expr] = {}
        self._setup_source = ""

    def decrypt(self, tree: ast.Block) -> ast.Block:
        self.changes = 0
        self._find_decoder_functions(tree)
        self._build_setup_source(tree)
        result = self.transform(tree)
        return result

    def _find_decoder_functions(self, tree: ast.Block):
        for stmt in tree.stmts:
            if isinstance(stmt, ast.LocalAssign):
                for i, val in enumerate(stmt.values):
                    if i < len(stmt.names) and self._is_decoder_pattern(val):
                        self._known_decoders[stmt.names[i]] = val
            elif isinstance(stmt, ast.Assign):
                for i, tgt in enumerate(stmt.targets):
                    if isinstance(tgt, ast.Name) and i < len(stmt.values):
                        if self._is_decoder_pattern(stmt.values[i]):
                            self._known_decoders[tgt.name] = stmt.values[i]

    def _is_decoder_pattern(self, expr: ast.Expr) -> bool:
        if isinstance(expr, ast.FunctionExpr):
            return self._body_has_string_ops(expr.body)
        if isinstance(expr, ast.Call) and isinstance(expr.func, ast.FunctionExpr):
            return True
        return False

    def _body_has_string_ops(self, body: ast.Block) -> bool:
        score = 0
        for node in _walk(body):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Field):
                if node.func.name in ('byte', 'char', 'sub', 'gsub', 'rep', 'reverse', 'format'):
                    score += 1
            if isinstance(node, ast.BinOp) and node.op in ('%', '^', '&', '|', '~'):
                score += 1
            if isinstance(node, ast.ForNumeric):
                score += 1
        return score >= 3

    def _build_setup_source(self, tree: ast.Block):
        lines = []
        for stmt in tree.stmts:
            if isinstance(stmt, ast.LocalAssign):
                for i, name in enumerate(stmt.names):
                    if name in self._known_decoders:
                        lines.append(emit(stmt))
                        break
            elif isinstance(stmt, ast.Assign):
                for tgt in stmt.targets:
                    if isinstance(tgt, ast.Name) and tgt.name in self._known_decoders:
                        lines.append(emit(stmt))
                        break
        self._setup_source = '\n'.join(lines)
        if self._setup_source:
            try:
                self.sandbox.execute(self._setup_source)
            except LuaError:
                self._setup_source = ""

    def transform_Call(self, node: ast.Call) -> ast.Expr:
        node = ast.Call(
            func=self.transform(node.func),
            args=[self.transform(a) for a in node.args],
            loc=node.loc,
        )
        if self._is_decode_call(node):
            result = self._try_eval(node)
            if isinstance(result, str):
                self.changes += 1
                self.decrypted.append((_call_str(node), result))
                return ast.String(value=result, raw='', loc=node.loc)
        if self._is_char_call(node):
            result = self._try_eval(node)
            if isinstance(result, str):
                self.changes += 1
                return ast.String(value=result, raw='', loc=node.loc)
        return node

    def transform_Concat(self, node: ast.Concat) -> ast.Expr:
        vals = [self.transform(v) for v in node.values]
        merged = []
        for v in vals:
            if merged and isinstance(merged[-1], ast.String) and isinstance(v, ast.String):
                merged[-1] = ast.String(value=merged[-1].value + v.value, raw='', loc=merged[-1].loc)
                self.changes += 1
            else:
                merged.append(v)
        if len(merged) == 1:
            return merged[0]
        return ast.Concat(values=merged, loc=node.loc)

    def _is_decode_call(self, node: ast.Call) -> bool:
        if isinstance(node.func, ast.Name) and node.func.name in self._known_decoders:
            return all(_is_const(a) for a in node.args)
        return False

    def _is_char_call(self, node: ast.Call) -> bool:
        if isinstance(node.func, ast.Field) and node.func.name == 'char':
            if isinstance(node.func.table, ast.Name) and node.func.table.name == 'string':
                return all(_is_const(a) for a in node.args)
        return False

    def _try_eval(self, node: ast.Call) -> Optional[Any]:
        src = f"return {emit(node)}"
        try:
            results = self.sandbox.execute(src)
            return results[0] if results else None
        except LuaError:
            return None

    def _try_eval_expr(self, expr: ast.Expr) -> Optional[Any]:
        src = f"return {emit(expr)}"
        try:
            results = self.sandbox.execute(src)
            return results[0] if results else None
        except LuaError:
            return None


class XORDecryptor(ast.ASTTransformer):
    def __init__(self):
        self.changes = 0

    def decrypt(self, tree: ast.Block) -> ast.Block:
        self.changes = 0
        return self.transform(tree)

    def transform_Call(self, node: ast.Call) -> ast.Expr:
        node = ast.Call(
            func=self.transform(node.func),
            args=[self.transform(a) for a in node.args],
            loc=node.loc,
        )
        pattern = self._match_xor_decrypt(node)
        if pattern:
            encrypted, key = pattern
            try:
                decrypted = self._xor_decrypt(encrypted, key)
                self.changes += 1
                return ast.String(value=decrypted, raw='', loc=node.loc)
            except Exception:
                pass
        return node

    def _match_xor_decrypt(self, node: ast.Call) -> Optional[Tuple[str, int]]:
        if not isinstance(node.func, ast.FunctionExpr):
            return None
        body = node.func.body
        if not body.stmts:
            return None
        for child in _walk(body):
            if isinstance(child, ast.Call) and isinstance(child.func, ast.Field):
                if child.func.name == 'char':
                    for arg in child.args:
                        if isinstance(arg, ast.BinOp) and arg.op == '%':
                            return self._try_extract_xor_params(node)
        return None

    def _try_extract_xor_params(self, node: ast.Call) -> Optional[Tuple[str, int]]:
        if len(node.args) >= 2:
            if isinstance(node.args[0], ast.String) and isinstance(node.args[1], ast.Number):
                return (node.args[0].value, int(node.args[1].value))
        return None

    def _xor_decrypt(self, data: str, key: int) -> str:
        result = []
        for i, c in enumerate(data):
            result.append(chr((ord(c) ^ (key + i)) % 256))
        return ''.join(result)


class Base91Decoder:
    ALPHABET = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789!#$%&()*+,./:;<=>?@[]^_`{|}~"'

    @staticmethod
    def decode(data: str) -> bytes:
        lookup = {c: i for i, c in enumerate(Base91Decoder.ALPHABET)}
        result = bytearray()
        v = -1
        b = 0
        n = 0
        for c in data:
            p = lookup.get(c)
            if p is None:
                continue
            if v < 0:
                v = p
            else:
                v += p * 91
                b |= v << n
                n += 13 if (v & 8191) > 88 else 14
                while n > 7:
                    result.append(b & 0xFF)
                    b >>= 8
                    n -= 8
                v = -1
        if v >= 0:
            result.append((b | (v << n)) & 0xFF)
        return bytes(result)


def _walk(node: ast.Node):
    yield node
    for child in node.children():
        yield from _walk(child)


def _is_const(expr: ast.Expr) -> bool:
    if isinstance(expr, (ast.Nil, ast.Bool, ast.Number, ast.String)):
        return True
    if isinstance(expr, ast.UnOp) and expr.op == '-' and isinstance(expr.operand, ast.Number):
        return True
    return False


def _call_str(node: ast.Call) -> str:
    try:
        return emit(node)
    except Exception:
        return "?"


def decrypt_strings(tree: ast.Block, sandbox: Optional[LuaSandbox] = None) -> ast.Block:
    sd = StringDecryptor(sandbox)
    tree = sd.decrypt(tree)
    xd = XORDecryptor()
    tree = xd.decrypt(tree)
    return tree
