import json

opmap = json.load(open('opcode_map_final.json'))

fixes = {
    '117': {'lua51': 'JMP', 'variant': 'JMP', 'note': 'D=jump_target, a=0, Z=0. 100% D valid as inst offset'},
    '294': {'lua51': 'JMP', 'variant': 'JMP', 'note': 'Same pattern as 117'},
    '159': {'lua51': 'TEST', 'variant': 'TEST_TRUE', 'note': 'if s[D[y]] then y=Z[y]. Dest=D, jump=Z'},
    '267': {'lua51': 'TEST', 'variant': 'TEST_FALSE', 'note': 'if not s[Z[y]] then y=D[y]. Test=Z, jump=D'},
    '55': {'lua51': 'NEWTABLE', 'variant': 'NEWTABLE_COMPUTED', 'note': 'Followed by SETTABLE. D=dest register via dispatch'},
    '47': {'lua51': 'NEWTABLE', 'variant': 'NEWTABLE_COMPUTED', 'note': 'Same dispatch pattern as 55'},
    '196': {'lua51': 'LOADNIL', 'variant': 'LOADNIL_aD', 'note': 'for S=a[y],D[y] do s[S]=nil end'},
    '197': {'lua51': 'LOADNIL', 'variant': 'LOADNIL_aD', 'note': 'for S=a[y],D[y] do s[S]=nil end'},
    '164': {'lua51': 'LOADNIL', 'variant': 'LOADNIL_Da', 'note': 'for S=D,a (H=D,F=a). nils D..a'},
    '171': {'lua51': 'LOADNIL', 'variant': 'LOADNIL_aD_HF', 'note': 'for S=H,F (H=a,F=D). nils a..D'},
    '169': {'lua51': 'LOADNIL', 'variant': 'LOADNIL_aZ_HF', 'note': 'for S=H,F (H=a,F=Z). nils a..Z'},
}

for op_str, fix in fixes.items():
    if op_str in opmap:
        old = opmap[op_str]
        opmap[op_str].update({
            'lua51': fix['lua51'],
            'variant': fix['variant'],
            'source': 'handler_analysis_fix',
        })
        print(f"Op {op_str}: {old.get('lua51')}:{old.get('variant')} -> {fix['lua51']}:{fix['variant']}")

with open('opcode_map_final.json', 'w') as f:
    json.dump(opmap, f, indent=2, default=str)
print(f"\nSaved updated opcode map")
