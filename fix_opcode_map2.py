import json

opmap = json.load(open('opcode_map_final.json'))

fixes = {
    '138': {'lua51': 'NEWTABLE', 'variant': 'NEWTABLE_HF', 'note': 'a=0,Z=0 always. D=dest reg. Followed by SETTABLE ops on r{D}'},
    '109': {'lua51': 'LE', 'variant': 'LE_K_STORE', 'note': 'if not(not(s[a[y]]<=m[y]))then else y=Z[y]'},
}

for op_str, fix in fixes.items():
    if op_str in opmap:
        old_lua51 = opmap[op_str].get('lua51', '?')
        old_var = opmap[op_str].get('variant', '?')
        opmap[op_str]['lua51'] = fix['lua51']
        opmap[op_str]['variant'] = fix['variant']
        opmap[op_str]['source'] = 'handler_analysis_fix2'
        print(f"Op {op_str}: {old_lua51}:{old_var} -> {fix['lua51']}:{fix['variant']}")

with open('opcode_map_final.json', 'w') as f:
    json.dump(opmap, f, indent=2, default=str)
print("Saved updated opcode map")
