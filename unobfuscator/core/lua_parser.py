from __future__ import annotations
from typing import List, Optional, Tuple
from .lua_lexer import Token, TK, tokenize
from . import lua_ast as ast


class ParseError(Exception):
    def __init__(self, msg: str, token: Optional[Token] = None):
        self.token = token
        loc = f" at line {token.line}:{token.col}" if token else ""
        super().__init__(f"{msg}{loc}")


UNOP_SET = frozenset({'not', '-', '#', '~'})

BINOP_PRIORITY = {
    'or':  (1, 1),
    'and': (2, 2),
    '<':   (3, 3), '>':  (3, 3), '<=': (3, 3), '>=': (3, 3), '~=': (3, 3), '==': (3, 3),
    '|':   (4, 4),
    '~':   (5, 5),
    '&':   (6, 6),
    '<<':  (7, 7), '>>': (7, 7),
    '..':  (8, 7),
    '+':   (9, 9), '-':  (9, 9),
    '*':   (10, 10), '/': (10, 10), '//': (10, 10), '%': (10, 10),
    '^':   (12, 11),
}

UNOP_PRIORITY = 11


class Parser:
    def __init__(self, tokens: List[Token]):
        self.tokens = [t for t in tokens if t.kind not in (TK.WS, TK.NEWLINE, TK.COMMENT, TK.LONG_COMMENT)]
        self.pos = 0

    def _cur(self) -> Token:
        if self.pos < len(self.tokens):
            return self.tokens[self.pos]
        return self.tokens[-1]

    def _peek_val(self) -> str:
        return self._cur().value

    def _peek_kind(self) -> TK:
        return self._cur().kind

    def _advance(self) -> Token:
        t = self._cur()
        if self.pos < len(self.tokens) - 1:
            self.pos += 1
        return t

    def _expect_val(self, val: str) -> Token:
        t = self._cur()
        if t.value != val:
            raise ParseError(f"expected '{val}', got '{t.value}'", t)
        return self._advance()

    def _expect_kind(self, kind: TK) -> Token:
        t = self._cur()
        if t.kind != kind:
            raise ParseError(f"expected {kind.name}, got {t.kind.name} '{t.value}'", t)
        return self._advance()

    def _check_val(self, val: str) -> bool:
        return self._cur().value == val

    def _check_kind(self, kind: TK) -> bool:
        return self._cur().kind == kind

    def _match_val(self, val: str) -> Optional[Token]:
        if self._cur().value == val:
            return self._advance()
        return None

    def _loc(self) -> ast.SourceLocation:
        t = self._cur()
        return ast.SourceLocation(t.line, t.col, t.line, t.col)

    def parse(self) -> ast.Block:
        block = self._block()
        if not self._check_kind(TK.EOF):
            raise ParseError(f"unexpected token '{self._peek_val()}'", self._cur())
        return block

    def _block(self) -> ast.Block:
        loc = self._loc()
        stmts: List[ast.Stmt] = []
        while True:
            self._skip_semicolons()
            s = self._statement()
            if s is None:
                break
            stmts.append(s)
            self._skip_semicolons()
        block = ast.Block(stmts=stmts, loc=loc)
        return block

    def _skip_semicolons(self):
        while self._match_val(';'):
            pass

    def _is_block_end(self) -> bool:
        v = self._peek_val()
        return v in ('else', 'elseif', 'end', 'until', '') or self._check_kind(TK.EOF)

    def _statement(self) -> Optional[ast.Stmt]:
        if self._is_block_end():
            return None

        v = self._peek_val()
        k = self._peek_kind()

        if v == 'if':
            return self._if_stmt()
        if v == 'while':
            return self._while_stmt()
        if v == 'do':
            return self._do_stmt()
        if v == 'for':
            return self._for_stmt()
        if v == 'repeat':
            return self._repeat_stmt()
        if v == 'function':
            return self._function_stmt()
        if v == 'local':
            return self._local_stmt()
        if v == 'return':
            return self._return_stmt()
        if v == 'break':
            return self._break_stmt()
        if v == 'continue':
            return self._continue_stmt()
        if v == 'goto':
            return self._goto_stmt()
        if v == '::':
            return self._label_stmt()

        return self._expr_or_assign_stmt()

    def _if_stmt(self) -> ast.If:
        loc = self._loc()
        self._expect_val('if')
        tests = []
        bodies = []
        cond = self._expr()
        self._expect_val('then')
        body = self._block()
        tests.append(cond)
        bodies.append(body)

        while self._match_val('elseif'):
            cond = self._expr()
            self._expect_val('then')
            body = self._block()
            tests.append(cond)
            bodies.append(body)

        else_body = None
        if self._match_val('else'):
            else_body = self._block()

        self._expect_val('end')
        return ast.If(tests=tests, bodies=bodies, else_body=else_body, loc=loc)

    def _while_stmt(self) -> ast.While:
        loc = self._loc()
        self._expect_val('while')
        cond = self._expr()
        self._expect_val('do')
        body = self._block()
        self._expect_val('end')
        return ast.While(condition=cond, body=body, loc=loc)

    def _do_stmt(self) -> ast.Do:
        loc = self._loc()
        self._expect_val('do')
        body = self._block()
        self._expect_val('end')
        return ast.Do(body=body, loc=loc)

    def _repeat_stmt(self) -> ast.Repeat:
        loc = self._loc()
        self._expect_val('repeat')
        body = self._block()
        self._expect_val('until')
        cond = self._expr()
        return ast.Repeat(body=body, condition=cond, loc=loc)

    def _for_stmt(self) -> ast.Stmt:
        loc = self._loc()
        self._expect_val('for')
        name = self._expect_kind(TK.NAME).value

        if self._match_val('='):
            start = self._expr()
            self._expect_val(',')
            stop = self._expr()
            step = None
            if self._match_val(','):
                step = self._expr()
            self._expect_val('do')
            body = self._block()
            self._expect_val('end')
            return ast.ForNumeric(name=name, start=start, stop=stop, step=step, body=body, loc=loc)
        else:
            names = [name]
            while self._match_val(','):
                names.append(self._expect_kind(TK.NAME).value)
            self._expect_val('in')
            iters = self._expr_list()
            self._expect_val('do')
            body = self._block()
            self._expect_val('end')
            return ast.ForGeneric(names=names, iterators=iters, body=body, loc=loc)

    def _function_stmt(self) -> ast.FunctionDecl:
        loc = self._loc()
        self._expect_val('function')
        name_expr = self._funcname()
        func = self._funcbody(loc)
        return ast.FunctionDecl(name=name_expr, is_local=False, func=func, loc=loc)

    def _funcname(self) -> ast.Expr:
        name = ast.Name(name=self._expect_kind(TK.NAME).value, loc=self._loc())
        result: ast.Expr = name
        while self._match_val('.'):
            field_name = self._expect_kind(TK.NAME).value
            result = ast.Field(table=result, name=field_name, loc=self._loc())
        if self._match_val(':'):
            method_name = self._expect_kind(TK.NAME).value
            result = ast.Field(table=result, name=method_name, loc=self._loc())
        return result

    def _funcbody(self, loc) -> ast.FunctionExpr:
        self._expect_val('(')
        params, has_vararg = self._parlist()
        self._expect_val(')')
        body = self._block()
        self._expect_val('end')
        return ast.FunctionExpr(params=params, has_vararg=has_vararg, body=body, loc=loc)

    def _parlist(self) -> Tuple[List[str], bool]:
        params = []
        has_vararg = False
        if self._check_val(')'):
            return params, has_vararg
        if self._check_val('...'):
            self._advance()
            return params, True
        params.append(self._expect_kind(TK.NAME).value)
        while self._match_val(','):
            if self._check_val('...'):
                self._advance()
                has_vararg = True
                break
            params.append(self._expect_kind(TK.NAME).value)
        return params, has_vararg

    def _local_stmt(self) -> ast.Stmt:
        loc = self._loc()
        self._expect_val('local')

        if self._check_val('function'):
            self._advance()
            name = self._expect_kind(TK.NAME).value
            func = self._funcbody(loc)
            name_node = ast.Name(name=name, loc=loc)
            return ast.FunctionDecl(name=name_node, is_local=True, func=func, loc=loc)

        names = [self._expect_kind(TK.NAME).value]
        attribs = [self._attrib()]
        while self._match_val(','):
            names.append(self._expect_kind(TK.NAME).value)
            attribs.append(self._attrib())

        values = []
        if self._match_val('='):
            values = self._expr_list()

        return ast.LocalAssign(names=names, attribs=attribs, values=values, loc=loc)

    def _attrib(self) -> Optional[str]:
        if self._match_val('<'):
            name = self._expect_kind(TK.NAME).value
            self._expect_val('>')
            return name
        return None

    def _return_stmt(self) -> ast.Return:
        loc = self._loc()
        self._expect_val('return')
        values = []
        if not self._is_block_end() and not self._check_val(';'):
            values = self._expr_list()
        self._match_val(';')
        return ast.Return(values=values, loc=loc)

    def _break_stmt(self) -> ast.Break:
        loc = self._loc()
        self._expect_val('break')
        return ast.Break(loc=loc)

    def _continue_stmt(self) -> ast.Continue:
        loc = self._loc()
        self._expect_val('continue')
        return ast.Continue(loc=loc)

    def _goto_stmt(self) -> ast.Goto:
        loc = self._loc()
        self._expect_val('goto')
        name = self._expect_kind(TK.NAME).value
        return ast.Goto(name=name, loc=loc)

    def _label_stmt(self) -> ast.Label:
        loc = self._loc()
        self._expect_val('::')
        name = self._expect_kind(TK.NAME).value
        self._expect_val('::')
        return ast.Label(name=name, loc=loc)

    def _expr_or_assign_stmt(self) -> ast.Stmt:
        loc = self._loc()
        expr = self._suffixed_expr()
        if self._check_val(',') or self._check_val('='):
            targets = [expr]
            while self._match_val(','):
                targets.append(self._suffixed_expr())
            self._expect_val('=')
            values = self._expr_list()
            return ast.Assign(targets=targets, values=values, loc=loc)

        compound_ops = {'+=', '-=', '*=', '/=', '%=', '^=', '..=', '//='}
        if self._peek_val() in compound_ops:
            op_tok = self._advance()
            op = op_tok.value[:-1]
            rhs = self._expr()
            value = ast.BinOp(op=op, left=expr, right=rhs, loc=loc)
            return ast.Assign(targets=[expr], values=[value], loc=loc)

        if not isinstance(expr, (ast.Call, ast.MethodCall)):
            raise ParseError(f"unexpected expression statement", self._cur())
        return ast.ExprStmt(expr=expr, loc=loc)

    def _expr_list(self) -> List[ast.Expr]:
        exprs = [self._expr()]
        while self._match_val(','):
            exprs.append(self._expr())
        return exprs

    def _expr(self, min_prec: int = 0) -> ast.Expr:
        return self._sub_expr(0)

    def _sub_expr(self, min_prec: int) -> ast.Expr:
        loc = self._loc()
        node: ast.Expr

        v = self._peek_val()
        if v in UNOP_SET or v == '-':
            op = self._advance().value
            operand = self._sub_expr(UNOP_PRIORITY)
            node = ast.UnOp(op=op, operand=operand, loc=loc)
        else:
            node = self._simple_expr()

        while True:
            v = self._peek_val()
            if v not in BINOP_PRIORITY:
                break
            left_prec, right_prec = BINOP_PRIORITY[v]
            if left_prec <= min_prec:
                break
            op = self._advance().value
            right = self._sub_expr(right_prec)
            if op == '..':
                if isinstance(node, ast.Concat):
                    node.values.append(right)
                else:
                    node = ast.Concat(values=[node, right], loc=loc)
            else:
                node = ast.BinOp(op=op, left=node, right=right, loc=loc)

        return node

    def _simple_expr(self) -> ast.Expr:
        v = self._peek_val()
        k = self._peek_kind()

        if k == TK.NUMBER:
            t = self._advance()
            raw = t.value
            try:
                if '.' in raw or 'e' in raw.lower() or 'E' in raw:
                    if raw.startswith('0x') or raw.startswith('0X'):
                        val = float.fromhex(raw.replace('_', ''))
                    else:
                        val = float(raw.replace('_', ''))
                elif raw.startswith('0x') or raw.startswith('0X'):
                    val = int(raw.replace('_', ''), 16)
                elif raw.startswith('0b') or raw.startswith('0B'):
                    val = int(raw.replace('_', ''), 2)
                else:
                    val = int(raw.replace('_', ''))
            except ValueError:
                val = 0
            return ast.Number(value=val, raw=raw, loc=ast.SourceLocation(t.line, t.col))

        if k == TK.STRING or k == TK.LONG_STRING:
            t = self._advance()
            decoded = self._decode_string(t.value)
            return ast.String(value=decoded, raw=t.value, loc=ast.SourceLocation(t.line, t.col))

        if v == 'nil':
            t = self._advance()
            return ast.Nil(loc=ast.SourceLocation(t.line, t.col))
        if v == 'true':
            t = self._advance()
            return ast.Bool(value=True, loc=ast.SourceLocation(t.line, t.col))
        if v == 'false':
            t = self._advance()
            return ast.Bool(value=False, loc=ast.SourceLocation(t.line, t.col))
        if v == '...':
            t = self._advance()
            return ast.Vararg(loc=ast.SourceLocation(t.line, t.col))
        if v == 'function':
            loc = self._loc()
            self._advance()
            return self._funcbody(loc)
        if v == '{':
            return self._table_constructor()

        return self._suffixed_expr()

    def _suffixed_expr(self) -> ast.Expr:
        node = self._primary_expr()
        while True:
            v = self._peek_val()
            if v == '.':
                self._advance()
                name = self._expect_kind(TK.NAME).value
                node = ast.Field(table=node, name=name, loc=self._loc())
            elif v == '[':
                self._advance()
                key = self._expr()
                self._expect_val(']')
                node = ast.Index(table=node, key=key, loc=self._loc())
            elif v == ':':
                self._advance()
                method = self._expect_kind(TK.NAME).value
                args = self._call_args()
                node = ast.MethodCall(object=node, method=method, args=args, loc=self._loc())
            elif v == '(' or v == '{' or self._peek_kind() in (TK.STRING, TK.LONG_STRING):
                args = self._call_args()
                node = ast.Call(func=node, args=args, loc=self._loc())
            else:
                break
        return node

    def _primary_expr(self) -> ast.Expr:
        v = self._peek_val()
        k = self._peek_kind()
        if k == TK.NAME:
            t = self._advance()
            return ast.Name(name=t.value, loc=ast.SourceLocation(t.line, t.col))
        if v == '(':
            self._advance()
            expr = self._expr()
            self._expect_val(')')
            return expr
        raise ParseError(f"unexpected token '{v}'", self._cur())

    def _call_args(self) -> List[ast.Expr]:
        v = self._peek_val()
        if v == '(':
            self._advance()
            args = []
            if not self._check_val(')'):
                args = self._expr_list()
            self._expect_val(')')
            return args
        if v == '{':
            return [self._table_constructor()]
        if self._peek_kind() in (TK.STRING, TK.LONG_STRING):
            t = self._advance()
            decoded = self._decode_string(t.value)
            return [ast.String(value=decoded, raw=t.value, loc=ast.SourceLocation(t.line, t.col))]
        raise ParseError(f"expected function arguments", self._cur())

    def _table_constructor(self) -> ast.TableConstructor:
        loc = self._loc()
        self._expect_val('{')
        fields = []
        while not self._check_val('}'):
            fields.append(self._table_field())
            if not self._match_val(',') and not self._match_val(';'):
                break
        self._expect_val('}')
        return ast.TableConstructor(fields=fields, loc=loc)

    def _table_field(self) -> ast.TableField:
        loc = self._loc()
        if self._check_val('['):
            self._advance()
            key = self._expr()
            self._expect_val(']')
            self._expect_val('=')
            value = self._expr()
            return ast.TableField(key=key, value=value, loc=loc)

        if self._peek_kind() == TK.NAME:
            saved = self.pos
            name = self._advance().value
            if self._match_val('='):
                value = self._expr()
                return ast.TableField(key=ast.String(value=name, raw=f'"{name}"'), value=value, loc=loc)
            self.pos = saved

        value = self._expr()
        return ast.TableField(key=None, value=value, loc=loc)

    def _decode_string(self, raw: str) -> str:
        if raw.startswith('[[') or raw.startswith('[='):
            eq = 0
            i = 1
            while i < len(raw) and raw[i] == '=':
                eq += 1
                i += 1
            close_len = 2 + eq
            inner = raw[close_len:]
            if inner.endswith(']' + '=' * eq + ']'):
                inner = inner[:-(close_len)]
            if inner.startswith('\n'):
                inner = inner[1:]
            return inner

        if len(raw) < 2:
            return raw
        quote = raw[0]
        if quote not in ('"', "'", '`'):
            return raw
        inner = raw[1:-1] if len(raw) >= 2 and raw[-1] == quote else raw[1:]
        return self._unescape(inner)

    def _unescape(self, s: str) -> str:
        result = []
        i = 0
        n = len(s)
        while i < n:
            if s[i] == '\\' and i + 1 < n:
                i += 1
                c = s[i]
                if c == 'a':
                    result.append('\a'); i += 1
                elif c == 'b':
                    result.append('\b'); i += 1
                elif c == 'f':
                    result.append('\f'); i += 1
                elif c == 'n':
                    result.append('\n'); i += 1
                elif c == 'r':
                    result.append('\r'); i += 1
                elif c == 't':
                    result.append('\t'); i += 1
                elif c == 'v':
                    result.append('\v'); i += 1
                elif c == '\\':
                    result.append('\\'); i += 1
                elif c == '"':
                    result.append('"'); i += 1
                elif c == "'":
                    result.append("'"); i += 1
                elif c == '\n' or c == '\r':
                    result.append('\n'); i += 1
                    if i < n and s[i] == '\n' and c == '\r':
                        i += 1
                elif c == 'x' or c == 'X':
                    i += 1
                    hex_str = ''
                    while i < n and len(hex_str) < 2 and s[i] in '0123456789abcdefABCDEF':
                        hex_str += s[i]
                        i += 1
                    if hex_str:
                        result.append(chr(int(hex_str, 16)))
                elif c == 'u' and i + 1 < n and s[i + 1] == '{':
                    i += 2
                    hex_str = ''
                    while i < n and s[i] != '}':
                        hex_str += s[i]
                        i += 1
                    if i < n:
                        i += 1
                    if hex_str:
                        result.append(chr(int(hex_str, 16)))
                elif c == 'z':
                    i += 1
                    while i < n and s[i] in ' \t\n\r\f\v':
                        i += 1
                elif c.isdigit():
                    num_str = c
                    i += 1
                    while i < n and len(num_str) < 3 and s[i].isdigit():
                        num_str += s[i]
                        i += 1
                    result.append(chr(int(num_str)))
                else:
                    result.append(c)
                    i += 1
            else:
                result.append(s[i])
                i += 1
        return ''.join(result)


def parse(source: str) -> ast.Block:
    tokens = tokenize(source)
    p = Parser(tokens)
    return p.parse()
