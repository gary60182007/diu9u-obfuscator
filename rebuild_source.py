"""
Luraph v14.7 Source Reconstructor (Parser-based)
Parses the decompiled instruction listing, traces execution through
JMP dispatch, filters noise, and reconstructs readable Lua source.
"""
import re
from collections import defaultdict

class ParsedInst:
    __slots__ = ['pc', 'opcode', 'cat', 'detail', 'jmp_target',
                 'dest_reg', 'expr', 'is_dispatch']

    def __init__(self, pc, opcode, cat, detail):
        self.pc = pc
        self.opcode = opcode
        self.cat = cat
        self.detail = detail
        self.jmp_target = None
        self.dest_reg = None
        self.expr = None
        self.is_dispatch = False


class ProtoData:
    def __init__(self, proto_num, index, num_inst, num_upvals, num_regs):
        self.proto_num = proto_num
        self.index = index
        self.num_inst = num_inst
        self.num_upvals = num_upvals
        self.num_regs = num_regs
        self.instructions = {}


def parse_decompiled(filename):
    with open(filename, encoding='utf-8') as f:
        lines = f.readlines()

    protos = []
    current = None

    proto_re = re.compile(
        r'-- Proto (\d+) \(index (\d+)\): (\d+) instructions, (\d+) upvals, (\d+) regs')
    inst_re = re.compile(r'\s+(\d+)\s+\[\s*(\d+)\]\s+(\w+)\s+(.*)')

    for line in lines:
        m = proto_re.search(line)
        if m:
            current = ProtoData(
                int(m.group(1)), int(m.group(2)),
                int(m.group(3)), int(m.group(4)), int(m.group(5)))
            protos.append(current)
            continue

        if current is None:
            continue

        m = inst_re.match(line)
        if m:
            pc = int(m.group(1))
            opcode = int(m.group(2))
            cat = m.group(3)
            detail = m.group(4).strip()
            inst = ParsedInst(pc, opcode, cat, detail)
            classify_inst(inst)
            current.instructions[pc] = inst

    return protos


def classify_inst(inst):
    cat = inst.cat
    detail = inst.detail

    if cat == 'JMP':
        m = re.match(r'goto (\d+)', detail)
        if m:
            inst.jmp_target = int(m.group(1))

    elif cat == 'GETGLOBAL':
        m = re.match(r'r(\d+)\s*=\s*(.+)', detail)
        if m:
            inst.dest_reg = int(m.group(1))
            inst.expr = m.group(2).strip()
        elif '-- dispatch' in detail:
            inst.is_dispatch = True

    elif cat == 'GETTABLE':
        m = re.match(r'r(\d+)\s*=\s*(.+)', detail)
        if m:
            inst.dest_reg = int(m.group(1))
            inst.expr = m.group(2).strip()

    elif cat == 'LOADK':
        m = re.match(r'r(\d+)\s*=\s*(.+)', detail)
        if m:
            inst.dest_reg = int(m.group(1))
            inst.expr = m.group(2).strip()

    elif cat == 'MOVE':
        m = re.match(r'r(\d+)\s*=\s*(.+)', detail)
        if m:
            inst.dest_reg = int(m.group(1))
            inst.expr = m.group(2).strip()

    elif cat == 'NEWTABLE':
        m = re.match(r'r(\d+)\s*=\s*\{\}', detail)
        if m:
            inst.dest_reg = int(m.group(1))
            inst.expr = '{}'

    elif cat == 'LOADNIL':
        pass

    elif cat == 'LOADBOOL':
        m = re.match(r'r(\d+)\s*=\s*(.+)', detail)
        if m:
            inst.dest_reg = int(m.group(1))
            inst.expr = m.group(2).strip()

    elif cat == 'CALL':
        m = re.match(r'r(\d+)\s*=\s*(.+)', detail)
        if m:
            inst.dest_reg = int(m.group(1))
            inst.expr = m.group(2).strip()
        elif re.match(r'r(\d+)\(', detail):
            inst.expr = detail

    elif cat == 'SETTABLE':
        if 'SETTABLE_dispatch' in detail:
            inst.is_dispatch = True
        else:
            inst.expr = detail

    elif cat == 'TEST':
        if '-- dispatch' in detail:
            inst.is_dispatch = True
        else:
            inst.expr = detail

    elif cat in ('EQ', 'LT', 'LE'):
        if '-- dispatch' in detail:
            inst.is_dispatch = True
        else:
            inst.expr = detail

    elif cat == 'RETURN':
        inst.expr = detail

    elif cat == 'VARARG':
        m = re.match(r'r(\d+)', detail)
        if m:
            inst.dest_reg = int(m.group(1))
            inst.expr = '...'

    elif cat == 'GETUPVAL':
        m = re.match(r'r(\d+)\s*=\s*(.+)', detail)
        if m:
            inst.dest_reg = int(m.group(1))
            inst.expr = m.group(2).strip()

    elif cat == 'CLOSURE':
        if 'upval setup' in detail:
            pass
        else:
            m = re.match(r'r(\d+)\s*=\s*(.+)', detail)
            if m:
                inst.dest_reg = int(m.group(1))
                inst.expr = m.group(2).strip()

    elif cat in ('MUL', 'ADD', 'SUB', 'DIV', 'MOD', 'POW', 'UNM', 'CONCAT'):
        m = re.match(r'r(\d+)\s*=\s*(.+)', detail)
        if m:
            inst.dest_reg = int(m.group(1))
            inst.expr = m.group(2).strip()

    elif cat in ('CLOSE', 'DISPATCH'):
        inst.is_dispatch = True

    elif cat == 'FORLOOP':
        inst.expr = detail

    elif cat == 'MULTI_WRITE':
        inst.is_dispatch = True


