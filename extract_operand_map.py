"""
Extract operand usage patterns from handler code for each opcode.
Determines which operand (D/a/Z) is destination register, which is source, etc.
"""
import json, re

dispatch = json.load(open('opcode_dispatch_map.json'))
handler_map = dispatch['handler_map']
handler_code = dispatch['handler_code']
opmap = json.load(open('opcode_map_final.json'))

def analyze_handler(code, variant):
    if not code:
        return {}
    h = code.strip()
    # Remove junk prefixes
    h = re.sub(r'^return\s+[\w\[\]/.%*+\-()0xXbBoO_]+\s*;', '', h).strip()
    while h.startswith('end;'):
        h = h[4:].strip()
    # Normalize (s)[ -> s[
    h = re.sub(r'\(s\)\s*\[', 's[', h)
    h = re.sub(r'\(r\)\s*\[', 'r[', h)

    result = {}

    # Detect destination register pattern: s[X[y]] = ...
    dest_m = re.search(r's\[\s*([DaZ])\s*\[\s*y\s*\]\s*\]\s*=', h[:150])
    if dest_m:
        result['dest'] = dest_m.group(1)

    # Detect GETGLOBAL: s[X[y]] = GLOBALNAME
    gg_m = re.search(r's\[\s*([DaZ])\s*\[\s*y\s*\]\s*\]\s*=\s*\(?\s*([A-Za-z_]\w+)\s*\)?;', h[:120])
    if gg_m:
        reg = gg_m.group(1)
        name = gg_m.group(2)
        skip = {'s','q','w','m','D','a','Z','Y','y','H','k','x','n','b','F','K','G',
                'true','false','nil','not','and','or','type','end','do','local','then',
                'else','if','while','for','repeat','until','return','function','in',
                'S','C','c','f','o','_','L','P','I','X','J','V','N'}
        if name not in skip:
            result['getglobal_dest'] = reg
            result['global_name'] = name

    # Detect table access: s[X[y]][Y[y]] or s[X[y]][m[y]]
    tbl_m = re.search(r's\[\s*([DaZ])\s*\[\s*y\s*\]\s*\]\s*\[\s*([DaZqwm])\s*\[\s*y\s*\]\s*\]', h[:150])
    if tbl_m:
        result['table_reg'] = tbl_m.group(1)
        result['table_key'] = tbl_m.group(2)

    # Detect assignment to table: s[X[y]][key] = value
    st_m = re.search(r's\[\s*([DaZ])\s*\[\s*y\s*\]\s*\]\s*\[\s*([DaZqwm])\s*\[\s*y\s*\]\s*\]\s*=\s*\(?\s*([DaZqwm])\s*\[\s*y\s*\]\s*\)?', h[:200])
    if st_m:
        result['settable_base'] = st_m.group(1)
        result['settable_key'] = st_m.group(2)
        result['settable_val'] = st_m.group(3)

    # Detect binary ops: s[X[y]] = s[Y[y]] OP s[Z[y]] or s[X[y]] OP const
    binop_m = re.search(r's\[\s*([DaZ])\s*\[\s*y\s*\]\s*\]\s*=\s*s\[\s*([DaZ])\s*\[\s*y\s*\]\s*\]\s*([+\-*/%^]|\.\.)\s*s\[\s*([DaZ])\s*\[\s*y\s*\]\s*\]', h[:200])
    if binop_m:
        result['arith_dest'] = binop_m.group(1)
        result['arith_left'] = binop_m.group(2)
        result['arith_op'] = binop_m.group(3)
        result['arith_right'] = binop_m.group(4)

    # Detect comparison jump: if s[X[y]] CMP s[Y[y]] then y=(Z[y])
    cmp_m = re.search(r'if\s+(?:not\s*\()?\s*(?:s\[\s*([DaZ])\s*\[\s*y\s*\]\s*\]|([qwm])\s*\[\s*y\s*\])\s*([<>=~]+)\s*(?:s\[\s*([DaZ])\s*\[\s*y\s*\]\s*\]|([qwm])\s*\[\s*y\s*\])', h[:300])
    if cmp_m:
        result['cmp_left_reg'] = cmp_m.group(1) or None
        result['cmp_left_const'] = cmp_m.group(2) or None
        result['cmp_op'] = cmp_m.group(3)
        result['cmp_right_reg'] = cmp_m.group(4) or None
        result['cmp_right_const'] = cmp_m.group(5) or None

    # Detect jump target: y=(X[y]) or y=X[y]
    jmp_m = re.search(r'y\s*=\s*\(?\s*([DaZ])\s*\[\s*y\s*\]\s*\)?', h[:300])
    if jmp_m:
        result['jump_target'] = jmp_m.group(1)

    # Detect CALL pattern: s[H]=s[H](...) where H=X[y]
    call_m = re.search(r'H\s*=\s*([DaZ])\s*\[\s*y\s*\]', h[:150])
    if call_m:
        result['call_base'] = call_m.group(1)

    # Detect MOVE: s[X[y]] = s[Y[y]]
    move_m = re.search(r's\[\s*([DaZ])\s*\[\s*y\s*\]\s*\]\s*=\s*\(?\s*s\[\s*([DaZ])\s*\[\s*y\s*\]\s*\]\s*\)?;', h[:150])
    if move_m:
        if not re.search(r's\[\w+\[y\]\]\[', h[:150]):
            result['move_dest'] = move_m.group(1)
            result['move_src'] = move_m.group(2)

    return result

operand_info = {}
for op_str, variant in handler_map.items():
    code = handler_code.get(op_str, '')
    info = analyze_handler(code, variant)
    if info:
        info['variant'] = variant
        operand_info[op_str] = info

with open('operand_map.json', 'w') as f:
    json.dump(operand_info, f, indent=2)

# Summary
dest_patterns = {}
for op_str, info in operand_info.items():
    v = info.get('variant', '?')
    d = info.get('dest') or info.get('getglobal_dest') or info.get('arith_dest') or info.get('move_dest') or '?'
    key = f"{v}:{d}"
    if key not in dest_patterns:
        dest_patterns[key] = []
    dest_patterns[key].append(int(op_str))

print(f"Operand info extracted for {len(operand_info)} opcodes")
print(f"\nDestination register patterns:")
for key in sorted(dest_patterns.keys()):
    ops = dest_patterns[key]
    print(f"  {key:<45s} ({len(ops)} ops): {ops[:10]}")

# GETGLOBAL specifics
print(f"\nGETGLOBAL destination registers:")
for op_str, info in sorted(operand_info.items(), key=lambda x: int(x[0])):
    if 'global_name' in info:
        print(f"  Op {op_str:>3}: s[{info['getglobal_dest']}[y]] = {info['global_name']}")

print(f"\nSETTABLE operand patterns:")
for op_str, info in sorted(operand_info.items(), key=lambda x: int(x[0])):
    if 'settable_base' in info:
        print(f"  Op {op_str:>3}: s[{info['settable_base']}[y]][{info['settable_key']}[y]] = {info['settable_val']}[y]")

print(f"\nComparison operand patterns:")
for op_str, info in sorted(operand_info.items(), key=lambda x: int(x[0])):
    if 'cmp_op' in info:
        left = f"s[{info['cmp_left_reg']}[y]]" if info.get('cmp_left_reg') else f"{info.get('cmp_left_const','?')}[y]"
        right = f"s[{info['cmp_right_reg']}[y]]" if info.get('cmp_right_reg') else f"{info.get('cmp_right_const','?')}[y]"
        jmp = info.get('jump_target', '?')
        print(f"  Op {op_str:>3}: if {left} {info['cmp_op']} {right} then y={jmp}[y]")
