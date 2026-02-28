import json, sys, os, re
from collections import Counter, defaultdict

with open('extracted_protos.json') as f:
    protos = json.load(f)

print(f"Loaded {len(protos)} prototypes")

# Collect ALL string constants across all prototypes
all_strings = set()
for p in protos:
    raw = p.get('raw_fields', {})
    f2 = raw.get(2, raw.get('2', []))
    for v in f2:
        if isinstance(v, str) and not v.startswith('<Lua table'):
            all_strings.add(v)

print(f"\n{'='*60}")
print(f"ALL STRING CONSTANTS ({len(all_strings)} unique)")
print(f"{'='*60}")
for s in sorted(all_strings):
    if len(s) > 100:
        print(f"  {repr(s[:100])}...")
    else:
        print(f"  {repr(s)}")

# Opcode classification based on patterns
# op=232: always has m[L], often has q[L] strings → GETFIELD/GETTABLE
# op=117: D varies, a=0, Z=0, no q/m → LOADNIL/MOVE (single operand)
# op=194: no sparse, operands used → JMP/RETURN
# op=152: always has q[L] with table refs → LOADTABLE/LOADREF
# op=170: has q[L] numbers → LOADK (numeric constant)
# op=141: has q[L] strings/numbers → LOADK or SETTABLE
# op=138: no sparse → CALL
# op=55: no sparse → likely CALL/RETURN variant
# op=171: no sparse → likely SETTABLE/SETLIST
# op=169: always has m[L] → comparison (TEST/EQ/LT/LE)
# op=1: always has m[L] → comparison
# op=278: always has m[L] → comparison

OP_NAMES = {
    117: 'LOAD/INIT',
    232: 'GETFIELD',
    194: 'JMP/RET',
    138: 'CALL',
    141: 'LOADK',
    65: 'GET/SET',
    170: 'LOADCONST',
    197: 'SETTABLE',
    55: 'PREPARE',
    171: 'STORE',
    196: 'FORLOOP',
    227: 'SETUPVAL',
    99: 'ARITH',
    152: 'LOADREF',
    164: 'CLOSURE',
    208: 'SETFIELD',
    169: 'TEST',
    122: 'BINOP',
    1: 'CMP',
    318: 'RETURN',
    309: 'FORPREP',
    253: 'MOVE',
    278: 'CMP2',
    136: 'CONCAT',
    103: 'CALL2',
    67: 'SELF',
    229: 'SETFIELD2',
    304: 'NEWTABLE',
}

# Generate pseudo-code for each prototype
output_lines = []
output_lines.append(f"-- Deobfuscated from Luraph v14.7")
output_lines.append(f"-- {len(protos)} prototypes, {sum(len(p.get('raw_fields',{}).get(4, p.get('raw_fields',{}).get('4',[]))) for p in protos)} total instructions")
output_lines.append(f"-- {len(all_strings)} unique string constants")
output_lines.append("")

