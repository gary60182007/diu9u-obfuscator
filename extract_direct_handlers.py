import json, re
from collections import Counter

with open('i3_executor_chunk.lua', 'r') as f:
    src = f.read()

protos = json.load(open('all_protos_data.json'))
op_freq = Counter()
for p in protos:
    for op in p.get('C4', []):
        op_freq[op] += 1

# Import tokenizer and classifier from trace_dispatch_tree
exec(open('trace_dispatch_tree.py').read().split('# Trace each used opcode')[0])

# Extract direct T== and T~= handlers
direct_handlers = {}

for idx, tok in enumerate(tokens):
    if tok[1] != 'T_CMP':
        continue
    _, _, op, val = tok
    
    if op == '==':
        # T==val: handler is in the then-branch (code after 'then')
        j = idx + 1
        while j < len(tokens) and tokens[j][1] != 'then':
            j += 1
        if j < len(tokens):
            then_pos = tokens[j][0] + 4  # after 'then'
            handler = src[then_pos:then_pos+600]
            if val not in direct_handlers:
                direct_handlers[val] = ('T==', handler)
    
    elif op == '~=':
        # T~=val: handler for val is in the else-branch
        j = idx + 1
        while j < len(tokens) and tokens[j][1] != 'then':
            j += 1
        if j < len(tokens):
            skip_result, skip_type = skip_branch(tokens, j + 1)
            if skip_type == 'else':
                else_pos = tokens[skip_result][0] + 4  # after 'else'
                handler = src[else_pos:else_pos+600]
                if val not in direct_handlers:
                    direct_handlers[val] = ('T~=', handler)
            elif skip_type == 'elseif':
                # Check if the elseif handles T~=val
                k = skip_result + 1
                while k < len(tokens) and tokens[k][1] != 'then':
                    k += 1
                if k < len(tokens):
                    then_pos2 = tokens[k][0] + 4
                    handler = src[then_pos2:then_pos2+600]
                    if val not in direct_handlers:
                        direct_handlers[val] = ('T~=_elseif', handler)

print(f"Direct T== matches: {sum(1 for v in direct_handlers.values() if v[0]=='T==')}")
print(f"Direct T~= matches: {sum(1 for v in direct_handlers.values() if v[0]=='T~=')}")
print(f"T~= elseif matches: {sum(1 for v in direct_handlers.values() if v[0]=='T~=_elseif')}")
print(f"Total direct handlers: {len(direct_handlers)}")
print(f"Values covered: {sorted(direct_handlers.keys())[:20]}...")

# Classify direct handlers
direct_classified = {}
for val, (match_type, code) in direct_handlers.items():
    cls = classify_handler(code, val)
    direct_classified[val] = cls

# Load runtime data
runtime_cls = {}
try:
    combined = json.load(open('opcode_combined.json'))
    runtime_cls = combined.get('classifications', {})
except: pass

runtime_trace = {}
try:
    runtime_trace = json.load(open('opcode_trace_fast.json'))
except: pass

runtime_deltas = {}
try:
    combined = json.load(open('opcode_combined.json'))
    runtime_deltas = combined.get('deltas', {})
except: pass

# Build final map
final_map = {}
all_ops = sorted(op_freq.keys())

for op in all_ops:
    sources = {}
    
    # Source 1: Direct T== / T~= handler
    if op in direct_classified:
        sources['direct'] = direct_classified[op]
    
    # Source 2: Runtime classification  
    if str(op) in runtime_cls:
        sources['runtime'] = runtime_cls[str(op)]
    
    # Source 3: Runtime trace (operand types)
    if str(op) in runtime_trace:
        t = runtime_trace[str(op)]
        sources['trace'] = t
    
    # Source 4: Runtime deltas
    if str(op) in runtime_deltas:
        sources['delta'] = runtime_deltas[str(op)]
    
    # Priority: direct handler > runtime delta > runtime classification
    if 'direct' in sources and sources['direct'] != 'UNKNOWN':
        final_cls = sources['direct']
        source = 'direct'
    elif 'runtime' in sources:
        final_cls = sources['runtime']
        source = 'runtime'
    elif 'delta' in sources:
        final_cls = f"DELTA:{sources['delta']}"
        source = 'delta'
    else:
        final_cls = 'UNKNOWN'
        source = 'none'
    
    final_map[op] = {
        'classification': final_cls,
        'source': source,
        'freq': op_freq[op],
        'all_sources': {k: str(v)[:100] for k, v in sources.items()},
    }

# Summary
cats = Counter()
inst_cats = Counter()
source_counts = Counter()
for op, info in final_map.items():
    c = info['classification']
    if c.startswith('GETGLOBAL('):
        c = 'GETGLOBAL'
    cats[c] += 1
    inst_cats[c] += info['freq']
    source_counts[info['source']] += 1

print(f"\n{'='*70}")
print(f"FINAL MAP: {len(final_map)} opcodes -> {len(cats)} categories")
print(f"{'='*70}")
print(f"\nSources: {dict(source_counts)}")
print(f"\n{'Category':<35} {'Opcodes':>8} {'Instructions':>12}")
print('-'*58)
for cat, cnt in sorted(cats.items(), key=lambda x: -inst_cats[x[0]]):
    print(f"{cat:<35} {cnt:>8} {inst_cats[cat]:>12}")

unknown_ops = [(op, info) for op, info in final_map.items() if info['classification'] == 'UNKNOWN']
if unknown_ops:
    print(f"\nStill UNKNOWN ({len(unknown_ops)}):")
    for op, info in sorted(unknown_ops, key=lambda x: -x[1]['freq']):
        print(f"  Op {op:>3} ({info['freq']:>5}x): sources={info['all_sources']}")

with open('opcode_map_final_v2.json', 'w') as f:
    json.dump(final_map, f, indent=2, default=str)
print(f"\nSaved to opcode_map_final_v2.json")
