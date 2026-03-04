"""
Luraph v14.7 Source Reconstructor v2
Completely rewritten with pattern-based dispatch detection.
"""
import re, json
from collections import defaultdict

DISPATCH_SENTINELS = {
    'UDim', 'Vector2', 'Vector3', 'Color3', 'BrickColor', 'DateTime',
    'ElapsedTime', 'Enum', 'NumberSequence', 'NumberSequenceKeypoint',
    'ColorSequence', 'WebSocket', 'Window',
}

VM_DISPATCH_MAP = {
    2: 'gsub', 4: '[C]', 5: 'gmatch', 6: 'namewhat',
    9: 'format', 10: 'select', 11: 'info', 13: 'error',
    14: 'concat', 18: 'match', 19: 'byte', 20: 'tonumber',
    22: 'rawget', 23: 'gmatch', 24: 'unpack', 26: 'number',
    27: 'status', 28: 'yield', 29: 'close', 30: 'resume',
    32: 'info', 36: 'info', 37: 'traceback', 41: 'insert',
    46: 'wrap', 56: 'function', 59: 'setmetatable', 60: 'tonumber',
    61: 'getinfo', 62: 'tostring', 68: 'pcall', 70: 'type',
    72: 'typeof', 74: 'create', 75: 'wrap', 76: 'table',
    80: 'rrotate',
}

REAL_GLOBALS = {
    'game', 'pcall', 'xpcall', 'select', 'tonumber', 'tostring',
    'require', 'loadstring', 'debug', 'coroutine', 'next',
    'newcclosure', 'hookmetamethod', 'getrenv', 'isfile', 'readfile',
    'writefile', 'bit32_band', 'enc', 'noclipRan', 'customerPosition',
    'nextPageCursor',
}

with open('luraph_strings_full.json', encoding='utf-8') as f:
    raw_consts = json.load(f)
CONSTANTS = {}
for k, v in raw_consts.items():
    idx = int(k)
    if v.get('type') == 's':
        CONSTANTS[idx] = v.get('text', f'<str_{idx}>')
    elif v.get('type') == 'n':
        CONSTANTS[idx] = v.get('val', 0)


class Inst:
    __slots__ = ['pc', 'op', 'cat', 'detail', 'jmp_target',
                 'dest_reg', 'expr', 'is_dispatch']
    def __init__(self, pc, op, cat, detail):
        self.pc = pc
        self.op = op
        self.cat = cat
        self.detail = detail
        self.jmp_target = None
        self.dest_reg = None
        self.expr = None
        self.is_dispatch = False


class Proto:
    def __init__(self, num, idx, ninst, nupv, nreg):
        self.num = num
        self.idx = idx
        self.ninst = ninst
        self.nupv = nupv
        self.nreg = nreg
        self.insts = {}


def parse_file(filename):
    protos = []
    cur = None
    proto_re = re.compile(
        r'-- Proto (\d+) \(index (\d+)\): (\d+) instructions, (\d+) upvals, (\d+) regs')
    inst_re = re.compile(r'\s+(\d+)\s+\[\s*(\d+)\]\s+(\w+)\s+(.*)')

    for line in open(filename, encoding='utf-8'):
        m = proto_re.search(line)
        if m:
            cur = Proto(int(m.group(1)), int(m.group(2)),
                        int(m.group(3)), int(m.group(4)), int(m.group(5)))
            protos.append(cur)
            continue
        if cur is None:
            continue
        m = inst_re.match(line)
        if m:
            inst = Inst(int(m.group(1)), int(m.group(2)),
                        m.group(3), m.group(4).strip())
            classify(inst)
            cur.insts[inst.pc] = inst
    return protos


def classify(inst):
    cat, d = inst.cat, inst.detail

    if cat == 'JMP':
        m = re.match(r'goto (\d+)', d)
        if m: inst.jmp_target = int(m.group(1))

    elif cat in ('GETGLOBAL', 'GETTABLE', 'LOADK', 'MOVE', 'LOADBOOL',
                 'GETUPVAL', 'NEWTABLE', 'VARARG'):
        if '-- dispatch' in d:
            inst.is_dispatch = True
            return
        m = re.match(r'r(\d+)\s*=\s*(.*)', d)
        if m:
            inst.dest_reg = int(m.group(1))
            inst.expr = m.group(2).strip()
        if cat == 'NEWTABLE':
            m2 = re.match(r'r(\d+)\s*=\s*\{\}', d)
            if m2:
                inst.dest_reg = int(m2.group(1))
                inst.expr = '{}'
        if cat == 'VARARG':
            m2 = re.match(r'VARARG\(', d)
            if m2:
                inst.dest_reg = None
                inst.expr = '...'

    elif cat in ('MUL', 'ADD', 'SUB', 'DIV', 'MOD', 'POW', 'UNM', 'CONCAT'):
        m = re.match(r'r(\d+)\s*=\s*(.*)', d)
        if m:
            inst.dest_reg = int(m.group(1))
            inst.expr = m.group(2).strip()

    elif cat == 'CALL':
        m = re.match(r'r(\d+)\s*=\s*(.*)', d)
        if m:
            inst.dest_reg = int(m.group(1))
            inst.expr = m.group(2).strip()
        elif re.match(r'r\d+\(', d):
            inst.expr = d

    elif cat == 'SETTABLE':
        if 'SETTABLE_dispatch' in d:
            inst.is_dispatch = True
        else:
            inst.expr = d

    elif cat in ('EQ', 'LT', 'LE'):
        if '-- dispatch' in d:
            inst.is_dispatch = True
        else:
            inst.expr = d
            jm = re.search(r'goto\s+(\d+)', d)
            if jm:
                inst.jmp_target = int(jm.group(1))

    elif cat == 'TEST':
        if '-- dispatch' in d or d.startswith('TEST(D='):
            inst.is_dispatch = True
        else:
            inst.expr = d
            jm = re.search(r'goto\s+(\d+)', d)
            if jm:
                inst.jmp_target = int(jm.group(1))

    elif cat == 'RETURN':
        inst.expr = d

    elif cat == 'CLOSURE':
        m = re.match(r'r(\d+)\s*=\s*(.*)', d)
        if m:
            inst.dest_reg = int(m.group(1))
            inst.expr = m.group(2).strip() or 'function() end'

    elif cat == 'FORLOOP':
        inst.expr = d

    elif cat in ('CLOSE', 'DISPATCH', 'MULTI_WRITE', 'LOADNIL'):
        inst.is_dispatch = True