for pidx, p in enumerate(protos):
    raw = p.get('raw_fields', {})
    opcodes = raw.get(4, raw.get('4', []))
    f2 = raw.get(2, raw.get('2', []))
    f6 = raw.get(6, raw.get('6', []))
    f7 = raw.get(7, raw.get('7', []))
    f8 = raw.get(8, raw.get('8', []))
    f9 = raw.get(9, raw.get('9', []))
    f11 = raw.get(11, raw.get('11', []))
    f3 = raw.get(3, raw.get('3', []))
    numregs = raw.get(10, raw.get('10', 0))
    
    num_params = 0
    if isinstance(f3, list) and len(f3) > 0 and f3[0] is not None:
        try:
            num_params = int(f3[0])
        except (ValueError, TypeError):
            num_params = 0

    param_str = ', '.join(f'arg{i}' for i in range(num_params)) if num_params > 0 else ''
    output_lines.append(f"-- ============ Proto #{p['id']} ============")
    output_lines.append(f"-- Instructions: {len(opcodes)}, Registers: {numregs}, Params: {num_params}")
    output_lines.append(f"function proto_{p['id']}({param_str})")

    # Collect string constants used in this proto
    proto_strings = set()
    for v in f2:
        if isinstance(v, str) and not v.startswith('<Lua table'):
            proto_strings.add(v)
    if proto_strings:
        output_lines.append(f"  -- Uses strings: {sorted(proto_strings)[:10]}")

    # Generate pseudo-code
    indent = "  "
    indent_level = 1
    for L in range(len(opcodes)):
        op = opcodes[L]
        if op is None:
            continue
        d = f7[L] if L < len(f7) else None
        a = f8[L] if L < len(f8) else None
        z = f9[L] if L < len(f9) else None
        q = f2[L] if L < len(f2) else None
        w = f6[L] if L < len(f6) else None
        m = f11[L] if L < len(f11) else None

        op_name = OP_NAMES.get(op, f'OP_{op}')
        
        # Generate readable pseudo-code based on opcode
        if op == 232:  # GETFIELD
            if isinstance(q, str) and not q.startswith('<Lua'):
                line = f"r{d} = GETFIELD({q!r})"
            elif isinstance(q, (int, float)):
                line = f"r{d} = GETFIELD(const_{int(q)})"
            else:
                line = f"r{d} = GETFIELD(D={d}, B={a}, C={z})"
        elif op == 117:  # LOAD/INIT
            line = f"r{d} = nil"
        elif op == 194:  # JMP/RET
            if a is not None and a > 0:
                line = f"JMP +{a}  -- to L={L+a}"
            else:
                line = f"RETURN"
        elif op == 152:  # LOADREF
            if isinstance(q, str):
                if q.startswith('<Lua table'):
                    line = f"r{z} = TABLE_REF  -- {q[:50]}"
                else:
                    line = f"r{z} = {q!r}"
            else:
                line = f"r{z} = LOADREF(D={d}, B={a}, C={z})"
        elif op == 170:  # LOADCONST
            if isinstance(q, (int, float)):
                line = f"r{d} = {q}"
            elif isinstance(q, str):
                line = f"r{d} = {q!r}"
            else:
                line = f"r{d} = CONST(D={d}, B={a}, C={z})"
        elif op == 141:  # LOADK
            if isinstance(q, str):
                line = f"r{d} = {q!r}"
            elif isinstance(q, (int, float)):
                line = f"r{d} = {q}"
            else:
                line = f"r{d} = LOADK(D={d}, B={a}, C={z})"
        elif op == 138:  # CALL
            line = f"CALL(base={d}, nargs={a}, nret={z})"
        elif op == 65:  # GET/SET
            if isinstance(q, str):
                line = f"r{d} = GET({q!r})"
            else:
                line = f"r{d} = GET(D={d}, B={a}, C={z})"
        elif op == 169:  # TEST
            line = f"TEST(D={d}, m={m})"
        elif op == 1:  # CMP
            line = f"CMP(D={d}, B={a}, C={z}, m={m})"
        elif op == 278:  # CMP2
            line = f"CMP2(D={d}, B={a}, C={z}, m={m})"
        elif op == 99:  # ARITH
            line = f"r{d} = ARITH(B={a}, C={z})"
        elif op == 171:  # STORE
            line = f"STORE(D={d}, B={a}, C={z})"
        elif op == 197:  # SETTABLE
            line = f"SETTABLE(D={d}, B={a}, C={z})"
        elif op == 196:  # FORLOOP
            line = f"FORLOOP(D={d}, step={a}, limit={z})"
        elif op == 309:  # FORPREP
            line = f"FORPREP(D={d}, step={a}, limit={z})"
        elif op == 227:  # SETUPVAL
            line = f"SETUPVAL(D={d}, C={z})"
        elif op == 164:  # CLOSURE
            line = f"r{d} = CLOSURE()"
        elif op == 208:  # SETFIELD
            line = f"SETFIELD(D={d}, B={a}, C={z})"
        elif op == 318:  # RETURN
            line = f"RETURN(base={d})"
        elif op == 253:  # MOVE
            line = f"r{d} = MOVE(C={z})"
        elif op == 67:  # SELF
            line = f"SELF(D={d}, B={a}, C={z})"
        elif op == 304:  # NEWTABLE
            if isinstance(q, str):
                line = f"r{d} = NEWTABLE({q!r})"
            else:
                line = f"r{d} = NEWTABLE(size={a})"
        else:
            parts = [f"D={d}", f"B={a}", f"C={z}"]
            if q is not None:
                if isinstance(q, str) and not q.startswith('<Lua'):
                    parts.append(f"q={q!r}")
                elif isinstance(q, (int, float)):
                    parts.append(f"q={q}")
            if m is not None:
                parts.append(f"m={m}")
            if w is not None:
                parts.append(f"w={w}")
            line = f"{op_name}({', '.join(parts)})"
        
        output_lines.append(f"{indent * indent_level}[{L:4d}] {line}")

    output_lines.append("end")
    output_lines.append("")

# Write output
output_path = os.path.join('unobfuscator', 'cracked script', 'bloxburg_deobfuscated.lua')
os.makedirs(os.path.dirname(output_path), exist_ok=True)
with open(output_path, 'w', encoding='utf-8') as f:
    f.write('\n'.join(output_lines))
print(f"\nWrote {len(output_lines)} lines to {output_path}")

# Also write a summary
summary_path = os.path.join('unobfuscator', 'cracked script', 'deobfuscation_summary.txt')
with open(summary_path, 'w', encoding='utf-8') as f:
    f.write(f"Luraph v14.7 Deobfuscation Summary\n")
    f.write(f"{'='*50}\n")
    f.write(f"Prototypes: {len(protos)}\n")
    total_instr = sum(len(p.get('raw_fields',{}).get(4, p.get('raw_fields',{}).get('4',[]))) for p in protos)
    f.write(f"Total instructions: {total_instr}\n")
    f.write(f"Unique opcodes: {len(set(op for p in protos for op in p.get('raw_fields',{}).get(4, p.get('raw_fields',{}).get('4',[])) if op is not None))}\n")
    f.write(f"String constants: {len(all_strings)}\n\n")
    f.write(f"Opcode Distribution:\n")
    all_ops = [op for p in protos for op in p.get('raw_fields',{}).get(4, p.get('raw_fields',{}).get('4',[])) if op is not None]
    for op, cnt in Counter(all_ops).most_common(30):
        name = OP_NAMES.get(op, f'OP_{op}')
        f.write(f"  {name:15s} (op={op:3d}): {cnt:5d} ({cnt/len(all_ops)*100:5.1f}%)\n")
    f.write(f"\nAll String Constants:\n")
    for s in sorted(all_strings):
        f.write(f"  {repr(s)}\n")
print(f"Wrote summary to {summary_path}")