def trace_execution(proto):
    insts = proto.instructions
    n = proto.num_inst
    visited = set()
    path = []
    pc = 0
    limit = n * 4

    while 0 <= pc < n and len(path) < limit:
        if pc in visited:
            break
        visited.add(pc)

        inst = insts.get(pc)
        if inst is None:
            pc += 1
            continue

        if inst.cat == 'JMP' and inst.jmp_target is not None:
            pc = inst.jmp_target
            continue

        path.append(inst)
        pc += 1

    return path


def is_dispatch_block(path, start_idx):
    if start_idx >= len(path):
        return 0
    inst = path[start_idx]
    if inst.cat != 'NEWTABLE':
        return 0

    block_len = 1
    i = start_idx + 1
    while i < len(path):
        ni = path[i]
        if ni.cat == 'SETTABLE' and ni.expr:
            m = re.match(r'r\d+\[(\d+)\]\s*=\s*(.+)', ni.expr)
            if m:
                block_len += 1
                i += 1
                continue
        elif ni.cat == 'LOADNIL':
            block_len += 1
            i += 1
            continue
        break

    if block_len >= 3:
        return block_len
    return 0


def filter_dispatch(path, num_regs):
    n = len(path)
    is_noise = [False] * n

    i = 0
    while i < n:
        bl = is_dispatch_block(path, i)
        if bl > 0:
            for j in range(i, min(i + bl, n)):
                is_noise[j] = True
            i += bl
            continue
        i += 1

    for i, inst in enumerate(path):
        if inst.is_dispatch:
            is_noise[i] = True
            continue
        if inst.cat == 'CLOSE':
            is_noise[i] = True
            continue

        if inst.cat == 'GETGLOBAL' and inst.expr:
            for j in range(i+1, min(i+3, n)):
                nxt = path[j]
                if nxt.cat in ('EQ', 'LT', 'LE') and nxt.expr:
                    if re.search(r'\b\d+\b', nxt.expr) and 'then' in nxt.expr:
                        is_noise[i] = True
                        is_noise[j] = True
                    break
                if nxt.cat not in ('LOADNIL', 'CLOSE'):
                    break

        if inst.cat == 'SETTABLE' and inst.expr:
            if re.match(r'SETTABLE_dispatch', inst.expr):
                is_noise[i] = True
                continue
            if inst.expr.startswith('{}['):
                is_noise[i] = True
                continue
            m = re.match(r'r\d+\[(\d+)\]\s*=\s*(-?\d+)$', inst.expr)
            if m:
                key = int(m.group(1))
                val = int(m.group(2))
                if (key > 10 and abs(val) > 10) or val < -100 or val > 500:
                    is_noise[i] = True
                    continue

        if inst.cat in ('EQ', 'LT', 'LE') and inst.expr:
            if re.match(r'r\d+\s*=\s*\(', inst.expr):
                is_noise[i] = True
                continue

        if inst.cat == 'TEST' and inst.expr:
            if re.match(r'TEST\(D=', inst.expr):
                is_noise[i] = True
                continue
            if inst.expr.startswith('test '):
                is_noise[i] = True
                continue

    for i, inst in enumerate(path):
        if inst.cat == 'LOADNIL' and not is_noise[i]:
            near = any(is_noise[j] for j in range(max(0,i-3), min(n,i+3)) if j != i)
            if near:
                is_noise[i] = True

    return [inst for i, inst in enumerate(path) if not is_noise[i]]


