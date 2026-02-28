"""
Luraph v14.7 Source Reconstructor
Traces execution through JMP dispatch, filters noise, builds expressions.
"""
import json, re
from collections import defaultdict

protos_raw = json.load(open('all_protos_data.json'))
opcode_map = json.load(open('opcode_map_final.json'))
constants_raw = json.load(open('luraph_strings_full.json', encoding='utf-8'))
try:
    operand_info = json.load(open('operand_map.json'))
except:
    operand_info = {}

constants = {}
for k, v in constants_raw.items():
    idx = int(k)
    if v.get('type') == 'n':
        constants[idx] = v.get('val', 0)
    elif v.get('type') == 's':
        constants[idx] = v.get('text', '')
    elif v.get('type') == 'b':
        constants[idx] = v.get('val', False)

NOISE = {'CLOSE', 'DISPATCH', 'FRAGMENT', 'RANGE', 'ARITH', 'UNKNOWN'}

def resolve_const(raw):
    if not raw:
        return None
    if isinstance(raw, str):
        if raw.startswith('n:'):
            return int(raw[2:])
        elif raw.startswith('x:'):
            return raw[2:]
        elif raw.startswith('t:'):
            parts = raw.split(':')
            if len(parts) >= 3 and parts[1] != '?':
                cidx = int(parts[1])
                if cidx in constants:
                    return constants[cidx]
    elif isinstance(raw, (int, float)):
        cidx = int(raw) // 4
        if cidx in constants:
            return constants[cidx]
    return None

def lua_val(v):
    if v is None:
        return None
    if isinstance(v, str):
        return repr(v)
    if isinstance(v, bool):
        return 'true' if v else 'false'
    if isinstance(v, float) and v == int(v):
        return str(int(v))
    return str(v)


class Inst:
    __slots__ = ['pc','op','cat','var','D','a','Z','q','w','m','nr']
    def __init__(self, pc, op, cat, var, D, a, Z, q, w, m, nr):
        self.pc, self.op, self.cat, self.var = pc, op, cat, var
        self.D, self.a, self.Z = D, a, Z
        self.q = resolve_const(q)
        self.w = resolve_const(w)
        self.m = resolve_const(m)
        self.nr = nr

    def valid(self, v):
        return 0 <= v < self.nr

    def dest(self):
        oi = operand_info.get(str(self.op), {})
        for key in ('dest', 'getglobal_dest', 'arith_dest', 'move_dest'):
            d = oi.get(key)
            if d:
                v = {'D': self.D, 'a': self.a, 'Z': self.Z}.get(d, self.D)
                if self.valid(v):
                    return v
        for v in [self.D, self.a, self.Z]:
            if self.valid(v):
                return v
        return self.D

    def jmp_target(self):
        oi = operand_info.get(str(self.op), {})
        jt = oi.get('jump_target')
        if jt:
            return {'D': self.D, 'a': self.a, 'Z': self.Z}.get(jt, self.D)
        return self.D

    def global_name(self):
        v = opcode_map.get(str(self.op), {}).get('variant', '')
        if v.startswith('GETGLOBAL(') and v.endswith(')'):
            return v[10:-1]
        return None

    def const(self):
        for c in [self.q, self.w, self.m]:
            if c is not None:
                return c
        return None


def parse_proto(idx, raw):
    c4 = raw.get('C4', [])
    c7, c8, c9 = raw.get('C7', []), raw.get('C8', []), raw.get('C9', [])
    c2 = raw.get('C2_sparse', {})
    c6 = raw.get('C6_sparse', {})
    c11 = raw.get('C11_sparse', {})
    nr = raw.get('C10', 0)
    insts = []
    for i in range(len(c4)):
        op = c4[i]
        info = opcode_map.get(str(op), {})
        cat = info.get('lua51', 'UNKNOWN')
        var = info.get('variant', '')
        D = c7[i] if i < len(c7) else 0
        a = c8[i] if i < len(c8) else 0
        Z = c9[i] if i < len(c9) else 0
        q = c2.get(str(i+1), '') or c2.get(str(i), '') or None
        w = c6.get(str(i+1), '') or c6.get(str(i), '') or None
        m = c11.get(str(i+1), '') or c11.get(str(i), '') or None
        insts.append(Inst(i, op, cat, var, D, a, Z, q, w, m, nr))
    return insts, nr, raw.get('C5', 0), raw.get('C3', 0)


