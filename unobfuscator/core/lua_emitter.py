from __future__ import annotations
from typing import List, Optional
from . import lua_ast as ast


class LuaEmitter:
    def __init__(self, indent_str: str = '    ', newline: str = '\n'):
        self._indent = indent_str
        self._nl = newline
        self._depth = 0
        self._parts: List[str] = []

    def emit(self, node: ast.Node) -> str:
        self._parts = []
        self._depth = 0
        self._emit_node(node)
        return ''.join(self._parts)

    def _w(self, text: str):
        self._parts.append(text)

    def _wln(self, text: str = ''):
        self._parts.append(text + self._nl)

    def _wind(self):
        self._parts.append(self._indent * self._depth)

    def _emit_node(self, node: ast.Node):
        method = '_emit_' + type(node).__name__
        emitter = getattr(self, method, None)
        if emitter:
            emitter(node)
        else:
            self._w(f'--[[ unknown node: {type(node).__name__} ]]')

    def _emit_Block(self, node: ast.Block):
        for s in node.stmts:
            self._wind()
            self._emit_node(s)
            self._wln()

    def _emit_Assign(self, node: ast.Assign):
        for i, t in enumerate(node.targets):
            if i > 0:
                self._w(', ')
            self._emit_expr(t)
        self._w(' = ')
        for i, v in enumerate(node.values):
            if i > 0:
                self._w(', ')
            self._emit_expr(v)

    def _emit_LocalAssign(self, node: ast.LocalAssign):
        self._w('local ')
        for i, name in enumerate(node.names):
            if i > 0:
                self._w(', ')
            self._w(name)
            if node.attribs and i < len(node.attribs) and node.attribs[i]:
                self._w(f' <{node.attribs[i]}>')
        if node.values:
            self._w(' = ')
            for i, v in enumerate(node.values):
                if i > 0:
                    self._w(', ')
                self._emit_expr(v)

    def _emit_Do(self, node: ast.Do):
        self._wln('do')
        self._depth += 1
        self._emit_node(node.body)
        self._depth -= 1
        self._wind()
        self._w('end')

    def _emit_While(self, node: ast.While):
        self._w('while ')
        self._emit_expr(node.condition)
        self._wln(' do')
        self._depth += 1
        self._emit_node(node.body)
        self._depth -= 1
        self._wind()
        self._w('end')

    def _emit_Repeat(self, node: ast.Repeat):
        self._wln('repeat')
        self._depth += 1
        self._emit_node(node.body)
        self._depth -= 1
        self._wind()
        self._w('until ')
        self._emit_expr(node.condition)

    def _emit_If(self, node: ast.If):
        for idx in range(len(node.tests)):
            if idx == 0:
                self._w('if ')
            else:
                self._wind()
                self._w('elseif ')
            self._emit_expr(node.tests[idx])
            self._wln(' then')
            self._depth += 1
            self._emit_node(node.bodies[idx])
            self._depth -= 1
        if node.else_body:
            self._wind()
            self._wln('else')
            self._depth += 1
            self._emit_node(node.else_body)
            self._depth -= 1
        self._wind()
        self._w('end')

    def _emit_ForNumeric(self, node: ast.ForNumeric):
        self._w(f'for {node.name} = ')
        self._emit_expr(node.start)
        self._w(', ')
        self._emit_expr(node.stop)
        if node.step:
            self._w(', ')
            self._emit_expr(node.step)
        self._wln(' do')
        self._depth += 1
        self._emit_node(node.body)
        self._depth -= 1
        self._wind()
        self._w('end')

    def _emit_ForGeneric(self, node: ast.ForGeneric):
        self._w('for ')
        self._w(', '.join(node.names))
        self._w(' in ')
        for i, it in enumerate(node.iterators):
            if i > 0:
                self._w(', ')
            self._emit_expr(it)
        self._wln(' do')
        self._depth += 1
        self._emit_node(node.body)
        self._depth -= 1
        self._wind()
        self._w('end')

    def _emit_Return(self, node: ast.Return):
        self._w('return')
        if node.values:
            self._w(' ')
            for i, v in enumerate(node.values):
                if i > 0:
                    self._w(', ')
                self._emit_expr(v)

    def _emit_Break(self, _node: ast.Break):
        self._w('break')

    def _emit_Continue(self, _node: ast.Continue):
        self._w('continue')

    def _emit_Label(self, node: ast.Label):
        self._w(f'::{node.name}::')

    def _emit_Goto(self, node: ast.Goto):
        self._w(f'goto {node.name}')

    def _emit_ExprStmt(self, node: ast.ExprStmt):
        self._emit_expr(node.expr)

    def _emit_FunctionDecl(self, node: ast.FunctionDecl):
        if node.is_local:
            self._w('local ')
        self._w('function ')
        self._emit_expr(node.name)
        self._emit_funcbody(node.func)

    def _emit_funcbody(self, func: ast.FunctionExpr):
        self._w('(')
        params = list(func.params)
        if func.has_vararg:
            params.append('...')
        self._w(', '.join(params))
        self._w(')')
        self._wln()
        self._depth += 1
        self._emit_node(func.body)
        self._depth -= 1
        self._wind()
        self._w('end')

    def _emit_expr(self, node: ast.Expr, prec: int = 0):
        if isinstance(node, ast.Nil):
            self._w('nil')
        elif isinstance(node, ast.Bool):
            self._w('true' if node.value else 'false')
        elif isinstance(node, ast.Number):
            self._emit_number(node)
        elif isinstance(node, ast.String):
            self._emit_string(node)
        elif isinstance(node, ast.Vararg):
            self._w('...')
        elif isinstance(node, ast.Name):
            self._w(node.name)
        elif isinstance(node, ast.BinOp):
            self._emit_binop(node, prec)
        elif isinstance(node, ast.UnOp):
            self._emit_unop(node, prec)
        elif isinstance(node, ast.Concat):
            self._emit_concat(node, prec)
        elif isinstance(node, ast.Index):
            self._emit_expr(node.table, 100)
            self._w('[')
            self._emit_expr(node.key)
            self._w(']')
        elif isinstance(node, ast.Field):
            self._emit_expr(node.table, 100)
            self._w(f'.{node.name}')
        elif isinstance(node, ast.Call):
            self._emit_expr(node.func, 100)
            self._w('(')
            for i, a in enumerate(node.args):
                if i > 0:
                    self._w(', ')
                self._emit_expr(a)
            self._w(')')
        elif isinstance(node, ast.MethodCall):
            self._emit_expr(node.object, 100)
            self._w(f':{node.method}(')
            for i, a in enumerate(node.args):
                if i > 0:
                    self._w(', ')
                self._emit_expr(a)
            self._w(')')
        elif isinstance(node, ast.FunctionExpr):
            self._w('function')
            self._emit_funcbody(node)
        elif isinstance(node, ast.TableConstructor):
            self._emit_table(node)
        else:
            self._w(f'--[[ ? {type(node).__name__} ]]')

    def _emit_number(self, node: ast.Number):
        if node.raw:
            self._w(node.raw)
        elif isinstance(node.value, float):
            s = repr(node.value)
            if s == 'inf':
                self._w('1/0')
            elif s == '-inf':
                self._w('-1/0')
            elif s == 'nan':
                self._w('0/0')
            else:
                self._w(s)
        else:
            self._w(str(node.value))

    def _emit_string(self, node: ast.String):
        if node.raw:
            self._w(node.raw)
        else:
            self._w(self._escape_string(node.value))

    def _escape_string(self, s: str) -> str:
        r = ['"']
        for c in s:
            if c == '"':
                r.append('\\"')
            elif c == '\\':
                r.append('\\\\')
            elif c == '\n':
                r.append('\\n')
            elif c == '\r':
                r.append('\\r')
            elif c == '\t':
                r.append('\\t')
            elif c == '\0':
                r.append('\\0')
            elif ord(c) < 32 or ord(c) == 127:
                r.append(f'\\{ord(c)}')
            else:
                r.append(c)
        r.append('"')
        return ''.join(r)

    _BINOP_PREC = {
        'or': 1, 'and': 2,
        '<': 3, '>': 3, '<=': 3, '>=': 3, '~=': 3, '==': 3,
        '|': 4, '~': 5, '&': 6,
        '<<': 7, '>>': 7,
        '+': 9, '-': 9,
        '*': 10, '/': 10, '//': 10, '%': 10,
        '^': 12,
    }

    def _emit_binop(self, node: ast.BinOp, outer_prec: int):
        my_prec = self._BINOP_PREC.get(node.op, 0)
        need_parens = my_prec < outer_prec
        if need_parens:
            self._w('(')
        self._emit_expr(node.left, my_prec)
        self._w(f' {node.op} ')
        right_prec = my_prec
        if node.op == '^':
            right_prec = my_prec - 1
        self._emit_expr(node.right, right_prec)
        if need_parens:
            self._w(')')

    def _emit_unop(self, node: ast.UnOp, outer_prec: int):
        need_parens = 11 < outer_prec
        if need_parens:
            self._w('(')
        if node.op == 'not':
            self._w('not ')
        else:
            self._w(node.op)
        self._emit_expr(node.operand, 11)
        if need_parens:
            self._w(')')

    def _emit_concat(self, node: ast.Concat, outer_prec: int):
        my_prec = 8
        need_parens = my_prec < outer_prec
        if need_parens:
            self._w('(')
        for i, v in enumerate(node.values):
            if i > 0:
                self._w(' .. ')
            self._emit_expr(v, my_prec + 1)
        if need_parens:
            self._w(')')

    def _emit_table(self, node: ast.TableConstructor):
        if not node.fields:
            self._w('{}')
            return
        if len(node.fields) <= 3 and all(self._is_simple_field(f) for f in node.fields):
            self._w('{')
            for i, f in enumerate(node.fields):
                if i > 0:
                    self._w(', ')
                self._emit_table_field(f)
            self._w('}')
            return
        self._wln('{')
        self._depth += 1
        for i, f in enumerate(node.fields):
            self._wind()
            self._emit_table_field(f)
            if i < len(node.fields) - 1:
                self._w(',')
            self._wln()
        self._depth -= 1
        self._wind()
        self._w('}')

    def _emit_table_field(self, f: ast.TableField):
        if f.key is None:
            self._emit_expr(f.value)
        elif isinstance(f.key, ast.String) and f.key.value.isidentifier():
            self._w(f'{f.key.value} = ')
            self._emit_expr(f.value)
        else:
            self._w('[')
            self._emit_expr(f.key)
            self._w('] = ')
            self._emit_expr(f.value)

    def _is_simple_field(self, f: ast.TableField) -> bool:
        if f.key is not None and not isinstance(f.key, (ast.String, ast.Number)):
            return False
        return isinstance(f.value, (ast.Nil, ast.Bool, ast.Number, ast.String, ast.Name, ast.Vararg))


def emit(node: ast.Node, indent: str = '    ') -> str:
    return LuaEmitter(indent_str=indent).emit(node)
