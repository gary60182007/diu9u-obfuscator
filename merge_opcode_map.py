import json, re
from collections import Counter

dispatch = json.load(open('opcode_dispatch_map.json'))
protos = json.load(open('all_protos_data.json'))

combined = {}
try:
    combined = json.load(open('opcode_combined.json'))
except: pass

handler_map = dispatch.get('handler_map', {})
handler_code = dispatch.get('handler_code', {})

op_freq = Counter()
total_inst = 0
for p in protos:
    opcodes = p.get('C4', [])
    for op in opcodes:
        op_freq[op] += 1
        total_inst += 1

def normalize(cls, op_val, code=''):
    if cls.startswith('GETGLOBAL('):
        name = cls[10:-1]
        return 'GETGLOBAL', {'global_name': name}
    
    lua51_map = {
        'MOVE': 'MOVE',
        'LOADK_q': 'LOADK', 'LOADK_w': 'LOADK', 'LOADK_m': 'LOADK',
        'LOADNIL': 'LOADNIL', 'LOADNIL_RANGE': 'LOADNIL',
        'LOADBOOL_TRUE': 'LOADBOOL', 'LOADBOOL_FALSE': 'LOADBOOL',
        'NEWTABLE': 'NEWTABLE',
        'GETTABLE': 'GETTABLE', 'GETTABLE_Kq': 'GETTABLE', 'GETTABLE_Kw': 'GETTABLE', 'GETTABLE_Km': 'GETTABLE',
        'SETTABLE': 'SETTABLE', 'SETTABLE_Kq': 'SETTABLE', 'SETTABLE_Kw': 'SETTABLE', 'SETTABLE_Km': 'SETTABLE',
        'SETTABLE_KqKq': 'SETTABLE', 'SETTABLE_KqKw': 'SETTABLE', 'SETTABLE_KqKm': 'SETTABLE',
        'SETTABLE_KwKq': 'SETTABLE', 'SETTABLE_KwKw': 'SETTABLE', 'SETTABLE_KwKm': 'SETTABLE',
        'SETTABLE_KmKq': 'SETTABLE', 'SETTABLE_KmKw': 'SETTABLE', 'SETTABLE_KmKm': 'SETTABLE',
        'SETTABLE_Km_V': 'SETTABLE', 'SETTABLE_Vq': 'SETTABLE', 'SETTABLE_Vw': 'SETTABLE', 'SETTABLE_Vm': 'SETTABLE',
        'SETTABLE_Kq_BOOL': 'SETTABLE', 'SETTABLE_Kw_BOOL': 'SETTABLE',
        'SETTABLE_Kq_NIL': 'SETTABLE', 'SETTABLE_Kw_NIL': 'SETTABLE',
        'SETTABLE_HFK': 'SETTABLE',
        'ADD': 'ADD', 'SUB': 'SUB', 'MUL': 'MUL', 'DIV': 'DIV', 'MOD': 'MOD', 'POW': 'POW',
        'ADD_Kq': 'ADD', 'ADD_Kw': 'ADD', 'ADD_Km': 'ADD',
        'SUB_Kq': 'SUB', 'SUB_Kw': 'SUB', 'SUB_Km': 'SUB',
        'MUL_Kq': 'MUL', 'MUL_Kw': 'MUL', 'MUL_Km': 'MUL',
        'DIV_Kq': 'DIV', 'DIV_qK': 'DIV', 'DIV_Kw': 'DIV', 'DIV_Km': 'DIV',
        'MOD_Kq': 'MOD', 'MOD_Kw': 'MOD', 'MOD_Km': 'MOD',
        'POW_Kq': 'POW', 'POW_Kw': 'POW', 'POW_Km': 'POW',
        'ADD_qK': 'ADD', 'ADD_wK': 'ADD', 'ADD_mK': 'ADD',
        'SUB_qK': 'SUB', 'SUB_wK': 'SUB', 'SUB_mK': 'SUB',
        'MUL_qK': 'MUL', 'MUL_wK': 'MUL', 'MUL_mK': 'MUL',
        'MOD_qK': 'MOD', 'MOD_wK': 'MOD', 'MOD_mK': 'MOD',
        'POW_qK': 'POW', 'POW_wK': 'POW', 'POW_mK': 'POW',
        'SUB_kK': 'SUB',
        'CONCAT': 'CONCAT', 'CONCAT_Kq': 'CONCAT', 'CONCAT_Kw': 'CONCAT', 'CONCAT_Km': 'CONCAT',
        'CONCAT_KqR': 'CONCAT', 'CONCAT_KwR': 'CONCAT', 'CONCAT_KmR': 'CONCAT',
        'UNM': 'UNM', 'NOT': 'NOT', 'LEN': 'LEN',
        'EQ_JMP': 'EQ', 'NE_JMP': 'EQ', 'LT_JMP': 'LT', 'LE_JMP': 'LE',
        'GT_JMP': 'LT', 'GE_JMP': 'LE',
        'EQ_K_JMP': 'EQ', 'NE_K_JMP': 'EQ', 'LT_K_JMP': 'LT', 'LE_K_JMP': 'LE',
        'GT_K_JMP': 'LT', 'GE_K_JMP': 'LE',
        'EQ_STORE': 'EQ', 'NE_STORE': 'EQ', 'LT_STORE': 'LT', 'LE_STORE': 'LE',
        'GT_STORE': 'LT', 'GE_STORE': 'LE',
        'CMP_KK_STORE': 'EQ',
        'TEST_TRUE': 'TEST', 'TEST_FALSE': 'TEST',
        'TEST_NIL': 'TEST', 'TEST_NOT_NIL': 'TEST',
        'JMP': 'JMP',
        'CALL': 'CALL', 'CALL_0': 'CALL', 'CALL_1_0': 'CALL',
        'CALL_SPREAD': 'CALL', 'CALL_UNPACK': 'CALL',
        'CALL_SETUP': 'CALL', 'SELF': 'SELF',
        'RETURN': 'RETURN', 'RETURN_VAL': 'RETURN',
        'GETUPVAL': 'GETUPVAL', 'SETUPVAL': 'SETUPVAL',
        'UPVAL_ACCESS': 'GETUPVAL', 'UPVAL_OP': 'GETUPVAL',
        'SETGLOBAL': 'SETGLOBAL',
        'CLOSURE': 'CLOSURE',
        'FORLOOP': 'FORLOOP', 'FORPREP': 'FORPREP',
        'TFORLOOP': 'TFORLOOP',
        'VARARG': 'VARARG',
        'SETLIST': 'SETLIST',
        'CLOSE': 'CLOSE',
        'COMPUTED_DISPATCH': 'COMPUTED',
        'ARITH_BUILTIN': 'ARITH',
        'RANGE_SETUP': 'CALL',
        'ASSIGN_K': 'LOADK',
        'GETTABLE_Fk': 'GETTABLE',
        'REG_ASSIGN': 'MOVE',
    }
    
    if cls in lua51_map:
        return lua51_map[cls], {'variant': cls}
    
    return cls, {'variant': cls}

