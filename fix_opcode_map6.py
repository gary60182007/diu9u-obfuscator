import json

om = json.load(open('opcode_map_final.json'))

fixes = {
    '87': {'lua51': 'JMP', 'variant': 'JMP_COMPUTED'},
    '136': {'lua51': 'TEST', 'variant': 'TEST_Z', 'operand_map': {'test_reg': 'Z'}},
    '25': {'lua51': 'TEST', 'variant': 'TEST_Z', 'operand_map': {'test_reg': 'Z'}},
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
print("Saved")
