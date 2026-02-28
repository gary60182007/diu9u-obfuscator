"""Final decompiler: produce clean readable Lua source from Luraph VM bytecode."""
import json
import re
from collections import defaultdict

with open('unobfuscator/cracked script/target2_bytecode.json') as f:
    protos = json.load(f)

p1 = protos[0]
CT = {}
for idx in range(p1['num_instructions']):
    if p1['opcodes'][idx] == 108:
        g = p1['constG'][idx]
        t = p1['constT'][idx]
        if g and t:
            CT[str(g)] = str(t)

# Additional mappings inferred from code analysis
# r1.It = UDim2.new, r1.wU = UDim.new, r1.KU = UDim.new variant
EXTRA_CT = {
    'S': 'setfenv',
    'W': 'string',
    'w': 'rawset',
    'M': 'next',
    'Z': 'getfenv',
    'E': 'type',
    'T': 'table',
    'h': 'pcall',
    'Y': 'UDim2',
    's': 'select',
    'p': 'Luraph',
    'L': 'coroutine',
    'i': 'coroutine_create_key',
    'b': 'assert',
    '_': 'xpcall',
    'y': 'error',
    'd': 'typeof',
    't': 'Instance',
    'q': 'rawget',
    'J': 'tonumber',
    'j': 'debug_getinfo_key',
    'A': 'getmetatable_key',
    'O': 'tostring_key',
    'Ct': 'setmetatable_key',
    'It': 'UDim2_new',
    'wU': 'UDim_new',
    'KU': 'UDim_new2',
    'YU': 'UDim2_new2',
    'yt': 'nparams_key',
}
for k, v in EXTRA_CT.items():
    if k not in CT:
        CT[k] = v

# Register name inference for Proto 2 main function
REG_NAMES_P2 = {
    1: 'const_tbl',
    2: 'setfenv_fn',
    3: 'string_lib',
    4: 'rawset_fn',
    5: 'string_gmatch',
    6: 'Vector2',
    7: 'next_fn',
    8: 'getfenv_fn',
    9: 'type_fn',
    10: 'string_format',
    11: 'table_lib',
    12: 'pcall_fn',
    13: 'string_match',
    14: 'string_find',
    15: 'UDim2',
    16: 'string_char',
    17: 'string_byte',
    18: 'string_gsub',
    19: 'string_sub',
    20: 'string_rep',
    21: 'xpcall_fn',
    22: 'env_register',
    23: 'table_concat',
    24: 'string_unpack',
    25: 'select_fn',
    26: 'luraph_key',
    27: 'string_pack',
    28: 'coroutine',
    29: 'table_insert',
    30: 'co_isyieldable',
    31: 'co_running',
    32: 'co_create_key',
    33: 'co_create',
    34: 'task',
    35: 'task_cancel',
    36: 'task_spawn',
    37: 'empty_tbl',
    38: 'co_resume',
    39: 'co_status',
    40: 'co_yield',
    41: 'assert_fn',
    42: 'co_close',
    43: 'task_defer',
    44: 'luraph_key2',
    45: 'task_delay',
    46: 'error_fn',
    47: 'typeof_fn',
    48: 'Instance',
    49: 'rawget_fn',
    50: 'tonumber_fn',
    51: 'debug_lib',
    52: 'bool_map',
    53: 'debug_info',
    54: 'task_wait',
    55: 'anti_tamper_fn',
    56: 'debug_traceback',
    57: 'getmetatable_key',
    58: 'check_fn',
    59: 'tostring_key',
    60: 'identifyexecutor',
    61: 'main_closure',
    62: 'setmetatable_key',
    67: 'seed_fn',
    70: 'proto1_fn',
    71: 'co_wrap',
    76: 'register_fn2',
    79: 'gui_fn',
    80: 'screen_gui',
    81: 'viewport_frame',
}

def i(v):
    return int(v) if v is not None else 0

def show(v):
    if v is None: return "nil"
    if isinstance(v, str):
        if len(v) > 60: return f'"{v[:57]}..."'
        return f'"{v}"'
    if isinstance(v, float) and v == int(v): return str(int(v))
    return str(v)

def resolve_key(Q):
    if Q is None: return "nil"
    k = str(Q)
    if isinstance(Q, float) and Q == int(Q):
        return str(int(Q))
    return CT.get(k, k)