def substitute_regs(expr, regs):
    if not expr:
        return expr

    def replace_reg(m):
        rnum = int(m.group(1))
        if rnum in regs:
            val = regs[rnum]
            if needs_parens(val) and not is_simple(val):
                return f'({val})'
            return val
        return m.group(0)

    return re.sub(r'r(\d+)', replace_reg, expr)


def is_simple(expr):
    return bool(re.match(r'^[a-zA-Z_]\w*(\.\w+)*$', expr))


def needs_parens(expr):
    if re.match(r'^[a-zA-Z_]\w*$', expr):
        return False
    if re.match(r'^[a-zA-Z_][\w.]*$', expr):
        return False
    if re.match(r"^'[^']*'$", expr) or re.match(r'^"[^"]*"$', expr):
        return False
    if re.match(r'^-?\d+(\.\d+)?$', expr):
        return False
    if expr == '{}' or expr == '...' or expr == 'true' or expr == 'false' or expr == 'nil':
        return False
    return True


def resolve_remaining_regs(expr):
    return re.sub(r'\br(\d+)\b', lambda m: f'v{m.group(1)}', expr)


def format_call(expr, regs):
    resolved = substitute_regs(expr, regs)
    resolved = re.sub(r',\s*\.\.\.\s*,\s*', ', ', resolved)
    resolved = re.sub(r'\(\s*\.\.\.\s*\)', '()', resolved)
    resolved = resolve_remaining_regs(resolved)
    return resolved


def reconstruct_proto(proto):
    path = trace_execution(proto)
    real = filter_dispatch(path, proto.num_regs)

    if not real:
        return []

    regs = {}
    stmts = []

    for inst in real:
        cat = inst.cat

        if inst.dest_reg is not None and inst.expr:
            if cat in ('GETGLOBAL', 'LOADK', 'GETTABLE', 'MOVE',
                       'GETUPVAL', 'NEWTABLE', 'LOADBOOL', 'VARARG',
                       'MUL', 'ADD', 'SUB', 'DIV', 'MOD', 'POW', 'UNM', 'CONCAT'):
                resolved = substitute_regs(inst.expr, regs)
                regs[inst.dest_reg] = resolved
                continue

        if cat == 'CALL' and inst.expr:
            resolved = format_call(inst.expr, regs)
            if inst.dest_reg is not None:
                regs[inst.dest_reg] = resolved
                stmts.append(f'local v{inst.dest_reg} = {resolved}')
            else:
                stmts.append(resolved)
            continue

        if cat == 'CLOSURE':
            if inst.dest_reg is not None:
                regs[inst.dest_reg] = 'function() end'
            continue

        if cat == 'SETTABLE' and inst.expr:
            resolved = substitute_regs(inst.expr, regs)
            resolved = resolve_remaining_regs(resolved)
            stmts.append(resolved)
            continue

        if cat == 'TEST' and inst.expr:
            resolved = substitute_regs(inst.expr, regs)
            resolved = re.sub(r'\s*then\s+goto\s+\d+', ' then', resolved)
            resolved = resolve_remaining_regs(resolved)
            stmts.append(resolved)
            continue

        if cat in ('EQ', 'LT', 'LE') and inst.expr:
            resolved = substitute_regs(inst.expr, regs)
            resolved = re.sub(r'\s*then\s+goto\s+\d+', ' then', resolved)
            resolved = resolve_remaining_regs(resolved)
            stmts.append(resolved)
            continue

        if cat == 'RETURN' and inst.expr:
            resolved = substitute_regs(inst.expr, regs)
            resolved = re.sub(r'return\s+r(\d+)\.\.r(\d+)',
                              lambda m: build_return_range(m, regs), resolved)
            resolved = resolve_remaining_regs(resolved)
            stmts.append(resolved)
            continue

        if cat == 'FORLOOP' and inst.expr:
            stmts.append(f'-- {inst.expr}')
            continue

    return stmts


