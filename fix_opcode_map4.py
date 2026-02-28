import json

om = json.load(open('opcode_map_final.json'))

fixes = {
    '65': {'lua51': 'GETTABLE', 'variant': 'GETTABLE_COMPUTED', 'operand_map': {'dest': 'D', 'table_reg': 'a', 'table_key': 'q'}},
    '67': {'lua51': 'GETTABLE', 'variant': 'GETTABLE_COMPUTED', 'operand_map': {'dest': 'D', 'table_reg': 'a', 'table_key': 'q'}},
    '304': {'lua51': 'LOADK', 'variant': 'LOADK_COMPUTED', 'operand_map': {'dest': 'D'}},
    '246': {'lua51': 'LOADBOOL', 'variant': 'LOADBOOL_COMPUTED', 'operand_map': {'dest': 'D'}},
    '63': {'lua51': 'MOVE', 'variant': 'MOVE_COMPUTED', 'operand_map': {'move_dest': 'D', 'move_src': 'a'}},
}

for opstr, fix in fixes.items():
    old = om.get(opstr, {})
    old_cat = old.get('lua51', '?')
    old_var = old.get('variant', '?')
    for k, v in fix.items():
        old[k] = v
    om[opstr] = old
    print(f"Op {opstr}: {old_cat}:{old_var} -> {fix['lua51']}:{fix['variant']}")

json.dump(om, open('opcode_map_final.json', 'w'), indent=2)
print("Saved updated opcode map")
