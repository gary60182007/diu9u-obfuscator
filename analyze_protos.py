"""Analyze the extracted proto data from all_protos_data.json"""
import json

with open('all_protos_data.json', 'r', encoding='utf-8') as f:
    all_protos = json.load(f)

with open('luraph_strings_full.json', 'r', encoding='utf-8') as f:
    gt_raw = json.load(f)
# Convert to 0-indexed list for easy access
gt_max = max(int(k) for k in gt_raw.keys())
gt = [None] * (gt_max + 1)
for k, v in gt_raw.items():
    gt[int(k)] = v

print(f"Total protos: {len(all_protos)}")
total_inst = sum(p.get('C4_len', 0) for p in all_protos)
total_crefs = sum(len(p.get('C2_sparse', {})) for p in all_protos)
print(f"Total instructions: {total_inst}")
print(f"Total constant references: {total_crefs}")
print(f"Ground truth constants: {len(gt)}")

# Parse C[2] and C[11] entries
def parse_entry(entry):
    if entry.startswith('t:'):
        parts = entry.split(':')
        try:
            return {'type': 'table', 'v1': int(parts[1]), 'v2': int(parts[2])}
        except:
            return {'type': 'table', 'v1': None, 'v2': None}
    elif entry.startswith('n:'):
        try:
            return {'type': 'number', 'value': int(entry.split(':')[1])}
        except:
            return {'type': 'number', 'value': None}
    return {'type': 'other'}

# Analyze C[2] entry types and values
print(f"\n=== C[2] Entry Analysis ===")
c2_types = {'table': 0, 'number': 0, 'other': 0}
c2_values = []
for p in all_protos:
    for idx_str, entry in p.get('C2_sparse', {}).items():
        parsed = parse_entry(entry)
        c2_types[parsed['type']] += 1
        if parsed['type'] == 'number' and parsed['value'] is not None:
            c2_values.append(parsed['value'])
        elif parsed['type'] == 'table':
            c2_values.append(f"({parsed['v1']},{parsed['v2']})")
print(f"  Types: {c2_types}")
if c2_values:
    num_vals = [v for v in c2_values if isinstance(v, int)]
    if num_vals:
        print(f"  Number range: {min(num_vals)} to {max(num_vals)}")
        small = [v for v in num_vals if v < 1170]
        print(f"  Values < 1170 (valid const idx): {len(small)} / {len(num_vals)}")
        large = [v for v in num_vals if v >= 1170]
        print(f"  Values >= 1170: {len(large)}")
        if large:
            print(f"  Sample large values: {large[:20]}")

# Analyze C[11] entry types and values
print(f"\n=== C[11] Entry Analysis ===")
c11_types = {'table': 0, 'number': 0, 'other': 0}
c11_values = []
for p in all_protos:
    for idx_str, entry in p.get('C11_sparse', {}).items():
        parsed = parse_entry(entry)
        c11_types[parsed['type']] += 1
        if parsed['type'] == 'number' and parsed['value'] is not None:
            c11_values.append(parsed['value'])
        elif parsed['type'] == 'table':
            c11_values.append(f"({parsed['v1']},{parsed['v2']})")
print(f"  Types: {c11_types}")
if c11_values:
    num_vals = [v for v in c11_values if isinstance(v, int)]
    tbl_vals = [v for v in c11_values if isinstance(v, str)]
    if num_vals:
        print(f"  Number range: {min(num_vals)} to {max(num_vals)}")
        print(f"  Sample number values: {num_vals[:30]}")
    if tbl_vals:
        print(f"  Table entries: {len(tbl_vals)}")
        print(f"  Sample table values: {tbl_vals[:20]}")

# Opcode frequency
print(f"\n=== Opcode Frequency (top 25) ===")
opcode_freq = {}
for p in all_protos:
    for op in p.get('C4', []):
        if op is not None:
            opcode_freq[op] = opcode_freq.get(op, 0) + 1

by_freq = sorted(opcode_freq.items(), key=lambda x: x[1], reverse=True)
print(f"Unique opcodes: {len(opcode_freq)}")
for op, count in by_freq[:25]:
    pct = count / total_inst * 100
    print(f"  opcode {op:4d}: {count:5d} ({pct:5.1f}%)")

# Per-proto analysis: show C[2] data for first 5 protos
print(f"\n=== Per-Proto C[2] Data (first 5) ===")
for p in all_protos[:5]:
    entries = sorted(p.get('C2_sparse', {}).items(), key=lambda x: int(x[0]))
    print(f"\n  Proto[{p['id']}] ({p.get('C4_len', 0)} inst):")
    for idx_str, entry in entries[:20]:
        parsed = parse_entry(entry)
        inst_idx = int(idx_str)
        opcode = p['C4'][inst_idx - 1] if inst_idx - 1 < len(p.get('C4', [])) else '?'
        if parsed['type'] == 'number':
            v = parsed['value']
            div4 = v // 4
            mod4 = v % 4
            const_name = ''
            if div4 < len(gt) and gt[div4] is not None:
                entry = gt[div4]
                cv = entry.get('val', entry.get('value', entry.get('string', '?')))
                if isinstance(cv, str) and len(cv) > 30:
                    cv = cv[:30] + '..'
                const_name = f" → const[{div4}]={cv}"
            print(f"    inst[{inst_idx:3d}] op={opcode:4}: val={v} (÷4={div4}, %4={mod4}){const_name}")
        elif parsed['type'] == 'table':
            print(f"    inst[{inst_idx:3d}] op={opcode:4}: table({parsed['v1']}, {parsed['v2']})")

# C[6] sparse analysis
c6_count = sum(1 for p in all_protos if p.get('C6_sparse'))
print(f"\n=== C[6] Sparse Array ===")
print(f"Protos with C[6] data: {c6_count}/{len(all_protos)}")
for p in all_protos[:5]:
    if p.get('C6_sparse'):
        print(f"  Proto[{p['id']}]: {p['C6_sparse']}")