def trace(insts, num_inst):
    visited = set()
    path = []
    pc = 0
    limit = num_inst * 4

    while 0 <= pc < num_inst and len(path) < limit:
        if pc in visited:
            break
        visited.add(pc)
        inst = insts[pc]

        if inst.cat == 'JMP':
            t = inst.jmp_target()
            if 0 <= t < num_inst:
                pc = t
                continue
            break

        if inst.cat in NOISE:
            pc += 1
            continue

        path.append(inst)
        pc += 1

    return path


def filter_noise(path):
    n = len(path)
    is_noise = [False] * n
    dispatch_regs = set()

    for i, inst in enumerate(path):
        if inst.cat in NOISE:
            is_noise[i] = True
            continue

        if inst.cat == 'SETTABLE' and not inst.valid(inst.D):
            is_noise[i] = True
            continue

        if inst.cat == 'NEWTABLE':
            dest = inst.dest()
            has_dispatch_st = False
            for j in range(i+1, min(i+8, n)):
                fi = path[j]
                if fi.cat == 'SETTABLE':
                    c = fi.const()
                    if isinstance(c, (int, float)) and not isinstance(c, str):
                        has_dispatch_st = True
                elif fi.cat not in ('LOADNIL', 'NEWTABLE', 'SETTABLE'):
                    break
            if has_dispatch_st:
                is_noise[i] = True
                dispatch_regs.add(dest)
                continue

        if inst.cat == 'SETTABLE':
            base_r = inst.D if inst.valid(inst.D) else (inst.a if inst.valid(inst.a) else inst.Z)
            c = inst.const()
            m = inst.m
            w = inst.w
            if base_r in dispatch_regs:
                is_noise[i] = True
                continue
            if isinstance(c, (int, float)) and not isinstance(c, str):
                if isinstance(m, (int, float)) and not isinstance(m, str):
                    is_noise[i] = True
                    continue
                if isinstance(w, (int, float)) and not isinstance(w, str):
                    is_noise[i] = True
                    continue
                if m is None and w is None:
                    val_from_reg = False
                    for v in [inst.a, inst.Z]:
                        if inst.valid(v) and v != base_r:
                            val_from_reg = True
                            break
                    if not val_from_reg:
                        is_noise[i] = True
                        continue

        if inst.cat == 'LOADNIL':
            nearby_dispatch = False
            for j in range(max(0, i-4), min(n, i+4)):
                if j != i and is_noise[j]:
                    nearby_dispatch = True
                    break
                if j != i and j < n and path[j].cat == 'SETTABLE' and not path[j].valid(path[j].D):
                    nearby_dispatch = True
                    break
            if nearby_dispatch:
                is_noise[i] = True
                continue

    return [inst for i, inst in enumerate(path) if not is_noise[i]]


