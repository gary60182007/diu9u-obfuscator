"""
Luraph v14.7 Bytecode Decompiler
Reads extracted proto data and produces readable Lua source code.

Data sources:
- all_protos_data.json: 167 protos with C4/C7/C8/C9/C2/C6/C11
- opcode_map_final.json: 287 opcodes → Lua 5.1 categories
- c2_full_data.json: C2 sparse entries with string literals
- luraph_strings_full.json: 1170 constants (207 str, 961 num, 2 bool)
"""
import json, re, sys
from collections import defaultdict
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple, Set


# ── Data Loading ──────────────────────────────────────────────────────────

@dataclass
class LProto:
    num: int
    n_inst: int
    n_reg: int
    n_upv: int
    opcodes: List[int]
    op_a: List[int]
    op_b: List[int]
    op_c: List[int]
    c2: Dict[int, str]
    c6: Dict[int, Any]
    c11: Dict[int, Any]
    sub_protos: List[int] = field(default_factory=list)


def load_data():
    protos_raw = json.load(open('all_protos_data.json', encoding='utf-8'))
    opmap_raw = json.load(open('opcode_map_final.json', encoding='utf-8'))
    c2_raw = json.load(open('c2_full_data.json', encoding='utf-8'))
    consts_raw = json.load(open('luraph_strings_full.json', encoding='utf-8'))

    opmap = {}
    opinfo = {}
    for k, v in opmap_raw.items():
        opmap[int(k)] = v.get('lua51', 'UNKNOWN')
        opinfo[int(k)] = v

    str_pool = []
    num_pool = []
    for k in sorted(consts_raw.keys(), key=int):
        entry = consts_raw[k]
        if entry['type'] == 's':
            str_pool.append(entry.get('text', entry.get('raw', '???')))
        elif entry['type'] == 'n':
            num_pool.append(entry['val'])

    protos = []
    for i, p in enumerate(protos_raw):
        pnum = i + 1
        c2_sparse = {}
        c2_data = c2_raw.get(str(pnum), {})
        for pc_str, val in c2_data.items():
            c2_sparse[int(pc_str)] = val

        c6_sparse = {}
        for pc_str, val in p.get('C6_sparse', {}).items():
            c6_sparse[int(pc_str)] = val

        c11_sparse = {}
        for pc_str, val in p.get('C11_sparse', {}).items():
            c11_sparse[int(pc_str)] = val

        protos.append(LProto(
            num=pnum,
            n_inst=p.get('C4_len', len(p.get('C4', []))),
            n_reg=p.get('C10', 0),
            n_upv=p.get('C5', 0),
            opcodes=p.get('C4', []),
            op_a=p.get('C7', []),
            op_b=p.get('C8', []),
            op_c=p.get('C9', []),
            c2=c2_sparse,
            c6=c6_sparse,
            c11=c11_sparse,
        ))

    return protos, opmap, opinfo, str_pool, num_pool


def resolve_df(raw_val, str_pool, num_pool):
    if not isinstance(raw_val, (int, float)):
        return raw_val
    raw_val = int(raw_val)
    idx = raw_val // 4
    mode = raw_val % 4
    if mode == 0:
        if 0 <= idx < len(num_pool):
            return num_pool[idx]
        return raw_val
    elif mode == 1:
        if 0 <= idx < len(str_pool):
            return str_pool[idx]
        return f'<str_{idx}>'
    elif mode == 2:
        return True
    elif mode == 3:
        return None
    return raw_val


def resolve_c2(c2_val, str_pool, num_pool):
    if not c2_val:
        return None
    if isinstance(c2_val, str):
        if c2_val.startswith('n:'):
            try:
                raw = int(float(c2_val[2:]))
            except (ValueError, OverflowError):
                return None
            if abs(raw) > 10_000_000:
                return None
            return resolve_df(raw, str_pool, num_pool)
        elif c2_val.startswith('s:'):
            parts = c2_val.split(':', 2)
            if len(parts) >= 3:
                return parts[2]
        elif c2_val.startswith('t:'):
            return None
    return None


# ── Instruction Emitter ───────────────────────────────────────────────────

