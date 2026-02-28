from __future__ import annotations
import math
import re
import time
import threading
from typing import Any, Dict, List, Optional, Callable
from .lua_parser import parse as lua_parse
from . import lua_ast as ast


class LuaError(Exception):
    pass

class LuaInternalReturn(Exception):
    def __init__(self, values: list):
        self.values = values

class LuaInternalBreak(Exception):
    pass

class LuaInternalContinue(Exception):
    pass

class SandboxTimeout(LuaError):
    pass

class SandboxOpLimit(LuaError):
    pass

class LuaCoroutineYield(Exception):
    def __init__(self, values: list):
        self.values = values

NIL = None


class LuaCoroutine:
    def __init__(self, sandbox, func):
        self.sandbox = sandbox
        self.func = func
        self.status = 'suspended'
        self._resume_event = threading.Event()
        self._yield_event = threading.Event()
        self._resume_args = []
        self._yield_vals = []
        self._error = None
        self._thread = None
        self._finished = False

    def resume(self, args):
        if self.status == 'dead':
            return [False, "cannot resume dead coroutine"]
        if self.status == 'running':
            return [False, "cannot resume running coroutine"]

        self._resume_args = args
        self.status = 'running'

        if self._thread is None:
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._yield_event.clear()
            self._thread.start()
        else:
            self._yield_event.clear()
            self._resume_event.set()

        self._yield_event.wait(timeout=self.sandbox.timeout)
        if not self._yield_event.is_set():
            self.status = 'dead'
            return [False, "coroutine timeout"]

        if self._error is not None:
            self.status = 'dead'
            err = self._error
            self._error = None
            return [False, str(err)]

        if self._finished:
            self.status = 'dead'
            return [True] + self._yield_vals

        self.status = 'suspended'
        return [True] + self._yield_vals

    def _run(self):
        old_co = getattr(self.sandbox, '_current_coroutine', None)
        self.sandbox._current_coroutine = self
        try:
            result = self.sandbox._call(self.func, self._resume_args)
            self._yield_vals = result if result else []
            self._finished = True
        except LuaCoroutineYield as y:
            self._yield_vals = y.values
        except LuaError as e:
            self._error = e
            self._finished = True
        except Exception as e:
            self._error = LuaError(str(e))
            self._finished = True
        finally:
            self.sandbox._current_coroutine = old_co
            self._yield_event.set()

    def do_yield(self, values):
        self._yield_vals = values
        self._yield_event.set()
        self._resume_event.clear()
        self._resume_event.wait(timeout=self.sandbox.timeout)
        if not self._resume_event.is_set():
            raise LuaError("coroutine yield timeout")
        return self._resume_args


class LuaTable:
    def __init__(self):
        self.hash: Dict[Any, Any] = {}
        self.array: List[Any] = []
        self.metatable: Optional[LuaTable] = None
        self._next_seq = 0

    def rawget(self, key):
        if isinstance(key, (int, float)):
            idx = int(key)
            if idx == key and 1 <= idx <= len(self.array):
                return self.array[idx - 1]
        if key is None:
            return None
        return self.hash.get(key)

    def rawset(self, key, value):
        if key is None:
            raise LuaError("table index is nil")
        if isinstance(key, float) and math.isnan(key):
            raise LuaError("table index is NaN")
        if isinstance(key, (int, float)):
            idx = int(key)
            if idx == key and idx >= 1:
                if idx <= len(self.array):
                    self.array[idx - 1] = value
                    if value is None:
                        while self.array and self.array[-1] is None:
                            self.array.pop()
                    return
                elif idx == len(self.array) + 1 and value is not None:
                    self.array.append(value)
                    while True:
                        nk = len(self.array) + 1
                        if nk in self.hash:
                            self.array.append(self.hash.pop(nk))
                        else:
                            break
                    return
        if value is None:
            self.hash.pop(key, None)
        else:
            self.hash[key] = value

    def length(self) -> int:
        return len(self.array)

    def next_pair(self, key=None):
        if key is None:
            if self.array:
                return 1, self.array[0]
            if self.hash:
                k = next(iter(self.hash))
                return k, self.hash[k]
            return None, None
        if isinstance(key, (int, float)):
            idx = int(key)
            if idx == key and 1 <= idx <= len(self.array):
                for j in range(idx, len(self.array)):
                    if self.array[j] is not None:
                        return j + 1, self.array[j]
                if self.hash:
                    k = next(iter(self.hash))
                    return k, self.hash[k]
                return None, None
        keys = list(self.hash.keys())
        try:
            ki = keys.index(key)
            if ki + 1 < len(keys):
                nk = keys[ki + 1]
                return nk, self.hash[nk]
            return None, None
        except ValueError:
            return None, None

    def __repr__(self):
        return f"table: 0x{id(self):016x}"


class LuaClosure:
    def __init__(self, func: Callable, name: str = "?"):
        self.func = func
        self.name = name

    def __repr__(self):
        return f"function: 0x{id(self):016x}"


class Environment:
    def __init__(self, parent: Optional['Environment'] = None):
        self.vars: Dict[str, Any] = {}
        self.parent = parent

    def get(self, name: str) -> Any:
        if name in self.vars:
            return self.vars[name]
        if self.parent:
            return self.parent.get(name)
        return None

    def set_existing(self, name: str, value: Any) -> bool:
        if name in self.vars:
            self.vars[name] = value
            return True
        if self.parent:
            return self.parent.set_existing(name, value)
        return False

    def set_local(self, name: str, value: Any):
        self.vars[name] = value

    def set_global(self, name: str, value: Any):
        env = self
        while env.parent:
            env = env.parent
        env.vars[name] = value