class ExprTracker:
    def __init__(self, num_regs):
        self.regs = {}
        self.nr = num_regs
        self.stmts = []
        self.used_as_stmt = set()

    def v(self, r):
        return 0 <= r < self.nr

    def reg(self, r):
        if r in self.regs:
            return self.regs[r]
        return f'v{r}'

    def sr(self, *candidates):
        for c in candidates:
            if self.v(c):
                return c
        return candidates[0] if candidates else 0

    def set_reg(self, r, expr):
        if self.v(r):
            self.regs[r] = expr

    def emit(self, stmt):
        self.stmts.append(stmt)

    def process(self, inst):
        cat = inst.cat
        var = inst.var
        D, a, Z = inst.D, inst.a, inst.Z

        if cat == 'GETGLOBAL':
            dest = inst.dest()
            name = inst.global_name()
            if name:
                self.set_reg(dest, name)
            else:
                c = inst.const()
                if c and isinstance(c, str):
                    self.set_reg(dest, c)
                else:
                    self.set_reg(dest, f'_G[{lua_val(c)}]' if c else '_G[?]')

        elif cat == 'GETTABLE':
            base = self.sr(a, D, Z)
            dest = inst.dest()
            c = inst.const()
            base_expr = self.reg(base)
            if c is not None and isinstance(c, str):
                if re.match(r'^[a-zA-Z_]\w*$', c):
                    self.set_reg(dest, f'{base_expr}.{c}')
                else:
                    self.set_reg(dest, f'{base_expr}[{lua_val(c)}]')
            elif c is not None:
                self.set_reg(dest, f'{base_expr}[{lua_val(c)}]')
            elif inst.valid(Z) and Z != base:
                self.set_reg(dest, f'{base_expr}[{self.reg(Z)}]')
            else:
                self.set_reg(dest, f'{base_expr}[?]')

        elif cat == 'SETTABLE':
            base_r = self.sr(D, a, Z)
            c = inst.const()
            m = inst.m
            base_expr = self.reg(base_r)

            if c is not None and isinstance(c, str):
                key = c
            elif c is not None:
                key = str(c)
            else:
                key = '?'

            if m is not None:
                val = lua_val(m)
            elif inst.w is not None:
                val = lua_val(inst.w)
            elif inst.valid(a) and a != base_r:
                val = self.reg(a)
            elif inst.valid(Z) and Z != base_r:
                val = self.reg(Z)
            else:
                val = '?'

            if isinstance(c, str) and re.match(r'^[a-zA-Z_]\w*$', c):
                self.emit(f'{base_expr}.{key} = {val}')
            else:
                self.emit(f'{base_expr}[{lua_val(c) if isinstance(c, str) else key}] = {val}')

        elif cat == 'LOADK':
            dest = inst.dest()
            c = inst.const()
            self.set_reg(dest, lua_val(c) if c is not None else '?')

        elif cat == 'MOVE':
            dest = inst.dest()
            src = self.sr(Z, a, D)
            if src != dest:
                self.set_reg(dest, self.reg(src))

        elif cat == 'CALL':
            func_r = self.sr(a, D, Z)
            func_expr = self.reg(func_r)

            oi = operand_info.get(str(inst.op), {})
            call_type = oi.get('call_type', '')

            if 'SPREAD' in var or 'SPREAD' in call_type:
                end_r = self.sr(Z, D, a)
                if inst.valid(end_r) and end_r > func_r:
                    args = ', '.join(self.reg(r) for r in range(func_r+1, end_r+1))
                    expr = f'{func_expr}({args})'
                else:
                    expr = f'{func_expr}(...)'
            elif self.v(func_r + 1):
                nargs = 0
                for r in range(func_r + 1, self.nr):
                    if r in self.regs:
                        nargs = r - func_r
                    else:
                        break
                if nargs > 0:
                    args = ', '.join(self.reg(r) for r in range(func_r+1, func_r+1+nargs))
                    expr = f'{func_expr}({args})'
                else:
                    expr = f'{func_expr}()'
            else:
                expr = f'{func_expr}()'

            dest = inst.dest()
            self.set_reg(dest, expr)
            self.emit(f'local v{dest} = {expr}')

        elif cat == 'RETURN':
            if 'RANGE' in var:
                start = self.sr(D, a, Z)
                end = self.sr(Z, a, D)
                if inst.valid(start) and inst.valid(end) and end > start:
                    vals = ', '.join(self.reg(r) for r in range(start, end+1))
                    self.emit(f'return {vals}')
                else:
                    self.emit(f'return {self.reg(start)}')
            elif inst.valid(D):
                self.emit(f'return {self.reg(D)}')
            else:
                self.emit('return')

        elif cat == 'VARARG':
            dest = inst.dest()
            self.set_reg(dest, '...')

        elif cat == 'CLOSURE':
            if 'SETUP' in var:
                return
            dest = inst.dest()
            self.set_reg(dest, f'function() --[[ closure ]] end')

        elif cat == 'TEST':
            r = self.sr(Z, D, a)
            if inst.valid(r):
                self.emit(f'if {self.reg(r)} then')
            else:
                self.emit('-- test (dispatch)')

        elif cat in ('EQ', 'LT', 'LE'):
            ops_map = {'EQ': '==', 'LT': '<', 'LE': '<='}
            op_str = ops_map[cat]
            if 'NE' in var: op_str = '~='
            elif 'GT' in var: op_str = '>'
            elif 'GE' in var: op_str = '>='

            c = inst.const()
            if c is not None:
                r = self.sr(Z, a, D)
                self.emit(f'if {self.reg(r)} {op_str} {lua_val(c)} then')
            else:
                l = self.sr(D, a, Z)
                r2 = self.sr(Z, D, a)
                if l == r2:
                    r2 = self.sr(a, Z, D)
                self.emit(f'if {self.reg(l)} {op_str} {self.reg(r2)} then')

        elif cat == 'NEWTABLE':
            dest = inst.dest()
            self.set_reg(dest, '{}')

        elif cat in ('ADD', 'SUB', 'MUL', 'DIV', 'MOD', 'POW'):
            ops = {'ADD':'+', 'SUB':'-', 'MUL':'*', 'DIV':'/', 'MOD':'%', 'POW':'^'}
            dest = inst.dest()
            c = inst.const()
            if c is not None:
                src = self.sr(Z, a, D)
                self.set_reg(dest, f'{self.reg(src)} {ops[cat]} {lua_val(c)}')
            else:
                l = self.sr(a, D, Z)
                r = self.sr(Z, D, a)
                self.set_reg(dest, f'{self.reg(l)} {ops[cat]} {self.reg(r)}')

        elif cat == 'UNM':
            dest = inst.dest()
            src = self.sr(Z, a, D)
            self.set_reg(dest, f'-{self.reg(src)}')

        elif cat == 'CONCAT':
            dest = inst.dest()
            c = inst.const()
            if c is not None:
                src = self.sr(a, D, Z)
                self.set_reg(dest, f'{self.reg(src)} .. {lua_val(c)}')
            else:
                l = self.sr(a, D, Z)
                r = self.sr(Z, D, a)
                self.set_reg(dest, f'{self.reg(l)} .. {self.reg(r)}')

        elif cat == 'LOADBOOL':
            dest = inst.dest()
            self.set_reg(dest, 'true')

        elif cat == 'GETUPVAL':
            dest = inst.dest()
            self.set_reg(dest, f'upval_{Z}')

        elif cat == 'SETUPVAL':
            r = self.sr(Z, a, D)
            self.emit(f'upval_{D} = {self.reg(r)}')

        elif cat == 'SELF':
            dest = inst.dest()
            base = self.sr(a, D, Z)
            key = self.sr(Z, D, a)
            self.set_reg(dest, f'{self.reg(base)}:{self.reg(key)}')

        elif cat == 'FORLOOP':
            base = self.sr(D, a, Z)
            self.emit(f'-- for loop (v{base})')

        elif cat == 'LOADNIL':
            pass

        elif cat == 'MULTI_WRITE':
            pass

        else:
            pass


