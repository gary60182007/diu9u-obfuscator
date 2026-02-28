"""
Luraph v14.7 Source Reconstructor
Phase 1: Trace execution through JMP dispatch state machine
Phase 2: Filter dispatch noise (NEWTABLE+SETTABLE(OOR)+LOADNIL blocks)
Phase 3: Build expression trees from real instructions
Phase 4: Emit readable Lua source
"""
import json, re, sys
from collections import defaultdict, OrderedDict

with open('all_protos_data.json') as f:
    protos_raw = json.load(f)
with open('opcode_map_final.json') as f:
    opcode_map = json.load(f)
with open('luraph_strings_full.json', encoding='utf-8') as f:
    constants_raw = json.load(f)

try:
    with open('operand_map.json') as f:
        operand_info = json.load(f)
except:
    operand_info = {}

constants = {}
for k, v in constants_raw.items():
    idx = int(k)
    if v.get('type') == 'n':
        constants[idx] = v.get('val', 0)
    elif v.get('type') == 's':
        constants[idx] = v.get('text', f'<str_{idx}>')
    elif v.get('type') == 'b':
        constants[idx] = v.get('val', False)

NOISE_CATS = {'CLOSE', 'DISPATCH', 'FRAGMENT', 'RANGE', 'ARITH', 'UNKNOWN'}

def parse_sparse_val(entry):
    if isinstance(entry, (int, float)):
        return ('number', entry)
    if not isinstance(entry, str):
        return ('unknown', str(entry))
    if entry.startswith('n:'):
        return ('number', int(entry[2:]))
    elif entry.startswith('x:'):
        return ('string', entry[2:])
    elif entry.startswith('t:'):
        parts = entry.split(':')
        if len(parts) >= 3 and parts[1] != '?' and parts[2] != '?':
            return ('const_ref', int(parts[1]), int(parts[2]))
    return ('unknown', entry)

def format_const(val_tuple):
    if val_tuple is None:
        return None
    kind = val_tuple[0]
    if kind == 'number':
        return str(val_tuple[1])
    elif kind == 'string':
        return repr(val_tuple[1])
    elif kind == 'const_ref':
        cidx = val_tuple[1]
        if cidx in constants:
            cv = constants[cidx]
            if isinstance(cv, str):
                return repr(cv)
            return str(cv)
        return f'K[{cidx}]'
    return None

def resolve_const_idx(raw_val):
    if isinstance(raw_val, str):
        parsed = parse_sparse_val(raw_val)
        return format_const(parsed)
    if isinstance(raw_val, (int, float)):
        cidx = int(raw_val) // 4
        if cidx in constants:
            cv = constants[cidx]
            if isinstance(cv, str):
                return repr(cv)
            return str(cv)
    return None


class Instruction:
    def __init__(self, pc, op, cat, variant, D, a, Z, q_raw, w_raw, m_raw, num_regs):
        self.pc = pc
        self.op = op
        self.cat = cat
        self.variant = variant
        self.D = D
        self.a = a
        self.Z = Z
        self.num_regs = num_regs
        self.q_str = resolve_const_idx(q_raw) if q_raw else None
        self.w_str = resolve_const_idx(w_raw) if w_raw else None
        self.m_str = resolve_const_idx(m_raw) if m_raw else None
        self.q_raw = q_raw
        self.w_raw = w_raw
        self.m_raw = m_raw

    def is_noise(self):
        return self.cat in NOISE_CATS

    def is_jmp(self):
        return self.cat == 'JMP'

    def valid_reg(self, v):
        return 0 <= v < self.num_regs

    def get_global_name(self):
        info = opcode_map.get(str(self.op), {})
        v = info.get('variant', '')
        if v.startswith('GETGLOBAL(') and v.endswith(')'):
            return v[10:-1]
        return None


