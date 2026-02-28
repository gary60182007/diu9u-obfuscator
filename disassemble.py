"""Disassemble extracted Luraph VM bytecode into readable Lua pseudocode."""
import json
import sys

with open('unobfuscator/cracked script/target2_bytecode.json') as f:
    protos = json.load(f)

OPCODES = {
    0:   ("SUB",            lambda M,L,P,t,Q,g: f"r{i(M)} = r{i(P)} - r{i(L)}"),
    1:   ("CONCAT_KR",      lambda M,L,P,t,Q,g: f"r{i(P)} = {Q} .. r{i(M)}"),
    6:   ("SETUPVAL_K",     lambda M,L,P,t,Q,g: f"upval[{i(P)}] = {show(t)}"),
    8:   ("LT_KK",          lambda M,L,P,t,Q,g: f"r{i(P)} = ({Q} < {show(t)})"),
    9:   ("GT_JMP",          lambda M,L,P,t,Q,g: f"if r{i(M)} > r{i(P)} then goto {i(L)}"),
    10:  ("VARARG",          lambda M,L,P,t,Q,g: f"r{i(M)}... = vararg"),
    11:  ("SUB_RK",          lambda M,L,P,t,Q,g: f"r{i(P)} = r{i(L)} - {show(t)}"),
    12:  ("GETTABLE_K",      lambda M,L,P,t,Q,g: f"r{i(P)} = r{i(M)}[{show_key(Q)}]"),
    13:  ("TEST_JMP",        lambda M,L,P,t,Q,g: f"if r{i(P)} then goto {i(L)}"),
    14:  ("LT",              lambda M,L,P,t,Q,g: f"r{i(P)} = (r{i(M)} < r{i(L)})"),
    16:  ("CALL0_VOID",      lambda M,L,P,t,Q,g: f"r{i(L)}()"),
    20:  ("GETTABLE_UV",     lambda M,L,P,t,Q,g: f"r{i(P)} = upval[{i(M)}][r{i(L)}]"),
    22:  ("GE",              lambda M,L,P,t,Q,g: f"r{i(L)} = (r{i(P)} >= r{i(M)})"),
    23:  ("MOD",             lambda M,L,P,t,Q,g: f"r{i(M)} = r{i(P)} % r{i(L)}"),
    25:  ("NOP",             lambda M,L,P,t,Q,g: f"nop"),
    27:  ("CONCAT_RANGE",    lambda M,L,P,t,Q,g: f"r{i(L)}..r{i(L)+i(M)} = concat(r{i(L)}..r{i(L)+i(M)})"),
    30:  ("DIV",             lambda M,L,P,t,Q,g: f"r{i(P)} = r{i(M)} / r{i(L)}"),
    31:  ("LE_K_JMP",        lambda M,L,P,t,Q,g: f"if r{i(M)} <= {Q} then goto {i(P)}"),
    34:  ("SETTABLE_UV_RK",  lambda M,L,P,t,Q,g: f"upval[{i(L)}][r{i(P)}] = {show(t)}"),
    35:  ("GT_KK",           lambda M,L,P,t,Q,g: f"r{i(L)} = ({show(t)} > {show(g)})"),
    38:  ("MOVE",            lambda M,L,P,t,Q,g: f"r{i(M)} = r{i(P)}"),
    39:  ("GETTABLE_UV2",    lambda M,L,P,t,Q,g: f"r{i(L)} = upval[{i(P)}][r{i(M)}]"),
    40:  ("LT_K_JMP",        lambda M,L,P,t,Q,g: f"if r{i(P)} < {show(t)} then goto {i(L)}"),
    41:  ("SETTABLE_KR",     lambda M,L,P,t,Q,g: f"r{i(P)}[{show(t)}] = r{i(L)}"),
    42:  ("CALL0_RET1",      lambda M,L,P,t,Q,g: f"r{i(L)} = r{i(L)}()"),
    43:  ("CALL2_VOID",      lambda M,L,P,t,Q,g: f"r{i(L)}(r{i(L)+1}, r{i(L)+2})"),
    45:  ("SETTABLE_UV_KR",  lambda M,L,P,t,Q,g: f"upval[{i(L)}][{show(t)}] = r{i(P)}"),
    47:  ("LE_JMP",          lambda M,L,P,t,Q,g: f"if r{i(P)} <= r{i(L)} then goto {i(M)}"),
    48:  ("GETUPVAL",        lambda M,L,P,t,Q,g: f"r{i(L)} = upval[{i(M)}]"),
    50:  ("LOAD_INSTPTR",    lambda M,L,P,t,Q,g: f"r{i(M)} = instptr"),
    52:  ("SETTABLE_UV3",    lambda M,L,P,t,Q,g: f"upval[{i(P)}][r{i(M)}] = r{i(L)}"),
    53:  ("GETGLOBAL",       lambda M,L,P,t,Q,g: f"r{i(M)} = globals[{i(P)}]"),
    54:  ("SETGLOBAL",       lambda M,L,P,t,Q,g: f"globals[{i(M)}] = r{i(P)}"),
    55:  ("LOADENV",         lambda M,L,P,t,Q,g: f"r{i(M)} = env"),
    56:  ("GETUPVAL_RAW",    lambda M,L,P,t,Q,g: f"r{i(M)} = upvals_raw[{i(P)}]"),
    57:  ("NE_KK",           lambda M,L,P,t,Q,g: f"r{i(M)} = ({show(g)} ~= {Q})"),
    59:  ("CLOSURE",         lambda M,L,P,t,Q,g: f"r{i(M)} = closure(proto_{i(P)})"),
    61:  ("RETURN_MULTI",    lambda M,L,P,t,Q,g: f"return r{i(L)}.."),
    62:  ("EQ_JMP",          lambda M,L,P,t,Q,g: f"if r{i(M)} == r{i(L)} then goto {i(P)}"),
    63:  ("SETTABLE_RRK",    lambda M,L,P,t,Q,g: f"r{i(P)}[r{i(L)}] = {show(t)}"),
    64:  ("MUL_RK",          lambda M,L,P,t,Q,g: f"r{i(L)} = r{i(M)} * {show(g)}"),
    66:  ("LOAD_X",          lambda M,L,P,t,Q,g: f"r{i(P)} = x[{Q}]"),
    67:  ("CALL_MULTI_VOID", lambda M,L,P,t,Q,g: f"r{i(M)}(r{i(M)+1}..r_top)"),
    69:  ("TFORLOOP",        lambda M,L,P,t,Q,g: f"tforloop r{i(P)} goto {i(M)}"),
    70:  ("CALL_N_VOID",     lambda M,L,P,t,Q,g: f"r{i(L)}(r{i(L)+1}..r{i(L)+i(P)-1})"),
    71:  ("LEN",             lambda M,L,P,t,Q,g: f"r{i(L)} = #r{i(M)}"),
    73:  ("GETTABLE_RR",     lambda M,L,P,t,Q,g: f"r{i(M)} = r{i(L)}[r{i(P)}]"),
    74:  ("VARARG_SIMPLE",   lambda M,L,P,t,Q,g: f"r1..r{i(L)} = vararg"),
    77:  ("JMP",             lambda M,L,P,t,Q,g: f"goto {i(L)}"),
    78:  ("NE_K_JMP",        lambda M,L,P,t,Q,g: f"if r{i(L)} ~= {show(g)} then goto {i(M)}"),
    79:  ("ADD_KK",          lambda M,L,P,t,Q,g: f"r{i(P)} = {Q} + {show(t)}"),
    80:  ("ADD_RK",          lambda M,L,P,t,Q,g: f"r{i(M)} = r{i(L)} + {show(g)}"),
    82:  ("SELF",            lambda M,L,P,t,Q,g: f"r{i(P)+1}=r{i(M)}; r{i(P)}=r{i(M)}[{show_key(Q)}]"),
    85:  ("UNM",             lambda M,L,P,t,Q,g: f"r{i(M)} = -r{i(L)}"),
    86:  ("CONT",            lambda M,L,P,t,Q,g: f"cont"),
    88:  ("RETURN_VOID",     lambda M,L,P,t,Q,g: f"return"),
    89:  ("RETURN1",         lambda M,L,P,t,Q,g: f"return r{i(M)}"),
    91:  ("NEWTABLE_N",      lambda M,L,P,t,Q,g: f"r{i(P)} = table.create({i(M)})"),
    92:  ("CALL_MULTI_RET1", lambda M,L,P,t,Q,g: f"r{i(M)} = r{i(M)}(r{i(M)+1}..r{i(M)+i(L)-1})"),
    98:  ("IDIV_RK",         lambda M,L,P,t,Q,g: f"r{i(P)} = r{i(L)} // {show(t)}"),
    99:  ("FORPREP",         lambda M,L,P,t,Q,g: f"forprep r{i(L)} goto {i(P)}"),
    100: ("CALL_VAR_RET1",   lambda M,L,P,t,Q,g: f"r{i(M)} = r{i(M)}(r{i(M)+1}..r_top)"),
    101: ("LOAD_REGFILE",    lambda M,L,P,t,Q,g: f"r{i(M)} = regfile"),
    102: ("CALL",            lambda M,L,P,t,Q,g: f"r{i(M)}..r{i(M)+i(L)-2} = r{i(M)}(r{i(M)+1}..r{i(M)+i(P)-1})"),
    103: ("CONCAT_RK",       lambda M,L,P,t,Q,g: f"r{i(M)} = r{i(L)} .. {show(g)}"),
    108: ("SETTABLE_KK",     lambda M,L,P,t,Q,g: f"r{i(L)}[{show(g)}] = {show(t)}"),
    109: ("NEWTABLE",        lambda M,L,P,t,Q,g: f"r{i(M)} = {{}}"),
    110: ("FORLOOP_RESTORE", lambda M,L,P,t,Q,g: f"forloop_restore"),
    111: ("LOADNIL",         lambda M,L,P,t,Q,g: f"r{i(P)} = nil"),
    112: ("ADD_KR",          lambda M,L,P,t,Q,g: f"r{i(L)} = {show(t)} + r{i(P)}"),
    114: ("ADD",             lambda M,L,P,t,Q,g: f"r{i(M)} = r{i(L)} + r{i(P)}"),
    115: ("EQ",              lambda M,L,P,t,Q,g: f"r{i(L)} = (r{i(M)} == r{i(P)})"),
    116: ("MOD_KK",          lambda M,L,P,t,Q,g: f"r{i(P)} = {show(t)} % {Q}"),
    117: ("POW_KR",          lambda M,L,P,t,Q,g: f"r{i(P)} = {show(t)} ^ r{i(L)}"),
    118: ("SUB_KR",          lambda M,L,P,t,Q,g: f"r{i(M)} = {Q} - r{i(P)}"),
    119: ("SETTABLE_UV_KK",  lambda M,L,P,t,Q,g: f"upval[{i(P)}][{show(t)}] = {Q}"),
    120: ("FORLOOP",         lambda M,L,P,t,Q,g: f"forloop goto {i(M)}"),
    124: ("CALL2_RET1",      lambda M,L,P,t,Q,g: f"r{i(M)} = r{i(M)}(r{i(M)+1}, r{i(M)+2})"),
    125: ("LOADK",           lambda M,L,P,t,Q,g: f"r{i(M)} = {Q}"),
    128: ("TEST_FALSE_JMP",  lambda M,L,P,t,Q,g: f"if not r{i(M)} then goto {i(P)}"),
    130: ("CONCAT",          lambda M,L,P,t,Q,g: f"r{i(M)} = r{i(P)} .. r{i(L)}"),
    134: ("CLOSE_UPVALS",    lambda M,L,P,t,Q,g: f"close_upvals >= {i(M)}"),
    135: ("GE_KK",           lambda M,L,P,t,Q,g: f"r{i(M)} = ({Q} >= {show(g)})"),
    136: ("RETURN_CLOSE",    lambda M,L,P,t,Q,g: f"close+return r{i(L)}..r{i(L)+i(M)-1}"),
    141: ("SETLIST",         lambda M,L,P,t,Q,g: f"setlist r{i(L)}[1..{i(P)}]"),
    142: ("NE_RK",           lambda M,L,P,t,Q,g: f"r{i(M)} = (r{i(P)} ~= {Q})"),
    143: ("MOD_RK",          lambda M,L,P,t,Q,g: f"r{i(M)} = r{i(L)} % {show(g)}"),
    144: ("BIT_OP",          lambda M,L,P,t,Q,g: f"r{i(P)} = bit_op(r{i(L)}, {show(t)})"),
    149: ("SETTABLE_UV_RR",  lambda M,L,P,t,Q,g: f"upval[{i(L)}][r{i(P)}] = r{i(M)}"),
    152: ("GE_JMP",          lambda M,L,P,t,Q,g: f"if r{i(P)} >= r{i(L)} then goto {i(M)}"),
    153: ("MUL_KK",          lambda M,L,P,t,Q,g: f"r{i(P)} = {show(t)} * {Q}"),
    154: ("CALL1_VOID",      lambda M,L,P,t,Q,g: f"r{i(L)}(r{i(L)+1})"),
    155: ("LE_KK",           lambda M,L,P,t,Q,g: f"r{i(L)} = ({show(t)} <= {show(g)})"),
    156: ("LOAD_L",          lambda M,L,P,t,Q,g: f"r{i(P)} = L_var"),
    157: ("CALL1_RET1",      lambda M,L,P,t,Q,g: f"r{i(L)} = r{i(L)}(r{i(L)+1})"),
    159: ("SETUPVAL",        lambda M,L,P,t,Q,g: f"upval[{i(L)}] = r{i(M)}"),
    160: ("LE_K_JMP2",       lambda M,L,P,t,Q,g: f"if {Q} <= r{i(P)} then goto {i(M)}"),
    161: ("GETUPVAL_K",      lambda M,L,P,t,Q,g: f"r{i(M)} = upval[{i(P)}][{Q}]"),
    162: ("NOT",             lambda M,L,P,t,Q,g: f"r{i(L)} = not r{i(M)}"),
    163: ("NE_JMP",          lambda M,L,P,t,Q,g: f"if r{i(M)} ~= r{i(L)} then goto {i(P)}"),
    164: ("EQ_K_JMP",        lambda M,L,P,t,Q,g: f"if r{i(P)} == {show(t)} then goto {i(L)}"),
    165: ("SETTABLE_RRR",    lambda M,L,P,t,Q,g: f"r{i(L)}[r{i(M)}] = r{i(P)}"),
}