def trace(proto):
    """Multi-path BFS: explore all reachable states through dispatch."""
    insts = proto.insts
    visited = set()
    collected = {}
    queue = [0]
    order = 0

    while queue:
        pc = queue.pop(0)
        while 0 <= pc < proto.ninst:
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

            collected[pc] = (order, inst)
            order += 1

            if inst.cat in ('EQ', 'LT', 'LE', 'TEST'):
                jmp_inst = insts.get(pc + 1)
                if jmp_inst and jmp_inst.cat == 'JMP' and jmp_inst.jmp_target is not None:
                    visited.add(pc + 1)
                    queue.append(jmp_inst.jmp_target)
                    queue.append(pc + 2)
                    if inst.jmp_target is not None:
                        queue.append(inst.jmp_target)
                    break
                else:
                    queue.append(pc + 1)
                    if inst.jmp_target is not None:
                        queue.append(inst.jmp_target)
                    break

            pc += 1

    path = [inst for _, inst in sorted(collected.values(), key=lambda x: x[0])]
    return path


def is_sentinel_global(name):
    return name in DISPATCH_SENTINELS


def filter_noise(path, nreg):
    n = len(path)
    noise = [False] * n

    i = 0
    while i < n:
        inst = path[i]
        if inst.cat == 'NEWTABLE':
            bl = 1
            j = i + 1
            while j < n:
                nj = path[j]
                if nj.cat == 'SETTABLE' and nj.expr and re.match(r'r\d+\[', nj.expr):
                    bl += 1; j += 1; continue
                if nj.cat == 'LOADNIL':
                    bl += 1; j += 1; continue
                break
            if bl >= 3:
                for k in range(i, j):
                    noise[k] = True
                i = j; continue
        i += 1

    sentinel_regs = set()
    for i, inst in enumerate(path):
        if inst.is_dispatch:
            noise[i] = True
            continue

        if inst.cat == 'GETGLOBAL' and inst.expr:
            gname = inst.expr.strip()
            if is_sentinel_global(gname):
                sentinel_regs.add(inst.dest_reg)
                noise[i] = True
                for j in range(i+1, min(i+4, n)):
                    nj = path[j]
                    if nj.cat in ('EQ', 'LT', 'LE') and nj.expr:
                        noise[j] = True
                        break
                    if nj.cat in ('LOADNIL', 'CLOSE'):
                        noise[j] = True
                        continue
                    break
                continue

        if inst.cat == 'SETTABLE' and inst.expr:
            if re.match(r'r\d+\[\d+\]\s*=\s*-?\d+$', inst.expr):
                noise[i] = True; continue
            if inst.expr.startswith('{}['):
                noise[i] = True; continue
            m = re.match(r'r(\d+)\[(\d+)\]\s*=\s*r(\d+)', inst.expr)
            if m:
                tbl = int(m.group(1))
                key = int(m.group(2))
                if key > 50:
                    noise[i] = True; continue

        if inst.cat == 'GETTABLE' and inst.expr:
            m = re.match(r'r\d+\s*=\s*r(\d+)\[(\d+)\]', inst.expr)
            if m:
                base_r = int(m.group(1))
                key = int(m.group(2))
                if key > 200:
                    noise[i] = True; continue
                if base_r in sentinel_regs:
                    noise[i] = True; continue

        if inst.cat in ('EQ', 'LT', 'LE') and inst.expr:
            if re.search(r'\b\d{3,}\b', inst.expr):
                noise[i] = True; continue

        if inst.cat == 'TEST' and inst.expr:
            if inst.expr.startswith('test r'):
                m = re.match(r'test r(\d+)', inst.expr)
                if m and int(m.group(1)) in sentinel_regs:
                    noise[i] = True; continue

        if inst.cat == 'LOADK' and inst.expr:
            m = re.match(r'r\d+\s*=\s*(-?\d+)$', inst.expr)
            if m and abs(int(m.group(1))) > 50000:
                noise[i] = True; continue

    for i, inst in enumerate(path):
        if not noise[i] and inst.cat == 'LOADNIL':
            near = any(noise[j] for j in range(max(0,i-3), min(n,i+4)) if j != i)
            if near:
                noise[i] = True

    return [inst for i, inst in enumerate(path) if not noise[i]]


def sub_regs(expr, regs):
    if not expr: return expr
    def repl(m):
        rn = int(m.group(1))
        if rn in regs:
            v = regs[rn]
            if re.match(r'^[\w.]+$', v) or re.match(r"^'[^']*'$", v) or re.match(r'^-?\d+(\.\d+)?$', v):
                return v
            if v in ('{}', '...', 'true', 'false', 'nil', 'function() end'):
                return v
            return f'({v})'
        return f'v{m.group(1)}'
    return re.sub(r'\br(\d+)\b', repl, expr)


