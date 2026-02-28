import json, re
from collections import Counter

protos = json.load(open('all_protos_data.json'))
dispatch = json.load(open('opcode_dispatch_map.json'))
constants = json.load(open('luraph_strings_full.json', encoding='utf-8'))

runtime_trace = {}
try: runtime_trace = json.load(open('opcode_trace_fast.json'))
except: pass

combined = {}
try: combined = json.load(open('opcode_combined.json'))
except: pass
runtime_cls = combined.get('classifications', {})
runtime_deltas = combined.get('deltas', {})

handler_map = dispatch.get('handler_map', {})
handler_code = dispatch.get('handler_code', {})

op_freq = Counter()
for p in protos:
    for op in p.get('C4', []):
        op_freq[op] += 1

SUSPICIOUS_BULK = {'TEST_TRUE', 'TEST_FALSE', 'RETURN', 'REG_ASSIGN', 'DISPATCH_FRAGMENT'}

def infer_from_runtime(op):
    rt = runtime_cls.get(str(op))
    if rt:
        if 'LOADNIL' in rt: return 'LOADNIL'
        if 'LOADK' in rt: return 'LOADK'
        if 'SETTABLE' in rt: return 'SETTABLE'
        if 'SETGLOBAL' in rt: return 'SETGLOBAL'
        if 'GETGLOBAL' in rt: return 'GETGLOBAL'
        if 'NEWTABLE' in rt and 'GETTBL' in rt: return 'GETTABLE'
        if 'NEWTABLE' in rt: return 'NEWTABLE'
        if 'ARITH' in rt or 'MOVE(n)' in rt: return 'ARITH_OR_MOVE'
        if 'CMP_STORE' in rt or 'LOADBOOL' in rt: return 'CMP_STORE'
        if 'MULTI' in rt: return 'MULTI_WRITE'
        if 'WRITE_Z(nil)' in rt: return 'WRITE_NIL'
        if 'JMP/TEST/RETURN/SET*' in rt: return 'JMP_TEST_RETURN'
    return None

def normalize_to_lua51(cls):
    if cls.startswith('GETGLOBAL('): return 'GETGLOBAL'
    mapping = {
        'MOVE': 'MOVE', 'REG_ASSIGN': 'MOVE', 'REG_READ': 'MOVE',
        'LOADK_q': 'LOADK', 'LOADK_w': 'LOADK', 'LOADK_m': 'LOADK',
        'LOADK_VM': 'LOADK', 'ASSIGN_K': 'LOADK',
        'LOADNIL': 'LOADNIL', 'LOADNIL_RANGE': 'LOADNIL',
        'NEWTABLE': 'NEWTABLE',
        'GETTABLE': 'GETTABLE', 'GETTABLE_Kq': 'GETTABLE', 'GETTABLE_kK': 'GETTABLE',
        'GETTABLE_Fk': 'GETTABLE', 'GETTABLE_TEMP': 'GETTABLE',
        'SETTABLE': 'SETTABLE', 'SETTABLE_KmKq': 'SETTABLE', 'SETTABLE_HFK': 'SETTABLE',
        'ADD': 'ADD', 'SUB': 'SUB', 'MUL': 'MUL', 'DIV': 'DIV', 'MOD': 'MOD', 'POW': 'POW',
        'UNM': 'UNM', 'NOT': 'NOT', 'LEN': 'LEN',
        'CONCAT': 'CONCAT', 'CONCAT_Kq': 'CONCAT', 'CONCAT_KqR': 'CONCAT',
        'EQ_JMP': 'EQ', 'NE_JMP': 'EQ', 'EQ_K_JMP': 'EQ', 'NE_K_JMP': 'EQ',
        'EQ_STORE': 'EQ', 'NE_STORE': 'EQ', 'CMP_KK_STORE': 'EQ',
        'LT_JMP': 'LT', 'GT_JMP': 'LT', 'LT_K_JMP': 'LT', 'GT_K_JMP': 'LT',
        'LT_STORE': 'LT', 'GT_STORE': 'LT', 'LT_K_STORE': 'LT',
        'LE_JMP': 'LE', 'GE_JMP': 'LE', 'LE_K_JMP': 'LE', 'GE_K_JMP': 'LE',
        'LE_STORE': 'LE', 'GE_STORE': 'LE',
        'TEST_TRUE': 'TEST', 'TEST_FALSE': 'TEST', 'TEST_NIL': 'TEST',
        'JMP': 'JMP',
        'CALL': 'CALL', 'CALL_0': 'CALL', 'CALL_1_0': 'CALL',
        'CALL_SPREAD': 'CALL', 'CALL_UNPACK': 'CALL', 'CALL_SETUP': 'CALL',
        'SELF': 'SELF',
        'RETURN': 'RETURN', 'RETURN_VAL': 'RETURN',
        'GETUPVAL': 'GETUPVAL', 'SETUPVAL': 'SETUPVAL', 'UPVAL_OP': 'GETUPVAL',
        'UPVAL_ACCESS': 'GETUPVAL',
        'SETGLOBAL': 'SETGLOBAL', 'GETGLOBAL_ENV': 'GETGLOBAL',
        'CLOSURE': 'CLOSURE',
        'FORLOOP': 'FORLOOP', 'FORPREP': 'FORPREP', 'TFORLOOP': 'TFORLOOP',
        'VARARG': 'VARARG', 'SETLIST': 'SETLIST',
        'CLOSE': 'CLOSE',
        'COMPUTED_DISPATCH': 'COMPUTED',
        'ARITH_BUILTIN': 'ARITH',
        'RANGE_SETUP': 'CALL', 'RANGE_OP': 'RANGE',
        'SUB_kK': 'SUB', 'MUL_wK': 'MUL', 'POW_qK': 'POW', 'DIV_qK': 'DIV',
        'DISPATCH_FRAGMENT': 'FRAGMENT',
    }
    return mapping.get(cls, cls)

