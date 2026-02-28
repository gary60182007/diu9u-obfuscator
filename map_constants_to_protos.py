"""
Build comprehensive constant→proto mapping.
For each proto, extract which constants it references and their modes.
Use string constants to identify what each function does.
"""
import json
from collections import defaultdict

with open('all_protos_data.json', 'r', encoding='utf-8') as f:
    all_protos = json.load(f)

with open('luraph_strings_full.json', 'r', encoding='utf-8') as f:
    gt_raw = json.load(f)

gt = {}
for k, v in gt_raw.items():
    gt[int(k)] = v

print(f"Protos: {len(all_protos)}, Constants: {len(gt)}")

# Build per-proto constant reference list
proto_consts = {}
const_to_protos = defaultdict(list)

for p in all_protos:
    pid = p['id']
    refs = []
    
    for idx_str, entry in p.get('C2_sparse', {}).items():
        inst_idx = int(idx_str)
        val = None
        
        if entry.startswith('n:'):
            try:
                val = int(entry.split(':')[1])
            except:
                continue
        elif entry.startswith('t:'):
            parts = entry.split(':')
            try:
                v1, v2 = int(parts[1]), int(parts[2])
                val = v1 * 4 + v2
            except:
                continue
        
        if val is None:
            continue
        
        const_idx = val // 4
        mode = val % 4
        
        if 1 <= const_idx <= max(gt.keys()):
            entry_data = gt.get(const_idx)
            if entry_data:
                refs.append({
                    'inst': inst_idx,
                    'const_idx': const_idx,
                    'mode': mode,
                    'type': entry_data.get('type', '?'),
                    'val': entry_data.get('val', entry_data.get('value', '?'))
                })
                const_to_protos[const_idx].append(pid)
    
    proto_consts[pid] = refs

# Identify each proto by its string constants
print(f"\n{'='*80}")
print(f"PROTO IDENTIFICATION BY STRING CONSTANTS")
print(f"{'='*80}")

for p in all_protos:
    pid = p['id']
    refs = proto_consts.get(pid, [])
    n_inst = p.get('C4_len', 0)
    n_regs = p.get('C10', '?')
    n_ups = p.get('C5', '?')
    
    str_refs = [r for r in refs if r['type'] == 's']
    num_refs = [r for r in refs if r['type'] == 'n']
    
    # Get unique string values
    str_vals = []
    seen = set()
    for r in str_refs:
        v = r['val']
        if isinstance(v, str) and v not in seen:
            seen.add(v)
            str_vals.append(v)
    
    # Function identification heuristics
    label = ''
    sv_lower = [s.lower() for s in str_vals if isinstance(s, str)]
    
    if any('getservice' in s for s in sv_lower):
        services = [s for s in str_vals if s not in ('GetService', 'game')]
        if services:
            label = f"[Service: {', '.join(services[:3])}]"
    if any('connect' in s for s in sv_lower):
        events = [s for s in str_vals if s not in ('Connect', 'connect')]
        if not label:
            label = f"[Event handler]"
    if any('remotefunction' in s or 'remoteevent' in s for s in sv_lower):
        label = f"[Remote]"
    if any('textlabel' in s or 'textbutton' in s or 'frame' in s for s in sv_lower):
        label = f"[UI]"
    if any('tween' in s for s in sv_lower):
        label = f"[Tween/Animation]"
    if any('raycast' in s for s in sv_lower):
        label = f"[Raycast]"
    if any('humanoid' in s for s in sv_lower):
        label = f"[Character]"
    if any('datastoreservice' in s for s in sv_lower):
        label = f"[DataStore]"
    
    if str_vals or num_refs:
        str_preview = ', '.join(f'"{s}"' if isinstance(s, str) else str(s) for s in str_vals[:8])
        if len(str_vals) > 8:
            str_preview += f' ...+{len(str_vals)-8}'
        
        num_preview = ', '.join(str(r['val']) for r in num_refs[:5])
        if len(num_refs) > 5:
            num_preview += f' ...+{len(num_refs)-5}'
        
        print(f"\nProto[{pid:3d}] {n_inst:4d} inst, {n_regs:3} regs, {n_ups:2} ups {label}")
        if str_vals:
            print(f"  strings: {str_preview}")
        if num_refs:
            print(f"  numbers: {num_preview}")