def resolve_regs(expr):
    return re.sub(r'\br(\d+)\b', lambda m: f'v{m.group(1)}', expr)


def expr_depth(expr):
    depth = 0
    max_d = 0
    for c in expr:
        if c == '(': depth += 1; max_d = max(max_d, depth)
        elif c == ')': depth -= 1
    return max_d


def _expand_call_range(expr):
    def expand(m):
        start = int(m.group(1))
        end = int(m.group(2))
        if end - start > 4:
            return f'r{start}, r{end}'
        return ', '.join(f'r{i}' for i in range(start, end + 1))
    return re.sub(r'r(\d+),\s*\.\.\.,\s*r(\d+)', expand, expr)


def reconstruct(proto):
    path = trace(proto)
    real = filter_noise(path, proto.nreg)
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
                resolved = sub_regs(inst.expr, regs)
                if expr_depth(resolved) > 2:
                    resolved = resolve_regs(inst.expr)
                regs[inst.dest_reg] = resolved
                continue

        if cat == 'CALL' and inst.expr:
            expanded = _expand_call_range(inst.expr)
            resolved = sub_regs(expanded, regs)
            if expr_depth(resolved) > 2:
                resolved = resolve_regs(expanded)
            resolved = resolve_regs(resolved)
            resolved = re.sub(r',\s*\.\.\.\s*,', ',', resolved)
            resolved = re.sub(r'\(\s*\.\.\.\s*\)', '()', resolved)
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
            resolved = sub_regs(inst.expr, regs)
            resolved = resolve_regs(resolved)
            stmts.append(resolved)
            continue

        if cat in ('TEST', 'EQ', 'LT', 'LE') and inst.expr:
            resolved = sub_regs(inst.expr, regs)
            resolved = resolve_regs(resolved)
            resolved = re.sub(r'\s*then\s+goto\s+\d+', ' then', resolved)
            stmts.append(resolved)
            continue

        if cat == 'RETURN' and inst.expr:
            resolved = re.sub(r'return\s+r(\d+)\.\.r(\d+)',
                              lambda m: _build_return(m, regs), inst.expr)
            resolved = sub_regs(resolved, regs)
            resolved = resolve_regs(resolved)
            stmts.append(resolved)
            continue

        if cat == 'FORLOOP' and inst.expr:
            if 'dispatch' not in inst.expr:
                m = re.match(r'FORLOOP r(\d+)', inst.expr)
                if m:
                    base = int(m.group(1))
                    init = regs.get(base, f'v{base}')
                    limit = regs.get(base+1, f'v{base+1}')
                    step = regs.get(base+2, f'v{base+2}')
                    vals = [str(init), str(limit), str(step)]
                    if any('{}' in v for v in vals):
                        continue
                    if any(v == 'v0' or v == 'v1' for v in vals):
                        continue
                    stmts.append(f'-- for v{base+3} = {init}, {limit}, {step} do ... end')
                else:
                    stmts.append(f'-- forloop: {inst.expr}')
            continue

    return stmts


def _build_return(m, regs):
    s, e = int(m.group(1)), int(m.group(2))
    if e - s > 10: e = s + 5
    parts = [regs.get(r, f'v{r}') for r in range(s, e+1)]
    return 'return ' + ', '.join(parts)