def linearize_proto(proto, proto_idx, reg_names=None):
    ops = proto['opcodes']
    n = proto['num_instructions']
    if reg_names is None:
        reg_names = {}
    
    def Mv(idx): return proto['operM'][idx]
    def Lv(idx): return proto['operL'][idx]
    def Pv(idx): return proto['operP'][idx]
    def tv(idx): return proto['constT'][idx]
    def Qv(idx): return proto['constQ'][idx]
    def gv(idx): return proto['constG'][idx]
    
    def r(v):
        rv = i(v)
        if rv in reg_names:
            return reg_names[rv]
        return f"r{rv}"
    
    def rk(Q):
        key = resolve_key(Q)
        if isinstance(key, str) and key.isidentifier() and not key.startswith('r'):
            return f".{key}"
        return f"[{show(Q)}]"
    
    def decompile_one(idx):
        op = ops[idx]
        m, l, p_ = Mv(idx), Lv(idx), Pv(idx)
        t, q, g = tv(idx), Qv(idx), gv(idx)
        
        if op == 0:    return f"{r(m)} = {r(p_)} - {r(l)}"
        if op == 1:    return f"{r(p_)} = {q} .. {r(m)}"
        if op == 6:    return f"upval[{i(p_)}] = {show(t)}"
        if op == 9:    return f"if {r(m)} > {r(p_)} then goto L{i(l)}"
        if op == 11:   return f"{r(p_)} = {r(l)} - {show(t)}"
        if op == 12:
            key = resolve_key(q)
            src = r(m)
            if isinstance(key, str) and key.isidentifier():
                return f"{r(p_)} = {src}.{key}"
            return f"{r(p_)} = {src}[{show(q)}]"
        if op == 13:   return f"if {r(p_)} then goto L{i(l)}"
        if op == 14:   return f"{r(p_)} = ({r(m)} < {r(l)})"
        if op == 15:   return f"{r(p_)} = bit_xor({r(m)}, {r(l)})"
        if op == 16:   return f"{r(l)}()"
        if op == 20:   return f"{r(p_)} = upval[{i(m)}][{r(l)}]"
        if op == 22:   return f"{r(l)} = ({r(p_)} >= {r(m)})"
        if op == 25:   return "-- nop"
        if op == 23:   return f"{r(m)} = {r(p_)} % {r(l)}"
        if op == 27:   return f"-- concat range"
        if op == 30:   return f"{r(p_)} = {r(m)} / {r(l)}"
        if op == 31:   return f"if {r(m)} <= {q} then goto L{i(p_)}"
        if op == 34:   return f"upval[{i(l)}][{r(p_)}] = {show(t)}"
        if op == 38:   return f"{r(m)} = {r(p_)}"
        if op == 39:   return f"{r(l)} = upval[{i(p_)}][{r(m)}]"
        if op == 40:   return f"if {r(p_)} < {show(t)} then goto L{i(l)}"
        if op == 41:
            tk = str(t) if t else ""
            real = CT.get(tk, tk)
            if real and isinstance(real, str) and real.isidentifier():
                return f"{r(p_)}.{real} = {r(l)}"
            return f"{r(p_)}[{show(t)}] = {r(l)}"
        if op == 42:   return f"{r(l)} = {r(l)}()"
        if op == 43:   return f"{r(l)}({r(i(l)+1)}, {r(i(l)+2)})"
        if op == 45:
            tk = str(t) if t else ""
            real = CT.get(tk, tk)
            if real and isinstance(real, str) and real.isidentifier():
                return f"upval[{i(l)}].{real} = {r(p_)}"
            return f"upval[{i(l)}][{show(t)}] = {r(p_)}"
        if op == 47:   return f"if {r(p_)} <= {r(l)} then goto L{i(m)}"
        if op == 48:   return f"{r(l)} = upval[{i(m)}]"
        if op == 52:   return f"upval[{i(p_)}][{r(m)}] = {r(l)}"
        if op == 53:   return f"{r(m)} = _G[{i(p_)}]"
        if op == 54:   return f"_G[{i(m)}] = {r(p_)}"
        if op == 55:   return f"{r(m)} = _ENV"
        if op == 56:   return f"{r(m)} = upval[{i(p_)}]"
        if op == 57:   return f"{r(m)} = ({show(g)} ~= {q})"
        if op == 59:   return f"{r(m)} = function() --[[proto_{i(p_)}]] end"
        if op == 61:   return f"return {r(l)}, ..."
        if op == 62:   return f"if {r(m)} == {r(l)} then goto L{i(p_)}"
        if op == 63:
            tk = str(t) if t else ""
            real = CT.get(tk, tk)
            return f"{r(p_)}[{r(l)}] = {show(real)}"
        if op == 64:   return f"{r(l)} = {r(m)} * {show(g)}"
        if op == 66:   return f"{r(p_)} = closure_upval[{show(q)}]"
        if op == 67:   return f"{r(m)}(r{i(m)+1}..top)"
        if op == 69:   return f"-- tforloop {r(p_)} goto L{i(m)}"
        if op == 70:
            args = ', '.join(r(i(l)+1+j) for j in range(max(i(p_)-1, 0)))
            return f"{r(l)}({args})"
        if op == 71:   return f"{r(l)} = #{r(m)}"
        if op == 72:   return f"{r(p_)} = {show(t)} * {r(l)}"
        if op == 73:   return f"{r(m)} = {r(l)}[{r(p_)}]"
        if op == 74:   return f"... = vararg({i(l)})"
        if op == 77:   return f"goto L{i(l)}"
        if op == 78:   return f"if {r(l)} ~= {show(g)} then goto L{i(m)}"
        if op == 79:   return f"{r(p_)} = {q} + {show(t)}"
        if op == 80:   return f"{r(m)} = {r(l)} + {show(g)}"
        if op == 82:
            key = resolve_key(q)
            return f"{r(i(p_)+1)} = {r(m)}; {r(p_)} = {r(m)}:{key}"
        if op == 35:
            return f"if {r(l)} <= {show(t)} then goto L{i(m)}"
        if op == 85:   return f"{r(m)} = -{r(l)}"
        if op == 86:   return "-- close upvals; return"
        if op == 88:   return "return"
        if op == 89:   return f"return {r(m)}"
        if op == 91:   return f"{r(p_)} = table.create({i(m)})"
        if op == 93:   return f"{r(m)} = ({r(p_)} == {show(q)})"
        if op == 94:
            return f"-- setlist {r(p_)} from stack (count={i(l)})"
        if op == 92:
            args = ', '.join(r(i(m)+1+j) for j in range(max(i(l)-1, 0)))
            return f"{r(m)} = {r(m)}({args})"
        if op == 101:  return f"{r(m)} = _STACK"
        if op == 98:   return f"{r(p_)} = {r(l)} // {show(t)}"
        if op == 99:   return f"for {r(l)} = init, limit, step do"
        if op == 100:  return f"{r(m)} = {r(m)}(r{i(m)+1}..top)"
        if op == 102:
            args = ', '.join(r(i(m)+1+j) for j in range(max(i(p_)-1, 0)))
            nrets = i(l)
            if nrets <= 1:
                return f"{r(m)} = {r(m)}({args})"
            rets = ', '.join(r(i(m)+j) for j in range(nrets-1))
            return f"{rets} = {r(m)}({args})"
        if op == 103:  return f"{r(m)} = {r(l)} .. {show(g)}"
        if op == 108:
            gk = show(g) if g else "nil"
            return f"{r(l)}[{gk}] = {show(t)}"
        if op == 109:  return f"{r(m)} = {{}}"
        if op == 110:  return "-- for loop restore"
        if op == 111:  return f"{r(p_)} = nil"
        if op == 112:  return f"{r(l)} = {show(t)} + {r(p_)}"
        if op == 116:  return f"{r(p_)} = {show(t)} % {show(q)}"
        if op == 114:  return f"{r(m)} = {r(l)} + {r(p_)}"
        if op == 115:  return f"{r(l)} = ({r(m)} == {r(p_)})"
        if op == 117:  return f"{r(p_)} = {show(t)} ^ {r(l)}"
        if op == 118:  return f"{r(m)} = {q} - {r(p_)}"
        if op == 120:  return f"end -- for loop"
        if op == 124:  return f"{r(m)} = {r(m)}({r(i(m)+1)}, {r(i(m)+2)})"
        if op == 125:
            if isinstance(q, float) and q == int(q):
                return f"{r(m)} = {int(q)}"
            return f"{r(m)} = {show(q)}"
        if op == 128:  return f"if not {r(m)} then goto L{i(p_)}"
        if op == 130:  return f"{r(m)} = {r(p_)} .. {r(l)}"
        if op == 132:
            return f"for e = {i(l)}, {i(p_)} do r[e] = nil end"
        if op == 134:  return "-- close upvals"
        if op == 135:  return f"{r(m)} = ({q} >= {show(g)})"
        if op == 136:  return f"return {r(l)}..r{i(l)+i(m)-1}"
        if op == 141:  return "-- setlist"
        if op == 142:  return f"{r(m)} = ({r(p_)} ~= {q})"
        if op == 143:  return f"{r(m)} = {r(l)} % {show(g)}"
        if op == 145:  return f"{r(m)} = {r(l)} * {r(p_)}"
        if op == 146:  return f"{r(p_)} = {show(t)} - {show(q)}"
        if op == 144:  return f"{r(p_)} = bit_op({r(l)}, {show(t)})"
        if op == 149:  return f"upval[{i(l)}][{r(p_)}] = {r(m)}"
        if op == 152:  return f"if {r(p_)} >= {r(l)} then goto L{i(m)}"
        if op == 153:  return f"{r(l)} = {r(p_)} / {show(t)}"
        if op == 154:  return f"{r(l)}({r(i(l)+1)})"
        if op == 155:  return f"{r(l)} = {r(p_)} / {show(t)}"
        if op == 157:  return f"{r(l)} = {r(l)}({r(i(l)+1)})"
        if op == 159:  return f"upval[{i(l)}] = {r(m)}"
        if op == 160:  return f"if {q} <= {r(p_)} then goto L{i(m)}"
        if op == 161:  return f"{r(m)} = upval[{i(p_)}][{show(q)}]"
        if op == 162:  return f"{r(l)} = not {r(m)}"
        if op == 163:  return f"if {r(m)} ~= {r(l)} then goto L{i(p_)}"
        if op == 164:  return f"if {r(p_)} == {show(t)} then goto L{i(l)}"
        if op == 165:  return f"{r(l)}[{r(m)}] = {r(p_)}"
        
        return f"-- OP_{op} M={m} L={l} P={p_} t={show(t)} Q={q} g={show(g)}"
    
    # Build jump targets
    jump_targets = set()
    for idx in range(n):
        op = ops[idx]
        for field in [Mv(idx), Lv(idx), Pv(idx)]:
            if field is not None:
                v = int(field)
                if 0 <= v < n:
                    jump_targets.add(v)
    
    # Linearize
    visited = set()
    output = []
    
    def follow(start_pc, depth=0):
        pc = start_pc
        while pc < n and pc not in visited:
            visited.add(pc)
            op = ops[pc]
            
            if pc in jump_targets:
                output.append(f"::L{pc}::")
            
            if op == 77:  # JMP - follow silently
                target = i(Lv(pc))
                if target not in visited:
                    pc = target
                    continue
                else:
                    output.append(f"    goto L{target}")
                    break
            
            line = decompile_one(pc)
            output.append(f"    {line}")
            
            if op in (88, 89, 61, 136):
                break
            elif op in (13, 128):
                target = i(Lv(pc)) if op == 13 else i(Pv(pc))
                pc += 1
                if depth < 200:
                    follow(target, depth + 1)
            elif op in (9, 31, 40, 47, 62, 78, 152, 160, 163, 164):
                targets = set()
                for field in [Mv(pc), Lv(pc), Pv(pc)]:
                    if field is not None:
                        v = int(field)
                        if 0 <= v < n and v != pc + 1:
                            targets.add(v)
                pc += 1
                if depth < 200:
                    for t in sorted(targets):
                        follow(t, depth + 1)
            elif op in (99, 120):
                for field in [Mv(pc), Pv(pc)]:
                    if field is not None:
                        v = int(field)
                        if 0 <= v < n and depth < 200:
                            follow(v, depth + 1)
                pc += 1
            else:
                pc += 1
    
    entry = 0
    if ops[0] == 77:
        entry = i(Lv(0))
    follow(entry)
    
    # Follow unvisited
    for idx in range(n):
        if idx not in visited:
            follow(idx)
    
    return '\n'.join(output)