class Proto:
    def __init__(self, idx, raw):
        self.idx = idx
        self.num_regs = raw.get('C10', 0)
        self.num_upvalues = raw.get('C5', 0)
        self.num_params = raw.get('C3', 0)
        c4 = raw.get('C4', [])
        c7 = raw.get('C7', [])
        c8 = raw.get('C8', [])
        c9 = raw.get('C9', [])
        c2 = raw.get('C2_sparse', {})
        c6 = raw.get('C6_sparse', {})
        c11 = raw.get('C11_sparse', {})
        self.num_inst = len(c4)
        self.instructions = []
        for i in range(len(c4)):
            op = c4[i]
            info = opcode_map.get(str(op), {})
            cat = info.get('lua51', 'UNKNOWN')
            variant = info.get('variant', '')
            D = c7[i] if i < len(c7) else 0
            a_val = c8[i] if i < len(c8) else 0
            Z = c9[i] if i < len(c9) else 0
            q = c2.get(str(i+1), '') or c2.get(str(i), '')
            w = c6.get(str(i+1), '') or c6.get(str(i), '')
            m = c11.get(str(i+1), '') or c11.get(str(i), '')
            self.instructions.append(
                Instruction(i, op, cat, variant, D, a_val, Z,
                           q or None, w or None, m or None, self.num_regs)
            )

    def get_jmp_target(self, inst):
        oi = operand_info.get(str(inst.op), {})
        jt = oi.get('jump_target')
        if jt:
            return {'D': inst.D, 'a': inst.a, 'Z': inst.Z}.get(jt, inst.D)
        return inst.D

    def get_dest_reg(self, inst):
        oi = operand_info.get(str(inst.op), {})
        d = oi.get('dest') or oi.get('getglobal_dest') or oi.get('arith_dest') or oi.get('move_dest')
        val = {'D': inst.D, 'a': inst.a, 'Z': inst.Z}.get(d, inst.D) if d else inst.D
        if inst.valid_reg(val):
            return val
        for c in [inst.D, inst.a, inst.Z]:
            if inst.valid_reg(c):
                return c
        return inst.D


def trace_execution(proto):
    """Trace execution through the JMP dispatch state machine.
    Returns a list of basic blocks, each being a sequence of real instructions."""
    visited = set()
    blocks = []
    work = [(0, [])]  # (start_pc, path_context)

    while work:
        pc, ctx = work.pop(0)
        if pc in visited or pc < 0 or pc >= proto.num_inst:
            continue

        block = []
        current_pc = pc

        while 0 <= current_pc < proto.num_inst:
            if current_pc in visited and current_pc != pc:
                break
            visited.add(current_pc)
            inst = proto.instructions[current_pc]

            if inst.is_noise():
                current_pc += 1
                continue

            if inst.is_jmp():
                target = proto.get_jmp_target(inst)
                if 0 <= target < proto.num_inst and target not in visited:
                    current_pc = target
                    continue
                else:
                    break

            if inst.cat == 'TEST':
                block.append(inst)
                next_pc = current_pc + 1
                if next_pc < proto.num_inst:
                    next_inst = proto.instructions[next_pc]
                    if next_inst.is_jmp():
                        jmp_target = proto.get_jmp_target(next_inst)
                        work.append((jmp_target, []))
                        visited.add(next_pc)
                current_pc = next_pc + 1
                continue

            if inst.cat in ('EQ', 'LT', 'LE'):
                block.append(inst)
                jmp_target = inst.a
                if inst.valid_reg(inst.a):
                    pass
                elif 0 <= inst.a < proto.num_inst:
                    work.append((inst.a, []))
                current_pc += 1
                continue

            if inst.cat == 'LOADNIL':
                current_pc += 1
                continue

            if inst.cat == 'NEWTABLE':
                block.append(inst)
                current_pc += 1
                continue

            block.append(inst)
            current_pc += 1

        if block:
            blocks.append(block)

    return blocks


