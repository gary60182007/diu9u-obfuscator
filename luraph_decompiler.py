"""
Luraph v14.7 Decompiler
Converts extracted proto data + opcode map into reconstructed Lua source.

Data sources:
- all_protos_data.json: 167 protos with C[] arrays
- opcode_map_final.json: 287 opcodes -> Lua 5.1 categories
- operand_map.json: per-opcode operand usage from handler analysis
- luraph_strings_full.json: 1170 constants


Operand mapping (VM variables):
  C4=Y=opcode, C7=D, C8=a, C9=Z (register/operand arrays)
  C2=q, C6=w, C11=m (sparse constant operands)
  C5=i=num_upvalues, C10=Q=num_registers
"""
import json, sys, re
from collections import defaultdict

with open('all_protos_data.json') as f:
    protos = json.load(f)
with open('opcode_map_final.json') as f:
    opcode_map = json.load(f)
with open('luraph_strings_full.json', encoding='utf-8') as f:
    constants_raw = json.load(f)

operand_info = {}
try:
    with open('operand_map.json') as f:
        operand_info = json.load(f)
except:
    pass

constants = {}
for k, v in constants_raw.items():
    idx = int(k)
    if v.get('type') == 'n':
        constants[idx] = v.get('val', 0)
    elif v.get('type') == 's':
        constants[idx] = v.get('text', f'<str_{idx}>')
    elif v.get('type') == 'b':
        constants[idx] = v.get('val', False)

def parse_sparse_val(entry):
    if entry.startswith('n:'):
        return ('number', int(entry[2:]))
    elif entry.startswith('x:'):
        return ('string', entry[2:])
    elif entry.startswith('t:'):
        parts = entry.split(':')
        if len(parts) >= 3 and parts[1] != '?' and parts[2] != '?':
            return ('const_ref', int(parts[1]), int(parts[2]))
        return ('const_ref_unknown', None, None)
    return ('unknown', entry)

def format_const(val_tuple):
    if val_tuple is None:
        return ''
    kind = val_tuple[0]
    if kind == 'number':
        return str(val_tuple[1])
    elif kind == 'string':
        return repr(val_tuple[1])
    elif kind == 'const_ref':
        idx = val_tuple[1]
        if idx in constants:
            v = constants[idx]
            if isinstance(v, str):
                return repr(v)
            return str(v)
        return f'const[{idx}]'
    return '<?>'


class Proto:
    def __init__(self, data, index):
        self.id = data.get('id', index)
        self.index = index
        self.num_upvalues = data.get('C5', 0)
        self.num_registers = data.get('C10', 0)
        self.opcodes = data.get('C4', [])
        self.reg_D = data.get('C7', [])
        self.reg_a = data.get('C8', [])
        self.reg_Z = data.get('C9', [])
        self.num_inst = len(self.opcodes)

        self.const_q = {}
        for k, v in data.get('C2_sparse', {}).items():
            self.const_q[int(k)] = parse_sparse_val(v)

        self.const_w = {}
        for k, v in data.get('C6_sparse', {}).items():
            self.const_w[int(k)] = ('number', int(v))

        self.const_m = {}
        for k, v in data.get('C11_sparse', {}).items():
            self.const_m[int(k)] = parse_sparse_val(v)

    def get_q(self, pc):
        return self.const_q.get(pc)

    def get_w(self, pc):
        return self.const_w.get(pc)

    def get_m(self, pc):
        return self.const_m.get(pc)


def resolve_reg(op_info, operand_name, D, a, Z):
    """Resolve which physical operand a logical operand maps to for this opcode."""
    mapping = {'D': D, 'a': a, 'Z': Z}
    reg_letter = op_info.get(operand_name)
    if reg_letter and reg_letter in mapping:
        return mapping[reg_letter]
    return None