# Build output
result = []
result.append("-- =============================================")
result.append("-- Decompiled from Luraph VM bytecode")
result.append("-- target2.lua - VM lifted and deobfuscated")
result.append(f"-- {len(protos)} prototypes, {sum(p['num_instructions'] for p in protos)} total instructions")
result.append(f"-- {len(CT)} constant table entries resolved")
result.append("-- =============================================")
result.append("")
result.append("-- Constant table mapping (obfuscated -> real):")
for k in sorted(CT.keys()):
    v = CT[k]
    if v != k and not k.startswith('r') and len(k) <= 3:
        result.append(f"--   {k:5s} = {v}")
result.append("")

# Proto 2 = main function
result.append("-- ========== MAIN FUNCTION ==========")
result.append(f"-- Proto 2: {protos[1]['num_instructions']} instructions, {protos[1]['numregs']} registers")
result.append("")
result.append(linearize_proto(protos[1], 2, REG_NAMES_P2))
result.append("")

# Sub-prototypes
for idx in range(2, len(protos)):
    p = protos[idx]
    result.append(f"-- ========== CLOSURE proto_{idx+1} ({p['num_instructions']} instructions) ==========")
    result.append(linearize_proto(p, idx+1))
    result.append("")

output_text = '\n'.join(result)

with open('unobfuscator/cracked script/target2_decompiled.lua', 'w', encoding='utf-8') as f:
    f.write(output_text)

total = len(output_text.splitlines())
print(f"Final decompiled output: {total} lines")
print(f"Saved to: unobfuscator/cracked script/target2_decompiled.lua")

# Show summary stats
print(f"\nPrototype summary:")
for idx, p in enumerate(protos):
    print(f"  Proto {idx+1}: {p['num_instructions']:4d} instructions, {p['numregs']:3d} registers, type={p['type']}")

# Show first 100 lines of main function
print("\n=== Main function (first 100 lines) ===\n")
main_start = output_text.find("MAIN FUNCTION")
main_lines = output_text[main_start:].splitlines()
for line in main_lines[:100]:
    print(line)