def is_dispatch_stmt(line):
    if not line or not line.strip():
        return True
    s = line.strip()

    if s.startswith('-- dispatch') or s.startswith('-- closure upval'):
        return True
    if s == 'close upvals':
        return True

    if re.match(r'local\s+v(\d+)\s*=\s*\(v\1\(', s):
        return True

    if re.search(r'\{\}\[', s):
        return True
    if re.search(r'\{\}\s*\(', s):
        return True
    if re.search(r'\(\{\}\(', s):
        return True

    m = re.match(r'v\d+\[(\d+)\]\s*=\s*(-?\d+)$', s)
    if m:
        key, val = int(m.group(1)), int(m.group(2))
        if key > 10 or abs(val) > 200:
            return True

    if re.match(r'if\s+(\d+)\s+then', s):
        return True

    m = re.match(r'if\s+not\s+(\d+)\s+then', s)
    if m:
        return True

    if s.startswith('if ') and s.endswith(' then'):
        cond = s[3:-5].strip()
        for op in ('>=', '<=', '~=', '==', '>', '<'):
            if op in cond:
                parts = cond.split(op, 1)
                if len(parts) == 2:
                    lhs = parts[0].strip()
                    rhs = parts[1].strip()
                    if lhs == rhs:
                        return True
                break

    if re.match(r'if\s+\{\}\s*(>|<|>=|<=|==|~=)', s):
        return True
    if re.match(r'if\s+\S+\s*(>|<|>=|<=|==|~=)\s*\{\}\s+then', s):
        return True

    m = re.match(r'if\s+(\d+)\s*(==|~=)\s*(\d+)\s+then', s)
    if m:
        return True

    if re.search(r'(>|<|>=|<=|==|~=)\s*\(?\(v0\(v1', s):
        return True

    m2 = re.match(r'if\s+v\d+\s*(==|~=)\s*(\d+)\s+then', s)
    if m2 and int(m2.group(2)) > 10:
        return True

    if re.match(r'\d+\(', s):
        return True
    if re.match(r'local\s+v\d+\s*=\s*\d+\(', s):
        return True

    if s.startswith('test '):
        return True

    if re.match(r'v\d+\s*=\s*\(.*\s*(<=|>=|<|>|==|~=)\s*.*\)', s):
        return True

    if s.startswith('if not (') and s.endswith(' then'):
        inner = s[8:-5].strip()
        if re.search(r'\*.*\*', inner):
            return True

    if re.search(r'\bv(\d+)\b.*\*.*\bv\1\b', s):
        return True

    if re.match(r'local\s+v\d+\s*=\s*v\d+\s*$', s):
        return True
    if re.search(r'\(?upval\[\d+\]\)?\(\)', s):
        return True
    if re.match(r'if\s+not\s+\(?upval\[\d+\]\)?\s+then', s):
        return True

    m = re.match(r'local\s+v(\d+)\s*=\s*v(\d+)\(', s)
    if m and m.group(1) == m.group(2):
        return True

    if re.match(r'return\s+\d+\.\.', s):
        return True
    if re.match(r'return\s+-\d+\.\.',  s):
        return True
    if re.search(r'\d+\s*\*\s*v\d+', s) and s.startswith('return '):
        return True

    if s.startswith('return '):
        nums = re.findall(r'\b(\d+)\b', s)
        if any(int(n) > 60 for n in nums):
            return True
        negs = re.findall(r'(-\d+)', s)
        if negs:
            return True

    if re.search(r'\([^)]+\s*\*\s*[^)]+\)\s*\(', s):
        return True

    if re.search(r'\bv\d+\s*\*\s*v\d+', s):
        m2 = re.search(r'\bv(\d+)\s*\*\s*v(\d+)', s)
        if m2 and m2.group(1) == m2.group(2):
            return True

    if re.search(r'\(upval\[\d+\]\)\s*\*\s*\(upval\[\d+\]\)', s):
        return True

    if re.search(r'\brequire\s*\*', s):
        return True

    if re.search(r'\bk\d+\b', s):
        return True

    if re.match(r'\d+\s*=\s*', s):
        return True

    if re.search(r'\(\d+\(', s):
        return True
    if re.search(r'\b\d+\s*\(', s) and not re.match(r'(if|local|return)\b', s):
        return True

    m2 = re.match(r'(\w+)\s*=\s*\(\1\s*(<=|>=|<|>|==|~=)\s*\1\)', s)
    if m2:
        return True
    m2 = re.match(r'(v\d+)\s*=\s*\(\1\s*(<=|>=|<|>|==|~=)\s*\1\)', s)
    if m2:
        return True
    m2 = re.search(r'=\s*\((\w+)\s*(<=|>=|<|>|==|~=)\s*\1\)', s)
    if m2:
        return True

    if re.search(r'\{\}\s*\.\.', s):
        return True

    if re.search(r"\('string'\)\s*\(", s):
        return True
    if re.search(r"\)\s*\('string'\)\s*$", s):
        return True
    if re.search(r"\)\)\s*\('string'\)", s):
        return True

    if re.search(r'\^\s*\w+\)\s*\(', s):
        return True

    if '?' in s and not s.startswith('--'):
        return True

    if re.match(r'if\s+\{\}\s+then', s):
        return True

    if 'k?' in s:
        return True

    if re.match(r'\(.*\)\s*=\s*', s):
        return True

    if re.search(r"'string'\s*\(", s):
        return True
    if re.search(r"'string'\s*\*", s):
        return True
    if re.search(r"v\d+\s*>\s*'string'", s):
        return True
    if re.search(r"'string'\s*>\s*", s):
        return True
    if re.search(r"v\d+\s*==\s*'string'", s):
        return True
    if re.search(r"v\d+\s*==\s*\(v\d+\('string'\)\)", s):
        return True
    if re.search(r"\(\d+\('string'\)\)", s):
        return True
    if re.search(r"v\d+\s*==\s*-\d+", s):
        return True

    depth = 0
    max_d = 0
    for c in s:
        if c == '(': depth += 1; max_d = max(max_d, depth)
        elif c == ')': depth -= 1
    if max_d > 4:
        return True

    m = re.match(r'([\w.]+)\[(\d+)\]\s*=', s)
    if m:
        key = int(m.group(2))
        if key > 50:
            return True

    if re.match(r'\(.*\)\[(\d+)\]\s*=', s):
        return True

    if re.search(r'\[(-?\d+)\]', s):
        nums = [abs(int(x)) for x in re.findall(r'\[(-?\d+)\]', s)]
        if any(n > 100 for n in nums):
            return True

    all_nums = re.findall(r'\b(\d{3,})\b', s)
    if all_nums and not s.startswith('--'):
        if any(int(n) > 200 for n in all_nums):
            return True

    if re.match(r'\(v0\(v1,', s):
        return True

    if re.match(r'if\s+\(v0\(v1,', s):
        return True
    if re.match(r'if\s+\(\(v0\(v1,', s):
        return True

    if re.search(r'\(v\d+\(\d+\)\)\s*(==|~=|>|<|>=|<=)\s*\d+', s):
        return True

    if re.search(r'=\s*\(v0\(v1,\s*\{\}\)\)', s):
        return True

    if re.search(r'\bv0\s*\(', s):
        return True
    if re.search(r'\bv0\s*(>|<|>=|<=|==|~=)', s):
        return True
    if re.search(r'(>|<|>=|<=|==|~=)\s*v0\b', s):
        return True

    if re.search(r'\d+\s*\^\s*\(', s):
        return True
    if re.search(r'\^\s*\d+', s):
        return True
    if re.search(r'\^\s*next\b', s):
        return True

    if re.match(r'\(\(.*\)\)\(', s):
        return True

    if re.match(r'\(\d+\s*\*\s*\d+\)', s):
        return True

    if re.search(r'\b\d+\s*\*\s*\d+\b', s) and re.search(r'\)\s*\(', s):
        return True

    return False


