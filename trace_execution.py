"""Trace execution paths through Luraph dispatch state machine."""
import json
from collections import defaultdict

protos = json.load(open('all_protos_data.json'))
opmap = json.load(open('opcode_map_final.json'))
try:
    operand_info = json.load(open('operand_map.json'))
except:
    operand_info = {}

def get_cat(op):
    return opmap.get(str(op), {}).get('lua51', '?')

def get_jmp_target(op, D, a, Z):
    oi = operand_info.get(str(op), {})
    jt = oi.get('jump_target')
    if jt:
        return {'D': D, 'a': a, 'Z': Z}.get(jt, D)
    return D

def trace_proto(pidx, raw):
    c4 = raw.get('C4', [])
    c7 = raw.get('C7', [])
    c8 = raw.get('C8', [])
    c9 = raw.get('C9', [])
    n = len(c4)
    if n == 0:
        return []

    path = []
    visited = set()
    pc = 0
    max_steps = n * 3

    while 0 <= pc < n and len(path) < max_steps:
        if pc in visited:
            break
        visited.add(pc)

        op = c4[pc]
        cat = get_cat(op)
        D = c7[pc] if pc < len(c7) else 0
        a = c8[pc] if pc < len(c8) else 0
        Z = c9[pc] if pc < len(c9) else 0

        if cat == 'JMP':
            target = get_jmp_target(op, D, a, Z)
            if 0 <= target < n:
                pc = target
                continue
            else:
                break
        
        if cat in ('CLOSE', 'DISPATCH', 'FRAGMENT', 'RANGE', 'ARITH', 'UNKNOWN'):
            pc += 1
            continue

        path.append((pc, op, cat, D, a, Z))
        pc += 1

    return path

# Trace a few protos and show the linearized sequence
for pidx in [0, 1, 2, 17, 75, 76]:
    if pidx >= len(protos):
        continue
    raw = protos[pidx]
    nr = raw.get('C10', 0)
    c2 = raw.get('C2_sparse', {})
    path = trace_proto(pidx, raw)
    
    print(f"\n=== Proto {pidx+1} ({len(raw.get('C4',[]))} inst, {nr} regs) ===")
    print(f"Linearized: {len(path)} real instructions")
    
    for pc, op, cat, D, a, Z in path[:40]:
        q = c2.get(str(pc+1), '') or c2.get(str(pc), '')
        var = opmap.get(str(op), {}).get('variant', '')
        extra = ''
        if q: extra = f' q={q}'
        if var and '(' in var: extra += f' [{var}]'
        print(f"  {pc:4d} {cat:12s} D={D:4d} a={a:4d} Z={Z:4d}{extra}")
    if len(path) > 40:
        print(f"  ... ({len(path)-40} more)")