def i(v):
    if v is None: return 0
    return int(v)

def show(v):
    if v is None: return "nil"
    if isinstance(v, str):
        if len(v) > 40: return f'"{v[:37]}..."'
        return f'"{v}"'
    if isinstance(v, float) and v == int(v): return str(int(v))
    return str(v)

def show_key(v):
    if v is None: return "nil"
    if isinstance(v, float) and v == int(v): return str(int(v))
    if isinstance(v, str):
        if v.isidentifier(): return f'"{v}"'
        return f'"{v[:30]}"'
    return str(v)

def disassemble_proto(proto, proto_idx):
    lines = []
    lines.append(f"--- Proto {proto_idx} (type={proto['type']} regs={proto['numregs']} ops={proto['num_instructions']}) ---")
    if proto.get('strings'):
        api_strings = [s for s in proto['strings'] if s and len(s) < 50 and s.isidentifier()]
        if api_strings:
            lines.append(f"  Identifiers: {', '.join(api_strings[:30])}")
    lines.append("")
    
    for idx in range(proto['num_instructions']):
        op = proto['opcodes'][idx]
        M = proto['operM'][idx]
        L = proto['operL'][idx]
        P = proto['operP'][idx]
        t = proto['constT'][idx]
        Q = proto['constQ'][idx]
        g = proto['constG'][idx]
        
        if op in OPCODES:
            name, fmt_fn = OPCODES[op]
            try:
                desc = fmt_fn(M, L, P, t, Q, g)
            except:
                desc = f"M={M} L={L} P={P} t={show(t)} Q={Q} g={show(g)}"
            lines.append(f"  {idx:4d}  [{name:20s}]  {desc}")
        else:
            lines.append(f"  {idx:4d}  [OP_{op:<17d}]  M={M} L={L} P={P} t={show(t)} Q={Q} g={show(g)}")
    
    return '\n'.join(lines)

# Disassemble all prototypes
output = []
for idx, proto in enumerate(protos):
    output.append(disassemble_proto(proto, idx + 1))
    output.append("")

result = '\n'.join(output)

# Save to file
with open('unobfuscator/cracked script/target2_disasm.txt', 'w', encoding='utf-8') as f:
    f.write(result)

print(f"Disassembly saved to unobfuscator/cracked script/target2_disasm.txt")
print(f"Total lines: {len(result.splitlines())}")

# Show Proto 2 (main function) first 100 lines
print("\n=== Proto 2 (main function) first 100 instructions ===\n")
p2_lines = disassemble_proto(protos[1], 2).splitlines()
for line in p2_lines[:103]:
    print(line)
