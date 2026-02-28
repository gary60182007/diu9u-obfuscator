import json

opmap = json.load(open('opcode_map_final.json'))

# JTR op 122 (169x): Z sometimes valid reg, always followed by MUL
# Pattern: conditional test before arithmetic - likely TEST variant
opmap['122'] = {**opmap['122'], 'lua51': 'TEST', 'variant': 'TEST_Z'}

# JTR op 97 (12x): D always valid reg, a often valid jump, followed by LOADNIL
# Pattern: test r{D}, jump to a - conditional jump
opmap['97'] = {**opmap['97'], 'lua51': 'TEST', 'variant': 'TEST_D_JMP'}

# JTR op 30 (5x): a always valid jump target, mixed D/Z
# Pattern: conditional jump to a
opmap['30'] = {**opmap['30'], 'lua51': 'TEST', 'variant': 'TEST_JMP_A'}

# COMPUTED op 278 (124x): has m=n:XXX, Z sometimes valid
# Can't determine exact semantics without handler. Mark as DISPATCH_OP
opmap['278'] = {**opmap['278'], 'lua51': 'DISPATCH', 'variant': 'DISPATCH_MK'}

# COMPUTED op 68 (17x): a often valid reg, mixed
opmap['68'] = {**opmap['68'], 'lua51': 'DISPATCH', 'variant': 'DISPATCH_A'}

# COMPUTED op 299 (12x): all OOR - pure dispatch
opmap['299'] = {**opmap['299'], 'lua51': 'DISPATCH', 'variant': 'DISPATCH_PURE'}

# COMPUTED op 298 (5x): all OOR
opmap['298'] = {**opmap['298'], 'lua51': 'DISPATCH', 'variant': 'DISPATCH_PURE'}

# COMPUTED ops with D valid, others OOR - likely LOADK or MOVE with encoded source
for op_id in ['42', '43', '49', '50', '62', '70', '95', '243', '244', '266', '268']:
    if op_id in opmap and opmap[op_id].get('lua51') == 'COMPUTED':
        opmap[op_id] = {**opmap[op_id], 'lua51': 'DISPATCH', 'variant': 'DISPATCH_D'}

# Remaining low-freq COMPUTED ops
for op_id in ['53', '60', '44', '52', '64', '248', '274', '279', '301', '45', '48', '94', '263', '269']:
    if op_id in opmap and opmap[op_id].get('lua51') == 'COMPUTED':
        opmap[op_id] = {**opmap[op_id], 'lua51': 'DISPATCH', 'variant': 'DISPATCH_MISC'}

json.dump(opmap, open('opcode_map_final.json', 'w'), indent=2)
print("Updated opcode map: reclassified JTR->TEST and COMPUTED->DISPATCH")