def disassemble_proto(proto, opmap, op_info_map):
    lines = []
    for pc in range(proto.num_inst):
        op = proto.opcodes[pc]
        D = proto.reg_D[pc] if pc < len(proto.reg_D) else 0
        a = proto.reg_a[pc] if pc < len(proto.reg_a) else 0
        Z = proto.reg_Z[pc] if pc < len(proto.reg_Z) else 0

        pc1 = pc + 1
        q = proto.get_q(pc1)
        w = proto.get_w(pc1)
        m = proto.get_m(pc1)

        info = opmap.get(str(op), {})
        lua51 = info.get('lua51', 'UNKNOWN')
        variant = info.get('variant', 'UNKNOWN')
        global_name = info.get('global_name')
        oi = op_info_map.get(str(op), {})

        q_str = format_const(q)
        w_str = format_const(w)
        m_str = format_const(m)

        def get_dest():
            d = oi.get('dest') or oi.get('getglobal_dest') or oi.get('arith_dest') or oi.get('move_dest')
            val = {'D': D, 'a': a, 'Z': Z}.get(d, D)
            if 0 <= val < proto.num_registers:
                return val
            for candidate in [D, a, Z]:
                if 0 <= candidate < proto.num_registers:
                    return candidate
            return D

        def get_any_const():
            return q_str or w_str or m_str or '?'

        if lua51 == 'GETGLOBAL' and global_name:
            dest = get_dest()
            line = f'r{dest} = {global_name}'
        elif lua51 == 'GETGLOBAL':
            dest = get_dest()
            line = f'r{dest} = _G[{get_any_const()}]'
        elif lua51 == 'SETGLOBAL':
            line = f'_G[{get_any_const()}] = r{D}'
        elif lua51 == 'LOADK':
            dest = get_dest()
            line = f'r{dest} = {get_any_const()}'
        elif lua51 == 'LOADBOOL':
            dest = get_dest()
            line = f'r{dest} = bool'
        elif lua51 == 'LOADNIL':
            nr = proto.num_registers
            def clamp_reg(v):
                return min(v, nr - 1) if v >= 0 else 0
            if variant == 'LOADNIL_aD' or variant == 'LOADNIL_aD_HF':
                lo, hi = clamp_reg(a), clamp_reg(D)
            elif variant == 'LOADNIL_Da':
                lo, hi = clamp_reg(D), clamp_reg(a)
            elif variant == 'LOADNIL_aZ_HF':
                lo, hi = clamp_reg(a), clamp_reg(Z)
            else:
                lo, hi = clamp_reg(min(D, a)), clamp_reg(max(D, a))
            if lo == hi:
                line = f'r{lo} = nil'
            else:
                line = f'r{lo}..r{hi} = nil'
        elif lua51 == 'MOVE':
            md = oi.get('move_dest', 'D')
            ms = oi.get('move_src', 'Z')
            dst = {'D': D, 'a': a, 'Z': Z}.get(md, D)
            src = {'D': D, 'a': a, 'Z': Z}.get(ms, Z)
            line = f'r{dst} = r{src}'
        elif lua51 == 'NEWTABLE':
            if 'COMPUTED' in variant or variant == 'NEWTABLE_HF':
                line = f'r{D} = {{}}'
            else:
                dest = get_dest()
                line = f'r{dest} = {{}}'
        elif lua51 == 'GETTABLE':
            dest = get_dest()
            tbl_reg = oi.get('table_reg')
            key_op = oi.get('table_key')
            if tbl_reg:
                base = {'D': D, 'a': a, 'Z': Z}.get(tbl_reg, a)
            else:
                base = a
            if not (0 <= base < proto.num_registers):
                for c in [a, D, Z]:
                    if 0 <= c < proto.num_registers:
                        base = c
                        break
            if key_op and key_op in ('q', 'w', 'm'):
                key = {'q': q_str, 'w': w_str, 'm': m_str}.get(key_op, '?')
                line = f'r{dest} = r{base}[{key}]'
            elif key_op and key_op in ('D', 'a', 'Z'):
                key_r = {'D': D, 'a': a, 'Z': Z}.get(key_op, Z)
                line = f'r{dest} = r{base}[r{key_r}]'
            else:
                if m_str:
                    line = f'r{dest} = r{base}[{m_str}]'
                elif q_str:
                    line = f'r{dest} = r{base}[{q_str}]'
                else:
                    line = f'r{dest} = r{base}[r{Z}]'
        elif lua51 == 'SETTABLE':
            if op == 170:
                key = q_str or '?'
                tbl = D if 0 <= D < proto.num_registers else (a if 0 <= a < proto.num_registers else D)
                val_r = a if (tbl != a and 0 <= a < proto.num_registers) else (Z if 0 <= Z < proto.num_registers else a)
                line = f'r{tbl}[{key}] = r{val_r}'
            elif op == 99:
                line = f'SETTABLE_dispatch(D={D}, a={a}, Z={Z})'
            else:
                sb = oi.get('settable_base', 'a')
                sk = oi.get('settable_key', 'm')
                sv = oi.get('settable_val', 'q')
                base = {'D': D, 'a': a, 'Z': Z}.get(sb, a)
                if sk in ('q', 'w', 'm'):
                    key = {'q': q_str, 'w': w_str, 'm': m_str}.get(sk, '?') or '?'
                else:
                    key_reg = {'D': D, 'a': a, 'Z': Z}.get(sk, a)
                    key = f'r{key_reg}'
                if sv in ('q', 'w', 'm'):
                    val = {'q': q_str, 'w': w_str, 'm': m_str}.get(sv, '?') or '?'
                else:
                    val_reg = {'D': D, 'a': a, 'Z': Z}.get(sv, Z)
                    val = f'r{val_reg}'
                line = f'r{base}[{key}] = {val}'
        elif lua51 in ('ADD', 'SUB', 'MUL', 'DIV', 'MOD', 'POW'):
            ops = {'ADD': '+', 'SUB': '-', 'MUL': '*', 'DIV': '/', 'MOD': '%', 'POW': '^'}
            op_sym = ops[lua51]
            const_val = q_str or w_str or m_str
            d_valid = 0 <= D < proto.num_registers
            a_valid = 0 <= a < proto.num_registers
            z_valid = 0 <= Z < proto.num_registers
            dest = D if d_valid else (a if a_valid else D)
            src_r = Z if z_valid else (a if a_valid else Z)
            if 'wK' in variant and w_str:
                line = f'r{dest} = {w_str} {op_sym} r{src_r}'
            elif 'Kw' in variant and w_str:
                line = f'r{dest} = r{src_r} {op_sym} {w_str}'
            elif 'qK' in variant and q_str:
                line = f'r{dest} = {q_str} {op_sym} r{src_r}'
            elif 'Kq' in variant and q_str:
                line = f'r{dest} = r{src_r} {op_sym} {q_str}'
            elif 'mK' in variant and m_str:
                line = f'r{dest} = {m_str} {op_sym} r{src_r}'
            elif 'Km' in variant and m_str:
                line = f'r{dest} = r{src_r} {op_sym} {m_str}'
            elif d_valid and a_valid:
                line = f'r{dest} = r{a} {op_sym} r{src_r}'
            elif d_valid and const_val:
                line = f'r{dest} = {const_val} {op_sym} r{src_r}'
            else:
                line = f'r{dest} = r{a} {op_sym} r{src_r}'
        elif lua51 == 'UNM':
            dest = get_dest()
            line = f'r{dest} = -r{a}'
        elif lua51 == 'NOT':
            dest = get_dest()
            line = f'r{dest} = not r{a}'
        elif lua51 == 'LEN':
            dest = get_dest()
            line = f'r{dest} = #r{a}'
        elif lua51 == 'CONCAT':
            dest = get_dest()
            if q_str:
                line = f'r{dest} = r{a} .. {q_str}'
            else:
                line = f'r{dest} = r{a} .. r{Z}'
        elif lua51 in ('EQ', 'LT', 'LE'):
            const_val = q_str or w_str or m_str
            nr = proto.num_registers
            def sr(v, *fb):
                if 0 <= v < nr: return v
                for f in fb:
                    if 0 <= f < nr: return f
                return v

            def cmp_op_from_variant(v):
                if 'NE' in v: return '~='
                elif 'GT' in v: return '>'
                elif 'GE' in v: return '>='
                elif 'LT' in v: return '<'
                elif 'LE' in v: return '<='
                else: return '=='

            sD = sr(D, a, Z)
            sZ = sr(Z, a, D)
            sa = sr(a, Z, D)

            if 'KK_STORE' in variant:
                cop = cmp_op_from_variant(variant)
                if w_str and q_str:
                    line = f'r{sD} = ({q_str} {cop} {w_str})'
                elif const_val:
                    line = f'r{sD} = ({const_val} {cop} ?)'
                else:
                    line = f'r{sD} = (k? {cop} k?)'
            elif 'K_JMP' in variant or 'K_STORE' in variant:
                cop = cmp_op_from_variant(variant)
                if const_val:
                    left = f'r{sZ}'
                    right = const_val
                else:
                    left = f'r{sa}'
                    right = f'r{sZ}'
                if 'STORE' in variant:
                    line = f'r{sD} = ({left} {cop} {right})'
                else:
                    if const_val:
                        line = f'if r{sZ} {cop} {const_val} then goto {a}'
                    else:
                        line = f'if r{sa} {cop} r{sZ} then goto {D}'
            elif 'JMP' in variant:
                cop = cmp_op_from_variant(variant)
                line = f'if r{sa} {cop} r{sZ} then goto {D}'
            elif 'STORE' in variant:
                cop = cmp_op_from_variant(variant)
                if const_val:
                    line = f'r{sD} = (r{sZ} {cop} {const_val})'
                else:
                    line = f'r{sD} = (r{sa} {cop} r{sZ})'
            else:
                cop = cmp_op_from_variant(variant) if variant != 'UNKNOWN' else '=='
                if const_val:
                    line = f'if r{sZ} {cop} {const_val} then goto {a}'
                else:
                    line = f'if r{sD} {cop} r{sZ} then goto {a}'
        elif lua51 == 'TEST':
            if variant == 'TEST_FALSE':
                line = f'if not r{Z} then goto {D}'
            elif variant == 'TEST_TRUE':
                line = f'if r{D} then goto {Z}'
            elif variant == 'TEST_Z':
                z_valid = 0 <= Z < proto.num_registers
                a_jmp = 0 <= a < proto.num_inst
                if z_valid and a_jmp:
                    line = f'if r{Z} then goto {a}'
                elif z_valid:
                    line = f'test r{Z}'
                else:
                    line = f'TEST(D={D}, a={a}, Z={Z})'
            elif variant == 'TEST_D_JMP':
                d_valid = 0 <= D < proto.num_registers
                a_jmp = 0 <= a < proto.num_inst
                if d_valid and a_jmp:
                    line = f'if r{D} then goto {a}'
                elif d_valid:
                    line = f'test r{D}'
                else:
                    line = f'TEST(D={D}, a={a}, Z={Z})'
            elif variant == 'TEST_JMP_A':
                a_jmp = 0 <= a < proto.num_inst
                z_valid = 0 <= Z < proto.num_registers
                d_valid = 0 <= D < proto.num_registers
                if z_valid and a_jmp:
                    line = f'if r{Z} then goto {a}'
                elif d_valid and a_jmp:
                    line = f'if r{D} then goto {a}'
                elif a_jmp:
                    line = f'goto {a}'
                else:
                    line = f'TEST(D={D}, a={a}, Z={Z})'
            elif 'NIL' in variant:
                line = f'if r{D} == nil then JUMP'
            else:
                line = f'if r{D} then JUMP'
        elif lua51 == 'JMP':
            jt = oi.get('jump_target')
            if jt:
                target = {'D': D, 'a': a, 'Z': Z}.get(jt, D)
                line = f'goto {target}'
            else:
                line = f'goto {D}'
        elif lua51 == 'CALL':
            if variant == 'CALL_1_0':
                line = f'r{D}(r{D+1})'
            elif variant == 'CALL_SPREAD' and op == 277:
                line = f'r{Z} = r{Z}(r{Z+1}, ..., r{Z+a-1})' if a > 1 else f'r{Z} = r{Z}()'
            elif variant == 'CALL_SPREAD' and op == 285:
                line = f'r{a}(r{a+1}, ..., r{a+Z-1})' if Z > 1 else f'r{a}()'
            elif op == 106:
                line = f'r{a} = r{a}(r{a+1}, r{a+2})'
            elif op == 227:
                if D > 1:
                    line = f'r{a} = r{a}(r{a+1}, ..., r{a+D-1})'
                else:
                    line = f'r{a} = r{a}()'
            elif op == 318:
                line = f'r{D} = r{D}(r{D+1})'
            else:
                cb = oi.get('call_base')
                if cb:
                    base = {'D': D, 'a': a, 'Z': Z}.get(cb, a)
                else:
                    base = a
                line = f'r{base} = r{base}(r{base+1}, ...)'
        elif lua51 == 'RETURN':
            if variant == 'RETURN_RANGE':
                if a > 1:
                    line = f'return r{Z}..r{Z+a-2}'
                elif a == 1:
                    line = f'return r{Z}'
                else:
                    line = f'return'
            elif variant == 'RETURN_VAL':
                line = f'return r{D}'
            else:
                line = 'return'
        elif lua51 == 'GETUPVAL':
            dest = get_dest()
            uv = oi.get('move_src')
            if uv:
                uv_idx = {'D': D, 'a': a, 'Z': Z}.get(uv, Z)
            else:
                uv_idx = Z
            if not (0 <= uv_idx < proto.num_upvalues):
                for c in [Z, a, D]:
                    if 0 <= c < proto.num_upvalues:
                        uv_idx = c
                        break
            line = f'r{dest} = upval[{uv_idx}]'
        elif lua51 == 'SETUPVAL':
            line = f'upval[{D}] = r{Z}'
        elif lua51 == 'CLOSURE':
            if variant == 'CLOSURE_SETUP':
                line = f'-- closure upval setup'
            else:
                dest = get_dest()
                line = f'r{dest} = closure(proto_{a})'
        elif lua51 == 'FORLOOP':
            line = f'FORLOOP r{D}, jump={a}'
        elif lua51 == 'FORPREP':
            line = f'FORPREP r{D}, jump={a}'
        elif lua51 == 'TFORLOOP':
            line = f'TFORLOOP r{D}'
        elif lua51 == 'VARARG':
            if a > 0 and a < proto.num_registers:
                line = f'r{a}... = VARARG({a} vals)'
            elif Z > 0 and Z < proto.num_registers:
                line = f'r{Z}... = VARARG'
            elif D < proto.num_registers:
                line = f'r{D}... = VARARG'
            else:
                line = f'VARARG(...)'
        elif lua51 == 'SETLIST':
            line = f'SETLIST r{D}'
        elif lua51 == 'CLOSE':
            if op == 309:
                line = f'return r{Z}..r{Z+a-1}' if a > 0 else f'return r{Z}'
            elif op == 233:
                line = f'close upvals'
            elif op == 152:
                line = f'close upvals (closure setup)'
            elif op == 229:
                if D > 0 and D < proto.num_registers:
                    line = f'close upvals from r{D}'
                else:
                    line = f'close upvals'
            else:
                if D > 0 and D < proto.num_registers:
                    line = f'close upvals from r{D}'
                else:
                    line = f'close upvals'
        elif lua51 == 'SELF':
            line = f'r{D+1} = r{a}; r{D} = r{a}[r{Z}]'
        elif lua51 == 'DISPATCH':
            z_valid = 0 <= Z < proto.num_registers
            a_valid = 0 <= a < proto.num_registers
            d_valid = 0 <= D < proto.num_registers
            const_parts = []
            if m_str: const_parts.append(m_str)
            elif q_str: const_parts.append(q_str)
            cinfo = ', '.join(const_parts)
            if variant == 'DISPATCH_MK' and z_valid and cinfo:
                line = f'-- dispatch r{Z} [{cinfo}]'
            elif d_valid and a_valid:
                line = f'-- dispatch r{D}, r{a}'
            elif z_valid:
                line = f'-- dispatch r{Z}'
            elif d_valid:
                line = f'-- dispatch r{D}'
            else:
                line = f'-- dispatch'
        elif lua51 == 'COMPUTED':
            const_parts = []
            if q_str: const_parts.append(f'q={q_str}')
            if w_str: const_parts.append(f'w={w_str}')
            if m_str: const_parts.append(f'm={m_str}')
            cinfo = ' ' + ' '.join(const_parts) if const_parts else ''
            line = f'COMPUTED(D={D}, a={a}, Z={Z}){cinfo}'
        elif lua51 == 'JMP_TEST_RETURN':
            z_is_reg = 0 <= Z < proto.num_registers
            a_is_jmp = 0 <= a < proto.num_inst
            if z_is_reg and a_is_jmp:
                line = f'if r{Z} then goto {a}'
            elif z_is_reg:
                line = f'test r{Z} (D={D}, a={a})'
            elif a_is_jmp:
                line = f'test_goto {a} (D={D}, Z={Z})'
            else:
                line = f'JTR(D={D}, a={a}, Z={Z})'
        elif lua51 == 'MULTI_WRITE':
            if w_str:
                line = f'env[r{Z}][r{D}] = {w_str}'
            else:
                line = f'MULTI_WRITE(D={D}, a={a}, Z={Z})'
        else:
            line = f'{lua51}(D={D}, a={a}, Z={Z})'

        const_info = ''
        skip_const_append = True
        if not skip_const_append:
            if q_str: const_info += f' q={q_str}'
            if w_str: const_info += f' w={w_str}'
            if m_str: const_info += f' m={m_str}'

        if lua51 not in ('DISPATCH', 'COMPUTED', 'JMP_TEST_RETURN', 'CLOSE', 'JMP', 'UNKNOWN', 'FRAGMENT', 'RANGE', 'ARITH'):
            reg_refs = re.findall(r'\br(\d+)\b', line)
            if reg_refs and not line.startswith('--'):
                oor_regs = [int(r) for r in reg_refs if int(r) >= proto.num_registers]
                if len(oor_regs) == len(reg_refs):
                    line = f'-- dispatch [{lua51}]'
                elif oor_regs:
                    for oor_r in oor_regs:
                        line = line.replace(f'r{oor_r}', f'k{oor_r}')

        lines.append({
            'pc': pc,
            'op': op,
            'lua51': lua51,
            'variant': variant,
            'line': line,
            'D': D, 'a': a, 'Z': Z,
            'const_info': const_info,
        })
    return lines