class LuaSandbox:
    def __init__(self, op_limit: int = 10_000_000, timeout: float = 30.0, trace: bool = False, tolerant: bool = False):
        self.op_limit = op_limit
        self.timeout = timeout
        self.trace = trace
        self.tolerant = tolerant
        self.ops = 0
        self.start_time = 0.0
        self.output: List[str] = []
        self.intercepted_loads: List[str] = []
        self.trace_log: List[dict] = []
        self._global = Environment()
        self._recursion = 0
        self._max_recursion = 200
        self._setup_globals()

    def _tick(self):
        self.ops += 1
        if self.ops > self.op_limit:
            raise SandboxOpLimit(f"op limit ({self.op_limit}) exceeded")
        if self.ops % 10000 == 0 and time.time() - self.start_time > self.timeout:
            raise SandboxTimeout(f"timeout ({self.timeout}s) exceeded")

    def execute(self, source: str) -> List[Any]:
        tree = lua_parse(source)
        self.ops = 0
        self.start_time = time.time()
        self.output.clear()
        self.intercepted_loads.clear()
        env = Environment(self._global)
        try:
            self._exec_block(tree, env)
        except LuaInternalReturn as r:
            return r.values
        return []

    def eval_expr(self, source: str) -> Any:
        r = self.execute(f"return {source}")
        return r[0] if r else None

    def call_function(self, func, args: list) -> list:
        return self._call(func, args)

    # ── statement execution ──

    def _exec_block(self, block: ast.Block, env: Environment):
        for stmt in block.stmts:
            self._tick()
            self._exec_stmt(stmt, env)

    def _exec_stmt(self, stmt: ast.Stmt, env: Environment):
        if isinstance(stmt, ast.LocalAssign):
            vals = self._eval_list(stmt.values, env)
            for i, nm in enumerate(stmt.names):
                env.set_local(nm, vals[i] if i < len(vals) else None)
        elif isinstance(stmt, ast.Assign):
            vals = self._eval_list(stmt.values, env)
            for i, tgt in enumerate(stmt.targets):
                self._set_target(tgt, vals[i] if i < len(vals) else None, env)
        elif isinstance(stmt, ast.ExprStmt):
            self._eval(stmt.expr, env)
        elif isinstance(stmt, ast.If):
            self._exec_if(stmt, env)
        elif isinstance(stmt, ast.While):
            self._exec_while(stmt, env)
        elif isinstance(stmt, ast.Repeat):
            self._exec_repeat(stmt, env)
        elif isinstance(stmt, ast.ForNumeric):
            self._exec_for_num(stmt, env)
        elif isinstance(stmt, ast.ForGeneric):
            self._exec_for_gen(stmt, env)
        elif isinstance(stmt, ast.Do):
            self._exec_block(stmt.body, Environment(env))
        elif isinstance(stmt, ast.Return):
            vals = self._eval_list(stmt.values, env)
            raise LuaInternalReturn(vals)
        elif isinstance(stmt, ast.Break):
            raise LuaInternalBreak()
        elif isinstance(stmt, ast.Continue):
            raise LuaInternalContinue()
        elif isinstance(stmt, ast.FunctionDecl):
            cl = self._make_closure(stmt.func, env, self._name_str(stmt.name))
            if stmt.is_local and isinstance(stmt.name, ast.Name):
                env.set_local(stmt.name.name, cl)
            else:
                self._set_target(stmt.name, cl, env)

    def _set_target(self, tgt: ast.Expr, val: Any, env: Environment):
        if isinstance(tgt, ast.Name):
            if not env.set_existing(tgt.name, val):
                env.set_global(tgt.name, val)
        elif isinstance(tgt, ast.Index):
            t = self._eval(tgt.table, env)
            k = self._eval(tgt.key, env)
            self._tbl_set(t, k, val)
        elif isinstance(tgt, ast.Field):
            t = self._eval(tgt.table, env)
            self._tbl_set(t, tgt.name, val)

    def _exec_if(self, stmt: ast.If, env: Environment):
        for i in range(len(stmt.tests)):
            if self._truthy(self._eval(stmt.tests[i], env)):
                self._exec_block(stmt.bodies[i], Environment(env))
                return
        if stmt.else_body:
            self._exec_block(stmt.else_body, Environment(env))

    def _exec_while(self, stmt: ast.While, env: Environment):
        while True:
            self._tick()
            if not self._truthy(self._eval(stmt.condition, env)):
                break
            try:
                self._exec_block(stmt.body, Environment(env))
            except LuaInternalBreak:
                break
            except LuaInternalContinue:
                continue

    def _exec_repeat(self, stmt: ast.Repeat, env: Environment):
        while True:
            self._tick()
            child = Environment(env)
            try:
                self._exec_block(stmt.body, child)
                if self._truthy(self._eval(stmt.condition, child)):
                    break
            except LuaInternalBreak:
                break
            except LuaInternalContinue:
                continue

    def _exec_for_num(self, stmt: ast.ForNumeric, env: Environment):
        start = self._tonum(self._eval(stmt.start, env))
        stop = self._tonum(self._eval(stmt.stop, env))
        step = self._tonum(self._eval(stmt.step, env)) if stmt.step else 1.0
        if step == 0:
            raise LuaError("'for' step is zero")
        val = start
        while (step > 0 and val <= stop) or (step < 0 and val >= stop):
            self._tick()
            child = Environment(env)
            child.set_local(stmt.name, val)
            try:
                self._exec_block(stmt.body, child)
            except LuaInternalBreak:
                break
            except LuaInternalContinue:
                pass
            val += step

    def _exec_for_gen(self, stmt: ast.ForGeneric, env: Environment):
        iters = self._eval_list(stmt.iterators, env)
        fn = iters[0] if len(iters) > 0 else None
        state = iters[1] if len(iters) > 1 else None
        ctrl = iters[2] if len(iters) > 2 else None
        while True:
            self._tick()
            results = self._call(fn, [state, ctrl])
            if not results or results[0] is None:
                break
            ctrl = results[0]
            child = Environment(env)
            for i, nm in enumerate(stmt.names):
                child.set_local(nm, results[i] if i < len(results) else None)
            try:
                self._exec_block(stmt.body, child)
            except LuaInternalBreak:
                break
            except LuaInternalContinue:
                continue

    # ── expression evaluation ──

    def _eval(self, expr: ast.Expr, env: Environment) -> Any:
        self._tick()
        if isinstance(expr, ast.Nil):
            return None
        if isinstance(expr, ast.Bool):
            return expr.value
        if isinstance(expr, ast.Number):
            return expr.value
        if isinstance(expr, ast.String):
            return expr.value
        if isinstance(expr, ast.Name):
            return env.get(expr.name)
        if isinstance(expr, ast.Vararg):
            va = env.get('...')
            if isinstance(va, list) and va:
                return va[0]
            return None
        if isinstance(expr, ast.BinOp):
            return self._eval_binop(expr, env)
        if isinstance(expr, ast.UnOp):
            return self._eval_unop(expr, env)
        if isinstance(expr, ast.Concat):
            parts = [self._tostring(self._eval(v, env)) for v in expr.values]
            return ''.join(parts)
        if isinstance(expr, ast.Call):
            results = self._eval_call(expr, env)
            return results[0] if results else None
        if isinstance(expr, ast.MethodCall):
            results = self._eval_mcall(expr, env)
            return results[0] if results else None
        if isinstance(expr, ast.Index):
            t = self._eval(expr.table, env)
            k = self._eval(expr.key, env)
            return self._tbl_get(t, k)
        if isinstance(expr, ast.Field):
            t = self._eval(expr.table, env)
            return self._tbl_get(t, expr.name)
        if isinstance(expr, ast.FunctionExpr):
            return self._make_closure(expr, env)
        if isinstance(expr, ast.TableConstructor):
            return self._eval_table(expr, env)
        return None

    def _eval_multi(self, expr: ast.Expr, env: Environment) -> list:
        if isinstance(expr, ast.Call):
            return self._eval_call(expr, env)
        if isinstance(expr, ast.MethodCall):
            return self._eval_mcall(expr, env)
        if isinstance(expr, ast.Vararg):
            va = env.get('...')
            return list(va) if isinstance(va, list) else []
        return [self._eval(expr, env)]

    def _eval_list(self, exprs: list, env: Environment) -> list:
        results = []
        for i, e in enumerate(exprs):
            if i == len(exprs) - 1:
                results.extend(self._eval_multi(e, env))
            else:
                results.append(self._eval(e, env))
        return results

    def _eval_binop(self, expr: ast.BinOp, env: Environment) -> Any:
        op = expr.op
        if op == 'and':
            l = self._eval(expr.left, env)
            return self._eval(expr.right, env) if self._truthy(l) else l
        if op == 'or':
            l = self._eval(expr.left, env)
            return l if self._truthy(l) else self._eval(expr.right, env)

        l = self._eval(expr.left, env)
        r = self._eval(expr.right, env)

        if op == '+': return self._arith(l, r, op, lambda a, b: a + b)
        if op == '-': return self._arith(l, r, op, lambda a, b: a - b)
        if op == '*': return self._arith(l, r, op, lambda a, b: a * b)
        if op == '/': return self._arith(l, r, op, lambda a, b: a / b if b != 0 else math.copysign(math.inf, a * b) if a != 0 else float('nan'))
        if op == '%': return self._arith(l, r, op, lambda a, b: math.fmod(a, b) if b != 0 else float('nan'))
        if op == '^': return self._arith(l, r, op, lambda a, b: a ** b)
        if op == '//': return self._arith(l, r, op, lambda a, b: math.floor(a / b) if b != 0 else math.copysign(math.inf, a) if a != 0 else float('nan'))
        if op == '==': return self._eq(l, r)
        if op == '~=': return not self._eq(l, r)
        if op == '<': return self._lt(l, r)
        if op == '>': return self._lt(r, l)
        if op == '<=': return not self._lt(r, l)
        if op == '>=': return not self._lt(l, r)
        if op == '..':
            return self._tostring(l) + self._tostring(r)
        if op == '&': return self._bitop(l, r, lambda a, b: a & b)
        if op == '|': return self._bitop(l, r, lambda a, b: a | b)
        if op == '~': return self._bitop(l, r, lambda a, b: a ^ b)
        if op == '<<': return self._bitop(l, r, lambda a, b: (a << b) & 0xFFFFFFFF if b >= 0 else (a >> (-b)) & 0xFFFFFFFF)
        if op == '>>': return self._bitop(l, r, lambda a, b: (a >> b) & 0xFFFFFFFF if b >= 0 else (a << (-b)) & 0xFFFFFFFF)
        raise LuaError(f"unknown binop '{op}'")

    def _eval_unop(self, expr: ast.UnOp, env: Environment) -> Any:
        val = self._eval(expr.operand, env)
        op = expr.op
        if op == '-':
            n = self._trynum(val)
            if n is not None:
                return -n
            raise LuaError(f"attempt to perform arithmetic on a {self._type(val)} value")
        if op == '#':
            if isinstance(val, str):
                return len(val)
            if isinstance(val, LuaTable):
                return val.length()
            raise LuaError(f"attempt to get length of a {self._type(val)} value")
        if op == 'not':
            return not self._truthy(val)
        if op == '~':
            n = self._trynum(val)
            if n is not None:
                return (~int(n)) & 0xFFFFFFFF
            raise LuaError(f"attempt to perform bitwise operation on a {self._type(val)} value")
        raise LuaError(f"unknown unop '{op}'")

    def _eval_call(self, expr: ast.Call, env: Environment) -> list:
        func = self._eval(expr.func, env)
        args = self._eval_list(expr.args, env)
        return self._call(func, args)

    def _eval_mcall(self, expr: ast.MethodCall, env: Environment) -> list:
        obj = self._eval(expr.object, env)
        method = self._tbl_get(obj, expr.method)
        args = [obj] + self._eval_list(expr.args, env)
        return self._call(method, args)

    def _eval_table(self, expr: ast.TableConstructor, env: Environment) -> LuaTable:
        tbl = LuaTable()
        seq = 1
        for i, f in enumerate(expr.fields):
            if f.key is None:
                if i == len(expr.fields) - 1:
                    multi = self._eval_multi(f.value, env)
                    for v in multi:
                        tbl.rawset(seq, v)
                        seq += 1
                else:
                    tbl.rawset(seq, self._eval(f.value, env))
                    seq += 1
            else:
                k = self._eval(f.key, env)
                v = self._eval(f.value, env)
                tbl.rawset(k, v)
        return tbl

    def _call(self, func, args: list) -> list:
        if func is None:
            raise LuaError("attempt to call a nil value")
        if isinstance(func, LuaClosure):
            self._recursion += 1
            if self._recursion > self._max_recursion:
                self._recursion -= 1
                raise LuaError("stack overflow")
            try:
                result = func.func(*args)
                if isinstance(result, list):
                    return result
                if result is None:
                    return []
                return [result]
            finally:
                self._recursion -= 1
        if callable(func):
            result = func(*args)
            if isinstance(result, list):
                return result
            if result is None:
                return []
            return [result]
        if isinstance(func, LuaTable) and func.metatable:
            call_mm = func.metatable.rawget('__call')
            if call_mm:
                return self._call(call_mm, [func] + args)
        if self.tolerant:
            return []
        raise LuaError(f"attempt to call a {self._type(func)} value")

    def _make_closure(self, func_expr: ast.FunctionExpr, env: Environment, name: str = "?") -> LuaClosure:
        captured_env = env

        def lua_fn(*args):
            child = Environment(captured_env)
            for i, p in enumerate(func_expr.params):
                child.set_local(p, args[i] if i < len(args) else None)
            if func_expr.has_vararg:
                child.set_local('...', list(args[len(func_expr.params):]))
            try:
                self._exec_block(func_expr.body, child)
            except LuaInternalReturn as ret:
                return ret.values
            return []

        return LuaClosure(func=lua_fn, name=name)

    def _name_str(self, n: ast.Expr) -> str:
        if isinstance(n, ast.Name):
            return n.name
        if isinstance(n, ast.Field):
            return self._name_str(n.table) + '.' + n.name
        return "?"

    # ── table access with metamethods ──

    def _tbl_get(self, obj, key) -> Any:
        if isinstance(obj, LuaTable):
            v = obj.rawget(key)
            if v is not None:
                return v
            if obj.metatable:
                idx = obj.metatable.rawget('__index')
                if isinstance(idx, LuaTable):
                    return self._tbl_get(idx, key)
                if idx is not None:
                    r = self._call(idx, [obj, key])
                    return r[0] if r else None
            return None
        if isinstance(obj, str):
            str_mt = self._global.get('__string_mt')
            if isinstance(str_mt, LuaTable):
                v = str_mt.rawget(key)
                if v is not None:
                    return v
            return None
        if self.tolerant:
            return None
        raise LuaError(f"attempt to index a {self._type(obj)} value")

    def _tbl_set(self, obj, key, val):
        if isinstance(obj, LuaTable):
            if obj.metatable:
                ni = obj.metatable.rawget('__newindex')
                if ni is not None and obj.rawget(key) is None:
                    if isinstance(ni, LuaTable):
                        self._tbl_set(ni, key, val)
                        return
                    self._call(ni, [obj, key, val])
                    return
            obj.rawset(key, val)
            return
        if self.tolerant:
            return
        raise LuaError(f"attempt to index a {self._type(obj)} value")

    # ── type helpers ──

    def _truthy(self, v) -> bool:
        return v is not None and v is not False

    def _type(self, v) -> str:
        if v is None: return "nil"
        if isinstance(v, bool): return "boolean"
        if isinstance(v, (int, float)): return "number"
        if isinstance(v, str): return "string"
        if isinstance(v, LuaTable): return "table"
        if isinstance(v, LuaClosure) or callable(v): return "function"
        return "userdata"

    def _tostring(self, v) -> str:
        if v is None: return "nil"
        if isinstance(v, bool): return "true" if v else "false"
        if isinstance(v, float):
            if v == math.inf: return "inf"
            if v == -math.inf: return "-inf"
            if math.isnan(v): return "nan" if v != v else "nan"
            if v == int(v) and not math.isinf(v):
                return str(int(v))
            return f"{v:g}"
        if isinstance(v, int): return str(v)
        if isinstance(v, str): return v
        if isinstance(v, LuaTable):
            if v.metatable:
                ts = v.metatable.rawget('__tostring')
                if ts:
                    r = self._call(ts, [v])
                    return r[0] if r else "table"
            return repr(v)
        if isinstance(v, LuaClosure) or callable(v): return repr(v) if isinstance(v, LuaClosure) else f"function: 0x{id(v):016x}"
        return str(v)

    def _tonum(self, v) -> float:
        n = self._trynum(v)
        if n is not None:
            return float(n)
        raise LuaError(f"attempt to perform arithmetic on a {self._type(v)} value")

    def _trynum(self, v):
        if isinstance(v, (int, float)):
            return v
        if isinstance(v, str):
            v = v.strip()
            try:
                if v.startswith('0x') or v.startswith('0X'):
                    return int(v, 16)
                return float(v) if '.' in v or 'e' in v.lower() else int(v)
            except ValueError:
                return None
        return None

    def _eq(self, a, b) -> bool:
        if type(a) != type(b):
            if isinstance(a, (int, float)) and isinstance(b, (int, float)):
                return float(a) == float(b)
            return False
        return a == b

    def _lt(self, a, b) -> bool:
        if isinstance(a, (int, float)) and isinstance(b, (int, float)):
            return a < b
        if isinstance(a, str) and isinstance(b, str):
            return a < b
        raise LuaError(f"attempt to compare {self._type(a)} with {self._type(b)}")

    def _arith(self, a, b, op, fn):
        na, nb = self._trynum(a), self._trynum(b)
        if na is not None and nb is not None:
            try:
                return fn(na, nb)
            except (OverflowError, ZeroDivisionError):
                return float('nan')
        if isinstance(a, LuaTable) and a.metatable:
            mm = a.metatable.rawget('__' + {'+':"add",'-':"sub",'*':"mul",'/':"div",'%':"mod",'^':"pow",'//':"idiv"}.get(op, op))
            if mm:
                r = self._call(mm, [a, b])
                return r[0] if r else None
        raise LuaError(f"attempt to perform arithmetic on a {self._type(a if na is None else b)} value")

    def _bitop(self, a, b, fn):
        na, nb = self._trynum(a), self._trynum(b)
        if na is not None and nb is not None:
            return fn(int(na) & 0xFFFFFFFF, int(nb) & 0xFFFFFFFF)
        raise LuaError(f"attempt to perform bitwise operation on a {self._type(a)} value")

    # ── standard library setup ──

    def _setup_globals(self):
        g = self._global

        g.set_local('print', LuaClosure(func=self._lib_print, name='print'))
        g.set_local('warn', LuaClosure(func=self._lib_print, name='warn'))
        g.set_local('type', LuaClosure(func=lambda v=None: [self._type(v)], name='type'))
        g.set_local('typeof', LuaClosure(func=lambda v=None: [self._type(v)], name='typeof'))
        g.set_local('tostring', LuaClosure(func=lambda v=None: [self._tostring(v)], name='tostring'))
        g.set_local('tonumber', LuaClosure(func=self._lib_tonumber, name='tonumber'))
        g.set_local('error', LuaClosure(func=self._lib_error, name='error'))
        g.set_local('assert', LuaClosure(func=self._lib_assert, name='assert'))
        g.set_local('pcall', LuaClosure(func=self._lib_pcall, name='pcall'))
        g.set_local('xpcall', LuaClosure(func=self._lib_xpcall, name='xpcall'))
        g.set_local('select', LuaClosure(func=self._lib_select, name='select'))
        g.set_local('unpack', LuaClosure(func=self._lib_unpack, name='unpack'))
        g.set_local('ipairs', LuaClosure(func=self._lib_ipairs, name='ipairs'))
        g.set_local('pairs', LuaClosure(func=self._lib_pairs, name='pairs'))
        g.set_local('next', LuaClosure(func=self._lib_next, name='next'))
        g.set_local('rawget', LuaClosure(func=lambda t, k: [t.rawget(k) if isinstance(t, LuaTable) else None], name='rawget'))
        g.set_local('rawset', LuaClosure(func=self._lib_rawset, name='rawset'))
        g.set_local('rawequal', LuaClosure(func=lambda a, b: [a is b or a == b], name='rawequal'))
        g.set_local('rawlen', LuaClosure(func=lambda t: [t.length() if isinstance(t, LuaTable) else len(t) if isinstance(t, str) else 0], name='rawlen'))
        g.set_local('setmetatable', LuaClosure(func=self._lib_setmetatable, name='setmetatable'))
        g.set_local('getmetatable', LuaClosure(func=self._lib_getmetatable, name='getmetatable'))
        g.set_local('loadstring', LuaClosure(func=self._lib_loadstring, name='loadstring'))
        g.set_local('load', LuaClosure(func=self._lib_loadstring, name='load'))
        g.set_local('setfenv', LuaClosure(func=self._lib_setfenv, name='setfenv'))
        g.set_local('getfenv', LuaClosure(func=self._lib_getfenv, name='getfenv'))
        g.set_local('_VERSION', "Lua 5.1")

        self._setup_string_lib()
        self._setup_math_lib()
        self._setup_table_lib()
        self._setup_bit_lib()
        self._setup_coroutine_lib()
        self._current_coroutine = None

    def _lib_print(self, *args):
        s = '\t'.join(self._tostring(a) for a in args)
        self.output.append(s)
        return []

    def _lib_tonumber(self, v=None, base=None):
        if base is not None:
            try:
                return [int(str(v), int(base))]
            except (ValueError, TypeError):
                return [None]
        n = self._trynum(v)
        return [n]

    def _lib_error(self, msg=None, level=None):
        raise LuaError(self._tostring(msg) if msg is not None else "")

    def _lib_assert(self, v=None, *args):
        if not self._truthy(v):
            msg = args[0] if args else "assertion failed!"
            raise LuaError(self._tostring(msg))
        return [v] + list(args)

    def _lib_pcall(self, func=None, *args):
        try:
            r = self._call(func, list(args))
            return [True] + r
        except (LuaError, Exception) as e:
            return [False, str(e)]

    def _lib_xpcall(self, func=None, handler=None, *args):
        try:
            r = self._call(func, list(args))
            return [True] + r
        except (LuaError, Exception) as e:
            try:
                hr = self._call(handler, [str(e)])
                return [False] + hr
            except Exception:
                return [False, str(e)]

    def _lib_select(self, idx=None, *args):
        if idx == '#' or (isinstance(idx, str) and idx == '#'):
            return [len(args)]
        n = int(self._tonum(idx))
        if n < 0:
            n = len(args) + n + 1
        if n < 1:
            n = 1
        return list(args[n - 1:])

    def _lib_unpack(self, tbl=None, i=None, j=None):
        if not isinstance(tbl, LuaTable):
            raise LuaError("bad argument #1 to 'unpack' (table expected)")
        start = int(i) if i is not None else 1
        end = int(j) if j is not None else tbl.length()
        return [tbl.rawget(k) for k in range(start, end + 1)]

    def _lib_ipairs(self, tbl=None):
        idx_box = [0]
        def _iter(t=None, _=None):
            idx_box[0] += 1
            v = tbl.rawget(idx_box[0]) if isinstance(tbl, LuaTable) else None
            if v is None:
                return [None]
            return [idx_box[0], v]
        return [LuaClosure(func=_iter, name='ipairs_iter'), tbl, 0]

    def _lib_pairs(self, tbl=None):
        def _iter(t=None, k=None):
            if not isinstance(tbl, LuaTable):
                return [None]
            nk, nv = tbl.next_pair(k)
            if nk is None:
                return [None]
            return [nk, nv]
        return [LuaClosure(func=_iter, name='pairs_iter'), tbl, None]

    def _lib_next(self, tbl=None, key=None):
        if not isinstance(tbl, LuaTable):
            raise LuaError("bad argument #1 to 'next' (table expected)")
        k, v = tbl.next_pair(key)
        if k is None:
            return [None]
        return [k, v]

    def _lib_rawset(self, tbl=None, key=None, val=None):
        if isinstance(tbl, LuaTable):
            tbl.rawset(key, val)
        return [tbl]

    def _lib_setmetatable(self, tbl=None, mt=None):
        if isinstance(tbl, LuaTable):
            tbl.metatable = mt if isinstance(mt, LuaTable) else None
        return [tbl]

    def _lib_getmetatable(self, tbl=None):
        if isinstance(tbl, LuaTable) and tbl.metatable:
            mt_field = tbl.metatable.rawget('__metatable')
            if mt_field is not None:
                return [mt_field]
            return [tbl.metatable]
        return [None]

    def _lib_loadstring(self, src=None, *_args):
        if not isinstance(src, str):
            return [None, "string expected"]
        self.intercepted_loads.append(src)
        try:
            tree = lua_parse(src)
        except Exception as e:
            return [None, str(e)]
        captured_env = self._global

        def loaded(*args):
            env = Environment(captured_env)
            if args:
                env.set_local('...', list(args))
            try:
                self._exec_block(tree, env)
            except LuaInternalReturn as r:
                return r.values
            return []

        return [LuaClosure(func=loaded, name='(loaded)')]

    def _lib_setfenv(self, f=None, env=None):
        if isinstance(env, LuaTable):
            self._fenv_table = env
        return [f]

    def _lib_getfenv(self, f=None):
        if hasattr(self, '_fenv_table') and self._fenv_table is not None:
            return [self._fenv_table]
        tbl = LuaTable()
        for k, v in self._global.vars.items():
            tbl.rawset(k, v)
        self._fenv_table = tbl
        return [tbl]

    # ── string library ──

    def _setup_string_lib(self):
        st = LuaTable()
        fns = {
            'byte': self._str_byte, 'char': self._str_char,
            'sub': self._str_sub, 'rep': self._str_rep,
            'reverse': self._str_reverse, 'len': self._str_len,
            'lower': self._str_lower, 'upper': self._str_upper,
            'format': self._str_format, 'find': self._str_find,
            'match': self._str_match, 'gmatch': self._str_gmatch,
            'gsub': self._str_gsub, 'dump': self._str_dump,
            'split': self._str_split,
            'unpack': self._str_unpack,
            'pack': self._str_pack,
            'packsize': self._str_packsize,
        }
        for name, fn in fns.items():
            st.rawset(name, LuaClosure(func=fn, name=f'string.{name}'))
        self._global.set_local('string', st)

        idx_tbl = LuaTable()
        idx_tbl.rawset('__index', st)
        self._global.set_local('__string_mt', idx_tbl)

    def _str_byte(self, s=None, i=None, j=None):
        if not isinstance(s, str): return [None]
        i = int(i) if i is not None else 1
        j = int(j) if j is not None else i
        if i < 0: i = len(s) + i + 1
        if j < 0: j = len(s) + j + 1
        return [ord(s[k - 1]) for k in range(i, j + 1) if 1 <= k <= len(s)]

    def _str_char(self, *args):
        try:
            return [''.join(chr(int(a)) for a in args)]
        except (ValueError, TypeError):
            return ['']

    def _str_sub(self, s=None, i=None, j=None):
        if not isinstance(s, str): return ['']
        i = int(i) if i is not None else 1
        j = int(j) if j is not None else -1
        if i < 0: i = max(len(s) + i + 1, 1)
        if j < 0: j = len(s) + j + 1
        if i < 1: i = 1
        return [s[i - 1:j]]

    def _str_rep(self, s=None, n=None, sep=None):
        if not isinstance(s, str): return ['']
        n = int(n) if n is not None else 0
        if n <= 0: return ['']
        if sep and isinstance(sep, str):
            return [sep.join([s] * n)]
        return [s * n]

    def _str_reverse(self, s=None):
        return [s[::-1] if isinstance(s, str) else '']

    def _str_len(self, s=None):
        return [len(s) if isinstance(s, str) else 0]

    def _str_lower(self, s=None):
        return [s.lower() if isinstance(s, str) else '']

    def _str_upper(self, s=None):
        return [s.upper() if isinstance(s, str) else '']

    def _str_format(self, fmt=None, *args):
        if not isinstance(fmt, str): return ['']
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
                spec_start = i - 1
                while i < len(fmt) and fmt[i] in '-+ #0':
                    i += 1
                while i < len(fmt) and fmt[i].isdigit():
                    i += 1
                if i < len(fmt) and fmt[i] == '.':
                    i += 1
                    while i < len(fmt) and fmt[i].isdigit():
                        i += 1
                if i < len(fmt):
                    conv = fmt[i]
                    i += 1
                    arg = args[ai] if ai < len(args) else None
                    ai += 1
                    if conv == 'd' or conv == 'i':
                        result.append(str(int(self._tonum(arg))) if arg is not None else '0')
                    elif conv == 'f' or conv == 'F':
                        spec = fmt[spec_start:i]
                        try:
                            result.append(spec % float(self._tonum(arg) if arg is not None else 0))
                        except Exception:
                            result.append('0')
                    elif conv == 'e' or conv == 'E' or conv == 'g' or conv == 'G':
                        spec = fmt[spec_start:i]
                        try:
                            result.append(spec % float(self._tonum(arg) if arg is not None else 0))
                        except Exception:
                            result.append('0')
                    elif conv == 's':
                        result.append(self._tostring(arg))
                    elif conv == 'q':
                        result.append('"' + self._tostring(arg).replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n').replace('\r', '\\r').replace('\0', '\\0') + '"')
                    elif conv == 'x' or conv == 'X':
                        val = int(self._tonum(arg)) if arg is not None else 0
                        result.append(format(val & 0xFFFFFFFF, 'x' if conv == 'x' else 'X'))
                    elif conv == 'o':
                        result.append(format(int(self._tonum(arg)) if arg is not None else 0, 'o'))
                    elif conv == 'c':
                        result.append(chr(int(self._tonum(arg)) & 0xFF) if arg is not None else '\0')
                    elif conv == 'u':
                        result.append(str(int(self._tonum(arg)) & 0xFFFFFFFF) if arg is not None else '0')
                    else:
                        result.append(fmt[spec_start:i])
            else:
                result.append(fmt[i])
                i += 1
        return [''.join(result)]

    def _str_find(self, s=None, pattern=None, init=None, plain=None):
        if not isinstance(s, str) or not isinstance(pattern, str):
            return [None]
        init = int(init) - 1 if init is not None else 0
        if init < 0: init = max(len(s) + init + 1, 0)
        if plain:
            idx = s.find(pattern, init)
            if idx == -1: return [None]
            return [idx + 1, idx + len(pattern)]
        try:
            py_pat = self._lua_pattern_to_re(pattern)
            m = re.search(py_pat, s[init:])
            if not m: return [None]
            return [m.start() + init + 1, m.end() + init] + list(m.groups())
        except re.error:
            idx = s.find(pattern, init)
            if idx == -1: return [None]
            return [idx + 1, idx + len(pattern)]

    def _str_match(self, s=None, pattern=None, init=None):
        if not isinstance(s, str) or not isinstance(pattern, str):
            return [None]
        init = int(init) - 1 if init is not None else 0
        if init < 0: init = max(len(s) + init + 1, 0)
        try:
            py_pat = self._lua_pattern_to_re(pattern)
            m = re.search(py_pat, s[init:])
            if not m: return [None]
            groups = m.groups()
            return list(groups) if groups else [m.group()]
        except re.error:
            return [None]

    def _str_gmatch(self, s=None, pattern=None):
        if not isinstance(s, str) or not isinstance(pattern, str):
            return [LuaClosure(func=lambda: [None], name='gmatch_iter')]
        try:
            py_pat = self._lua_pattern_to_re(pattern)
            matches = list(re.finditer(py_pat, s))
        except re.error:
            matches = []
        idx_box = [0]
        def _iter(*_):
            if idx_box[0] >= len(matches):
                return [None]
            m = matches[idx_box[0]]
            idx_box[0] += 1
            groups = m.groups()
            return list(groups) if groups else [m.group()]
        return [LuaClosure(func=_iter, name='gmatch_iter')]

    def _str_gsub(self, s=None, pattern=None, repl=None, n=None):
        if not isinstance(s, str) or not isinstance(pattern, str):
            return [s or '', 0]
        max_n = int(n) if n is not None else len(s) + 1
        try:
            py_pat = self._lua_pattern_to_re(pattern)
        except re.error:
            return [s, 0]
        count = [0]
        def _repl_fn(m):
            if count[0] >= max_n:
                return m.group()
            count[0] += 1
            if isinstance(repl, str):
                result = []
                i = 0
                while i < len(repl):
                    if repl[i] == '%' and i + 1 < len(repl):
                        c = repl[i + 1]
                        if c.isdigit():
                            gi = int(c)
                            try:
                                result.append(m.group(gi) or '')
                            except IndexError:
                                result.append('')
                            i += 2
                        else:
                            result.append(c)
                            i += 2
                    else:
                        result.append(repl[i])
                        i += 1
                return ''.join(result)
            if isinstance(repl, LuaTable):
                key = m.groups()[0] if m.groups() else m.group()
                v = repl.rawget(key)
                return self._tostring(v) if v is not None and v is not False else m.group()
            if callable(repl) or isinstance(repl, LuaClosure):
                args = list(m.groups()) if m.groups() else [m.group()]
                r = self._call(repl, args)
                v = r[0] if r else None
                return self._tostring(v) if v is not None and v is not False else m.group()
            return self._tostring(repl)
        result = re.sub(py_pat, _repl_fn, s)
        return [result, count[0]]

    def _str_dump(self, *args):
        return ['']

    def _str_split(self, s=None, sep=None):
        if not isinstance(s, str):
            return [LuaTable()]
        if sep is None or sep == '':
            parts = list(s)
        else:
            parts = s.split(sep)
        tbl = LuaTable()
        for i, p in enumerate(parts):
            tbl.rawset(i + 1, p)
        return [tbl]

    def _parse_pack_fmt(self, fmt):
        import struct as _struct
        items = []
        i = 0
        endian = '<'
        while i < len(fmt):
            c = fmt[i]
            if c in '<>=!':
                endian = c if c != '!' else '='
                i += 1
                continue
            if c == 'x':
                items.append((endian, 'x', 1, None))
                i += 1
                continue
            if c == 'X':
                i += 1
                continue
            if c in 'bBhHlLjJnfdT':
                sz_map = {'b': 1, 'B': 1, 'h': 2, 'H': 2, 'l': 8, 'L': 8,
                          'j': 8, 'J': 8, 'n': 8, 'f': 4, 'd': 8, 'T': 8}
                fmt_map = {'b': 'b', 'B': 'B', 'h': 'h', 'H': 'H', 'l': 'q', 'L': 'Q',
                           'j': 'q', 'J': 'Q', 'n': 'd', 'f': 'f', 'd': 'd', 'T': 'Q'}
                sz = sz_map[c]
                sf = fmt_map[c]
                items.append((endian, sf, sz, c))
                i += 1
                continue
            if c in 'iI':
                i += 1
                n = 0
                while i < len(fmt) and fmt[i].isdigit():
                    n = n * 10 + int(fmt[i])
                    i += 1
                if n == 0:
                    n = 4
                sz_to_fmt = {1: ('b', 'B'), 2: ('h', 'H'), 4: ('i', 'I'), 8: ('q', 'Q')}
                if n in sz_to_fmt:
                    sf = sz_to_fmt[n][0 if c == 'i' else 1]
                else:
                    sf = sz_to_fmt[4][0 if c == 'i' else 1]
                    n = 4
                items.append((endian, sf, n, c))
                continue
            if c == 's':
                i += 1
                n = 0
                while i < len(fmt) and fmt[i].isdigit():
                    n = n * 10 + int(fmt[i])
                    i += 1
                if n == 0:
                    n = 8
                items.append((endian, 's', n, 's'))
                continue
            if c == 'z':
                items.append((endian, 'z', 0, 'z'))
                i += 1
                continue
            i += 1
        return items

    def _str_unpack(self, fmt=None, s=None, pos=None):
        import struct as _struct
        if not isinstance(fmt, str) or not isinstance(s, str):
            raise LuaError("bad argument to 'string.unpack'")
        if pos is None:
            pos = 1
        pos = int(pos)
        offset = pos - 1
        raw = bytes(ord(c) & 0xFF for c in s)
        items = self._parse_pack_fmt(fmt)
        results = []
        for endian, sf, sz, orig in items:
            if sf == 'x':
                offset += 1
                continue
            if sf == 'z':
                end = raw.find(b'\x00', offset)
                if end < 0:
                    end = len(raw)
                results.append(raw[offset:end].decode('latin-1'))
                offset = end + 1
                continue
            if sf == 's':
                e = '<' if endian == '<' else '>'
                sz_to_ufmt = {1: 'B', 2: 'H', 4: 'I', 8: 'Q'}
                uf = sz_to_ufmt.get(sz, 'Q')
                slen = _struct.unpack_from(e + uf, raw, offset)[0]
                offset += sz
                results.append(raw[offset:offset + slen].decode('latin-1'))
                offset += slen
                continue
            e = '<' if endian == '<' else '>'
            try:
                val = _struct.unpack_from(e + sf, raw, offset)[0]
            except _struct.error:
                val = 0
            results.append(val)
            offset += sz
        results.append(offset + 1)
        return results

    def _str_pack(self, fmt=None, *args):
        import struct as _struct
        if not isinstance(fmt, str):
            raise LuaError("bad argument to 'string.pack'")
        items = self._parse_pack_fmt(fmt)
        result = b''
        ai = 0
        for endian, sf, sz, orig in items:
            if sf == 'x':
                result += b'\x00'
                continue
            if sf == 'z':
                v = str(args[ai]) if ai < len(args) else ''
                ai += 1
                result += v.encode('latin-1') + b'\x00'
                continue
            if sf == 's':
                v = str(args[ai]) if ai < len(args) else ''
                ai += 1
                vb = v.encode('latin-1')
                e = '<' if endian == '<' else '>'
                sz_to_ufmt = {1: 'B', 2: 'H', 4: 'I', 8: 'Q'}
                uf = sz_to_ufmt.get(sz, 'Q')
                result += _struct.pack(e + uf, len(vb)) + vb
                continue
            e = '<' if endian == '<' else '>'
            v = args[ai] if ai < len(args) else 0
            ai += 1
            if sf in 'bBhHiIqQ':
                v = int(self._tonum(v))
            else:
                v = float(self._tonum(v))
            try:
                result += _struct.pack(e + sf, v)
            except _struct.error:
                result += b'\x00' * sz
        return [result.decode('latin-1')]

    def _str_packsize(self, fmt=None):
        if not isinstance(fmt, str):
            return [0]
        items = self._parse_pack_fmt(fmt)
        total = 0
        for endian, sf, sz, orig in items:
            if sf == 'z' or sf == 's':
                raise LuaError("variable-size format in packsize")
            total += sz if sf == 'x' else sz
        return [total]

    def _lua_pattern_to_re(self, pattern: str) -> str:
        char_classes = {
            '%a': '[a-zA-Z]', '%A': '[^a-zA-Z]',
            '%d': '[0-9]', '%D': '[^0-9]',
            '%l': '[a-z]', '%L': '[^a-z]',
            '%u': '[A-Z]', '%U': '[^A-Z]',
            '%w': '[a-zA-Z0-9]', '%W': '[^a-zA-Z0-9]',
            '%s': '[ \\t\\n\\r\\f\\v]', '%S': '[^ \\t\\n\\r\\f\\v]',
            '%p': '[^a-zA-Z0-9\\s]', '%P': '[a-zA-Z0-9\\s]',
            '%c': '[\\x00-\\x1f\\x7f]', '%C': '[^\\x00-\\x1f\\x7f]',
        }
        result = []
        i = 0
        n = len(pattern)
        if i < n and pattern[i] == '^':
            result.append('^')
            i += 1
        while i < n:
            c = pattern[i]
            if c == '%' and i + 1 < n:
                pair = pattern[i:i + 2]
                if pair in char_classes:
                    result.append(char_classes[pair])
                    i += 2
                elif pattern[i + 1] == 'b' and i + 3 < n:
                    result.append(re.escape(pattern[i + 2]))
                    i += 4
                else:
                    result.append(re.escape(pattern[i + 1]))
                    i += 2
            elif c == '[':
                j = i + 1
                cls = '['
                if j < n and pattern[j] == '^':
                    cls += '^'
                    j += 1
                while j < n and pattern[j] != ']':
                    if pattern[j] == '%' and j + 1 < n:
                        pair = pattern[j:j + 2]
                        if pair in char_classes:
                            inner = char_classes[pair]
                            cls += inner[1:-1]
                        else:
                            cls += re.escape(pattern[j + 1])
                        j += 2
                    else:
                        if pattern[j] in '.^$*+?{}\\|()':
                            cls += '\\' + pattern[j]
                        else:
                            cls += pattern[j]
                        j += 1
                if j < n:
                    j += 1
                cls += ']'
                result.append(cls)
                i = j
            elif c == '$' and i == n - 1:
                result.append('$')
                i += 1
            elif c in '.^$*+?{}\\|()':
                if c == '-':
                    result.append('*?')
                else:
                    result.append(re.escape(c))
                i += 1
            elif c == '-':
                result.append('*?')
                i += 1
            else:
                result.append(c)
                i += 1
        return ''.join(result)

    # ── math library ──

    def _setup_math_lib(self):
        mt = LuaTable()
        consts = {'pi': math.pi, 'huge': math.inf, 'maxinteger': 2**53, 'mininteger': -(2**53)}
        for k, v in consts.items():
            mt.rawset(k, v)

        one_arg = {
            'abs': abs, 'ceil': math.ceil, 'floor': math.floor,
            'sqrt': math.sqrt, 'sin': math.sin, 'cos': math.cos,
            'tan': math.tan, 'asin': math.asin, 'acos': math.acos,
            'atan': math.atan, 'exp': math.exp, 'log': math.log,
            'rad': math.radians, 'deg': math.degrees,
        }
        for name, fn in one_arg.items():
            _fn = fn
            mt.rawset(name, LuaClosure(func=lambda x=None, _f=_fn: [_f(self._tonum(x)) if x is not None else None], name=f'math.{name}'))

        mt.rawset('max', LuaClosure(func=lambda *a: [max(a, key=lambda v: self._tonum(v) if v is not None else float('-inf'))] if a else [None], name='math.max'))
        mt.rawset('min', LuaClosure(func=lambda *a: [min(a, key=lambda v: self._tonum(v) if v is not None else float('inf'))] if a else [None], name='math.min'))
        mt.rawset('fmod', LuaClosure(func=lambda x=None, y=None: [math.fmod(self._tonum(x), self._tonum(y))], name='math.fmod'))
        mt.rawset('pow', LuaClosure(func=lambda x=None, y=None: [self._tonum(x) ** self._tonum(y)], name='math.pow'))
        mt.rawset('random', LuaClosure(func=self._math_random, name='math.random'))
        mt.rawset('randomseed', LuaClosure(func=lambda *_: [], name='math.randomseed'))
        mt.rawset('clamp', LuaClosure(func=lambda x=0, lo=0, hi=1: [max(self._tonum(lo), min(self._tonum(hi), self._tonum(x)))], name='math.clamp'))
        mt.rawset('sign', LuaClosure(func=lambda x=0: [1 if self._tonum(x) > 0 else -1 if self._tonum(x) < 0 else 0], name='math.sign'))
        mt.rawset('round', LuaClosure(func=lambda x=0: [round(self._tonum(x))], name='math.round'))
        mt.rawset('noise', LuaClosure(func=lambda *_: [0.0], name='math.noise'))
        self._global.set_local('math', mt)

    def _math_random(self, m=None, n=None):
        import random
        if m is None:
            return [random.random()]
        m = int(self._tonum(m))
        if n is None:
            return [random.randint(1, m)]
        return [random.randint(m, int(self._tonum(n)))]

    # ── table library ──

    def _setup_table_lib(self):
        tt = LuaTable()
        tt.rawset('insert', LuaClosure(func=self._tbl_insert, name='table.insert'))
        tt.rawset('remove', LuaClosure(func=self._tbl_remove, name='table.remove'))
        tt.rawset('sort', LuaClosure(func=self._tbl_sort, name='table.sort'))
        tt.rawset('concat', LuaClosure(func=self._tbl_concat, name='table.concat'))
        tt.rawset('unpack', LuaClosure(func=self._lib_unpack, name='table.unpack'))
        tt.rawset('move', LuaClosure(func=self._tbl_move, name='table.move'))
        tt.rawset('create', LuaClosure(func=self._tbl_create, name='table.create'))
        tt.rawset('find', LuaClosure(func=self._tbl_find, name='table.find'))
        tt.rawset('clear', LuaClosure(func=self._tbl_clear, name='table.clear'))
        tt.rawset('freeze', LuaClosure(func=lambda t: [t], name='table.freeze'))
        tt.rawset('isfrozen', LuaClosure(func=lambda t: [False], name='table.isfrozen'))
        tt.rawset('clone', LuaClosure(func=self._tbl_clone, name='table.clone'))
        tt.rawset('pack', LuaClosure(func=self._tbl_pack, name='table.pack'))
        self._global.set_local('table', tt)

    def _tbl_insert(self, tbl=None, *args):
        if not isinstance(tbl, LuaTable): return []
        if len(args) == 1:
            tbl.array.append(args[0])
        elif len(args) >= 2:
            pos = int(self._tonum(args[0])) - 1
            tbl.array.insert(pos, args[1])
        return []

    def _tbl_remove(self, tbl=None, pos=None):
        if not isinstance(tbl, LuaTable): return [None]
        if pos is None:
            if tbl.array:
                return [tbl.array.pop()]
            return [None]
        p = int(self._tonum(pos)) - 1
        if 0 <= p < len(tbl.array):
            return [tbl.array.pop(p)]
        return [None]

    def _tbl_sort(self, tbl=None, comp=None):
        if not isinstance(tbl, LuaTable): return []
        if comp:
            import functools
            def cmp(a, b):
                r = self._call(comp, [a, b])
                return -1 if (r and self._truthy(r[0])) else 1
            tbl.array.sort(key=functools.cmp_to_key(cmp))
        else:
            tbl.array.sort(key=lambda x: (0, x) if isinstance(x, (int, float)) else (1, str(x) if x else ''))
        return []

    def _tbl_concat(self, tbl=None, sep=None, i=None, j=None):
        if not isinstance(tbl, LuaTable): return ['']
        sep = sep if isinstance(sep, str) else ''
        start = int(i) if i is not None else 1
        end = int(j) if j is not None else tbl.length()
        parts = []
        for k in range(start, end + 1):
            v = tbl.rawget(k)
            parts.append(self._tostring(v) if v is not None else '')
        return [sep.join(parts)]

    def _tbl_move(self, a1=None, f=None, e=None, t=None, a2=None):
        if a2 is None: a2 = a1
        if not isinstance(a1, LuaTable) or not isinstance(a2, LuaTable): return [a2]
        f, e, t = int(self._tonum(f)), int(self._tonum(e)), int(self._tonum(t))
        for i in range(f, e + 1):
            a2.rawset(t + (i - f), a1.rawget(i))
        return [a2]

    def _tbl_create(self, n=None, val=None):
        tbl = LuaTable()
        if n is not None:
            cnt = int(self._tonum(n))
            for i in range(cnt):
                tbl.array.append(val)
        return [tbl]

    def _tbl_find(self, tbl=None, val=None, init=None):
        if not isinstance(tbl, LuaTable): return [None]
        start = int(init) if init is not None else 1
        for i in range(start - 1, len(tbl.array)):
            if self._eq(tbl.array[i], val):
                return [i + 1]
        return [None]

    def _tbl_clear(self, tbl=None):
        if isinstance(tbl, LuaTable):
            tbl.array.clear()
            tbl.hash.clear()
        return []

    def _tbl_clone(self, tbl=None):
        if not isinstance(tbl, LuaTable): return [tbl]
        new = LuaTable()
        new.array = list(tbl.array)
        new.hash = dict(tbl.hash)
        return [new]

    def _tbl_pack(self, *args):
        tbl = LuaTable()
        for i, a in enumerate(args):
            tbl.rawset(i + 1, a)
        tbl.rawset('n', len(args))
        return [tbl]

    # ── bit32 / bit library ──

    def _setup_bit_lib(self):
        bt = LuaTable()
        m32 = 0xFFFFFFFF
        bt.rawset('band', LuaClosure(func=lambda *a: [self._bit_reduce(a, lambda x, y: x & y, m32)], name='bit32.band'))
        bt.rawset('bor', LuaClosure(func=lambda *a: [self._bit_reduce(a, lambda x, y: x | y, 0)], name='bit32.bor'))
        bt.rawset('bxor', LuaClosure(func=lambda *a: [self._bit_reduce(a, lambda x, y: x ^ y, 0)], name='bit32.bxor'))
        bt.rawset('bnot', LuaClosure(func=lambda x=0: [(~int(self._tonum(x))) & m32], name='bit32.bnot'))
        bt.rawset('lshift', LuaClosure(func=lambda x=0, n=0: [(int(self._tonum(x)) << int(self._tonum(n))) & m32], name='bit32.lshift'))
        bt.rawset('rshift', LuaClosure(func=lambda x=0, n=0: [(int(self._tonum(x)) & m32) >> int(self._tonum(n))], name='bit32.rshift'))
        bt.rawset('arshift', LuaClosure(func=self._bit_arshift, name='bit32.arshift'))
        bt.rawset('lrotate', LuaClosure(func=self._bit_lrotate, name='bit32.lrotate'))
        bt.rawset('rrotate', LuaClosure(func=self._bit_rrotate, name='bit32.rrotate'))
        bt.rawset('btest', LuaClosure(func=lambda *a: [self._bit_reduce(a, lambda x, y: x & y, m32) != 0], name='bit32.btest'))
        bt.rawset('extract', LuaClosure(func=self._bit_extract, name='bit32.extract'))
        bt.rawset('replace', LuaClosure(func=self._bit_replace, name='bit32.replace'))
        bt.rawset('countrz', LuaClosure(func=self._bit_countrz, name='bit32.countrz'))
        bt.rawset('countlz', LuaClosure(func=self._bit_countlz, name='bit32.countlz'))
        self._global.set_local('bit32', bt)
        self._global.set_local('bit', bt)

    def _bit_reduce(self, args, fn, init):
        r = init
        for a in args:
            r = fn(r, int(self._tonum(a)) & 0xFFFFFFFF)
        return r & 0xFFFFFFFF

    def _bit_arshift(self, x=0, n=0):
        x = int(self._tonum(x)) & 0xFFFFFFFF
        n = int(self._tonum(n))
        if x & 0x80000000:
            x = x | ~0xFFFFFFFF
        return [(x >> n) & 0xFFFFFFFF]

    def _bit_lrotate(self, x=0, n=0):
        x = int(self._tonum(x)) & 0xFFFFFFFF
        n = int(self._tonum(n)) % 32
        return [((x << n) | (x >> (32 - n))) & 0xFFFFFFFF]

    def _bit_rrotate(self, x=0, n=0):
        x = int(self._tonum(x)) & 0xFFFFFFFF
        n = int(self._tonum(n)) % 32
        return [((x >> n) | (x << (32 - n))) & 0xFFFFFFFF]

    def _bit_extract(self, n=0, field=0, width=None):
        n = int(self._tonum(n)) & 0xFFFFFFFF
        f = int(self._tonum(field))
        w = int(self._tonum(width)) if width is not None else 1
        mask = (1 << w) - 1
        return [(n >> f) & mask]

    def _bit_replace(self, n=0, v=0, field=0, width=None):
        n_val = int(self._tonum(n)) & 0xFFFFFFFF
        v_val = int(self._tonum(v))
        f = int(self._tonum(field))
        w = int(self._tonum(width)) if width is not None else 1
        mask = ((1 << w) - 1) << f
        return [(n_val & ~mask) | ((v_val << f) & mask)]

    def _bit_countrz(self, x=0):
        x = int(self._tonum(x)) & 0xFFFFFFFF
        if x == 0:
            return [32]
        count = 0
        while (x & 1) == 0:
            count += 1
            x >>= 1
        return [count]

    def _bit_countlz(self, x=0):
        x = int(self._tonum(x)) & 0xFFFFFFFF
        if x == 0:
            return [32]
        count = 0
        while (x & 0x80000000) == 0:
            count += 1
            x <<= 1
        return [count]

    # ── coroutine library ──

    def _setup_coroutine_lib(self):
        co = LuaTable()
        co.rawset('create', LuaClosure(func=self._co_create, name='coroutine.create'))
        co.rawset('resume', LuaClosure(func=self._co_resume, name='coroutine.resume'))
        co.rawset('yield', LuaClosure(func=self._co_yield, name='coroutine.yield'))
        co.rawset('wrap', LuaClosure(func=self._co_wrap, name='coroutine.wrap'))
        co.rawset('status', LuaClosure(func=self._co_status, name='coroutine.status'))
        co.rawset('isyieldable', LuaClosure(func=lambda: [self._current_coroutine is not None], name='coroutine.isyieldable'))
        self._global.set_local('coroutine', co)

    def _co_create(self, f=None):
        if not isinstance(f, LuaClosure):
            raise LuaError("bad argument #1 to 'coroutine.create' (function expected)")
        return [LuaCoroutine(self, f)]

    def _co_resume(self, co=None, *args):
        if not isinstance(co, LuaCoroutine):
            raise LuaError("bad argument #1 to 'coroutine.resume' (coroutine expected)")
        return co.resume(list(args))

    def _co_yield(self, *args):
        co = self._current_coroutine
        if co is None:
            raise LuaError("cannot yield from main thread")
        resumed_args = co.do_yield(list(args))
        return resumed_args

    def _co_wrap(self, f=None):
        if not isinstance(f, LuaClosure):
            raise LuaError("bad argument #1 to 'coroutine.wrap' (function expected)")
        co = LuaCoroutine(self, f)
        def wrapped(*args):
            result = co.resume(list(args))
            if not result or not result[0]:
                err_msg = result[1] if len(result) > 1 else "cannot resume dead coroutine"
                raise LuaError(str(err_msg))
            return result[1:]
        return [LuaClosure(func=wrapped, name='wrapped_coroutine')]

    def _co_status(self, co=None):
        if isinstance(co, LuaCoroutine):
            return [co.status]
        return ['dead']
