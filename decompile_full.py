"""Full decompiler: linearize threaded bytecode and produce readable Lua source."""
import json
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

def i(v):
    return int(v) if v is not None else 0

def show(v):
    if v is None: return "nil"
    if isinstance(v, str):
        if len(v) > 60: return repr(v[:57] + "...")
        return repr(v)
    if isinstance(v, float) and v == int(v): return str(int(v))
    return str(v)

def resolve_key(Q):
    k = str(Q) if Q is not None else ""
    return CT.get(k, k)

def linearize_proto(proto, proto_idx):
    ops = proto['opcodes']
    n = proto['num_instructions']
    
    def M(idx): return proto['operM'][idx]
    def L(idx): return proto['operL'][idx]
    def P(idx): return proto['operP'][idx]
    def t(idx): return proto['constT'][idx]
    def Q(idx): return proto['constQ'][idx]
    def g(idx): return proto['constG'][idx]
    def r(v): return f"r{i(v)}"
    
    # Track register names for readability
    reg_info = {}
    
    def decompile_one(idx):
        op = ops[idx]
        m, l, p_ = M(idx), L(idx), P(idx)
        tv, qv, gv = t(idx), Q(idx), g(idx)
        
        if op == 0:    return f"{r(m)} = {r(p_)} - {r(l)}"
        if op == 1:    return f"{r(p_)} = {qv} .. {r(m)}"
        if op == 11:   return f"{r(p_)} = {r(l)} - {show(tv)}"
        if op == 12:
            key = resolve_key(qv)
            src = reg_info.get(i(m), r(m))
            if key and isinstance(key, str) and key.isidentifier():
                return f"{r(p_)} = {src}.{key}"
            return f"{r(p_)} = {src}[{show(qv)}]"
        if op == 13:   return f"if {r(p_)} then goto L{i(l)}"
        if op == 14:   return f"{r(p_)} = ({r(m)} < {r(l)})"
        if op == 16:   return f"{r(l)}()"
        if op == 20:   return f"{r(p_)} = upval[{i(m)}][{r(l)}]"
        if op == 22:   return f"{r(l)} = ({r(p_)} >= {r(m)})"
        if op == 23:   return f"{r(m)} = {r(p_)} % {r(l)}"
        if op == 27:   return f"-- concat range r{i(l)}..r{i(l)+i(m)}"
        if op == 30:   return f"{r(p_)} = {r(m)} / {r(l)}"
        if op == 31:   return f"if {r(m)} <= {qv} then goto L{i(p_)}"
        if op == 34:   return f"upval[{i(l)}][{r(p_)}] = {show(tv)}"
        if op == 38:
            reg_info[i(m)] = reg_info.get(i(p_), r(p_))
            return f"{r(m)} = {r(p_)}"
        if op == 39:   return f"{r(l)} = upval[{i(p_)}][{r(m)}]"
        if op == 40:   return f"if {r(p_)} < {show(tv)} then goto L{i(l)}"
        if op == 41:
            tk = str(tv) if tv else ""
            real = CT.get(tk, tk)
            if real and isinstance(real, str) and real.isidentifier():
                return f"{r(p_)}.{real} = {r(l)}"
            return f"{r(p_)}[{show(tv)}] = {r(l)}"
        if op == 42:   return f"{r(l)} = {r(l)}()"
        if op == 43:   return f"{r(l)}({r(i(l)+1)}, {r(i(l)+2)})"
        if op == 45:
            tk = str(tv) if tv else ""
            real = CT.get(tk, tk)
            if real and isinstance(real, str) and real.isidentifier():
                return f"upval[{i(l)}].{real} = {r(p_)}"
            return f"upval[{i(l)}][{show(tv)}] = {r(p_)}"
        if op == 47:   return f"if {r(p_)} <= {r(l)} then goto L{i(m)}"
        if op == 48:   return f"{r(l)} = upval[{i(m)}]"
        if op == 52:   return f"upval[{i(p_)}][{r(m)}] = {r(l)}"
        if op == 53:   return f"{r(m)} = _G[{i(p_)}]"
        if op == 54:   return f"_G[{i(m)}] = {r(p_)}"
        if op == 55:   return f"{r(m)} = _ENV"
        if op == 56:   return f"{r(m)} = upval[{i(p_)}]"
        if op == 59:   return f"{r(m)} = function() --[[proto_{i(p_)}]] end"
        if op == 61:   return f"return {r(l)}, ..."
        if op == 62:   return f"if {r(m)} == {r(l)} then goto L{i(p_)}"
        if op == 63:
            tk = str(tv) if tv else ""
            real = CT.get(tk, tk)
            return f"{r(p_)}[{r(l)}] = {show(real)}"
        if op == 64:   return f"{r(l)} = {r(m)} * {show(gv)}"
        if op == 66:   return f"{r(p_)} = closure_upval[{qv}]"
        if op == 67:   return f"{r(m)}(r{i(m)+1}..top)"
        if op == 69:   return f"-- tforloop {r(p_)} goto L{i(m)}"
        if op == 70:
            args = ', '.join(r(i(l)+1+j) for j in range(max(i(p_)-1, 0)))
            return f"{r(l)}({args})"
        if op == 71:   return f"{r(l)} = #{r(m)}"
        if op == 73:   return f"{r(m)} = {r(l)}[{r(p_)}]"
        if op == 74:   return f"r1..r{i(l)} = ..."
        if op == 77:   return f"goto L{i(l)}"
        if op == 78:   return f"if {r(l)} ~= {show(gv)} then goto L{i(m)}"
        if op == 79:   return f"{r(p_)} = {qv} + {show(tv)}"
        if op == 80:   return f"{r(m)} = {r(l)} + {show(gv)}"
        if op == 82:
            key = resolve_key(qv)
            return f"{r(i(p_)+1)} = {r(m)}; {r(p_)} = {r(m)}:{key}"
        if op == 85:   return f"{r(m)} = -{r(l)}"
        if op == 88:   return "return"
        if op == 89:   return f"return {r(m)}"
        if op == 91:   return f"{r(p_)} = table.create({i(m)})"
        if op == 92:
            args = ', '.join(r(i(m)+1+j) for j in range(max(i(l)-1, 0)))
            return f"{r(m)} = {r(m)}({args})"
        if op == 98:   return f"{r(p_)} = {r(l)} // {show(tv)}"
        if op == 99:   return f"for {r(l)}, _, _ do  -- goto L{i(p_)}"
        if op == 100:  return f"{r(m)} = {r(m)}(r{i(m)+1}..top)"
        if op == 102:
            args = ', '.join(r(i(m)+1+j) for j in range(max(i(p_)-1, 0)))
            nrets = i(l)
            if nrets <= 1:
                return f"{r(m)} = {r(m)}({args})"
            rets = ', '.join(r(i(m)+j) for j in range(nrets-1))
            return f"{rets} = {r(m)}({args})"
        if op == 103:  return f"{r(m)} = {r(l)} .. {show(gv)}"
        if op == 108:
            gk = show(gv)
            return f"{r(l)}[{gk}] = {show(tv)}"
        if op == 109:  return f"{r(m)} = {{}}"
        if op == 110:  return "-- forloop_restore"
        if op == 111:  return f"{r(p_)} = nil"
        if op == 112:  return f"{r(l)} = {show(tv)} + {r(p_)}"
        if op == 114:  return f"{r(m)} = {r(l)} + {r(p_)}"
        if op == 115:  return f"{r(l)} = ({r(m)} == {r(p_)})"
        if op == 117:  return f"{r(p_)} = {show(tv)} ^ {r(l)}"
        if op == 118:  return f"{r(m)} = {qv} - {r(p_)}"
        if op == 120:  return f"-- forloop goto L{i(m)}"
        if op == 124:  return f"{r(m)} = {r(m)}({r(i(m)+1)}, {r(i(m)+2)})"
        if op == 125:  return f"{r(m)} = {show(qv)}"
        if op == 128:  return f"if not {r(m)} then goto L{i(p_)}"
        if op == 130:  return f"{r(m)} = {r(p_)} .. {r(l)}"
        if op == 134:  return "-- close_upvals"
        if op == 135:  return f"{r(m)} = ({qv} >= {show(gv)})"
        if op == 136:  return f"return {r(l)}..r{i(l)+i(m)-1}"
        if op == 141:  return "-- setlist"
        if op == 142:  return f"{r(m)} = ({r(p_)} ~= {qv})"
        if op == 143:  return f"{r(m)} = {r(l)} % {show(gv)}"
        if op == 144:  return f"{r(p_)} = bit_op({r(l)}, {show(tv)})"
        if op == 149:  return f"upval[{i(l)}][{r(p_)}] = {r(m)}"
        if op == 152:  return f"if {r(p_)} >= {r(l)} then goto L{i(m)}"
        if op == 154:  return f"{r(l)}({r(i(l)+1)})"
        if op == 155:  return f"{r(l)} = ({show(tv)} <= {show(gv)})"
        if op == 157:  return f"{r(l)} = {r(l)}({r(i(l)+1)})"
        if op == 159:  return f"upval[{i(l)}] = {r(m)}"
        if op == 160:  return f"if {qv} <= {r(p_)} then goto L{i(m)}"
        if op == 161:  return f"{r(m)} = upval[{i(p_)}][{show(qv)}]"
        if op == 162:  return f"{r(l)} = not {r(m)}"
        if op == 163:  return f"if {r(m)} ~= {r(l)} then goto L{i(p_)}"
        if op == 164:  return f"if {r(p_)} == {show(tv)} then goto L{i(l)}"
        if op == 165:  return f"{r(l)}[{r(m)}] = {r(p_)}"
        
        return f"-- OP_{op} M={m} L={l} P={p_} t={show(tv)} Q={qv} g={show(gv)}"
    
    # Build jump target set
    jump_targets = set()
    for idx in range(n):
        op = ops[idx]
        for field in [M(idx), L(idx), P(idx)]:
            if field is not None:
                v = int(field)
                if 0 <= v < n:
                    jump_targets.add(v)
    
    # Linearize by following unconditional JMPs
    visited_jmps = set()
    output = []
    output.append(f"-- Proto {proto_idx} (regs={proto['numregs']} ops={n})")
    
    # Build linearized order: follow JMP chains
    linear_order = []
    visited_pcs = set()
    
    # Start from entry point
    entry = 0
    if ops[0] == 77:  # First instruction is JMP
        entry = i(L(0))
    
    def follow_chain(start_pc, depth=0):
        pc = start_pc
        while pc < n and pc not in visited_pcs:
            visited_pcs.add(pc)
            linear_order.append(pc)
            op = ops[pc]
            if op == 77:  # unconditional JMP
                target = i(L(pc))
                if target not in visited_pcs:
                    pc = target
                    continue
                else:
                    linear_order.append(('jmp_ref', target))
                    break
            elif op in (88, 89, 61, 136):  # return
                break
            elif op in (13, 128):  # conditional jump
                target = i(L(pc)) if op == 13 else i(P(pc))
                pc += 1
                if depth < 100:
                    follow_chain(target, depth + 1)
            elif op in (9, 31, 40, 47, 62, 78, 152, 160, 163, 164):
                targets = set()
                for field in [M(pc), L(pc), P(pc)]:
                    if field is not None:
                        v = int(field)
                        if 0 <= v < n and v != pc + 1:
                            targets.add(v)
                pc += 1
                if depth < 100:
                    for t in targets:
                        follow_chain(t, depth + 1)
            elif op in (99, 120):
                for field in [M(pc), P(pc)]:
                    if field is not None:
                        v = int(field)
                        if 0 <= v < n and depth < 100:
                            follow_chain(v, depth + 1)
                pc += 1
            else:
                pc += 1
    
    follow_chain(entry)
    
    # Add any unvisited blocks
    for idx in range(n):
        if idx not in visited_pcs:
            follow_chain(idx)
    
    # Emit in linearized order, collapsing simple JMPs
    prev_was_jmp = False
    for item in linear_order:
        if isinstance(item, tuple):
            if item[0] == 'jmp_ref':
                output.append(f"    goto L{item[1]}  -- (loop back)")
            continue
        
        idx = item
        op = ops[idx]
        
        if idx in jump_targets or idx == entry:
            output.append(f"::L{idx}::")
        
        if op == 77:  # skip simple JMPs (already followed)
            continue
        
        line = decompile_one(idx)
        output.append(f"    {line}")
    
    return '\n'.join(output)

