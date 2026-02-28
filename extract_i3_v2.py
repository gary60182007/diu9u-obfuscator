"""
Extract i==3 executor and parse dispatch tree properly.
"""
import re, json

with open(r'unobfuscator\pending crack\bloxburg_script.lua', 'r', encoding='utf-8', errors='replace') as f:
    src = f.read()

def parse_lua_num(s):
    s = s.replace('_', '').strip()
    if s.startswith('0x') or s.startswith('0X'): return int(s, 16)
    elif s.startswith('0b') or s.startswith('0B'): return int(s.replace('_',''), 2)
    return int(s)

# Find 'local T=Y[y]' - the i==3 opcode fetch
unpack_pat = re.compile(r'local\s+Q,i,O,a,q,D,Y,Z,w,m,J\s*=\s*C\[')
um = unpack_pat.search(src)
t_m = re.search(r'local\s+T\s*=\s*Y\[y\]', src[um.start():um.start()+50000])
t_global = um.start() + t_m.start()

# The i==3 function starts at 'function(...)local y,s' before T=Y[y]
# Find it
region_before = src[t_global-300:t_global]
func_m = re.search(r'function\(\.\.\.\)(local\s+y,s)', region_before)
if func_m:
    func_start = t_global - 300 + func_m.start()
    print(f"i==3 function starts at pos {func_start}")
else:
    print("Searching broader...")
    region_before = src[t_global-500:t_global]
    func_m = re.search(r'function\(\.\.\.\)', region_before)
    func_start = t_global - 500 + func_m.start()
    print(f"i==3 function starts at pos {func_start}")

# Extract 120KB chunk from the function start
chunk_size = 120000
chunk = src[func_start:func_start+chunk_size]

# Show the first 500 chars to verify
print(f"\nFirst 500 chars of i==3 executor:")
print(chunk[:500])

# Save the chunk
with open('i3_executor_chunk.lua', 'w', encoding='utf-8') as f:
    f.write(chunk)
print(f"\nSaved {len(chunk)} chars to i3_executor_chunk.lua")

# Now find the dispatch variable T and all its comparisons
# The dispatch is inside 'while true do' or 'while 0B1 do' etc
while_m = re.search(r'while\s+(?:true|0[bB]1|0[xX]1)\s+do', chunk)
if while_m:
    print(f"\nWhile loop at offset +{while_m.start()}")
    dispatch_body = chunk[while_m.end():]
else:
    print("No while loop found, using full chunk")
    dispatch_body = chunk[200:]  # skip function header

# Find ALL T comparisons in the dispatch body
t_comps = []
# T <op> <number>
for m in re.finditer(r'\bT\s*([<>=~!]+)\s*(0[xXbBoO][\da-fA-F_]+|\d+)\b', dispatch_body):
    op = m.group(1)
    try:
        val = parse_lua_num(m.group(2))
        t_comps.append((m.start(), op, val))
    except: pass

# <number> <op> T (reversed)
for m in re.finditer(r'\b(0[xXbBoO][\da-fA-F_]+|\d+)\s*([<>=~!]+)\s*T\b', dispatch_body):
    try:
        val = parse_lua_num(m.group(1))
        op = m.group(2)
        rev = {'<':'>','>':'<','<=':'>=','>=':'<=','==':'==','~=':'~='}
        t_comps.append((m.start(), rev.get(op, op), val))
    except: pass

t_comps.sort()

eq_vals = sorted(set(v for _, op, v in t_comps if op == '=='))
lt_vals = sorted(set(v for _, op, v in t_comps if op == '<'))
ge_vals = sorted(set(v for _, op, v in t_comps if op == '>='))
ne_vals = sorted(set(v for _, op, v in t_comps if op == '~='))

print(f"\nT comparisons: {len(t_comps)} total")
print(f"  T== : {len(eq_vals)} unique values")
print(f"  T<  : {len(lt_vals)} unique values") 
print(f"  T>= : {len(ge_vals)} unique values")
print(f"  T~= : {len(ne_vals)} unique values")