def _remove_empty_blocks(stmts):
    changed = True
    while changed:
        changed = False
        out = []
        i = 0
        while i < len(stmts):
            s = stmts[i]
            if s.startswith('if ') and s.endswith(' then'):
                if i + 1 < len(stmts) and stmts[i+1] == 'end':
                    i += 2; changed = True; continue
                if i + 1 >= len(stmts):
                    i += 1; changed = True; continue
            out.append(s)
            i += 1
        stmts = out
    return stmts


def _remove_contradictory_ifs(stmts):
    changed = True
    while changed:
        changed = False
        out = []
        i = 0
        while i < len(stmts):
            s = stmts[i]
            if s.startswith('if ') and s.endswith(' then') and i + 1 < len(stmts):
                cond = s[3:-5].strip()
                cond_bare = cond.strip('()')
                nxt = stmts[i+1]
                if nxt.startswith('if not ') and nxt.endswith(' then'):
                    ncond = nxt[7:-5].strip().strip('()')
                    if cond_bare == ncond:
                        i += 2; changed = True; continue
                if nxt.startswith('if ') and nxt.endswith(' then'):
                    ncond = nxt[3:-5].strip()
                    ncond_bare = ncond.strip('()')
                    if ncond.startswith('not '):
                        inner = ncond[4:].strip().strip('()')
                        if inner == cond_bare:
                            i += 2; changed = True; continue
                    if cond.startswith('not '):
                        inner = cond[4:].strip().strip('()')
                        if inner == ncond_bare:
                            i += 2; changed = True; continue

                if cond.startswith('not ') and nxt.startswith('if ') and nxt.endswith(' then'):
                    neg_var = cond[4:].strip().strip('()')
                    pos_cond = nxt[3:-5].strip().strip('()')
                    if re.match(re.escape(neg_var) + r"\('", pos_cond):
                        i += 2; changed = True; continue

                if cond.startswith('not '):
                    neg_var = cond[4:].strip().strip('()')
                    if re.search(r'\b' + re.escape(neg_var) + r'\s*\(', nxt):
                        out.extend(stmts[i+1:])
                        i = len(stmts)
                        changed = True
                        continue
            out.append(s)
            i += 1
        stmts = out
    return stmts


def _is_guard_cond(cond):
    if re.match(r'^(not\s+)?v\d+$', cond):
        return True
    if re.match(r'^v\d+\s*(>|<|>=|<=)\s*\w+$', cond):
        return True
    if re.match(r'^\(v\d+\[\d+\]\)$', cond):
        return True
    return False


def _collapse_guard_ifs(stmts):
    changed = True
    while changed:
        changed = False
        out = []
        i = 0
        while i < len(stmts):
            s = stmts[i]
            if s.startswith('if ') and s.endswith(' then'):
                cond = s[3:-5].strip()
                if _is_guard_cond(cond):
                    j = i + 1
                    guard_depth = 1
                    while j < len(stmts) and stmts[j].startswith('if ') and stmts[j].endswith(' then'):
                        inner_cond = stmts[j][3:-5].strip()
                        if _is_guard_cond(inner_cond):
                            guard_depth += 1
                            j += 1
                        else:
                            break
                    if guard_depth >= 3:
                        out.extend(stmts[j:])
                        i = len(stmts)
                        changed = True
                        continue
            out.append(s)
            i += 1
        stmts = out
    return stmts


def _merge_redundant_ifs(stmts):
    active_conds = []
    out = []
    for s in stmts:
        if s.startswith('if ') and s.endswith(' then'):
            cond = s[3:-5].strip()
            if cond in active_conds:
                continue
            active_conds.append(cond)
        out.append(s)
    return out


def clean(stmts):
    result = [s for s in stmts if not is_dispatch_stmt(s)]

    final = _remove_empty_blocks(result)
    final = _remove_contradictory_ifs(final)
    final = _remove_empty_blocks(final)
    final = _collapse_guard_ifs(final)
    final = _remove_empty_blocks(final)
    final = _merge_redundant_ifs(final)
    final = _remove_empty_blocks(final)

    deduped = []
    for s in final:
        if not deduped or s != deduped[-1]:
            deduped.append(s)

    seen_assigns = {}
    merged = []
    for s in deduped:
        m = re.match(r'local (v\d+) = (.+)', s)
        if m:
            var = m.group(1)
            if var in seen_assigns:
                continue
            seen_assigns[var] = True
        merged.append(s)

    cleaned = []
    for s in merged:
        s = re.sub(r'\(upval\[(\d+)\]\)', r'upval[\1]', s)
        s = re.sub(r'\(v(\d+)\[(\d+)\]\)', r'v\1[\2]', s)
        s = re.sub(r'=\s*\((v\d+\(.*?\))\)\s*$', r'= \1', s)
        s = re.sub(r'=\s*\((v\d+\[\d+\]\[\d+\])\)\s*$', r'= \1', s)
        m = re.match(r'if \(([^()]*\([^()]*\))\) then$', s)
        if m:
            s = f'if {m.group(1)} then'
        s = re.sub(r'not \((\w+\([^()]*\))\)', r'not \1', s)
        def _resolve_dispatch(m):
            prefix = m.group(1)
            idx = int(m.group(2))
            if idx in VM_DISPATCH_MAP:
                name = VM_DISPATCH_MAP[idx]
                if name.isidentifier():
                    return f'{prefix}.{name}'
            return m.group(0)
        s = re.sub(r'(v\d+|upval\[\d+\])\[(\d+)\]', _resolve_dispatch, s)
        cleaned.append(s)

    named = []
    for s in cleaned:
        s = s.replace('upval[0]', '_env')
        s = s.replace('upval[1]', '_env2')
        s = s.replace('upval[2]', '_env3')
        named.append(s)

    trimmed = []
    for i, s in enumerate(named):
        if (s.startswith('return ') or s == 'return') and i + 1 < len(named):
            trimmed.append(s)
            break
        trimmed.append(s)

    return trimmed