final = {}
for op in sorted(op_freq.keys()):
    tree_cls = handler_map.get(str(op), 'UNKNOWN')
    rt_inf = infer_from_runtime(op)
    
    # Determine best classification
    if tree_cls in SUSPICIOUS_BULK and op_freq[op] > 2:
        if rt_inf:
            best = rt_inf
            source = 'runtime_override'
        else:
            best = tree_cls
            source = 'tree_suspicious'
    elif tree_cls == 'UNKNOWN':
        best = rt_inf if rt_inf else 'UNKNOWN'
        source = 'runtime' if rt_inf else 'none'
    else:
        best = tree_cls
        source = 'tree'
    
    lua51 = normalize_to_lua51(best)
    global_name = None
    if best.startswith('GETGLOBAL('):
        global_name = best[10:-1]
    
    final[op] = {
        'lua51': lua51,
        'variant': best,
        'source': source,
        'freq': op_freq[op],
    }
    if global_name:
        final[op]['global_name'] = global_name
    if rt_inf and source != 'runtime_override':
        final[op]['runtime_hint'] = rt_inf

# Summary
cats = Counter()
inst_cats = Counter()
src_counts = Counter()
for op, info in final.items():
    cats[info['lua51']] += 1
    inst_cats[info['lua51']] += info['freq']
    src_counts[info['source']] += 1

print(f"{'='*70}")
print(f"FINAL OPCODE MAP: {len(final)} opcodes -> {len(cats)} Lua 5.1 categories")
print(f"{'='*70}")
print(f"\nSources: {dict(src_counts)}")
print(f"Total instructions: {sum(op_freq.values())}")
print(f"\n{'Category':<20} {'Opcodes':>8} {'Instructions':>13} {'%':>6}")
print('-'*50)
total_inst = sum(op_freq.values())
for cat, cnt in sorted(cats.items(), key=lambda x: -inst_cats[x[0]]):
    pct = 100*inst_cats[cat]/total_inst if total_inst else 0
    print(f"{cat:<20} {cnt:>8} {inst_cats[cat]:>13} {pct:>5.1f}%")

# Check suspicious classifications
print(f"\nRuntime-overridden opcodes:")
for op, info in sorted(final.items(), key=lambda x: -x[1]['freq']):
    if info['source'] == 'runtime_override':
        tree_cls = handler_map.get(str(op), '?')
        print(f"  Op {op:>3}: tree={tree_cls:<15} -> runtime={info['variant']:<20} ({info['freq']}x)")

unknowns = [(op, info) for op, info in final.items() if info['lua51'] in ('UNKNOWN', 'FRAGMENT')]
if unknowns:
    print(f"\nStill unresolved ({len(unknowns)}):")
    for op, info in sorted(unknowns, key=lambda x: -x[1]['freq']):
        print(f"  Op {op:>3} ({info['freq']:>5}x): variant={info['variant']}, source={info['source']}")

with open('opcode_map_final.json', 'w') as f:
    json.dump(final, f, indent=2, default=str)
print(f"\nSaved to opcode_map_final.json")