# The dispatch tree uses binary search with if/elseif/else
# For T~= comparisons: "if T~=X then <handler_for_not_X> else <handler_for_X>"
# This is equivalent to T==X in the else branch

# Combine T== and T~= to get all exact-match opcodes
all_exact = sorted(set(eq_vals + ne_vals))
print(f"\nAll exact-match opcodes (T== and T~=): {len(all_exact)}")
print(f"Values: {all_exact}")

# Load extracted opcode data
with open('all_protos_data.json', 'r', encoding='utf-8') as f:
    all_protos = json.load(f)
data_ops = set()
for p in all_protos:
    for op in p.get('C4', []):
        if op is not None: data_ops.add(op)

print(f"\nOpcodes in extracted data: {len(data_ops)}")
covered = data_ops & set(all_exact)
missing = data_ops - set(all_exact)
print(f"Covered by exact match: {len(covered)}")
print(f"Missing: {len(missing)}")
print(f"Missing values: {sorted(missing)}")

# For each exact-match opcode, extract the handler body and classify
print(f"\n{'='*90}")
print(f"OPCODE HANDLER CLASSIFICATION")
print(f"{'='*90}")

op_handlers = {}

for comp_pos, op_type, val in t_comps:
    if op_type not in ('==', '~='):
        continue
    
    # For T==val: handler is after 'then'
    # For T~=val: handler for val is after 'else' (the val case)
    
    if op_type == '==':
        then_search = dispatch_body[comp_pos:comp_pos+60]
        then_idx = then_search.find('then')
        if then_idx < 0: continue
        handler_start = comp_pos + then_idx + 4
        handler = dispatch_body[handler_start:handler_start+300]
    else:  # T~=val
        # The handler for val is in the else branch
        then_search = dispatch_body[comp_pos:comp_pos+60]
        then_idx = then_search.find('then')
        if then_idx < 0: continue
        # Find the matching else - this is complex, skip for now
        # Just mark as handled via T~=
        handler = ''
    
    if val in op_handlers:
        continue
    
    # Classify handler
    h = handler.strip()
    classification = 'UNKNOWN'
    details = ''
    
    # Check for global assignments: s[reg] = <GlobalName>
    gm = re.match(r'\s*\(?\s*s\s*\)?\s*\[\s*\w+\s*\[y\]\s*\]\s*=\s*\(?\s*([a-zA-Z_]\w*)\s*\)?', h)
    if gm:
        gname = gm.group(1)
        known_globals = {'Enum','game','workspace','CFrame','Vector3','Vector2','Color3',
            'BrickColor','UDim2','UDim','Instance','Ray','Region3','TweenInfo',
            'NumberSequence','ColorSequence','NumberRange','Rect','PhysicalProperties',
            'Font','DateTime','buffer','WebSocket','Theme',
            'tostring','tonumber','pcall','xpcall','error','assert','type','typeof',
            'select','unpack','rawset','rawget','rawequal','rawlen','require','next',
            'pairs','ipairs','print','warn','setmetatable','getmetatable',
            'loadstring','collectgarbage','coroutine','string','table','math','bit32',
            'debug','os','io','bit','task',
            'getrenv','getconnections','readfile','writefile','isfile','getgenv',
            'newcclosure','hookfunction','getfenv','setfenv','loadfile',
            'customerPosition','dec'}
        if gname in known_globals or gname[0].isupper():
            classification = f'GETGLOBAL_{gname}'
    
    # Register operations
    if classification == 'UNKNOWN':
        # MOVE: s[X[y]] = s[Y[y]]
        if re.search(r's\[\w+\[y\]\]\s*=\s*\(?s\[\w+\[y\]\]\)?;', h[:80]):
            classification = 'MOVE'
        # LOADK: s[reg] = q[y] or w[y] or m[y]
        elif re.match(r'\s*\(?\s*s\s*\)?\s*\[\s*\w+\s*\[y\]\s*\]\s*=\s*[qwm]\[y\]', h):
            classification = 'LOADK'
        # GETTABLE: s[reg] = s[reg][s[reg]]
        elif re.search(r's\[\w+\[y\]\]\s*=\s*\(?s\[\w+\[y\]\]\[s\[\w+\[y\]\]\]\)?', h[:100]):
            classification = 'GETTABLE'
        # GETTABLE_K: s[reg] = s[reg][q[y]] or [w[y]]
        elif re.search(r's\[\w+\[y\]\]\s*=\s*\(?s\[\w+\[y\]\]\[[qwm]\[y\]\]\)?', h[:100]):
            classification = 'GETTABLE_K'
        # SETTABLE: s[reg][s[reg]] = s[reg]
        elif re.search(r's\[\w+\[y\]\]\[s\[\w+\[y\]\]\]\s*=\s*s\[\w+\[y\]\]', h[:100]):
            classification = 'SETTABLE'
        # SETTABLE_K: s[reg][q[y]] = s[reg]
        elif re.search(r's\[\w+\[y\]\]\[[qwm]\[y\]\]\s*=\s*s\[\w+\[y\]\]', h[:100]):
            classification = 'SETTABLE_K'
        # ADD: s[reg] = s[reg] + s[reg]
        elif re.search(r's\[\w+\[y\]\]\s*\+\s*s\[\w+\[y\]\]', h[:100]):
            classification = 'ADD'
        elif re.search(r's\[\w+\[y\]\]\s*\+\s*[qwm]\[y\]', h[:100]):
            classification = 'ADD_K'
        elif re.search(r'[qwm]\[y\]\s*\+\s*s\[\w+\[y\]\]', h[:100]):
            classification = 'ADD_KR'
        # SUB
        elif re.search(r's\[\w+\[y\]\]\s*-\s*s\[\w+\[y\]\]', h[:100]):
            classification = 'SUB'
        elif re.search(r's\[\w+\[y\]\]\s*-\s*[qwm]\[y\]', h[:100]):
            classification = 'SUB_K'
        elif re.search(r'[qwm]\[y\]\s*-\s*s\[\w+\[y\]\]', h[:100]):
            classification = 'SUB_KR'
        # MUL
        elif re.search(r's\[\w+\[y\]\]\s*\*\s*s\[\w+\[y\]\]', h[:100]):
            classification = 'MUL'
        elif re.search(r's\[\w+\[y\]\]\s*\*\s*[qwm]\[y\]', h[:100]):
            classification = 'MUL_K'
        # DIV
        elif re.search(r's\[\w+\[y\]\]\s*/\s*s\[\w+\[y\]\]', h[:100]):
            classification = 'DIV'
        elif re.search(r's\[\w+\[y\]\]\s*/\s*[qwm]\[y\]', h[:100]):
            classification = 'DIV_K'
        # MOD
        elif re.search(r's\[\w+\[y\]\]\s*%\s*s\[\w+\[y\]\]', h[:100]):
            classification = 'MOD'
        # POW
        elif re.search(r's\[\w+\[y\]\]\s*\^\s*s\[\w+\[y\]\]', h[:100]):
            classification = 'POW'
        elif re.search(r's\[\w+\[y\]\]\s*\^\s*[qwm]\[y\]', h[:100]):
            classification = 'POW_K'
        # CONCAT
        elif re.search(r's\[\w+\[y\]\]\s*\.\.\s*s\[\w+\[y\]\]', h[:100]):
            classification = 'CONCAT'
        elif re.search(r's\[\w+\[y\]\]\s*\.\.\s*[qwm]\[y\]', h[:100]):
            classification = 'CONCAT_K'
        elif re.search(r'[qwm]\[y\]\s*\.\.\s*s\[\w+\[y\]\]', h[:100]):
            classification = 'CONCAT_KR'
        # UNM
        elif re.search(r'=\s*\(\s*-s\[\w+\[y\]\]\s*\)', h[:80]):
            classification = 'UNM'
        # NOT
        elif re.search(r'=\s*not\s+s\[\w+\[y\]\]', h[:80]):
            classification = 'NOT'
        # LEN
        elif re.search(r'=\s*#s\[\w+\[y\]\]', h[:80]):
            classification = 'LEN'
        # Comparisons with jump
        elif re.search(r'if\s+s\[\w+\[y\]\]\s*<\s*s\[\w+\[y\]\]\s*then\s+y\s*=', h[:100]):
            classification = 'LT_JMP'
        elif re.search(r'if\s+s\[\w+\[y\]\]\s*<=\s*s\[\w+\[y\]\]\s*then\s+y\s*=', h[:100]):
            classification = 'LE_JMP'
        elif re.search(r'if\s+s\[\w+\[y\]\]\s*==\s*s\[\w+\[y\]\]\s*then\s+y\s*=', h[:100]):
            classification = 'EQ_JMP'
        elif re.search(r'if\s+s\[\w+\[y\]\]\s*~=\s*s\[\w+\[y\]\]\s*then\s+y\s*=', h[:100]):
            classification = 'NE_JMP'
        elif re.search(r'if\s+s\[\w+\[y\]\]\s*>\s*s\[\w+\[y\]\]\s*then', h[:100]):
            classification = 'GT_JMP'
        # Comparison result stored
        elif re.search(r's\[\w+\[y\]\]\s*=\s*s\[\w+\[y\]\]\s*>\s*s\[\w+\[y\]\]', h[:100]):
            classification = 'GT_STORE'
        elif re.search(r's\[\w+\[y\]\]\s*=\s*s\[\w+\[y\]\]\s*<\s*[qwm]\[y\]', h[:100]):
            classification = 'LT_K_STORE'
        elif re.search(r's\[\w+\[y\]\]\s*=\s*s\[\w+\[y\]\]\s*~=\s*[qwm]\[y\]', h[:100]):
            classification = 'NE_K_STORE'
        elif re.search(r's\[\w+\[y\]\]\s*=\s*[qwm]\[y\]\s*~=\s*[qwm]\[y\]', h[:100]):
            classification = 'NE_KK_STORE'
        elif re.search(r'[qwm]\[y\]\s*<=\s*s\[\w+\[y\]\]', h[:100]):
            classification = 'GE_K_CMP'
        # TEST
        elif re.search(r'if\s+not\s+s\[\w+\[y\]\]\s*then\s+y\s*=', h[:100]):
            classification = 'TEST_FALSE'
        elif re.search(r'if\s+s\[\w+\[y\]\]\s*then\s+y\s*=', h[:100]):
            classification = 'TEST_TRUE'
        # JMP
        elif re.match(r'\s*y\s*=\s*\(?\s*D\[y\]\s*\)?', h[:40]):
            classification = 'JMP'
        # CALL with spread
        elif re.search(r'r\[0[xX]0*1[dD]\]|r\[29\]|r\[0[bB]11101\]', h[:150]):
            classification = 'CALL_SPREAD'
        # CALL simple
        elif re.search(r's\[\w+\[y\]\]\s*=\s*s\[\w+\[y\]\]\(s\[\w+\[y\]\]', h[:100]):
            classification = 'CALL'
        elif re.search(r's\[\w+\[y\]\]\s*=\s*s\[\w+\[y\]\]\(\)', h[:100]):
            classification = 'CALL_0'
        # SELF pattern
        elif re.search(r'G\s*=\s*\(?\s*s\[\w+\[y\]\]\s*\)?.*\(?\s*s\s*\)?\s*\[\w+\[y\]\]\s*=\s*\(?\s*G', h[:150]):
            classification = 'SELF'
        # RETURN
        elif re.match(r'\s*return\b', h[:20]):
            classification = 'RETURN'
        # GETUPVAL
        elif re.search(r's\[\w+\[y\]\]\s*=\s*W\[\w+\[y\]\]', h[:80]):
            classification = 'GETUPVAL'
        # SETUPVAL/SETGLOBAL via W or r[4]
        elif re.search(r'\(?\s*r\[0?[xX]?4\]\s*\)?\s*\[\w+\[y\]\]\s*=\s*s\[\w+\[y\]\]', h[:100]):
            classification = 'SETGLOBAL'
        elif re.search(r'W\[\w+\[y\]\]\s*=', h[:80]):
            classification = 'SETUPVAL'
        # NEWTABLE
        elif re.search(r's\[\w+\[y\]\]\s*=\s*\{\s*\}', h[:60]):
            classification = 'NEWTABLE'
        # CLOSURE
        elif 'function(' in h[:80]:
            classification = 'CLOSURE'
        # FORLOOP
        elif re.search(r'P\s*\+\s*=\s*I|P\s*=\s*P\s*\+\s*I', h[:80]):
            classification = 'FORLOOP'
        # VARARG
        elif re.search(r'N\[\w+\]', h[:80]):
            classification = 'VARARG'
        # Arith via r[37]
        elif re.search(r'r\[0[xX]25\]|r\[37\]', h[:80]):
            classification = 'ARITH_BUILTIN'
        # LOADNIL
        elif re.search(r's\[\w+\[y\]\]\s*=\s*nil', h[:60]):
            classification = 'LOADNIL'
        # LOADBOOL
        elif re.search(r's\[\w+\[y\]\]\s*=\s*(?:true|false)', h[:60]):
            classification = 'LOADBOOL'
        # Upvalue table access: W[idx][slot]
        elif re.search(r'W\[\w+\[y\]\]\)\s*\[', h[:80]) or re.search(r'H\s*=\s*W\[\w+\[y\]\]', h[:80]):
            classification = 'GETUPVAL_TABLE'
        # Comparison with immediate
        elif re.search(r'not\s*\(\s*not\s*\(\s*s\[\w+\[y\]\]\s*<=\s*[qwm]\[y\]\)', h[:100]):
            classification = 'LE_K_JMP'
        elif re.search(r'not\s*\(\s*s\[\w+\[y\]\]\s*<=\s*[qwm]\[y\]\)', h[:100]):
            classification = 'GT_K_JMP'

    op_handlers[val] = classification
    
    if handler:
        h_short = h[:120].replace('\n', ' ')
        print(f"  T=={val:4d}: [{classification:>20s}] {h_short}")

# Summary
print(f"\n{'='*90}")
print(f"CLASSIFICATION SUMMARY")
print(f"{'='*90}")

from collections import Counter
class_counts = Counter(op_handlers.values())
for cls, cnt in class_counts.most_common():
    print(f"  {cls:>25s}: {cnt}")

# Now handle T~= opcodes (the else branch)
ne_handled = set()
for comp_pos, op_type, val in t_comps:
    if op_type == '~=' and val not in op_handlers:
        # T~=val means: if T~=val then <other_handler> else <handler_for_val>
        # Need to extract the else branch
        ne_handled.add(val)

print(f"\nT~= opcodes (handler in else branch): {sorted(ne_handled)}")
print(f"Total classified: {len(op_handlers)} (T==) + {len(ne_handled)} (T~=) = {len(op_handlers)+len(ne_handled)}")

# Save results
with open('opcode_map.json', 'w') as f:
    json.dump({
        'handlers': {str(k): v for k, v in op_handlers.items()},
        'ne_opcodes': sorted(ne_handled),
        'eq_opcodes': eq_vals,
        'lt_boundaries': lt_vals,
        'ge_boundaries': ge_vals,
    }, f, indent=1)
print(f"\nSaved to opcode_map.json")
