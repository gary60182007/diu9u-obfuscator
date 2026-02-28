"""
Extract the full i==3 executor function body and save it.
Then parse the binary search dispatch tree to map ALL opcodes.
"""
import re, json

with open(r'unobfuscator\pending crack\bloxburg_script.lua', 'r', encoding='utf-8', errors='replace') as f:
    src = f.read()

def parse_lua_num(s):
    s = s.replace('_', '').strip()
    if s.startswith('0x') or s.startswith('0X'):
        return int(s, 16)
    elif s.startswith('0b') or s.startswith('0B'):
        return int(s, 2)
    elif s.startswith('0o') or s.startswith('0O'):
        return int(s, 8)
    return int(s)

# Find the unpack and both Y[] fetch patterns
unpack_pat = re.compile(r'local\s+Q,i,O,a,q,D,Y,Z,w,m,J\s*=\s*C\[')
um = unpack_pat.search(src)
unpack_pos = um.start()

# Find both executors
t_fetches = list(re.finditer(r'local\s+(\w+)\s*=\s*Y\[(\w+)\]', src[unpack_pos:unpack_pos+50000]))
print(f"Found {len(t_fetches)} Y[] fetches:")
for tf in t_fetches:
    print(f"  var={tf.group(1)} idx={tf.group(2)} at offset +{tf.start()}")

# The i==3 executor is the second one (T=Y[y])
i3_fetch = t_fetches[1]
i3_global = unpack_pos + i3_fetch.start()

# Find the function( that starts the i==3 executor
# Search backwards from the T=Y[y] position
search_back = src[i3_global-3000:i3_global]
# Find the LAST 'function(' before our position
func_matches = list(re.finditer(r'J=\(function\(', search_back))
if not func_matches:
    func_matches = list(re.finditer(r'function\(', search_back))
print(f"\nfunction( matches before T=Y[y]: {len(func_matches)}")
for fm in func_matches[-3:]:
    print(f"  at offset -{len(search_back)-fm.start()}: {search_back[fm.start():fm.start()+30]}")

# Use the last function( before T=Y[y]
last_func = func_matches[-1]
func_global_start = i3_global - 3000 + last_func.start()

# Now extract the full function body by tracking depth
# We need to find the matching 'end' for this function
depth = 0
pos = func_global_start
# Skip past 'function('
pos = src.index(')', pos) + 1

# Tokenize to track depth
# Simple approach: scan for keywords that increase/decrease depth
depth = 1  # We're inside the function
end_pos = None
i = pos
while i < len(src) and i < func_global_start + 200000:
    # Check for string literals (skip them)
    if src[i] == '"':
        i += 1
        while i < len(src) and src[i] != '"':
            if src[i] == '\\':
                i += 1
            i += 1
        i += 1
        continue
    if src[i] == "'":
        i += 1
        while i < len(src) and src[i] != "'":
            if src[i] == '\\':
                i += 1
            i += 1
        i += 1
        continue
    
    # Check for keywords
    if src[i:i+8] == 'function' and (i == 0 or not src[i-1].isalnum()):
        # Check it's not part of a larger word
        if i+8 < len(src) and src[i+8] == '(':
            depth += 1
            i += 8
            continue
    
    if src[i:i+2] == 'if' and (i == 0 or not src[i-1].isalnum()) and not src[i+2].isalnum():
        depth += 1
        i += 2
        continue
    
    if src[i:i+3] == 'for' and (i == 0 or not src[i-1].isalnum()) and not src[i+3].isalnum():
        depth += 1
        i += 3
        continue
    
    if src[i:i+5] == 'while' and (i == 0 or not src[i-1].isalnum()) and not src[i+5].isalnum():
        depth += 1
        i += 5
        continue
    
    if src[i:i+6] == 'repeat' and (i == 0 or not src[i-1].isalnum()) and not src[i+6].isalnum():
        depth += 1
        i += 6
        continue
    
    if src[i:i+2] == 'do' and (i == 0 or not src[i-1].isalnum()) and not src[i+2].isalnum():
        depth += 1
        i += 2
        continue
    
    if src[i:i+3] == 'end' and (i == 0 or not src[i-1].isalnum()) and (i+3 >= len(src) or not src[i+3].isalnum()):
        depth -= 1
        if depth == 0:
            end_pos = i + 3
            break
        i += 3
        continue
    
    i += 1