# Most referenced constants (strings)
print(f"\n{'='*80}")
print(f"TOP 30 MOST REFERENCED STRING CONSTANTS")
print(f"{'='*80}")

str_const_usage = {}
for ci, protos in const_to_protos.items():
    entry = gt.get(ci)
    if entry and entry.get('type') == 's':
        str_const_usage[ci] = {
            'val': entry.get('val', '?'),
            'count': len(protos),
            'protos': sorted(set(protos))
        }

by_count = sorted(str_const_usage.items(), key=lambda x: x[1]['count'], reverse=True)
for ci, info in by_count[:30]:
    val = info['val']
    if isinstance(val, str) and len(val) > 40:
        val = val[:40] + '..'
    proto_list = ', '.join(str(p) for p in info['protos'][:10])
    if len(info['protos']) > 10:
        proto_list += f' ...+{len(info["protos"])-10}'
    print(f"  const[{ci:4d}] \"{val}\" used in {info['count']} protos: [{proto_list}]")

# Save comprehensive mapping
mapping = {
    'proto_count': len(all_protos),
    'const_count': len(gt),
    'total_instructions': sum(p.get('C4_len', 0) for p in all_protos),
    'total_const_refs': sum(len(v) for v in proto_consts.values()),
    'protos': []
}

for p in all_protos:
    pid = p['id']
    refs = proto_consts.get(pid, [])
    
    proto_info = {
        'id': pid,
        'instructions': p.get('C4_len', 0),
        'registers': p.get('C10', None),
        'upvalues': p.get('C5', None),
        'buf_start': p.get('buf_start'),
        'buf_end': p.get('buf_end'),
        'const_refs': refs,
        'unique_opcodes': len(set(op for op in p.get('C4', []) if op is not None)),
    }
    mapping['protos'].append(proto_info)

mapping['const_to_protos'] = {
    str(k): sorted(set(v)) for k, v in const_to_protos.items()
}

with open('proto_const_mapping.json', 'w', encoding='utf-8') as f:
    json.dump(mapping, f, indent=1, ensure_ascii=False, default=str)
print(f"\nSaved mapping to proto_const_mapping.json")

# Opcode mapping analysis
print(f"\n{'='*80}")
print(f"OPCODE ANALYSIS")
print(f"{'='*80}")

opcode_freq = defaultdict(int)
opcode_operand_patterns = defaultdict(lambda: defaultdict(int))

for p in all_protos:
    opcodes = p.get('C4', [])
    c7 = p.get('C7', [])
    c8 = p.get('C8', [])
    c9 = p.get('C9', [])
    c2 = p.get('C2_sparse', {})
    
    for i, op in enumerate(opcodes):
        if op is None:
            continue
        opcode_freq[op] += 1
        
        has_c2 = str(i + 1) in c2
        a = c7[i] if i < len(c7) else None
        b = c8[i] if i < len(c8) else None
        c = c9[i] if i < len(c9) else None
        
        a_zero = a == 0 if a is not None else True
        b_zero = b == 0 if b is not None else True
        c_zero = c == 0 if c is not None else True
        
        pattern = f"{'A' if not a_zero else '_'}{'B' if not b_zero else '_'}{'C' if not c_zero else '_'}{'K' if has_c2 else '_'}"
        opcode_operand_patterns[op][pattern] += 1

# Print opcodes with their operand patterns
by_freq = sorted(opcode_freq.items(), key=lambda x: x[1], reverse=True)
print(f"\nTop 40 opcodes with operand patterns:")
for op, count in by_freq[:40]:
    patterns = opcode_operand_patterns[op]
    top_patterns = sorted(patterns.items(), key=lambda x: x[1], reverse=True)[:3]
    pat_str = ', '.join(f'{p}:{c}' for p, c in top_patterns)
    print(f"  op {op:4d}: {count:5d}x  patterns: {pat_str}")
