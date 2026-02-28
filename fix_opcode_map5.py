import json

om = json.load(open('opcode_map_final.json'))

fixes = {
    '303': {'lua51': 'MOVE', 'variant': 'MOVE_COMPUTED', 'operand_map': {'move_dest': 'D', 'move_src': 'Z'}},
    '261': {'lua51': 'CALL', 'variant': 'CALL_COMPUTED', 'operand_map': {'call_base': 'a'}},
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