# Decompile all protos
result_lines = []
result_lines.append("-- Decompiled from Luraph VM bytecode")
result_lines.append("-- target2.lua - VM lifted")
result_lines.append(f"-- {len(protos)} prototypes, {sum(p['num_instructions'] for p in protos)} total instructions")
result_lines.append(f"-- Constant table: {len(CT)} entries resolved")
result_lines.append("")

# Proto 2 is the main function
result_lines.append("-- ========== MAIN FUNCTION (Proto 2) ==========")
result_lines.append(linearize_proto(protos[1], 2))
result_lines.append("")

# Sub-prototypes
for idx in range(2, len(protos)):
    result_lines.append(f"-- ========== Sub-function (Proto {idx+1}) ==========")
    result_lines.append(linearize_proto(protos[idx], idx+1))
    result_lines.append("")

output = '\n'.join(result_lines)

with open('unobfuscator/cracked script/target2_decompiled.lua', 'w', encoding='utf-8') as f:
    f.write(output)

total_lines = len(output.splitlines())
print(f"Saved decompiled output: {total_lines} lines")
print(f"File: unobfuscator/cracked script/target2_decompiled.lua")

# Show first 200 lines
lines = output.splitlines()
print("\n=== First 200 lines ===\n")
for line in lines[:200]:
    print(line)