def format_val(v):
    if v is None:
        return 'nil'
    if isinstance(v, bool):
        return 'true' if v else 'false'
    if isinstance(v, str):
        if v.isidentifier() and v.isascii():
            return repr(v)
        safe = v.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n').replace('\r', '\\r')
        if all(c.isprintable() or c in '\n\r\t' for c in v):
            return f'"{safe}"'
        return f'"<bin_{len(v)}b>"'
    if isinstance(v, float):
        if v == int(v):
            return str(int(v))
        return str(v)
    return str(v)


def decompile_proto(proto, opmap, opinfo, str_pool, num_pool, all_protos):
    lines = []
    opcodes = proto.opcodes
    op_a = proto.op_a  # D = C7
    op_b = proto.op_b  # a = C8
    op_c = proto.op_c  # Z = C9
    c2 = proto.c2      # q = C2 sparse
    c6 = proto.c6      # w = C6 sparse
    c11 = proto.c11    # m = C11 sparse
    n = proto.n_inst
    nreg = proto.n_reg

    def _D(pc): return op_a[pc] if pc < len(op_a) else 0
    def _a(pc): return op_b[pc] if pc < len(op_b) else 0
    def _Z(pc): return op_c[pc] if pc < len(op_c) else 0
    def _q(pc): return resolve_c2(c2.get(pc), str_pool, num_pool)
    def _w(pc): return c6.get(pc)
    def _m(pc):
        if pc in c11:
            return resolve_c2(c11.get(pc), str_pool, num_pool)
        return None

    def _get_dest(pc, op):
        info = opinfo.get(op, {})
        omap = info.get('operand_map', {})
        dest_field = omap.get('dest') or omap.get('move_dest') or omap.get('call_base')
        if dest_field == 'D': return _D(pc)
        if dest_field == 'a': return _a(pc)
        if dest_field == 'Z': return _Z(pc)
        d = _D(pc)
        return d if 0 <= d < nreg else _a(pc)

    def _get_key(pc, op):
        info = opinfo.get(op, {})
        omap = info.get('operand_map', {})
        key_field = omap.get('table_key')
        if key_field == 'q': return _q(pc)
        if key_field == 'm': return _m(pc)
        if key_field == 'w': return _w(pc)
        return _q(pc) or _m(pc)

    reg_vals = {}

    jmp_targets = set()
    if_block_ends = {}

    for pc in range(n):
        if pc >= len(opcodes):
            break
        op = opcodes[pc]
        cat = opmap.get(op, 'UNKNOWN')
        dv = _D(pc)
        av = _a(pc)
        zv = _Z(pc)
        c2v = _q(pc)

        if cat == 'JMP':
            target = _w(pc)
            if target is None:
                target = dv
            if isinstance(target, (int, float)) and 0 <= target < n:
                jmp_targets.add(int(target))

        if cat in ('TEST', 'EQ', 'LT', 'LE'):
            target = _w(pc)
            if target is None:
                if 0 < zv < n:
                    target = zv
            if target and isinstance(target, (int, float)) and int(target) > pc:
                if_block_ends[pc] = int(target)

    for pc in range(n):
        if pc >= len(opcodes):
            break
        op = opcodes[pc]
        cat = opmap.get(op, 'UNKNOWN')
        dv = _D(pc)
        av = _a(pc)
        zv = _Z(pc)
        c2v = _q(pc)
        c2_raw = c2.get(pc, '')
        c11v = _m(pc)

        if pc in jmp_targets:
            lines.append(f'::label_{pc}::')

        if cat == 'JMP':
            target = _w(pc)
            if target is None:
                target = dv
            if isinstance(target, (int, float)) and 0 <= target < n:
                lines.append(f'goto label_{int(target)}')
            continue

        if cat == 'MOVE':
            dest = _get_dest(pc, op)
            info = opinfo.get(op, {})
            omap = info.get('operand_map', {})
            src_field = omap.get('move_src')
            if src_field == 'a': src = av
            elif src_field == 'Z': src = zv
            else: src = zv if 0 <= zv < nreg else av
            lines.append(f'r{dest} = r{src}')
            continue

        if cat == 'LOADK':
            dest = _get_dest(pc, op)
            key = _get_key(pc, op)
            if key is None: key = c2v
            if key is None: key = c11v
            if key is not None:
                reg_vals[dest] = key
                lines.append(f'r{dest} = {format_val(key)}')
            else:
                lines.append(f'r{dest} = {zv}')
            continue

        if cat == 'LOADBOOL':
            dest = _get_dest(pc, op)
            val = c2v if c2v is not None else True
            lines.append(f'r{dest} = {format_val(val)}')
            continue

        if cat == 'LOADNIL':
            lo = min(dv, zv) if zv > 0 else dv
            hi = max(dv, zv) if zv > 0 else dv
            for r in range(lo, min(hi + 1, nreg)):
                lines.append(f'r{r} = nil')
            continue

        if cat == 'GETGLOBAL':
            dest = _get_dest(pc, op)
            key = _get_key(pc, op)
            if key is None: key = c2v
            if key is not None and isinstance(key, str) and key.isidentifier():
                reg_vals[dest] = f'@global:{key}'
                lines.append(f'r{dest} = {key}')
            elif key is not None:
                lines.append(f'r{dest} = _G[{format_val(key)}]')
            else:
                lines.append(f'r{dest} = _G[r{av}]')
            continue

        if cat == 'GETTABLE':
            dest = _get_dest(pc, op)
            info = opinfo.get(op, {})
            omap = info.get('operand_map', {})
            tbl_field = omap.get('table_reg')
            if tbl_field == 'a': tbl = av
            elif tbl_field == 'D': tbl = dv
            else: tbl = av if 0 <= av < nreg and av != dest else dv
            key = _get_key(pc, op)
            if key is None: key = c2v
            if key is None: key = c11v
            if key is None:
                key_reg = zv
                if key_reg in reg_vals:
                    key = reg_vals[key_reg]
            if key is not None:
                if isinstance(key, str) and key.isidentifier() and key.isascii():
                    lines.append(f'r{dest} = r{tbl}.{key}')
                else:
                    lines.append(f'r{dest} = r{tbl}[{format_val(key)}]')
            else:
                lines.append(f'r{dest} = r{tbl}[r{zv}]')
            continue

        if cat == 'SETTABLE':
            key = _get_key(pc, op)
            if key is None: key = c2v
            if key is None: key = c11v
            if key is not None:
                tbl = dv if 0 <= dv < nreg else av
                val = av if av != tbl else zv
                if isinstance(key, str) and key.isidentifier() and key.isascii():
                    lines.append(f'r{tbl}.{key} = r{val}')
                else:
                    lines.append(f'r{tbl}[{format_val(key)}] = r{val}')
            else:
                lines.append(f'r{av}[r{zv}] = r{dv}')
            continue

        if cat == 'NEWTABLE':
            dest = _get_dest(pc, op)
            lines.append(f'r{dest} = {{}}')
            continue

        if cat == 'CALL':
            info = opinfo.get(op, {})
            omap = info.get('operand_map', {})
            base_field = omap.get('call_base')
            if base_field == 'a': func = av
            elif base_field == 'D': func = dv
            else: func = av if 0 <= av < nreg else dv
            nargs_hint = dv if base_field == 'a' else av
            nret_hint = zv
            nargs = max(0, nargs_hint - 1) if nargs_hint > 0 else 0
            nret = max(0, nret_hint - 1) if nret_hint > 0 else 0
            args = ', '.join(f'r{func + 1 + i}' for i in range(min(nargs, 15)))
            if nret > 0:
                rets = ', '.join(f'r{func + i}' for i in range(nret))
                lines.append(f'{rets} = r{func}({args})')
            else:
                lines.append(f'r{func}({args})')
            continue

        if cat == 'RETURN':
            if av > 1:
                rets = ', '.join(f'r{dv + i}' for i in range(av - 1))
                lines.append(f'return {rets}')
            elif av == 1:
                lines.append('return')
            else:
                lines.append(f'return r{dv}')
            continue

        if cat in ('TEST', 'EQ', 'LT', 'LE'):
            if pc in if_block_ends:
                target = if_block_ends[pc]
                info = opinfo.get(op, {})
                omap = info.get('operand_map', {})
                test_field = omap.get('test_reg')
                if cat == 'TEST':
                    if test_field == 'Z': reg = zv
                    elif test_field == 'D': reg = dv
                    else: reg = dv if 0 <= dv < nreg else av
                    lines.append(f'if not r{reg} then goto label_{target} end')
                elif cat == 'EQ':
                    lines.append(f'if r{dv} ~= r{zv} then goto label_{target} end')
                elif cat == 'LT':
                    lines.append(f'if r{av} >= r{zv} then goto label_{target} end')
                elif cat == 'LE':
                    lines.append(f'if r{av} > r{zv} then goto label_{target} end')
            continue

        if cat == 'FORLOOP':
            lines.append(f'-- FORLOOP r{dv}')
            continue

        if cat == 'CLOSURE':
            dest = _get_dest(pc, op)
            child_idx = zv if zv > 0 and zv <= len(all_protos) else 0
            if child_idx > 0:
                lines.append(f'r{dest} = closure(proto_{child_idx})')
            else:
                lines.append(f'r{dest} = function() end')
            continue

        if cat == 'GETUPVAL':
            dest = _get_dest(pc, op)
            lines.append(f'r{dest} = upval_{zv}')
            continue

        if cat in ('CLOSE', 'DISPATCH', 'MULTI_WRITE', 'FRAGMENT', 'RANGE'):
            continue

        if cat in ('MUL', 'SUB', 'DIV', 'POW', 'CONCAT'):
            sym = {'MUL': '*', 'SUB': '-', 'DIV': '/', 'POW': '^', 'CONCAT': '..'}
            dest = _get_dest(pc, op)
            lines.append(f'r{dest} = r{av} {sym.get(cat, "?")} r{zv}')
            continue

        if cat == 'UNM':
            dest = _get_dest(pc, op)
            lines.append(f'r{dest} = -r{av}')
            continue

        if cat == 'VARARG':
            lines.append(f'r{dv} = ...')
            continue

        if cat == 'SELF':
            lines.append(f'r{dv+1} = r{av}')
            key = _get_key(pc, op)
            if key is None: key = c2v
            if key is not None and isinstance(key, str) and key.isidentifier():
                lines.append(f'r{dv} = r{av}.{key}')
            else:
                lines.append(f'r{dv} = r{av}[r{zv}]')
            continue

        if cat not in ('NOP', 'UNKNOWN'):
            lines.append(f'-- {cat} op={op} D={dv} a={av} Z={zv}')

    return lines


