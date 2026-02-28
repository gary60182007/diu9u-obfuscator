# Convert Luau source to Lua 5.1/LuaJIT compatible source.
# Uses our Luau parser to parse the AST, then re-emits standard Lua.
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from unobfuscator.core.lua_parser import parse
from unobfuscator.core import lua_ast as ast


class Lua51Emitter:
    def __init__(self):
        self._parts = []
        self._depth = 0
        self._indent = '    '
        self._cont_id = 0
        self._cont_stack = []  # stack of label names for continue→goto

    def emit(self, node):
        self._parts = []
        self._depth = 0
        self._emit_node(node)
        return ''.join(self._parts)

    def _w(self, text):
        self._parts.append(text)

    def _wln(self, text=''):
        self._parts.append(text + '\n')

    def _wind(self):
        self._parts.append(self._indent * self._depth)

    def _emit_node(self, node):
        method = '_emit_' + type(node).__name__
        emitter = getattr(self, method, None)
        if emitter:
            emitter(node)
        else:
            self._w(f'--[[ unknown: {type(node).__name__} ]]')

    def _has_continue(self, node):
        if isinstance(node, ast.Continue):
            return True
        for attr_name in ('stmts', 'body', 'bodies', 'else_body'):
            val = getattr(node, attr_name, None)
            if val is None:
                continue
            if isinstance(val, list):
                for item in val:
                    if isinstance(item, ast.Node) and self._has_continue(item):
                        return True
            elif isinstance(val, ast.Node):
                if self._has_continue(val):
                    return True
        for attr_name in ('condition',):
            val = getattr(node, attr_name, None)
            if isinstance(val, ast.Node) and self._has_continue(val):
                return True
        return False

    def _emit_loop_body(self, body_node):
        has_cont = self._has_continue(body_node)
        if has_cont:
            self._cont_id += 1
            label = f'__cont_{self._cont_id}__'
            self._cont_stack.append(label)
        else:
            self._cont_stack.append(None)

        self._emit_node(body_node)

        if has_cont:
            self._wind()
            self._wln(f'::{label}::')

        self._cont_stack.pop()

    # ── Statements ──

    def _emit_Block(self, node):
        for s in node.stmts:
            self._wind()
            self._emit_node(s)
            self._wln()

    def _emit_Assign(self, node):
        for i, t in enumerate(node.targets):
            if i > 0: self._w(', ')
            self._emit_expr(t)
        self._w(' = ')
        for i, v in enumerate(node.values):
            if i > 0: self._w(', ')
            self._emit_expr(v)

    def _emit_LocalAssign(self, node):
        self._w('local ')
        self._w(', '.join(node.names))
        if node.values:
            self._w(' = ')
            for i, v in enumerate(node.values):
                if i > 0: self._w(', ')
                self._emit_expr(v)

    def _emit_Do(self, node):
        self._wln('do')
        self._depth += 1
        self._emit_node(node.body)
        self._depth -= 1
        self._wind()
        self._w('end')

    def _emit_While(self, node):
        self._w('while ')
        self._emit_expr(node.condition)
        self._wln(' do')
        self._depth += 1
        self._emit_loop_body(node.body)
        self._depth -= 1
        self._wind()
        self._w('end')

    def _emit_Repeat(self, node):
        self._wln('repeat')
        self._depth += 1
        self._emit_loop_body(node.body)
        self._depth -= 1
        self._wind()
        self._w('until ')
        self._emit_expr(node.condition)

    def _emit_If(self, node):
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

    def _emit_ForNumeric(self, node):
        self._w(f'for {node.name} = ')
        self._emit_expr(node.start)
        self._w(', ')
        self._emit_expr(node.stop)
        if node.step:
            self._w(', ')
            self._emit_expr(node.step)
        self._wln(' do')
        self._depth += 1
        self._emit_loop_body(node.body)
        self._depth -= 1
        self._wind()
        self._w('end')

    def _emit_ForGeneric(self, node):
        self._w('for ')
        self._w(', '.join(node.names))
        self._w(' in ')
        if len(node.iterators) == 1 and not isinstance(node.iterators[0], ast.Call) and not isinstance(node.iterators[0], ast.MethodCall):
            self._w('__luau_iter(')
            self._emit_expr(node.iterators[0])
            self._w(')')
        else:
            for i, it in enumerate(node.iterators):
                if i > 0: self._w(', ')
                self._emit_expr(it)
        self._wln(' do')
        self._depth += 1
        self._emit_loop_body(node.body)
        self._depth -= 1
        self._wind()
        self._w('end')

    def _emit_Return(self, node):
        self._w('return')
        if node.values:
            self._w(' ')
            for i, v in enumerate(node.values):
                if i > 0: self._w(', ')
                self._emit_expr(v)

    def _emit_Break(self, _node):
        self._w('break')

    def _emit_Continue(self, _node):
        if self._cont_stack and self._cont_stack[-1]:
            self._w(f'goto {self._cont_stack[-1]}')
        else:
            self._w('break')

    def _emit_Label(self, node):
        self._w(f'::{node.name}::')

    def _emit_Goto(self, node):
        self._w(f'goto {node.name}')

    def _emit_ExprStmt(self, node):
        self._emit_expr(node.expr)

    def _emit_FunctionDecl(self, node):
        if node.is_local:
            self._w('local ')
        self._w('function ')
        self._emit_expr(node.name)
        self._emit_funcbody(node.func)

    def _emit_funcbody(self, func):
        self._w('(')
        params = list(func.params)
        last_idx = {}
        for i in range(len(params) - 1, -1, -1):
            if params[i] not in last_idx:
                last_idx[params[i]] = i
        dup_count = {}
        for i in range(len(params)):
            p = params[i]
            if i != last_idx[p]:
                dup_count[p] = dup_count.get(p, 0) + 1
                params[i] = f'_dup{dup_count[p]}_{p}'
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

    # ── Expressions ──

    def _emit_expr(self, node, prec=0):
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
            if isinstance(node.table, ast.Vararg):
                self._w('(select(1, ...))')
            else:
                self._emit_expr(node.table, 100)
            self._w('[')
            if isinstance(node.key, ast.Vararg):
                self._w('select(1, ...)')
            else:
                self._emit_expr(node.key)
            self._w(']')
        elif isinstance(node, ast.Field):
            if isinstance(node.table, ast.Vararg):
                self._w('(select(1, ...))')
            else:
                self._emit_expr(node.table, 100)
            self._w(f'.{node.name}')
        elif isinstance(node, ast.Call):
            need_wrap = isinstance(node.func, (ast.FunctionExpr, ast.Vararg))
            if need_wrap:
                self._w('(')
            if isinstance(node.func, ast.Vararg):
                self._w('select(1, ...)')
            else:
                self._emit_expr(node.func, 100)
            if need_wrap:
                self._w(')')
            self._w('(')
            for i, a in enumerate(node.args):
                if i > 0: self._w(', ')
                self._emit_expr(a)
            self._w(')')
        elif isinstance(node, ast.MethodCall):
            need_wrap = isinstance(node.object, (ast.TableConstructor, ast.FunctionExpr, ast.Vararg))
            if need_wrap:
                self._w('(')
            self._emit_expr(node.object, 100)
            if need_wrap:
                self._w(')')
            self._w(f':{node.method}(')
            for i, a in enumerate(node.args):
                if i > 0: self._w(', ')
                self._emit_expr(a)
            self._w(')')
        elif isinstance(node, ast.FunctionExpr):
            self._w('function')
            self._emit_funcbody(node)
        elif isinstance(node, ast.TableConstructor):
            self._emit_table(node)
        elif isinstance(node, ast.InterpolatedString):
            self._emit_interpolated_string(node)
        else:
            self._w(f'--[[ ? {type(node).__name__} ]]')

    def _emit_number(self, node):
        v = node.value
        if isinstance(v, float):
            s = repr(v)
            if s == 'inf':
                self._w('(1/0)')
            elif s == '-inf':
                self._w('(-1/0)')
            elif s == 'nan':
                self._w('(0/0)')
            else:
                self._w(s)
        else:
            self._w(str(v))

    def _emit_string(self, node):
        if node.raw and node.raw.startswith('['):
            self._w(node.raw)
            return
        self._w(self._escape_string(node.value))

    def _escape_string(self, s):
        r = ['"']
        for c in s:
            o = ord(c)
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
            elif o < 32 or o == 127:
                r.append(f'\\{o}')
            elif o > 127:
                for b in c.encode('utf-8'):
                    r.append(f'\\{b}')
            else:
                r.append(c)
        r.append('"')
        return ''.join(r)

    def _emit_interpolated_string(self, node):
        parts = []
        for part in node.parts:
            if isinstance(part, ast.String):
                parts.append(self._escape_string(part.value))
            else:
                parts.append(f'tostring({self._sub_emit(part)})')
        if not parts:
            self._w('""')
        elif len(parts) == 1:
            self._w(parts[0])
        else:
            self._w('(' + ' .. '.join(parts) + ')')

    def _sub_emit(self, node):
        old = self._parts
        self._parts = []
        self._emit_expr(node)
        result = ''.join(self._parts)
        self._parts = old
        return result

    _BINOP_PREC = {
        'or': 1, 'and': 2,
        '<': 3, '>': 3, '<=': 3, '>=': 3, '~=': 3, '==': 3,
        '|': 4, '~': 5, '&': 6,
        '<<': 7, '>>': 7,
        '+': 9, '-': 9,
        '*': 10, '/': 10, '//': 10, '%': 10,
        '^': 12,
    }

    def _emit_binop(self, node, outer_prec):
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

    def _emit_unop(self, node, outer_prec):
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

    def _emit_concat(self, node, outer_prec):
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

    def _emit_table(self, node):
        if not node.fields:
            self._w('{}')
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

    def _emit_table_field(self, f):
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


def convert(source):
    tree = parse(source)
    emitter = Lua51Emitter()
    return emitter.emit(tree)


if __name__ == '__main__':
    input_file = sys.argv[1] if len(sys.argv) > 1 else 'unobfuscator/target2.lua'
    output_file = sys.argv[2] if len(sys.argv) > 2 else None

    with open(input_file, 'r', encoding='utf-8', errors='replace') as f:
        src = f.read()

    print(f"Input: {len(src)} chars")
    converted = convert(src)
    print(f"Output: {len(converted)} chars")

    if output_file:
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(converted)
        print(f"Saved to {output_file}")
    else:
        out_path = input_file.rsplit('.', 1)[0] + '_lua51.lua'
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write(converted)
        print(f"Saved to {out_path}")
