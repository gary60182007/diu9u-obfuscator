"""Decompile extracted Luraph VM bytecode into readable Lua pseudocode."""
import json
import re

with open('unobfuscator/cracked script/target2_bytecode.json') as f:
    protos = json.load(f)

# Build constant table from Proto 1
p1 = protos[0]
CONST_TABLE = {}
for idx in range(p1['num_instructions']):
    op = p1['opcodes'][idx]
    if op == 108:
        g = p1['constG'][idx]
        t = p1['constT'][idx]
        if g and t:
            CONST_TABLE[str(g)] = str(t)

def i(v):
    if v is None: return 0
    return int(v)

def show(v):
    if v is None: return "nil"
    if isinstance(v, str):
        if len(v) > 50: return f'"{v[:47]}..."'
        return f'"{v}"'
    if isinstance(v, float) and v == int(v): return str(int(v))
    return str(v)

def show_key(v):
    if v is None: return "nil"
    if isinstance(v, float):
        if v == int(v): return str(int(v))
        return str(v)
    return str(v)

class Decompiler:
    def __init__(self, proto, proto_idx, all_protos):
        self.proto = proto
        self.proto_idx = proto_idx
        self.all_protos = all_protos
        self.ops = proto['opcodes']
        self.n = proto['num_instructions']
        self.reg_names = {}
        self.output = []
        self.indent = 0
        
        # Identify which register holds the constant table (r1 in proto 2)
        self.const_reg = None
        
    def M(self, idx): return self.proto['operM'][idx]
    def L(self, idx): return self.proto['operL'][idx]
    def P(self, idx): return self.proto['operP'][idx]
    def t(self, idx): return self.proto['constT'][idx]
    def Q(self, idx): return self.proto['constQ'][idx]
    def g(self, idx): return self.proto['constG'][idx]
    
    def reg(self, v):
        r = i(v)
        if r in self.reg_names:
            return self.reg_names[r]
        return f"r{r}"
    
    def resolve_key(self, key_val):
        """Resolve obfuscated constant table key to real API name."""
        k = show_key(key_val)
        if k in CONST_TABLE:
            return CONST_TABLE[k]
        return k
    
    def emit(self, s):
        self.output.append("    " * self.indent + s)
    
    def decompile(self):
        self.output = []
        self.emit(f"-- Proto {self.proto_idx} (type={self.proto['type']} regs={self.proto['numregs']} ops={self.n})")
        
        # Find jump targets for basic block analysis
        jump_targets = set()
        for idx in range(self.n):
            op = self.ops[idx]
            if op in (77, 165):  # JMP
                jump_targets.add(i(self.L(idx)))
            elif op == 13:  # TEST_JMP
                jump_targets.add(i(self.L(idx)))
            elif op == 128:  # TEST_FALSE_JMP
                jump_targets.add(i(self.P(idx)))
            elif op in (9, 62, 163):  # GT_JMP, EQ_JMP, NE_JMP
                for field in [self.L(idx), self.P(idx), self.M(idx)]:
                    v = i(field)
                    if v > idx and v < self.n:
                        jump_targets.add(v)
            elif op == 99:  # FORPREP
                jump_targets.add(i(self.P(idx)))
            elif op == 120:  # FORLOOP
                jump_targets.add(i(self.M(idx)))
        
        for idx in range(self.n):
            if idx in jump_targets:
                self.emit(f"::L{idx}::")
            
            line = self.decompile_instruction(idx)
            if line:
                self.emit(line)
        
        return '\n'.join(self.output)
    
    def decompile_instruction(self, idx):
        op = self.ops[idx]
        M, L, P = self.M(idx), self.L(idx), self.P(idx)
        t, Q, g = self.t(idx), self.Q(idx), self.g(idx)
        
        r = self.reg
        
        if op == 0:    return f"{r(M)} = {r(P)} - {r(L)}"
        if op == 1:    return f"{r(P)} = {Q} .. {r(M)}"
        if op == 6:    return f"upval[{i(P)}] = {show(t)}"
        if op == 9:    return f"if {r(M)} > {r(P)} then goto L{i(L)}"
        if op == 11:   return f"{r(P)} = {r(L)} - {show(t)}"
        if op == 12:
            key = self.resolve_key(Q)
            return f"{r(P)} = {r(M)}.{key}" if key and key.isidentifier() else f"{r(P)} = {r(M)}[{show_key(Q)}]"
        if op == 13:   return f"if {r(P)} then goto L{i(L)}"
        if op == 14:   return f"{r(P)} = ({r(M)} < {r(L)})"
        if op == 16:   return f"{r(L)}()"
        if op == 20:   return f"{r(P)} = upval[{i(M)}][{r(L)}]"
        if op == 22:   return f"{r(L)} = ({r(P)} >= {r(M)})"
        if op == 23:   return f"{r(M)} = {r(P)} % {r(L)}"
        if op == 27:   return f"-- concat range r{i(L)}..r{i(L)+i(M)}"
        if op == 30:   return f"{r(P)} = {r(M)} / {r(L)}"
        if op == 31:   return f"if {r(M)} <= {Q} then goto L{i(P)}"
        if op == 34:   return f"upval[{i(L)}][{r(P)}] = {show(t)}"
        if op == 38:   return f"{r(M)} = {r(P)}"
        if op == 39:   return f"{r(L)} = upval[{i(P)}][{r(M)}]"
        if op == 40:   return f"if {r(P)} < {show(t)} then goto L{i(L)}"
        if op == 41:
            key = show(t)
            if t and isinstance(t, str) and t.isidentifier():
                key_resolved = CONST_TABLE.get(t, t)
                return f"{r(P)}.{key_resolved} = {r(L)}"
            return f"{r(P)}[{key}] = {r(L)}"
        if op == 42:   return f"{r(L)} = {r(L)}()"
        if op == 43:   return f"{r(L)}({r(i(L)+1)}, {r(i(L)+2)})"
        if op == 45:
            key = show(t)
            if t and isinstance(t, str) and t.isidentifier():
                key_resolved = CONST_TABLE.get(t, t)
                return f"upval[{i(L)}].{key_resolved} = {r(P)}"
            return f"upval[{i(L)}][{key}] = {r(P)}"
        if op == 47:   return f"if {r(P)} <= {r(L)} then goto L{i(M)}"
        if op == 48:   return f"{r(L)} = upval[{i(M)}]"
        if op == 52:   return f"upval[{i(P)}][{r(M)}] = {r(L)}"
        if op == 53:   return f"{r(M)} = _G[{i(P)}]"
        if op == 54:   return f"_G[{i(M)}] = {r(P)}"
        if op == 55:   return f"{r(M)} = _ENV"
        if op == 56:   return f"{r(M)} = upval_raw[{i(P)}]"
        if op == 59:   return f"{r(M)} = function() --[[proto_{i(P)}]] end"
        if op == 61:   return f"return {r(L)}, ..."
        if op == 62:   return f"if {r(M)} == {r(L)} then goto L{i(P)}"
        if op == 63:
            key = show(t)
            if t and isinstance(t, str) and t.isidentifier():
                key_resolved = CONST_TABLE.get(t, t)
                return f"{r(P)}[{r(L)}] = \"{key_resolved}\""
            return f"{r(P)}[{r(L)}] = {key}"
        if op == 64:   return f"{r(L)} = {r(M)} * {show(g)}"
        if op == 66:   return f"{r(P)} = closure_upval[{Q}]"
        if op == 67:   return f"{r(M)}(r{i(M)+1}..top)"
        if op == 69:   return f"-- tforloop {r(P)} goto L{i(M)}"
        if op == 70:   return f"{r(L)}({', '.join(r(i(L)+1+j) for j in range(i(P)-1))})"
        if op == 71:   return f"{r(L)} = #{r(M)}"
        if op == 73:   return f"{r(M)} = {r(L)}[{r(P)}]"
        if op == 74:   return f"r1..r{i(L)} = ..."
        if op == 77:   return f"goto L{i(L)}"
        if op == 78:   return f"if {r(L)} ~= {show(g)} then goto L{i(M)}"
        if op == 79:   return f"{r(P)} = {Q} + {show(t)}"
        if op == 80:   return f"{r(M)} = {r(L)} + {show(g)}"
        if op == 82:
            key = self.resolve_key(Q)
            method = key if key and key.isidentifier() else show_key(Q)
            return f"{r(i(P)+1)} = {r(M)}; {r(P)} = {r(M)}.{method}  -- SELF"
        if op == 85:   return f"{r(M)} = -{r(L)}"
        if op == 88:   return f"return"
        if op == 89:   return f"return {r(M)}"
        if op == 91:   return f"{r(P)} = table.create({i(M)})"
        if op == 92:   return f"{r(M)} = {r(M)}({', '.join(r(i(M)+1+j) for j in range(i(L)-1))})"
        if op == 98:   return f"{r(P)} = {r(L)} // {show(t)}"
        if op == 99:   return f"-- for {r(L)}, _, _ do (goto L{i(P)})"
        if op == 100:  return f"{r(M)} = {r(M)}(r{i(M)+1}..top)"
        if op == 102:
            nargs = i(P)
            nrets = i(L)
            args = ', '.join(r(i(M)+1+j) for j in range(max(nargs-1, 0)))
            if nrets <= 1:
                return f"{r(M)} = {r(M)}({args})"
            else:
                rets = ', '.join(r(i(M)+j) for j in range(nrets-1))
                return f"{rets} = {r(M)}({args})"
        if op == 103:  return f"{r(M)} = {r(L)} .. {show(g)}"
        if op == 108:
            key_g = show(g) if g else "nil"
            val_t = show(t) if t else "nil"
            if g and isinstance(g, str) and g.isidentifier():
                return f"{r(L)}.{g} = {val_t}"
            return f"{r(L)}[{key_g}] = {val_t}"
        if op == 109:  return f"{r(M)} = {{}}"
        if op == 110:  return f"-- forloop_restore"
        if op == 111:  return f"{r(P)} = nil"
        if op == 112:  return f"{r(L)} = {show(t)} + {r(P)}"
        if op == 114:  return f"{r(M)} = {r(L)} + {r(P)}"
        if op == 115:  return f"{r(L)} = ({r(M)} == {r(P)})"
        if op == 117:  return f"{r(P)} = {show(t)} ^ {r(L)}"
        if op == 118:  return f"{r(M)} = {Q} - {r(P)}"
        if op == 120:  return f"-- forloop goto L{i(M)}"
        if op == 124:  return f"{r(M)} = {r(M)}({r(i(M)+1)}, {r(i(M)+2)})"
        if op == 125:  return f"{r(M)} = {Q}"
        if op == 128:  return f"if not {r(M)} then goto L{i(P)}"
        if op == 130:  return f"{r(M)} = {r(P)} .. {r(L)}"
        if op == 134:  return f"-- close_upvals >= {i(M)}"
        if op == 136:  return f"return {r(L)}..r{i(L)+i(M)-1}"
        if op == 141:  return f"-- setlist r{i(L)}[1..{i(P)}]"
        if op == 142:  return f"{r(M)} = ({r(P)} ~= {Q})"
        if op == 143:  return f"{r(M)} = {r(L)} % {show(g)}"
        if op == 144:  return f"{r(P)} = bit_op({r(L)}, {show(t)})"
        if op == 149:  return f"upval[{i(L)}][{r(P)}] = {r(M)}"
        if op == 152:  return f"if {r(P)} >= {r(L)} then goto L{i(M)}"
        if op == 154:  return f"{r(L)}({r(i(L)+1)})"
        if op == 155:  return f"{r(L)} = ({show(t)} <= {show(g)})"
        if op == 157:  return f"{r(L)} = {r(L)}({r(i(L)+1)})"
        if op == 159:  return f"upval[{i(L)}] = {r(M)}"
        if op == 160:  return f"if {Q} <= {r(P)} then goto L{i(M)}"
        if op == 161:  return f"{r(M)} = upval[{i(P)}][{Q}]"
        if op == 162:  return f"{r(L)} = not {r(M)}"
        if op == 163:  return f"if {r(M)} ~= {r(L)} then goto L{i(P)}"
        if op == 164:  return f"if {r(P)} == {show(t)} then goto L{i(L)}"
        if op == 165:  return f"{r(L)}[{r(M)}] = {r(P)}"
        
        return f"-- OP_{op} M={M} L={L} P={P} t={show(t)} Q={Q} g={show(g)}"

# Decompile Proto 2 (main function)
d = Decompiler(protos[1], 2, protos)
result = d.decompile()

# Save full decompilation
with open('unobfuscator/cracked script/target2_decompiled.lua', 'w', encoding='utf-8') as f:
    f.write("-- Decompiled from Luraph VM bytecode\n")
    f.write("-- Constant table keys resolved from Proto 1\n\n")
    f.write(result)
    f.write("\n\n")
    # Also decompile sub-prototypes
    for idx in range(2, len(protos)):
        d2 = Decompiler(protos[idx], idx+1, protos)
        f.write(d2.decompile())
        f.write("\n\n")

print(f"Decompiled output saved to unobfuscator/cracked script/target2_decompiled.lua")
lines = result.splitlines()
print(f"Proto 2: {len(lines)} lines")

# Show first 150 lines
print("\n=== Proto 2 (first 150 lines) ===\n")
for line in lines[:150]:
    print(line)
