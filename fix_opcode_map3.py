import json

opmap = json.load(open('opcode_map_final.json'))

fixes = {
    '309': {'lua51': 'RETURN', 'variant': 'RETURN_RANGE',
            'note': 'H=Z[y]; return false,H,H+a[y]-2. Returns regs Z..Z+a-2, closes upvals first'},
    '152': {'lua51': 'CLOSURE', 'variant': 'CLOSURE_SETUP',
            'note': 'Sets up upvalue references for preceding CLOSURE instruction'},
    '233': {'lua51': 'CLOSURE', 'variant': 'CLOSURE_SETUP',
            'note': 'Sets up upvalue references for preceding CLOSURE instruction'},
}

for op_str, fix in fixes.items():
    if op_str in opmap:
        old_lua51 = opmap[op_str].get('lua51', '?')
        old_var = opmap[op_str].get('variant', '?')
        opmap[op_str]['lua51'] = fix['lua51']
        opmap[op_str]['variant'] = fix['variant']
        opmap[op_str]['source'] = 'handler_analysis_fix3'
        print(f"Op {op_str}: {old_lua51}:{old_var} -> {fix['lua51']}:{fix['variant']}")

with open('opcode_map_final.json', 'w') as f:
    json.dump(opmap, f, indent=2, default=str)
print("Saved updated opcode map")