def decompile_all(output_file='decompiled_output.lua'):
    out = []
    out.append(f'-- Luraph v14.7 Decompiled Output')
    out.append(f'-- {len(protos)} prototypes, {sum(len(p.get("C4",[])) for p in protos)} instructions')
    out.append(f'-- Opcode map: {len(opcode_map)} opcodes -> Lua 5.1 categories')
    out.append('')

    for pi, pdata in enumerate(protos):
        proto = Proto(pdata, pi)
        if proto.num_inst == 0:
            continue

        out.append(f'-- ============================================================')
        out.append(f'-- Proto {proto.id} (index {pi}): {proto.num_inst} instructions, '
                   f'{proto.num_upvalues} upvals, {proto.num_registers} regs')
        out.append(f'-- ============================================================')

        dis = disassemble_proto(proto, opcode_map, operand_info)

        for inst in dis:
            pc_str = f'{inst["pc"]:4d}'
            op_str = f'[{inst["op"]:3d}]'
            lua51_str = f'{inst["lua51"]:<12s}'
            line = inst['line']
            ci = inst['const_info']
            out.append(f'  {pc_str} {op_str} {lua51_str} {line}{ci}')

        out.append('')

    result = '\n'.join(out)
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(result)
    print(f'Decompiled {len(protos)} protos to {output_file}')
    print(f'Total lines: {len(out)}')

    cat_counts = defaultdict(int)
    for pdata in protos:
        proto = Proto(pdata, 0)
        for pc in range(proto.num_inst):
            op = proto.opcodes[pc]
            info = opcode_map.get(str(op), {})
            cat_counts[info.get('lua51', 'UNKNOWN')] += 1

    print(f'\nInstruction category breakdown:')
    for cat, cnt in sorted(cat_counts.items(), key=lambda x: -x[1]):
        pct = 100 * cnt / sum(cat_counts.values())
        print(f'  {cat:<20s} {cnt:>5d} ({pct:4.1f}%)')


if __name__ == '__main__':
    decompile_all()