def _has_side_effect(expr):
    if '(' in expr:
        return True
    return False


def _remove_unused_locals(stmts):
    changed = True
    while changed:
        changed = False
        defs = {}
        for i, s in enumerate(stmts):
            m = re.match(r'local (v\d+) = (.+)', s)
            if m:
                defs[m.group(1)] = (i, m.group(2))

        used = set()
        for var, (di, expr) in defs.items():
            for j, s in enumerate(stmts):
                if j == di:
                    continue
                if re.search(r'\b' + re.escape(var) + r'\b', s):
                    used.add(var)
                    break

        unused_no_fx = [var for var in defs if var not in used
                        and not _has_side_effect(defs[var][1])]
        unused_fx = [var for var in defs if var not in used
                     and _has_side_effect(defs[var][1])]
        if unused_no_fx:
            remove_indices = {defs[var][0] for var in unused_no_fx}
            stmts = [s for i, s in enumerate(stmts) if i not in remove_indices]
            changed = True
        if unused_fx:
            for var in unused_fx:
                idx, expr = defs[var]
                stmts[idx] = expr
            changed = True
    return stmts


def inline_vars(stmts):
    stmts = _remove_unused_locals(stmts)
    defs = {}

    for i, s in enumerate(stmts):
        m = re.match(r'local v(\d+) = (.+)', s)
        if m:
            defs[int(m.group(1))] = (i, m.group(2))

    post_uses = defaultdict(int)
    for rn, (di, expr) in defs.items():
        for j in range(di + 1, len(stmts)):
            for rm in re.finditer(r'\bv(\d+)\b', stmts[j]):
                if int(rm.group(1)) == rn:
                    post_uses[rn] += 1

    inlined = set()
    result = []
    for i, s in enumerate(stmts):
        skip = False
        for rn, (di, expr) in defs.items():
            if di == i and post_uses.get(rn, 0) == 1:
                inlined.add(rn)
                skip = True
                break
        if skip: continue

        for rn in inlined:
            tag = f'v{rn}'
            pat = r'\b' + re.escape(tag) + r'\b'
            if re.search(pat, s):
                _, expr = defs[rn]
                if re.match(r'^[\w.]+$', expr) or re.match(r"^'[^']*'$", expr):
                    s = re.sub(pat, expr, s)
                else:
                    s = re.sub(pat, f'({expr})', s)
        result.append(s)

    return result


def _infer_purpose(stmts):
    text = ' '.join(stmts)
    if 'writefile' in text:
        return 'file_writer'
    if 'require' in text:
        return 'module_loader'
    if 'newcclosure' in text:
        return 'closure_wrapper'
    if 'customerPosition' in text and 'return' in text:
        return 'position_handler'
    if 'customerPosition' in text:
        return 'position_setter'
    if re.search(r'\.traceback\b', text):
        return 'error_handler'
    if re.search(r'\.setmetatable\b', text):
        return 'meta_setup'
    if re.search(r'\.yield\b.*\.byte\b', text):
        return 'coroutine_processor'
    if re.search(r'\.gmatch\b', text) and re.search(r'\.gsub\b', text):
        return 'string_processor'
    if re.search(r'\.info\b.*\.info\b', text):
        return 'debug_inspector'
    if re.search(r'\.info\(', text):
        return 'info_caller'
    if re.search(r'\.yield\(', text) and 'return' in text:
        return 'yield_handler'
    if re.search(r'\.yield\(', text):
        return 'yield_caller'
    if re.search(r'\.concat\(', text):
        return 'concat_caller'
    if re.search(r'\.select\(', text):
        return 'select_caller'
    if re.search(r'\.wrap\s*=', text):
        return 'wrap_setter'
    if text.strip().startswith('return ') and text.count('\n') == 0:
        return 'value_returner'
    all_return = all(s.startswith('return ') or s == 'return' for s in stmts)
    if all_return:
        return 'value_returner'
    real = [s for s in stmts if not s.startswith('if') and not s.startswith('--') and not s.startswith('return') and s.strip() != 'end']
    if all(re.search(r'\w+[\[\.]\w+.*=', s) for s in real if s.strip()):
        return 'property_setter'
    if any(s.startswith('if ') for s in stmts) and any(s.startswith('return') for s in stmts):
        return 'conditional_returner'
    if any(s.startswith('if ') for s in stmts):
        return 'conditional_handler'
    if any(s.startswith('-- for ') for s in stmts):
        return 'loop_handler'
    if all('_env' in s for s in real if s.strip()):
        return 'env_caller'
    if re.search(r'_env2\(', text):
        return 'env2_caller'
    if re.search(r'\)\(', text) and len(stmts) <= 2:
        return 'indirect_caller'
    if len(stmts) == 1 and re.search(r'\w+\(', stmts[0]):
        return 'simple_caller'
    if len(stmts) <= 2 and any(re.search(r'\w+\(', s) for s in stmts):
        return 'caller'
    return None