def build_expression(inst, regs, proto):
    """Build a Lua expression string from an instruction, using register state."""
    cat = inst.cat
    variant = inst.variant
    D, a, Z = inst.D, inst.a, inst.Z

    def reg(r):
        if r in regs and regs[r]:
            return regs[r]
        return f'r{r}'

    def safe_reg(v, *fb):
        if inst.valid_reg(v): return v
        for f in fb:
            if inst.valid_reg(f): return f
        return v

    dest = proto.get_dest_reg(inst)

    if cat == 'GETGLOBAL':
        name = inst.get_global_name()
        if name:
            return dest, name
        const = inst.q_str or inst.w_str or inst.m_str
        if const:
            return dest, f'_G[{const}]'
        return dest, '_G[?]'

    elif cat == 'GETTABLE':
        base = safe_reg(a, D, Z)
        key = inst.q_str
        if not key and inst.valid_reg(Z):
            key = reg(Z)
        elif not key:
            key = str(Z)
        base_expr = reg(base)
        if key and (key.startswith("'") or key.startswith('"')):
            field = key.strip("'\"")
            if re.match(r'^[a-zA-Z_]\w*$', field):
                return dest, f'{base_expr}.{field}'
            return dest, f'{base_expr}[{key}]'
        return dest, f'{base_expr}[{key}]'

    elif cat == 'SETTABLE':
        if variant == 'SETTABLE_KmKq':
            key = inst.q_str or str(Z)
            val = inst.m_str or '?'
            base = safe_reg(D, a, Z)
            base_expr = reg(base)
            return None, f'{base_expr}[{key}] = {val}'
        elif inst.op == 170:
            base = safe_reg(D, a, Z)
            key = inst.q_str or str(a)
            val_r = safe_reg(a, Z, D)
            return None, f'{reg(base)}[{key}] = {reg(val_r)}'
        else:
            base = safe_reg(D, a, Z)
            key = inst.q_str or str(Z)
            val = inst.m_str or inst.w_str or '?'
            return None, f'{reg(base)}[{key}] = {val}'

    elif cat == 'LOADK':
        val = inst.q_str or inst.w_str or inst.m_str or '?'
        return dest, val

    elif cat == 'MOVE':
        src = safe_reg(Z, a, D)
        if src != dest:
            return dest, reg(src)
        src2 = safe_reg(a, Z, D)
        return dest, reg(src2)

    elif cat == 'CALL':
        func_r = safe_reg(a, D, Z)
        func_expr = reg(func_r)
        return dest, f'{func_expr}(...)'

    elif cat == 'RETURN':
        if variant == 'RETURN_RANGE':
            return None, f'return {reg(D)}, ...'
        elif variant == 'RETURN_VAL':
            return None, f'return {reg(D)}'
        else:
            return None, 'return'

    elif cat == 'GETUPVAL':
        return dest, f'upval_{Z}'

    elif cat == 'CLOSURE':
        if variant == 'CLOSURE_SETUP':
            return None, None
        return dest, f'function(...) --[[ proto_{a} ]] end'

    elif cat == 'TEST':
        r = safe_reg(Z, D, a)
        return None, f'if {reg(r)} then'

    elif cat in ('EQ', 'LT', 'LE'):
        ops = {'EQ': '==', 'LT': '<', 'LE': '<='}
        if 'NE' in variant: op = '~='
        elif 'GT' in variant: op = '>'
        elif 'GE' in variant: op = '>='
        else: op = ops.get(cat, '==')
        const = inst.q_str or inst.w_str or inst.m_str
        if const:
            r = safe_reg(Z, a, D)
            return None, f'if {reg(r)} {op} {const} then'
        else:
            left = safe_reg(D, a, Z)
            right = safe_reg(Z, D, a)
            return None, f'if {reg(left)} {op} {reg(right)} then'

    elif cat == 'NEWTABLE':
        return dest, '{}'

    elif cat == 'VARARG':
        return dest, '...'

    elif cat == 'FORLOOP':
        return None, f'-- for loop (r{D})'

    elif cat in ('ADD', 'SUB', 'MUL', 'DIV', 'MOD', 'POW'):
        ops = {'ADD': '+', 'SUB': '-', 'MUL': '*', 'DIV': '/', 'MOD': '%', 'POW': '^'}
        op = ops[cat]
        const = inst.q_str or inst.w_str or inst.m_str
        if const:
            src = safe_reg(Z, a, D)
            return dest, f'{reg(src)} {op} {const}'
        else:
            left = safe_reg(a, D, Z)
            right = safe_reg(Z, a, D)
            return dest, f'{reg(left)} {op} {reg(right)}'

    elif cat == 'UNM':
        src = safe_reg(Z, a, D)
        return dest, f'-{reg(src)}'

    elif cat == 'CONCAT':
        const = inst.q_str
        if const:
            src = safe_reg(a, D, Z)
            return dest, f'{reg(src)} .. {const}'
        else:
            left = safe_reg(a, D, Z)
            right = safe_reg(Z, D, a)
            return dest, f'{reg(left)} .. {reg(right)}'

    elif cat == 'LOADBOOL':
        return dest, 'true'

    elif cat == 'MULTI_WRITE':
        return None, f'-- multi_write'

    elif cat == 'SELF':
        return dest, f'{reg(a)}:{reg(Z)}'

    elif cat == 'SETUPVAL':
        return None, f'upval_{D} = {reg(Z)}'

    return None, f'-- {cat}({D}, {a}, {Z})'