if end_pos:
    func_body = src[func_global_start:end_pos]
    print(f"\ni==3 executor: {len(func_body)} chars, from {func_global_start} to {end_pos}")
    
    # Save the full function body
    with open('i3_executor.lua', 'w', encoding='utf-8') as f:
        f.write(func_body)
    print(f"Saved to i3_executor.lua")
    
    # Now parse the dispatch tree within this function
    # Find all T comparisons and their positions
    t_comps = []
    for m in re.finditer(r'\bT\s*([<>=~!]+)\s*(0[xXbBoO][\da-fA-F_]+|\d+)', func_body):
        op = m.group(1)
        raw = m.group(2)
        try:
            val = parse_lua_num(raw)
            t_comps.append((m.start(), op, val))
        except:
            pass
    
    # Also find reverse comparisons
    for m in re.finditer(r'(0[xXbBoO][\da-fA-F_]+|\d+)\s*([<>=~!]+)\s*T\b', func_body):
        raw = m.group(1)
        op = m.group(2)
        try:
            val = parse_lua_num(raw)
            rev = {'<': '>', '>': '<', '<=': '>=', '>=': '<=', '==': '==', '~=': '~='}
            t_comps.append((m.start(), rev.get(op, op), val))
        except:
            pass
    
    t_comps.sort()
    
    # Build the opcode mapping by simulating the binary search
    # For each target opcode, trace through the comparisons to find the handler
    
    # Extract the binary search structure
    # The dispatch uses: if T >= X then ... elseif T < Y then ... else ... end
    # At each branch, we know the range of T values
    
    # Collect all comparison values to find the partition points
    eq_vals = sorted(set(v for _, op, v in t_comps if op == '=='))
    lt_vals = sorted(set(v for _, op, v in t_comps if op == '<'))
    ge_vals = sorted(set(v for _, op, v in t_comps if op == '>='))
    
    # All boundary values define partition points
    all_bounds = sorted(set(lt_vals + ge_vals))
    print(f"\nBinary search boundaries: {all_bounds}")
    print(f"T== values: {eq_vals}")
    
    # The total opcode range: all values that appear in the data
    with open('all_protos_data.json', 'r', encoding='utf-8') as f:
        all_protos = json.load(f)
    
    all_ops = set()
    for p in all_protos:
        for op in p.get('C4', []):
            if op is not None:
                all_ops.add(op)
    
    print(f"\nAll opcodes in data: {len(all_ops)}, range {min(all_ops)}-{max(all_ops)}")
    
    # Now let's analyze the dispatch tree more carefully
    # The binary search splits on T values, creating ranges
    # Each leaf range maps to a handler
    
    # Strategy: for each handler block (between consecutive T comparisons),
    # extract the code and classify the operation
    
    # First, let's look at what operations appear in the handler bodies
    # by searching for common patterns
    
    patterns = {
        'MOVE': r's\[\w+\[y\]\]\s*=\s*\(?s\[\w+\[y\]\]',
        'LOADK_q': r's\[\w+\[y\]\]\s*=\s*q\[y\]',
        'LOADK_w': r's\[\w+\[y\]\]\s*=\s*w\[y\]',
        'LOADK_m': r's\[\w+\[y\]\]\s*=\s*m\[y\]',
        'GETTABLE_RR': r's\[\w+\[y\]\]\s*=\s*s\[\w+\[y\]\]\[s\[\w+\[y\]\]\]',
        'GETTABLE_RK': r's\[\w+\[y\]\]\s*=\s*s\[\w+\[y\]\]\[q\[y\]\]',
        'GETTABLE_RW': r's\[\w+\[y\]\]\s*=\s*s\[\w+\[y\]\]\[w\[y\]\]',
        'SETTABLE_RRR': r's\[\w+\[y\]\]\[s\[\w+\[y\]\]\]\s*=\s*s\[\w+\[y\]\]',
        'SETTABLE_RKR': r's\[\w+\[y\]\]\[q\[y\]\]\s*=\s*s\[\w+\[y\]\]',
        'ADD': r's\[\w+\[y\]\]\+s\[\w+\[y\]\]',
        'SUB': r's\[\w+\[y\]\]-s\[\w+\[y\]\]',
        'MUL': r's\[\w+\[y\]\]\*s\[\w+\[y\]\]',
        'DIV': r's\[\w+\[y\]\]/s\[\w+\[y\]\]',
        'MOD': r's\[\w+\[y\]\]%s\[\w+\[y\]\]',
        'POW': r's\[\w+\[y\]\]\^s\[\w+\[y\]\]',
        'CONCAT_RR': r's\[\w+\[y\]\]\.\.s\[\w+\[y\]\]',
        'CONCAT_RK': r's\[\w+\[y\]\]\.\.q\[y\]',
        'CONCAT_KR': r'q\[y\]\.\.s\[\w+\[y\]\]',
        'UNM': r'-s\[\w+\[y\]\]',
        'NOT': r'not\s+s\[\w+\[y\]\]',
        'LEN': r'#s\[\w+\[y\]\]',
        'JMP': r'y\s*=\s*D\[y\]',
        'TEST_FALSE': r'if\s+not\s+s\[\w+\[y\]\]\s*then\s+y\s*=',
        'TEST_TRUE': r'if\s+s\[\w+\[y\]\]\s*then\s+y\s*=',
        'EQ_RR': r's\[\w+\[y\]\]\s*==\s*s\[\w+\[y\]\]',
        'NE_RR': r's\[\w+\[y\]\]\s*~=\s*s\[\w+\[y\]\]',
        'LT_RR': r's\[\w+\[y\]\]\s*<\s*s\[\w+\[y\]\]',
        'LE_RR': r's\[\w+\[y\]\]\s*<=\s*s\[\w+\[y\]\]',
        'GT_RR': r's\[\w+\[y\]\]\s*>\s*s\[\w+\[y\]\]',
        'GE_RR': r's\[\w+\[y\]\]\s*>=\s*s\[\w+\[y\]\]',
        'CALL_0': r's\[\w+\[y\]\]\s*=\s*s\[\w+\[y\]\]\(\)',
        'CALL_1': r's\[\w+\[y\]\]\s*=\s*s\[\w+\[y\]\]\(s\[\w+\[y\]\]\)',
        'CALL_2': r's\[\w+\[y\]\]\s*=\s*s\[\w+\[y\]\]\(s\[\w+\[y\]\],s\[\w+\[y\]\]\)',
        'SELF': r'G\s*=\s*s\[\w+\[y\]\].*s\[\w+\[y\]\]\s*=\s*G\[',
        'RETURN': r'return\s',
        'FORLOOP': r'P\+',
        'GETUPVAL': r's\[\w+\[y\]\]\s*=\s*W\[\w+\[y\]\]',
        'SETUPVAL': r'W\[\w+\[y\]\]\s*=\s*s\[\w+\[y\]\]',
        'NEWTABLE': r's\[\w+\[y\]\]\s*=\s*\{\}',
        'CLOSURE': r'function\(',
        'SETLIST': r'r\[0[xX]1\w*\]',
        'GETGLOBAL': r's\[\w+\[y\]\]\s*=\s*[A-Z]\w+\b',
        'VARARG': r'N\[',
        'ADD_K': r's\[\w+\[y\]\]\+[qwm]\[y\]',
        'SUB_K': r's\[\w+\[y\]\]-[qwm]\[y\]',
        'MUL_K': r's\[\w+\[y\]\]\*[qwm]\[y\]',
        'DIV_K': r's\[\w+\[y\]\]/[qwm]\[y\]',
        'EQ_K': r's\[\w+\[y\]\]\s*==\s*[qwm]\[y\]',
        'NE_K': r's\[\w+\[y\]\]\s*~=\s*[qwm]\[y\]',
        'LT_K': r's\[\w+\[y\]\]\s*<\s*[qwm]\[y\]',
        'LE_K': r's\[\w+\[y\]\]\s*<=\s*[qwm]\[y\]',
    }
    
    # For each T== value, find the handler and classify it
    print(f"\n{'='*90}")
    print(f"HANDLER CLASSIFICATION FOR T== VALUES")
    print(f"{'='*90}")
    
    for comp_pos, op, val in t_comps:
        if op != '==':
            continue
        
        # Find the 'then' after this comparison
        then_search = func_body[comp_pos:comp_pos+60]
        then_idx = then_search.find('then')
        if then_idx < 0:
            continue
        
        handler_start = comp_pos + then_idx + 4
        # Extract handler up to next 'else' or 'elseif' or 'end' at same depth
        handler = func_body[handler_start:handler_start+400]
        
        # Classify
        matched = []
        for pat_name, pat_re in patterns.items():
            if re.search(pat_re, handler[:200]):
                matched.append(pat_name)
        
        # Check for specific global assignments
        global_match = re.search(r's\[\w+\[y\]\]\s*=\s*\(?([a-zA-Z_]\w+)\)?', handler[:150])
        if global_match:
            gname = global_match.group(1)
            if gname[0].isupper() or gname in ('tostring', 'tonumber', 'pcall', 'error', 'assert',
                'type', 'select', 'unpack', 'rawset', 'rawget', 'require', 'next',
                'pairs', 'ipairs', 'debug', 'coroutine', 'string', 'table', 'math', 'bit32',
                'setmetatable', 'getmetatable', 'loadstring', 'collectgarbage',
                'getrenv', 'getconnections', 'readfile', 'writefile', 'isfile',
                'newcclosure', 'getgenv', 'hookfunction', 'bit'):
                matched.append(f'GLOBAL_{gname}')
        
        # Check for arith via r[37] (r[0x25])
        if re.search(r'r\[0[xX]25\]|r\[37\]', handler[:150]):
            matched.append('ARITH_FUNC_r37')
        
        # Check for table.move via r[16] (r[0x10])
        if re.search(r'r\[0[xX]1\w*\]\(s', handler[:150]):
            matched.append('TABLE_MOVE_r16')
        
        handler_preview = handler[:100].replace('\n', ' ').strip()
        class_str = ', '.join(matched) if matched else 'UNKNOWN'
        print(f"  T=={val:4d}: [{class_str:>30s}] {handler_preview}")
    
    # Count opcodes handled by each classification
    print(f"\n{'='*90}")
    print(f"SUMMARY: {len(eq_vals)} opcodes found via T==")
    print(f"Missing opcodes (in data but not T==): {len(all_ops - set(eq_vals))}")
    missing_sample = sorted(all_ops - set(eq_vals))[:30]
    print(f"Missing sample: {missing_sample}")
    
    # These missing opcodes are handled by the else branches of binary search
    # which means they're implicit from range narrowing
    # Let's figure out which ranges they fall into
    
    # Build intervals from the binary search
    # The boundaries create intervals, and opcodes in each interval share a handler
    all_boundary_vals = sorted(set(lt_vals + ge_vals + eq_vals))
    print(f"\nAll boundary values: {all_boundary_vals}")
    
    # For opcodes that DON'T have T== handlers, they must be in an else branch
    # The else branch handles the "remaining" value after all explicit checks
    # In a binary search: if T<X then ... elseif T==Y then ... else (T>X and T!=Y) ...
    
else:
    print("Could not find function end!")