def _annotate_proto(stmts):
    if not stmts:
        return ''
    all_return = all(s.startswith('return ') or s == 'return' for s in stmts)
    if all_return:
        return ' [returns values]'
    has_return = any(s.startswith('return ') for s in stmts)
    has_assign = any(re.search(r'\w+[\[\.]\w+[\]\w]*\s*=', s) for s in stmts)
    has_call = any(re.search(r'[\w\]\)]\(', s) or s.startswith('(')
                   for s in stmts)
    has_if = any(s.startswith('if ') for s in stmts)
    has_forloop = any(s.startswith('-- for ') for s in stmts)
    tags = []
    if has_forloop:
        tags.append('loop')
    if has_if:
        tags.append('conditional')
    if has_assign:
        tags.append('setter')
    if has_call:
        tags.append('caller')
    if has_return:
        tags.append('returns')
    if any('writefile' in s for s in stmts):
        tags.append('file-io')
    return f' [{", ".join(tags)}]' if tags else ''


def _build_hierarchy():
    try:
        pd = json.load(open('all_protos_data.json', encoding='utf-8'))
        om = json.load(open('opcode_map_final.json', encoding='utf-8'))
        closure_ops = {int(k) for k, v in om.items() if v.get('lua51') == 'CLOSURE'}
        parent_of = {}
        children_of = defaultdict(list)
        for pidx, p in enumerate(pd):
            pnum = pidx + 1
            opcodes = p.get('C4', [])
            c2 = p.get('C2_sparse', {})
            for i, op in enumerate(opcodes):
                if op in closure_ops:
                    c9 = p.get('C9', [])
                    z = c9[i] if i < len(c9) else -1
                    c2v = c2.get(str(i), '')
                    child = None
                    if isinstance(c2v, str) and c2v.startswith('n:'):
                        raw = int(c2v[2:])
                        if 0 < raw <= len(pd):
                            child = raw
                    if child is None and 0 < z <= len(pd):
                        child = z
                    if child and child != pnum:
                        parent_of[child] = pnum
                        children_of[pnum].append(child)
        return parent_of, children_of
    except:
        return {}, {}