# ── Main ──────────────────────────────────────────────────────────────────

def main():
    protos, opmap, opinfo, str_pool, num_pool = load_data()
    print(f'Loaded {len(protos)} protos, {len(opmap)} opcodes, {len(str_pool)} strings, {len(num_pool)} numbers')

    out = []
    out.append('-- Luraph v14.7 Decompiled Source (bloxburg_script.lua)')
    out.append(f'-- {len(protos)} prototypes')
    out.append('')

    total_lines = 0
    nonempty = 0

    for proto in protos:
        if proto.num == 154:
            out.append(f'-- Proto {proto.num} (VM runtime, {proto.n_inst} inst) — skipped')
            out.append('')
            continue

        lines = decompile_proto(proto, opmap, opinfo, str_pool, num_pool, protos)
        real_lines = [l for l in lines if l.strip() and not l.startswith('--')]

        if not real_lines:
            continue

        nonempty += 1
        total_lines += len(real_lines)

        out.append(f'-- Proto {proto.num} ({proto.n_inst} inst, {proto.n_reg} regs)')
        out.append(f'local function proto_{proto.num}()')
        for line in lines:
            out.append(f'  {line}')
        out.append('end')
        out.append('')

    header = f'-- {nonempty} functions, {total_lines} statements'
    out.insert(2, header)

    output = '\n'.join(out)
    with open('bloxburg_decompiled_v2.lua', 'w', encoding='utf-8') as f:
        f.write(output)

    print(f'Output: bloxburg_decompiled_v2.lua')
    print(f'  {nonempty} non-empty protos, {total_lines} statements')
    print(f'  {len(out)} total lines')


if __name__ == '__main__':
    main()