def build_return_range(match, regs):
    start = int(match.group(1))
    end = int(match.group(2))
    if end - start > 10:
        end = start + 5
    parts = []
    for r in range(start, end + 1):
        if r in regs:
            parts.append(regs[r])
        else:
            parts.append(f'v{r}')
    return 'return ' + ', '.join(parts)


def clean_stmts(stmts):
    result = []
    for s in stmts:
        if not s or not s.strip():
            continue
        s = s.strip()
        if s.startswith('-- dispatch') or s.startswith('-- closure upval'):
            continue
        if s == 'close upvals':
            continue
        result.append(s)

    final = []
    i = 0
    while i < len(result):
        line = result[i]
        if line.startswith('if ') and line.endswith(' then'):
            if i + 1 < len(result) and result[i+1] == 'end':
                i += 2
                continue
        final.append(line)
        i += 1

    return final


def inline_single_use(stmts):
    reg_defs = {}
    reg_uses = defaultdict(int)

    for i, s in enumerate(stmts):
        m = re.match(r'local v(\d+) = (.+)', s)
        if m:
            reg_defs[int(m.group(1))] = (i, m.group(2))

        for rm in re.finditer(r'v(\d+)', s):
            rn = int(rm.group(1))
            if not (s.startswith(f'local v{rn} = ') and s.index(f'v{rn}') == 6):
                reg_uses[rn] += 1

    inlined = set()
    result = []
    for i, s in enumerate(stmts):
        skip = False
        for rn, (def_idx, expr) in reg_defs.items():
            if def_idx == i and reg_uses.get(rn, 0) == 1:
                inlined.add(rn)
                skip = True
                break
        if skip:
            continue

        for rn in inlined:
            if f'v{rn}' in s:
                _, expr = reg_defs[rn]
                if needs_parens(expr):
                    s = s.replace(f'v{rn}', f'({expr})')
                else:
                    s = s.replace(f'v{rn}', expr)
        result.append(s)

    return result


def emit_output(protos, all_stmts):
    out = []
    out.append('-- Luraph v14.7 Reconstructed Source')
    out.append('')

    for proto, stmts in zip(protos, all_stmts):
        if not stmts:
            continue

        out.append(f'-- ======== Proto {proto.proto_num} ({proto.num_inst} inst, '
                   f'{proto.num_regs} regs, {proto.num_upvals} upvals) ========')

        indent = 0
        for line in stmts:
            stripped = line.strip()
            if stripped in ('end', 'else', 'elseif'):
                indent = max(0, indent - 1)
            elif stripped.startswith('else') or stripped.startswith('elseif'):
                indent = max(0, indent - 1)

            out.append('    ' * indent + stripped)

            if stripped.endswith(' then') or stripped.endswith(' do') or stripped == 'else':
                indent += 1

        out.append('')

    return '\n'.join(out)


def main():
    protos = parse_decompiled('decompiled_output.lua')
    print(f"Parsed {len(protos)} protos")

    all_stmts = []
    for proto in protos:
        stmts = reconstruct_proto(proto)
        stmts = clean_stmts(stmts)
        stmts = inline_single_use(stmts)
        all_stmts.append(stmts)

    output = emit_output(protos, all_stmts)

    with open('reconstructed_source.lua', 'w', encoding='utf-8') as f:
        f.write(output)

    total = sum(len(s) for s in all_stmts)
    non_empty = sum(1 for s in all_stmts if s)
    print(f"Reconstructed {non_empty} non-empty protos, {total} statements")
    print(f"Output: reconstructed_source.lua")


if __name__ == '__main__':
    main()