# Manual classifications for the 5 remaining unknowns
manual = {
    74: ('GETTABLE', {'variant': 'GETTABLE_kK', 'note': 'k=(k[K]) temp table access'}),
    95: ('COMPUTED', {'variant': 'COMPUTED_DISPATCH', 'note': 'while true dispatch loop'}),
    167: ('LOADK', {'variant': 'LOADK_VM', 'note': 's[a[y]]=z.L9 (VM internal)'}),
    230: ('MOVE', {'variant': 'MOVE_KH', 'note': 'K=H temp var assign'}),
    262: ('LOADK', {'variant': 'LOADK_VM', 'note': 's[D[y]]=z.k9 (VM internal)'}),
}

final_map = {}
for op_str, cls in handler_map.items():
    op = int(op_str)
    if op in manual:
        lua_op, extra = manual[op]
    elif cls == 'UNKNOWN':
        lua_op, extra = 'UNKNOWN', {'variant': 'UNKNOWN'}
    else:
        lua_op, extra = normalize(cls, op, handler_code.get(op_str, ''))
    
    final_map[op] = {
        'lua51_op': lua_op,
        'dispatch_cls': cls,
        'freq': op_freq.get(op, 0),
        **extra,
    }

# Summary stats
cats = Counter()
inst_cats = Counter()
for op, info in final_map.items():
    cats[info['lua51_op']] += 1
    inst_cats[info['lua51_op']] += info['freq']

print(f"\n{'='*70}")
print(f"FINAL OPCODE MAP: {len(final_map)} opcodes -> {len(cats)} Lua 5.1 categories")
print(f"{'='*70}")
print(f"\n{'Category':<20} {'Opcodes':>8} {'Instructions':>13}")
print('-'*45)
for cat, cnt in sorted(cats.items(), key=lambda x: -inst_cats[x[0]]):
    print(f"{cat:<20} {cnt:>8} {inst_cats[cat]:>13}")

unknown_ops = [op for op, info in final_map.items() if info['lua51_op'] == 'UNKNOWN']
if unknown_ops:
    print(f"\nStill UNKNOWN ({len(unknown_ops)}): {sorted(unknown_ops)}")

# Verify coverage
all_used = set(op_freq.keys())
mapped = set(final_map.keys())
missing = all_used - mapped
if missing:
    print(f"\nWARNING: {len(missing)} used opcodes not in map: {sorted(missing)}")
else:
    print(f"\n100% coverage: all {len(all_used)} used opcodes are mapped")

with open('opcode_map_comprehensive.json', 'w') as f:
    json.dump(final_map, f, indent=2, default=str)
print(f"\nSaved to opcode_map_comprehensive.json")
