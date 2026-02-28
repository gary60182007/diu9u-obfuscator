"""
Extract the i==3 VM executor dispatch table.
Find ALL opcode comparisons using variable T in the i==3 executor body.
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

# Find the unpack position
unpack_pat = re.compile(r'local\s+Q,i,O,a,q,D,Y,Z,w,m,J\s*=\s*C\[')
um = unpack_pat.search(src)
unpack_pos = um.start()

# The i==3 executor starts with 'local T=Y[y]' at approximately offset +4107
# Let's find it precisely
chunk = src[unpack_pos:unpack_pos + 500000]

# Find 'local T=Y[y]' - the i==3 opcode fetch
t_fetch = re.search(r'local\s+T\s*=\s*Y\[y\]', chunk)
if t_fetch:
    i3_start = t_fetch.start()
    print(f"i==3 executor opcode fetch at offset +{i3_start}")
    print(f"Global pos: {unpack_pos + i3_start}")
    
    # Extract a LARGE chunk of the i==3 executor
    i3_chunk = chunk[i3_start:]
    
    # Find ALL T comparisons (T==, T<, T>=, T>, T<=)
    t_comps = []
    for m in re.finditer(r'T\s*([<>=!]+)\s*(0[xXbBoO][\da-fA-F_]+|\d+)', i3_chunk):
        op = m.group(1)
        raw = m.group(2)
        try:
            val = parse_lua_num(raw)
            t_comps.append((m.start(), op, val, raw))
        except:
            pass
    
    # Also find reverse comparisons: <number> <op> T
    for m in re.finditer(r'(0[xXbBoO][\da-fA-F_]+|\d+)\s*([<>=!]+)\s*T\b', i3_chunk):
        raw = m.group(1)
        op = m.group(2)
        try:
            val = parse_lua_num(raw)
            # Reverse the comparison
            rev_ops = {'<': '>', '>': '<', '<=': '>=', '>=': '<=', '==': '==', '~=': '~='}
            t_comps.append((m.start(), rev_ops.get(op, op), val, raw))
        except:
            pass
    
    t_comps.sort(key=lambda x: x[0])
    
    # Extract unique comparison values
    eq_vals = sorted(set(v for _, op, v, _ in t_comps if op == '=='))
    lt_vals = sorted(set(v for _, op, v, _ in t_comps if op == '<'))
    ge_vals = sorted(set(v for _, op, v, _ in t_comps if op == '>='))
    
    print(f"\nTotal T comparisons: {len(t_comps)}")
    print(f"T== values ({len(eq_vals)}): {eq_vals}")
    print(f"T< values ({len(lt_vals)}): {lt_vals}")
    print(f"T>= values ({len(ge_vals)}): {ge_vals}")
    
    # The opcode values are in the T== comparisons
    # The T< and T>= are binary search bounds
    all_opcodes = sorted(set(eq_vals))
    print(f"\nAll unique opcode values (from T==): {len(all_opcodes)}")
    print(f"Opcodes: {all_opcodes}")
    
    # Now extract the handler code for each opcode
    # For each T==<value>, extract the handler body (code between then...end/else/elseif)
    print(f"\n{'='*80}")
    print(f"OPCODE HANDLER ANALYSIS")
    print(f"{'='*80}")
    
    # Find each T==value handler and analyze what it does
    for comp_pos, op, val, raw in t_comps:
        if op != '==':
            continue
        
        # Find the 'then' after this comparison
        then_pos = i3_chunk.find('then', comp_pos + len(raw))
        if then_pos < 0 or then_pos > comp_pos + 50:
            continue
        
        # Extract handler body (up to 300 chars for analysis)
        handler_start = then_pos + 4
        handler = i3_chunk[handler_start:handler_start + 300]
        
        # Classify the operation based on handler patterns
        op_type = 'unknown'
        details = ''
        
        h = handler.strip()
        
        # MOVE: y[dst] = y[src]
        if re.match(r'\s*\(?\s*y\s*\)\s*\[\s*\w+\s*\]\s*=\s*\(?\s*y\s*\[', h):
            op_type = 'MOVE/COPY'
            
        # LOADK: y[dst] = q[L] (constant load)
        if 'q[' in h[:60] and 'y[' in h[:60]:
            if 'y[' in h[:30]:
                op_type = 'LOADK/CONST'
        
        # GETGLOBAL/GETUPVAL: y[dst] = W[...] or y[dst] = Enum/game etc
        if re.search(r'y\[\w+\]\s*=\s*W\[', h[:80]):
            op_type = 'GETUPVAL/GLOBAL'
        
        # GETTABLE: y[dst] = y[src][y[idx]] or y[dst] = y[src][q[L]]
        if re.search(r'y\[\w+\]\s*=\s*y\[\w+\]\[y\[', h[:80]):
            op_type = 'GETTABLE'
        if re.search(r'y\[\w+\]\s*=\s*y\[\w+\]\[q\[', h[:80]):
            op_type = 'GETTABLE_K'
        if re.search(r'y\[\w+\]\s*=\s*y\[\w+\]\[w\[', h[:80]):
            op_type = 'GETTABLE_W'
        
        # SETTABLE: y[a][b] = y[c] or y[a][q[L]] = y[c]
        if re.search(r'y\[\w+\]\[', h[:40]) and '=' in h[:80]:
            if op_type == 'unknown':
                op_type = 'SETTABLE'
        
        # CALL: y[base] = y[base](...)
        if re.search(r'y\[\w+\]\s*=\s*y\[\w+\]\(', h[:80]):
            op_type = 'CALL'
        if 'r[0X001D]' in h or 'r[29]' in h:
            op_type = 'CALL_VARARG'
        
        # RETURN
        if re.match(r'\s*return\b', h):
            op_type = 'RETURN'
        if 'return' in h[:60] and 'y[' in h[:60]:
            op_type = 'RETURN_VAL'
        
        # JMP: L = D[L] or L = a[L]
        if re.match(r'\s*L\s*=\s*\(?\s*D\[', h):
            op_type = 'JMP'
        if re.match(r'\s*y\s*=\s*\(?\s*D\[', h):
            op_type = 'JMP_Y'
        
        # FORLOOP/FORPREP
        if 'for ' in h[:60] or 'L+=' in h[:30]:
            if op_type == 'unknown':
                op_type = 'LOOP/ADVANCE'
        
        # LOADNIL
        if re.search(r'y\[\w+\]\s*=\s*nil', h[:60]):
            op_type = 'LOADNIL'
        
        # LOADBOOL
        if re.search(r'y\[\w+\]\s*=\s*true|y\[\w+\]\s*=\s*false', h[:60]):
            op_type = 'LOADBOOL'
        
        # NEWTABLE
        if re.search(r'y\[\w+\]\s*=\s*\{', h[:60]):
            op_type = 'NEWTABLE'
        
        # CLOSURE
        if 'function(' in h[:80]:
            op_type = 'CLOSURE'
        
        # Arithmetic
        if re.search(r'y\[\w+\]\+y\[|y\[\w+\]\-y\[|y\[\w+\]\*y\[|y\[\w+\]/y\[', h[:80]):
            op_type = 'ARITH'
        
        # CONCAT
        if '..' in h[:80]:
            op_type = 'CONCAT'
        
        # TEST/TESTSET: if y[reg] then or if not y[reg] then
        if re.search(r'if\s+(not\s+)?y\[', h[:60]):
            if op_type == 'unknown':
                op_type = 'TEST/COND'
        
        # LEN: #y[reg]
        if '#y[' in h[:60]:
            op_type = 'LEN'
        
        # UNM: -y[reg]  
        if re.search(r'=\s*-y\[', h[:60]):
            op_type = 'UNM'
        
        # NOT: not y[reg]
        if re.search(r'=\s*not\s+y\[', h[:60]):
            op_type = 'NOT'
        
        # Comparison: y[a] == y[b], y[a] < y[b], etc
        if re.search(r'y\[\w+\]\s*[<>=~]+\s*y\[', h[:80]):
            if op_type == 'unknown':
                op_type = 'COMPARE'
        
        # SELF: y[a+1]=y[b]; y[a]=y[b][k]
        if re.search(r'G\s*=\s*y\[\w+\].*y\[\w+\]\s*=\s*G\[', h[:120]):
            op_type = 'SELF'
        
        handler_preview = h[:120].replace('\n', ' ')
        print(f"\n  T=={val:4d} [{op_type:15s}]: {handler_preview}")

    # Count how many opcodes match our extracted data
    with open('all_protos_data.json', 'r', encoding='utf-8') as f:
        all_protos = json.load(f)
    
    extracted_opcodes = set()
    for p in all_protos:
        for op in p.get('C4', []):
            if op is not None:
                extracted_opcodes.add(op)
    
    print(f"\n{'='*80}")
    print(f"COVERAGE ANALYSIS")
    print(f"{'='*80}")
    print(f"Opcodes in extracted data: {len(extracted_opcodes)}")
    print(f"Opcodes in i==3 dispatcher: {len(all_opcodes)}")
    matched = extracted_opcodes & set(all_opcodes)
    print(f"Matched: {len(matched)}")
    unmatched = extracted_opcodes - set(all_opcodes)
    if unmatched:
        print(f"Unmatched (in data but not in dispatcher): {sorted(unmatched)[:30]}")
    extra = set(all_opcodes) - extracted_opcodes
    if extra:
        print(f"Extra (in dispatcher but not in data): {sorted(extra)[:30]}")