def reconstruct_proto(proto, proto_idx):
    """Reconstruct Lua source for a single prototype."""
    blocks = trace_execution(proto)

    regs = {}
    lines = []

    for block in blocks:
        for inst in block:
            dest, expr = build_expression(inst, regs, proto)
            if expr is None:
                continue

            if dest is not None and inst.valid_reg(dest):
                regs[dest] = expr
                if inst.cat in ('GETGLOBAL', 'LOADK', 'GETTABLE', 'CLOSURE',
                                'GETUPVAL', 'NEWTABLE', 'MOVE', 'LOADBOOL',
                                'VARARG', 'ADD', 'SUB', 'MUL', 'DIV', 'MOD',
                                'POW', 'UNM', 'CONCAT'):
                    pass
                elif inst.cat == 'CALL':
                    lines.append(f'local r{dest} = {expr}')
                    regs[dest] = f'r{dest}'
            else:
                if inst.cat == 'SETTABLE':
                    lines.append(expr)
                elif inst.cat == 'RETURN':
                    lines.append(expr)
                elif inst.cat in ('TEST', 'EQ', 'LT', 'LE'):
                    lines.append(expr)
                    lines.append('end')
                elif inst.cat == 'CALL':
                    lines.append(expr)
                elif inst.cat == 'SETUPVAL':
                    lines.append(expr)
                elif inst.cat == 'FORLOOP':
                    lines.append(expr)
                else:
                    lines.append(expr)

    return lines


def emit_lua(all_protos_lines):
    """Emit final Lua source."""
    output = []
    output.append('-- Luraph v14.7 Reconstructed Source')
    output.append('-- Auto-generated by luraph_reconstructor.py')
    output.append('')

    for idx, (proto, lines) in enumerate(all_protos_lines):
        if not lines:
            continue
        nr = proto.num_regs
        ni = proto.num_inst
        output.append(f'-- === Proto {idx+1} ({ni} inst, {nr} regs) ===')

        real_lines = [l for l in lines if l and not l.startswith('end')]
        cond_lines = [l for l in lines if l.startswith('if ')]

        indent = 0
        for line in lines:
            if line == 'end':
                indent = max(0, indent - 1)
                output.append('  ' * indent + line)
            elif line.startswith('if ') and line.endswith(' then'):
                output.append('  ' * indent + line)
                indent += 1
            elif line.startswith('for ') or line.startswith('while '):
                output.append('  ' * indent + line)
                indent += 1
            else:
                output.append('  ' * indent + line)

        output.append('')

    return '\n'.join(output)


# Main
parsed_protos = []
for i, raw in enumerate(protos_raw):
    parsed_protos.append(Proto(i, raw))

all_results = []
for i, proto in enumerate(parsed_protos):
    lines = reconstruct_proto(proto, i)
    all_results.append((proto, lines))

output = emit_lua(all_results)

with open('reconstructed_source.lua', 'w', encoding='utf-8') as f:
    f.write(output)

total_lines = output.count('\n')
non_empty = len([l for l in output.split('\n') if l.strip() and not l.strip().startswith('--')])
print(f"Reconstructed {len(parsed_protos)} protos")
print(f"Total lines: {total_lines}, non-empty code lines: {non_empty}")