def reconstruct_proto(idx, raw):
    insts, nr, nup, nparams = parse_proto(idx, raw)
    if not insts:
        return []

    path = trace(insts, len(insts))
    real = filter_noise(path)

    if not real:
        return []

    tracker = ExprTracker(nr)
    for inst in real:
        tracker.process(inst)

    return tracker.stmts


def clean_stmts(stmts):
    cleaned = []
    for s in stmts:
        if not s or s.strip() == '':
            continue
        if s.strip().startswith('-- test (dispatch)'):
            continue
        cleaned.append(s)

    result = []
    i = 0
    while i < len(cleaned):
        line = cleaned[i]
        if line.strip().startswith('if ') and line.strip().endswith(' then'):
            if i + 1 < len(cleaned) and cleaned[i+1].strip() == 'end':
                i += 2
                continue
        result.append(line)
        i += 1

    return result


def emit_lua(all_results):
    out = []
    out.append('-- Luraph v14.7 Reconstructed Source')
    out.append('')

    for idx, stmts in enumerate(all_results):
        if not stmts:
            continue

        raw = protos_raw[idx]
        nr = raw.get('C10', 0)
        ni = len(raw.get('C4', []))
        nparams = raw.get('C3', 0)

        out.append(f'-- ======== Proto {idx+1} ({ni} inst, {nr} regs) ========')

        indent = 0
        for line in stmts:
            stripped = line.strip()
            if stripped == 'end' or stripped.startswith('else') or stripped.startswith('elseif'):
                indent = max(0, indent - 1)

            out.append('    ' * indent + stripped)

            if stripped.endswith(' then') or stripped.endswith(' do') or stripped == 'else':
                indent += 1

        out.append('')

    return '\n'.join(out)


all_results = []
for i, raw in enumerate(protos_raw):
    stmts = reconstruct_proto(i, raw)
    stmts = clean_stmts(stmts)
    all_results.append(stmts)

output = emit_lua(all_results)

with open('reconstructed_source.lua', 'w', encoding='utf-8') as f:
    f.write(output)

total = sum(len(s) for s in all_results)
non_empty = sum(1 for s in all_results if s)
print(f"Reconstructed {len(protos_raw)} protos ({non_empty} non-empty)")
print(f"Total statements: {total}")
print(f"Output: reconstructed_source.lua")