def emit(protos, all_stmts):
    nonempty = [(p, s) for p, s in zip(protos, all_stmts) if s]
    total_stmts = sum(len(s) for _, s in nonempty)
    parent_of, children_of = _build_hierarchy()

    globals_found = set()
    for _, stmts in nonempty:
        for s in stmts:
            for g in REAL_GLOBALS:
                if re.search(r'\b' + re.escape(g) + r'\b', s):
                    globals_found.add(g)

    tag_counts = {}
    for _, stmts in nonempty:
        ann = _annotate_proto(stmts)
        for t in re.findall(r'\w[\w-]+', ann):
            tag_counts[t] = tag_counts.get(t, 0) + 1

    method_calls = {}
    method_reads = {}
    _acc_pat = re.compile(r'((?:v\d+|upval\[\d+\])(?:\.\w+|\[\d+\])?)')
    for _, stmts in nonempty:
        for s in stmts:
            for m in _acc_pat.finditer(s):
                k = m.group(1)
                if k == s.rstrip() or not ('.' in k or '[' in k):
                    continue
                end = m.end()
                if end < len(s) and s[end] == '(':
                    method_calls[k] = method_calls.get(k, 0) + 1
                else:
                    method_reads[k] = method_reads.get(k, 0) + 1
            if re.match(r'upval\[\d+\]\(', s):
                k = re.match(r'(upval\[\d+\])', s).group(1)
                method_calls[k] = method_calls.get(k, 0) + 1

    all_text = '\n'.join(s for _, stmts in nonempty for s in stmts)
    resolved_count = len(re.findall(r'(?:v\d+|upval\[\d+\])\.\w+', all_text))
    unresolved_count = len(re.findall(r'(?:v\d+|upval\[\d+\])\[\d+\]', all_text))

    runtime_data = None
    try:
        raw = json.load(open('unobfuscator/cracked script/bloxburg_api_map.json', encoding='utf-8'))
        guis = sorted(set(c['key'] for c in raw if c.get('path') in ('PlayerGui', 'ScriptCreated') and c.get('value_type') not in ('Folder',)))
        remotes = sorted(set(c['key'] for c in raw if c.get('path') == 'ReplicatedStorage'))
        services = sorted(set(c['key'].replace('GetService(','').rstrip(')') for c in raw if 'GetService' in c.get('key','')))
        runtime_data = {'guis': guis, 'remotes': remotes, 'services': services, 'total': len(raw)}
    except:
        pass

    out = ['-- Luraph v14.7 Reconstructed Source (bloxburg_script.lua)']
    out.append(f'-- {len(nonempty)} protos, {total_stmts} statements')
    if runtime_data:
        out.append(f'-- Runtime capture: {runtime_data["total"]} entries from live execution')
        out.append(f'-- Services: {", ".join(runtime_data["services"][:12])}')
        gui_sample = runtime_data['guis'][:8]
        out.append(f'-- Script GUIs: {", ".join(gui_sample)}{"..." if len(runtime_data["guis"])>8 else ""} ({len(runtime_data["guis"])} total)')
        rem_sample = [r for r in runtime_data['remotes'] if len(r) < 20][:8]
        out.append(f'-- Remotes: {", ".join(rem_sample)}{"..." if len(runtime_data["remotes"])>8 else ""} ({len(runtime_data["remotes"])} total)')
    if globals_found:
        out.append(f'-- Globals: {", ".join(sorted(globals_found))}')
    if tag_counts:
        dist = ', '.join(f'{k}:{v}' for k, v in sorted(tag_counts.items(), key=lambda x: -x[1]))
        out.append(f'-- Tags: {dist}')
    top_calls = sorted(method_calls.items(), key=lambda x: -x[1])[:5]
    top_reads = sorted(method_reads.items(), key=lambda x: -x[1])[:5]
    if top_calls:
        out.append(f'-- Frequent calls: {", ".join(f"{k}({v}x)" for k,v in top_calls)}')
    if top_reads:
        out.append(f'-- Frequent reads: {", ".join(f"{k}({v}x)" for k,v in top_reads)}')
    out.append('--')
    out.append('-- Legend: vN = register variable, upval[N] = upvalue/closure variable')
    out.append(f'--   vN.method = resolved VM dispatch ({resolved_count} resolved, {unresolved_count} unresolved)')
    env_calls = sum(v for k, v in method_calls.items() if '_env' in k)
    env_reads = sum(v for k, v in method_reads.items() if '_env' in k)
    if env_calls or env_reads:
        out.append(f'--   _env = VM constants/environment (called {env_calls}x, read {env_reads}x)')
    out.append(f'--   {len(nonempty)}/{len(protos)} protos have real code ({len(protos)-len(nonempty)} dispatch-only)')
    def _normalize(stmts):
        out = []
        for s in stmts:
            n = re.sub(r'v\d+', 'vX', s)
            n = re.sub(r'\.\w+', '.M', n)
            n = re.sub(r'\[\d+\]', '[N]', n)
            n = re.sub(r'\d+', 'N', n)
            out.append(n)
        return tuple(out)

    sim_groups = defaultdict(list)
    for proto, stmts in zip(protos, all_stmts):
        if stmts:
            sim_groups[_normalize(stmts)].append(proto.num)
    sim_map = {}
    for nums in sim_groups.values():
        if len(nums) > 1:
            for n in nums:
                sim_map[n] = [x for x in nums if x != n]

    out.append('')

    nonempty_nums = {p.num for p, s in nonempty}
    nested_children = set()
    for par_num, kids in children_of.items():
        if par_num != 154 and par_num in nonempty_nums:
            for c in kids:
                if c in nonempty_nums:
                    nested_children.add(c)

    stmts_by_num = {}
    proto_by_num = {}
    for proto, stmts in zip(protos, all_stmts):
        if stmts:
            stmts_by_num[proto.num] = stmts
            proto_by_num[proto.num] = proto

    def _emit_proto(proto, stmts, base_indent=0, is_nested=False):
        lines = []
        ann = _annotate_proto(stmts)
        sim = f' ~Proto {",".join(str(x) for x in sim_map[proto.num])}' if proto.num in sim_map else ''
        purpose = _infer_purpose(stmts)
        fname = f'{purpose}_{proto.num}' if purpose else f'proto_{proto.num}'
        if is_nested:
            lines.append('    ' * base_indent + f'-- child Proto {proto.num}{ann}{sim}')
            lines.append('    ' * base_indent + f'local function {fname}()')
            base_indent += 1
        else:
            lines.append(f'-- Proto {proto.num}{ann}{sim}')
            lines.append(f'local function {fname}()')
            base_indent = 1

        indent = base_indent
        open_ifs = 0
        for line in stmts:
            s = line.strip()
            if s in ('end', 'else', 'elseif') or s.startswith('else') or s.startswith('elseif'):
                indent = max(base_indent, indent - 1)
                if s == 'end':
                    open_ifs = max(0, open_ifs - 1)
            lines.append('    ' * indent + s)
            if s.endswith(' then') or s.endswith(' do') or s == 'else':
                indent += 1
                if s.endswith(' then'):
                    open_ifs += 1

        for _ in range(open_ifs):
            lines.append('    ' * max(base_indent, indent - 1) + 'end')
            indent = max(base_indent, indent - 1)

        kids = [c for c in children_of.get(proto.num, []) if c in nonempty_nums and c in nested_children]
        for kid_num in sorted(kids):
            if kid_num in stmts_by_num:
                lines.append('')
                lines.extend(_emit_proto(proto_by_num[kid_num], stmts_by_num[kid_num],
                                         base_indent, is_nested=True))

        if is_nested:
            base_indent -= 1
            lines.append('    ' * base_indent + 'end')
        else:
            lines.append('end')

        lines.append('')
        return lines

    for proto, stmts in zip(protos, all_stmts):
        if not stmts:
            continue
        if proto.num in nested_children:
            continue
        out.extend(_emit_proto(proto, stmts))

    return '\n'.join(out)


def main():
    protos = parse_file('decompiled_output.lua')
    print(f"Parsed {len(protos)} protos")

    all_stmts = []
    for proto in protos:
        stmts = reconstruct(proto)
        stmts = clean(stmts)
        stmts = inline_vars(stmts)
        all_stmts.append(stmts)

    output = emit(protos, all_stmts)

    with open('reconstructed_source.lua', 'w', encoding='utf-8') as f:
        f.write(output)

    total = sum(len(s) for s in all_stmts)
    nonempty = sum(1 for s in all_stmts if s)
    print(f"Reconstructed {nonempty} non-empty protos, {total} statements")
    print(f"Output: reconstructed_source.lua")


if __name__ == '__main__':
    main()
