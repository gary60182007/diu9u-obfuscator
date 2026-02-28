"""Analyze control flow and linearize the threaded bytecode."""
import json

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

p = protos[1]  # Proto 2
n = p['num_instructions']
ops = p['opcodes']

# Build basic blocks
JMP_OPS = {77, 9, 13, 31, 40, 47, 62, 78, 99, 120, 128, 152, 160, 163, 164}
block_starts = {0}
for idx in range(n):
    op = ops[idx]
    M, L, P = p['operM'][idx], p['operL'][idx], p['operP'][idx]
    if op in JMP_OPS or op in (88, 89, 61, 136):
        if idx + 1 < n:
            block_starts.add(idx + 1)
        for v in [M, L, P]:
            if v is not None:
                iv = int(v)
                if 0 <= iv < n:
                    block_starts.add(iv)

blocks = sorted(block_starts)
print(f"Basic blocks: {len(blocks)}")

# Follow control flow from entry (L844)
visited = set()
queue = [844]
reachable = []
while queue:
    pc = queue.pop(0)
    if pc in visited or pc < 0 or pc >= n:
        continue
    visited.add(pc)
    reachable.append(pc)
    
    # Find block end
    bi = blocks.index(pc) if pc in blocks else -1
    if bi >= 0 and bi + 1 < len(blocks):
        block_end = blocks[bi + 1]
    else:
        block_end = n
    
    # Scan block for exits
    for idx in range(pc, min(block_end, n)):
        op = ops[idx]
        M, L, P = p['operM'][idx], p['operL'][idx], p['operP'][idx]
        if op == 77:  # JMP
            target = int(L)
            queue.append(target)
            break
        elif op in (13, 128):  # conditional jump
            target = int(L) if op == 13 else int(P)
            queue.append(target)
            queue.append(idx + 1)
        elif op in (9, 31, 40, 47, 62, 78, 152, 160, 163, 164):
            for v in [M, L, P]:
                if v is not None:
                    iv = int(v)
                    if 0 <= iv < n:
                        queue.append(iv)
            queue.append(idx + 1)
        elif op in (88, 89, 61, 136):
            break
        elif op == 99:  # FORPREP
            queue.append(int(P))
            queue.append(idx + 1)
        elif op == 120:  # FORLOOP
            queue.append(int(M))
            queue.append(idx + 1)

reachable_blocks = sorted(set(blocks) & visited)
print(f"Reachable blocks from L844: {len(reachable_blocks)}")

# Now linearize: follow execution from L844, resolving simple JMP chains
print("\n=== Linearized flow from L844 (first 300 instructions) ===\n")

def resolve_key(Q):
    k = str(Q) if Q is not None else ""
    if k in CT:
        return CT[k]
    return k

def i(v):
    return int(v) if v is not None else 0

def show(v):
    if v is None: return "nil"
    if isinstance(v, str):
        if len(v) > 40: return repr(v[:37] + "...")
        return repr(v)
    if isinstance(v, float) and v == int(v): return str(int(v))
    return str(v)

def r(v):
    return f"r{i(v)}"

def decompile_one(idx):
    op = ops[idx]
    M, L, P = p['operM'][idx], p['operL'][idx], p['operP'][idx]
    t, Q, g = p['constT'][idx], p['constQ'][idx], p['constG'][idx]
    
    if op == 0:    return f"{r(M)} = {r(P)} - {r(L)}"
    if op == 11:   return f"{r(P)} = {r(L)} - {show(t)}"
    if op == 12:
        key = resolve_key(Q)
        return f"{r(P)} = {r(M)}.{key}" if key.isidentifier() else f"{r(P)} = {r(M)}[{show(Q)}]"
    if op == 13:   return f"if {r(P)} then goto L{i(L)}"
    if op == 14:   return f"{r(P)} = ({r(M)} < {r(L)})"
    if op == 16:   return f"{r(L)}()"
    if op == 22:   return f"{r(L)} = ({r(P)} >= {r(M)})"
    if op == 27:   return f"-- concat range"
    if op == 30:   return f"{r(P)} = {r(M)} / {r(L)}"
    if op == 38:   return f"{r(M)} = {r(P)}"
    if op == 40:   return f"if {r(P)} < {show(t)} then goto L{i(L)}"
    if op == 41:
        tk = str(t) if t else ""
        real = CT.get(tk, tk)
        if real and real.isidentifier():
            return f"{r(P)}.{real} = {r(L)}"
        return f"{r(P)}[{show(t)}] = {r(L)}"
    if op == 42:   return f"{r(L)} = {r(L)}()"
    if op == 43:   return f"{r(L)}({r(i(L)+1)}, {r(i(L)+2)})"
    if op == 47:   return f"if {r(P)} <= {r(L)} then goto L{i(M)}"
    if op == 56:   return f"{r(M)} = upval[{i(P)}]"
    if op == 59:   return f"{r(M)} = function() --[[proto_{i(P)}]] end"
    if op == 62:   return f"if {r(M)} == {r(L)} then goto L{i(P)}"
    if op == 63:
        tk = str(t) if t else ""
        real = CT.get(tk, tk)
        return f"{r(P)}[{r(L)}] = \"{real}\""
    if op == 64:   return f"{r(L)} = {r(M)} * {show(g)}"
    if op == 67:   return f"{r(M)}(r{i(M)+1}..top)"
    if op == 71:   return f"{r(L)} = #{r(M)}"
    if op == 73:   return f"{r(M)} = {r(L)}[{r(P)}]"
    if op == 77:   return f"goto L{i(L)}"
    if op == 78:   return f"if {r(L)} ~= {show(g)} then goto L{i(M)}"
    if op == 80:   return f"{r(M)} = {r(L)} + {show(g)}"
    if op == 82:
        key = resolve_key(Q)
        return f"{r(i(P)+1)} = {r(M)}; {r(P)} = {r(M)}:{key}  -- SELF"
    if op == 85:   return f"{r(M)} = -{r(L)}"
    if op == 88:   return "return"
    if op == 89:   return f"return {r(M)}"
    if op == 91:   return f"{r(P)} = table.create({i(M)})"
    if op == 92:   return f"{r(M)} = {r(M)}({', '.join(r(i(M)+1+j) for j in range(i(L)-1))})"
    if op == 99:   return f"-- forprep r{i(L)}, goto L{i(P)}"
    if op == 100:  return f"{r(M)} = {r(M)}(r{i(M)+1}..top)"
    if op == 102:
        args = ', '.join(r(i(M)+1+j) for j in range(max(i(P)-1, 0)))
        return f"{r(M)} = {r(M)}({args})"
    if op == 103:  return f"{r(M)} = {r(L)} .. {show(g)}"
    if op == 108:
        gk = show(g) if g else "nil"
        return f"{r(L)}[{gk}] = {show(t)}"
    if op == 109:  return f"{r(M)} = {{}}"
    if op == 110:  return "-- forloop_restore"
    if op == 111:  return f"{r(P)} = nil"
    if op == 114:  return f"{r(M)} = {r(L)} + {r(P)}"
    if op == 115:  return f"{r(L)} = ({r(M)} == {r(P)})"
    if op == 120:  return f"-- forloop goto L{i(M)}"
    if op == 124:  return f"{r(M)} = {r(M)}({r(i(M)+1)}, {r(i(M)+2)})"
    if op == 125:  return f"{r(M)} = {show(Q)}"
    if op == 128:  return f"if not {r(M)} then goto L{i(P)}"
    if op == 130:  return f"{r(M)} = {r(P)} .. {r(L)}"
    if op == 134:  return f"-- close_upvals"
    if op == 141:  return f"-- setlist"
    if op == 143:  return f"{r(M)} = {r(L)} % {show(g)}"
    if op == 144:  return f"{r(P)} = bit_op({r(L)}, {show(t)})"
    if op == 152:  return f"if {r(P)} >= {r(L)} then goto L{i(M)}"
    if op == 154:  return f"{r(L)}({r(i(L)+1)})"
    if op == 157:  return f"{r(L)} = {r(L)}({r(i(L)+1)})"
    if op == 159:  return f"upval[{i(L)}] = {r(M)}"
    if op == 161:  return f"{r(M)} = upval[{i(P)}][{show(Q)}]"
    if op == 162:  return f"{r(L)} = not {r(M)}"
    if op == 163:  return f"if {r(M)} ~= {r(L)} then goto L{i(P)}"
    if op == 164:  return f"if {r(P)} == {show(t)} then goto L{i(L)}"
    if op == 165:  return f"{r(L)}[{r(M)}] = {r(P)}"
    
    return f"-- OP_{op} M={M} L={L} P={P}"

# Linearize by following JMP chains
pc = 844
count = 0
while pc < n and count < 300:
    op = ops[pc]
    line = decompile_one(pc)
    
    # Check if this is a label target
    if pc in block_starts:
        print(f"::L{pc}::")
    
    print(f"  {pc:4d}  {line}")
    
    if op == 77:  # unconditional JMP - follow it
        pc = int(p['operL'][pc])
    elif op in (88, 89, 61, 136):  # return
        print("  -- (end of path)")
        break
    else:
        pc += 1
    count += 1

if count >= 300:
    print("  ... (truncated)")
