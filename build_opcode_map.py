"""
Build comprehensive opcode map by combining:
1. Static handler analysis from T== handlers
2. Operand patterns from proto data
3. Runtime trace data
4. T~= handler extraction
"""
import re, json
from collections import defaultdict

def parse_lua_num(s):
    s = s.replace('_', '').strip()
    if s.startswith('0x') or s.startswith('0X'): return int(s, 16)
    elif s.startswith('0b') or s.startswith('0B'): return int(s.replace('_',''), 2)
    return int(s)

# Load executor chunk
with open('i3_executor_chunk.lua', 'r', encoding='utf-8') as f:
    executor = f.read()

# Load proto data for patterns
with open('all_protos_data.json', 'r', encoding='utf-8') as f:
    all_protos = json.load(f)

with open('c2_full_data.json', 'r', encoding='utf-8') as f:
    c2_data = json.load(f)

# Load runtime trace
try:
    with open('opcode_trace_fast.json', 'r', encoding='utf-8') as f:
        rt_trace = json.load(f)
except:
    rt_trace = {}

# Build opcode frequency and pattern data
op_freq = defaultdict(int)
op_patterns = defaultdict(lambda: defaultdict(int))
op_c2_types = defaultdict(lambda: defaultdict(int))
op_c2_pct = {}

for p in all_protos:
    pid = str(p['id'])
    opcodes = p.get('C4', [])
    c7 = p.get('C7', [])
    c8 = p.get('C8', [])
    c9 = p.get('C9', [])
    p_c2 = c2_data.get(pid, {})
    
    for i, op in enumerate(opcodes):
        if op is None: continue
        op_freq[op] += 1
        a_val = c7[i] if i < len(c7) else None
        b_val = c8[i] if i < len(c8) else None
        c_val = c9[i] if i < len(c9) else None
        has_k = str(i+1) in p_c2
        
        pat = ''
        pat += 'A' if (a_val is not None and a_val != 0) else '_'
        pat += 'B' if (b_val is not None and b_val != 0) else '_'
        pat += 'C' if (c_val is not None and c_val != 0) else '_'
        pat += 'K' if has_k else '_'
        op_patterns[op][pat] += 1
        
        if has_k:
            entry = p_c2[str(i+1)]
            if entry.startswith('n:'): op_c2_types[op]['number'] += 1
            elif entry.startswith('s:'): op_c2_types[op]['string'] += 1
            elif entry.startswith('t:'): op_c2_types[op]['table'] += 1
            else: op_c2_types[op]['other'] += 1

for op in op_freq:
    total = op_freq[op]
    k_count = sum(op_c2_types[op].values())
    op_c2_pct[op] = k_count / total if total > 0 else 0

# Find all T comparisons in executor
t_eq = {}  # T==val -> handler_code
t_ne = {}  # T~=val -> handler_code (for the val case, in else branch)

for m in re.finditer(r'\bT\s*(==|~=)\s*(0[xXbBoO][\da-fA-F_]+|\d+)', executor):
    op_type = m.group(1)
    try: val = parse_lua_num(m.group(2))
    except: continue
    
    then_search = executor[m.end():m.end()+60]
    then_idx = then_search.find('then')
    if then_idx < 0: continue
    
    handler_start = m.end() + then_idx + 4
    handler = executor[handler_start:handler_start+500]
    
    if op_type == '==':
        if val not in t_eq:
            t_eq[val] = handler
    else:
        if val not in t_ne:
            # For T~=val, the handler for val is in the ELSE branch
            # Need to find the else block - skip the then block
            # Simple heuristic: find 'else' after handler
            t_ne[val] = f"T~={val} (else branch)"

# Also find comparisons written as: not(T>=X) or not(T<X)
for m in re.finditer(r'not\s*\(\s*T\s*(>=|<)\s*(0[xXbBoO][\da-fA-F_]+|\d+)\s*\)', executor):
    pass  # These are boundary comparisons, already handled

# Extract T~= else-branch handlers more carefully
for m in re.finditer(r'T\s*~=\s*(0[xXbBoO][\da-fA-F_]+|\d+)\s*then\s*(.*?)else\s*', executor):
    try: val = parse_lua_num(m.group(1))
    except: continue
    # The else branch is the handler for val
    else_start = m.end()
    else_handler = executor[else_start:else_start+500]
    t_ne[val] = else_handler

# Classify handler code - strip anti-analysis junk first
def strip_junk(code):
    """Remove r[X]~=r[Y]/r[X]==r[Y] anti-analysis guards and dead code"""
    # Remove patterns like: if r[N]~=r[M]then ... end;
    # These are always-true or always-false checks
    cleaned = code
    # Remove 'if r[X]~=r[Y]then while...' and 'if r[X]==r[Y]then while...'
    cleaned = re.sub(r'if\s+r\[0?[xXbBoO]?[\da-fA-F_]+\]\s*[~=]=\s*r\[0?[xXbBoO]?[\da-fA-F_]+\]\s*then\s+(?:while[^;]+do[^;]+;(?:return[^;]*;)?end;|return[^;]*;|[^;]+;)+(?:end;)?', '', cleaned)
    # Remove standalone 'else if r[X]...' blocks
    cleaned = re.sub(r'else\s+if\s+r\[0?[xXbBoO]?[\da-fA-F_]+\]\s*[~=]=\s*r\[0?[xXbBoO]?[\da-fA-F_]+\].*?end;', '', cleaned)
    return cleaned.strip()

def classify_handler(handler_code, op_val):
    """Classify a handler code snippet into a Lua operation"""
    h = strip_junk(handler_code)
    if not h:
        return 'JUNK_ONLY'
    
    # GETGLOBAL: s[reg] = <GlobalName>
    gm = re.search(r'\(?\s*s\s*\)?\s*\[\s*(\w+)\s*\[y\]\s*\]\s*=\s*\(?\s*([a-zA-Z_]\w*)\s*\)?;', h[:200])
    if gm:
        reg_var = gm.group(1)
        gname = gm.group(2)
        builtins = {'tostring','tonumber','pcall','xpcall','error','assert','type','typeof',
            'select','unpack','rawset','rawget','rawequal','rawlen','require','next',
            'pairs','ipairs','print','warn','setmetatable','getmetatable',
            'loadstring','collectgarbage','coroutine','string','table','math','bit32',
            'debug','os','io','bit','task','buffer','newproxy',
            'getrenv','getconnections','readfile','writefile','isfile','getgenv','getfenv','setfenv',
            'newcclosure','hookfunction','loadfile','tick','wait','delay','spawn',
            'game','workspace','Enum','Instance','CFrame','Vector3','Vector2','Color3',
            'BrickColor','UDim2','UDim','Ray','Region3','TweenInfo','Font','DateTime',
            'NumberSequence','ColorSequence','NumberRange','Rect','PhysicalProperties',
            'NumberSequenceKeypoint','ColorSequenceKeypoint','OverlapParams','RaycastParams',
            'TweenService','Players','ReplicatedStorage','RunService','StarterGui',
            'UserInputService','Lighting','SoundService','WebSocket','Theme',
            'UtilitiesSecureWait','customerPosition','dec','noclipRan'}
        if gname in builtins or gname[0].isupper():
            return f'GETGLOBAL_{gname}'
    
    # MOVE: s[X[y]] = s[Y[y]]
    if re.search(r'\(?\s*s\s*\)?\s*\[\s*\w+\s*\[y\]\s*\]\s*=\s*\(?\s*s\s*\[(\w+)\[y\]\]\s*\)?;', h[:100]):
        return 'MOVE'
    
    # LOADK from q/w/m (constant operands)
    if re.search(r'\(?\s*s\s*\)?\s*\[\s*\w+\s*\[y\]\s*\]\s*=\s*\(?\s*q\[y\]\s*\)?;', h[:100]):
        return 'LOADK_q'
    if re.search(r'\(?\s*s\s*\)?\s*\[\s*\w+\s*\[y\]\s*\]\s*=\s*\(?\s*w\[y\]\s*\)?;', h[:100]):
        return 'LOADK_w'
    if re.search(r'\(?\s*s\s*\)?\s*\[\s*\w+\s*\[y\]\s*\]\s*=\s*\(?\s*m\[y\]\s*\)?;', h[:100]):
        return 'LOADK_m'
    
    # LOADNIL: s[reg] = nil
    if re.search(r'\(?\s*s\s*\)?\s*\[\s*\w+\s*\[y\]\s*\]\s*=\s*nil', h[:80]):
        return 'LOADNIL'
    
    # LOADBOOL: s[reg] = true/false
    if re.search(r'\(?\s*s\s*\)?\s*\[\s*\w+\s*\[y\]\s*\]\s*=\s*\(?\s*(?:true|false)\s*\)?', h[:80]):
        return 'LOADBOOL'
    
    # NEWTABLE: s[reg] = {}
    if re.search(r'\(?\s*s\s*\)?\s*\[\s*\w+\s*\[y\]\s*\]\s*=\s*\{\s*\}', h[:80]):
        return 'NEWTABLE'
    
    # GETTABLE: s[dst] = s[tbl][s[key]]
    if re.search(r's\[\w+\[y\]\]\s*=\s*\(?s\[\w+\[y\]\]\[s\[\w+\[y\]\]\]\)?', h[:120]):
        return 'GETTABLE'
    # GETTABLE_K: s[dst] = s[tbl][q[y]]
    if re.search(r's\[\w+\[y\]\]\s*=\s*\(?s\[\w+\[y\]\]\[q\[y\]\]\)?', h[:120]):
        return 'GETTABLE_K'
    if re.search(r's\[\w+\[y\]\]\s*=\s*\(?s\[\w+\[y\]\]\[w\[y\]\]\)?', h[:120]):
        return 'GETTABLE_W'
    if re.search(r's\[\w+\[y\]\]\s*=\s*\(?s\[\w+\[y\]\]\[m\[y\]\]\)?', h[:120]):
        return 'GETTABLE_M'
    
    # SETTABLE: s[tbl][s[key]] = s[val]
    if re.search(r's\[\w+\[y\]\]\[s\[\w+\[y\]\]\]\s*=\s*\(?s\[\w+\[y\]\]\)?', h[:120]):
        return 'SETTABLE'
    # SETTABLE_K: s[tbl][q[y]] = s[val]
    if re.search(r'\(?\s*s\[\w+\[y\]\]\s*\)?\s*\[q\[y\]\]\s*=\s*\(?s\[\w+\[y\]\]\)?', h[:120]):
        return 'SETTABLE_K'
    if re.search(r'\(?\s*s\[\w+\[y\]\]\s*\)?\s*\[w\[y\]\]\s*=\s*\(?s\[\w+\[y\]\]\)?', h[:120]):
        return 'SETTABLE_W'
    # SETTABLE_KK: s[tbl][q[y]] = w[y]
    if re.search(r's\[\w+\[y\]\]\[q\[y\]\]\s*=\s*w\[y\]', h[:120]):
        return 'SETTABLE_KK'
    if re.search(r's\[\w+\[y\]\]\[q\[y\]\]\s*=\s*m\[y\]', h[:120]):
        return 'SETTABLE_KM'
    
    # Arithmetic: s[dst] = s[a] op s[b]
    arith_ops = [
        (r'\+', 'ADD'), (r'-', 'SUB'), (r'\*', 'MUL'),
        (r'/', 'DIV'), (r'%', 'MOD'), (r'\^', 'POW'),
    ]
    for regex_op, name in arith_ops:
        if re.search(rf's\[\w+\[y\]\]\s*=\s*\(?s\[\w+\[y\]\]\s*{regex_op}\s*s\[\w+\[y\]\]\)?', h[:120]):
            return name
        if re.search(rf's\[\w+\[y\]\]\s*=\s*\(?s\[\w+\[y\]\]\s*{regex_op}\s*q\[y\]\)?', h[:120]):
            return f'{name}_Kq'
        if re.search(rf's\[\w+\[y\]\]\s*=\s*\(?q\[y\]\s*{regex_op}\s*s\[\w+\[y\]\]\)?', h[:120]):
            return f'{name}_qK'
        if re.search(rf's\[\w+\[y\]\]\s*=\s*\(?s\[\w+\[y\]\]\s*{regex_op}\s*w\[y\]\)?', h[:120]):
            return f'{name}_Kw'
        if re.search(rf's\[\w+\[y\]\]\s*=\s*\(?s\[\w+\[y\]\]\s*{regex_op}\s*m\[y\]\)?', h[:120]):
            return f'{name}_Km'
        if re.search(rf's\[\w+\[y\]\]\s*=\s*\(?w\[y\]\s*{regex_op}\s*s\[\w+\[y\]\]\)?', h[:120]):
            return f'{name}_wK'
        if re.search(rf's\[\w+\[y\]\]\s*=\s*\(?m\[y\]\s*{regex_op}\s*s\[\w+\[y\]\]\)?', h[:120]):
            return f'{name}_mK'
    
    # Arith via r[37] (bit operations or other builtins)
    if re.search(r'r\[(?:0[xX]25|37|0[bB]100101)\]', h[:120]):
        return 'ARITH_BUILTIN'
    
    # CONCAT: s[dst] = s[a] .. s[b]
    if re.search(r's\[\w+\[y\]\]\s*=\s*s\[\w+\[y\]\]\s*\.\.\s*s\[\w+\[y\]\]', h[:120]):
        return 'CONCAT'
    if re.search(r's\[\w+\[y\]\]\s*=\s*s\[\w+\[y\]\]\s*\.\.\s*q\[y\]', h[:120]):
        return 'CONCAT_Kq'
    if re.search(r's\[\w+\[y\]\]\s*=\s*q\[y\]\s*\.\.\s*s\[\w+\[y\]\]', h[:120]):
        return 'CONCAT_qK'
    
    # UNM: s[dst] = -s[src]
    if re.search(r's\[\w+\[y\]\]\s*=\s*\(\s*-s\[\w+\[y\]\]\s*\)', h[:80]):
        return 'UNM'
    
    # NOT: s[dst] = not s[src]
    if re.search(r's\[\w+\[y\]\]\s*=\s*not\s+s\[\w+\[y\]\]', h[:80]):
        return 'NOT'
    
    # LEN: s[dst] = #s[src]
    if re.search(r's\[\w+\[y\]\]\s*=\s*\(?\s*#s\[\w+\[y\]\]\s*\)?', h[:80]):
        return 'LEN'
    
    # Comparison + jump patterns
    cmp_patterns = [
        (r'if\s+s\[\w+\[y\]\]\s*<\s*s\[\w+\[y\]\]\s*then\s+y\s*=', 'LT_JMP'),
        (r'if\s+s\[\w+\[y\]\]\s*<=\s*s\[\w+\[y\]\]\s*then\s+y\s*=', 'LE_JMP'),
        (r'if\s+s\[\w+\[y\]\]\s*==\s*s\[\w+\[y\]\]\s*then\s+y\s*=', 'EQ_JMP'),
        (r'if\s+s\[\w+\[y\]\]\s*~=\s*s\[\w+\[y\]\]\s*then\s+y\s*=', 'NE_JMP'),
        (r'if\s+s\[\w+\[y\]\]\s*>\s*s\[\w+\[y\]\]\s*then\s+y\s*=', 'GT_JMP'),
        (r'if\s+s\[\w+\[y\]\]\s*>=\s*s\[\w+\[y\]\]\s*then\s+y\s*=', 'GE_JMP'),
        (r'if\s+s\[D\[y\]\]\s*~=\s*s\[Z\[y\]\]\s*then.*y\s*=\s*a\[y\]', 'NE_JMP'),
        (r'if\s+not\s+s\[\w+\[y\]\]\s*then\s+y\s*=', 'TEST_FALSE'),
        (r'if\s+s\[\w+\[y\]\]\s*then\s+y\s*=', 'TEST_TRUE'),
        (r'if\s+s\[D\[y\]\]\s*then\s+y\s*=', 'TEST_TRUE'),
        # Comparison with constants + jump
        (r'if\s+s\[\w+\[y\]\]\s*<\s*[qwm]\[y\]\s*then\s+y\s*=', 'LT_K_JMP'),
        (r'if\s+s\[\w+\[y\]\]\s*<=\s*[qwm]\[y\]\s*then\s+y\s*=', 'LE_K_JMP'),
        (r'if\s+s\[\w+\[y\]\]\s*==\s*[qwm]\[y\]\s*then\s+y\s*=', 'EQ_K_JMP'),
        (r'if\s+s\[\w+\[y\]\]\s*~=\s*[qwm]\[y\]\s*then\s+y\s*=', 'NE_K_JMP'),
        (r'if\s+[qwm]\[y\]\s*<\s*s\[\w+\[y\]\]\s*then', 'GT_K_CMP'),
        (r'if\s+not\s*\(\s*not\s*\(\s*s\[\w+\[y\]\]\s*<=\s*[qwm]\[y\]\s*\)\s*\)\s*then\s+else.*y\s*=', 'GT_K_JMP'),
        (r'if\s+not\s*\(\s*[qwm]\[y\]\s*<\s*s\[\w+\[y\]\]\s*\)\s*then\s+else.*y\s*=', 'LE_K_JMP2'),
        (r'if\s+not\s*\(\s*not\s*\(\s*q\[y\]\s*<\s*s\[\w+\[y\]\]', 'GT_K_JMP2'),
    ]
    for pat, name in cmp_patterns:
        if re.search(pat, h[:200]):
            return name
    
    # Comparison result stored (no jump)
    cmp_store = [
        (r's\[\w+\[y\]\]\s*=\s*\(?s\[\w+\[y\]\]\s*>\s*s\[\w+\[y\]\]\)?', 'GT_STORE'),
        (r's\[\w+\[y\]\]\s*=\s*\(?s\[\w+\[y\]\]\s*<\s*s\[\w+\[y\]\]\)?', 'LT_STORE'),
        (r's\[\w+\[y\]\]\s*=\s*\(?s\[\w+\[y\]\]\s*>=\s*s\[\w+\[y\]\]\)?', 'GE_STORE'),
        (r's\[\w+\[y\]\]\s*=\s*\(?s\[\w+\[y\]\]\s*<=\s*s\[\w+\[y\]\]\)?', 'LE_STORE'),
        (r's\[\w+\[y\]\]\s*=\s*\(?s\[\w+\[y\]\]\s*==\s*s\[\w+\[y\]\]\)?', 'EQ_STORE'),
        (r's\[\w+\[y\]\]\s*=\s*\(?s\[\w+\[y\]\]\s*~=\s*s\[\w+\[y\]\]\)?', 'NE_STORE'),
        (r's\[\w+\[y\]\]\s*=\s*s\[\w+\[y\]\]\s*<\s*[qwm]\[y\]', 'LT_K_STORE'),
        (r's\[\w+\[y\]\]\s*=\s*s\[\w+\[y\]\]\s*<=\s*[qwm]\[y\]', 'LE_K_STORE'),
        (r's\[\w+\[y\]\]\s*=\s*s\[\w+\[y\]\]\s*>\s*[qwm]\[y\]', 'GT_K_STORE'),
        (r's\[\w+\[y\]\]\s*=\s*s\[\w+\[y\]\]\s*>=\s*[qwm]\[y\]', 'GE_K_STORE'),
        (r's\[\w+\[y\]\]\s*=\s*s\[\w+\[y\]\]\s*==\s*[qwm]\[y\]', 'EQ_K_STORE'),
        (r's\[\w+\[y\]\]\s*=\s*s\[\w+\[y\]\]\s*~=\s*[qwm]\[y\]', 'NE_K_STORE'),
        (r's\[\w+\[y\]\]\s*=\s*[qwm]\[y\]\s*>\s*[qwm]\[y\]', 'GT_KK_STORE'),
        (r's\[\w+\[y\]\]\s*=\s*[qwm]\[y\]\s*~=\s*[qwm]\[y\]', 'NE_KK_STORE'),
        (r's\[\w+\[y\]\]\s*=\s*q\[y\]\s*<=\s*w\[y\]', 'LE_KK_STORE'),
    ]
    for pat, name in cmp_store:
        if re.search(pat, h[:200]):
            return name
    
    # JMP: y = D[y]
    if re.match(r'\s*y\s*=\s*\(?\s*D\[y\]\s*\)?', h[:40]):
        return 'JMP'
    
    # CALL patterns
    if re.search(r'H\s*=\s*\w+\[y\].*s\[H\]\s*=\s*s\[H\]\(', h[:200]):
        return 'CALL'
    if re.search(r'r\[(?:0[xX]0*1[dD]|29|0[bB]0*11101)\]\(', h[:200]):
        return 'CALL_SPREAD'
    if re.search(r's\[\w+\[y\]\]\s*=\s*s\[\w+\[y\]\]\(\)', h[:120]):
        return 'CALL_0'
    if re.search(r's\[\w+\]\s*=\s*s\[\w+\]\(s\[\w+\+0[bBxX]', h[:120]):
        return 'CALL_1'
    
    # SELF: G = s[tbl]; s[dst] = G[key]; s[dst+1] = G
    if re.search(r'G\s*=\s*\(?s\[\w+\[y\]\]\)?.*s\[\w+\[y\]\]\s*=\s*\(?G\[', h[:200]):
        return 'SELF'
    
    # RETURN
    if re.match(r'\s*return\s', h[:20]):
        return 'RETURN'
    
    # GETUPVAL: s[reg] = W[idx]
    if re.search(r's\[\w+\[y\]\]\s*=\s*W\[\w+\[y\]\]', h[:80]):
        return 'GETUPVAL'
    # SETUPVAL: W[idx] = s[reg]
    if re.search(r'W\[\w+\[y\]\]\s*=\s*s\[\w+\[y\]\]', h[:80]):
        return 'SETUPVAL'
    # GETUPVAL table: W[idx][2][W[idx][1]]
    if re.search(r'W\[\w+\[y\]\].*\[0[bBxX]', h[:120]):
        return 'GETUPVAL_TABLE'
    if re.search(r'H\s*=\s*W\[\w+\[y\]\]', h[:80]):
        return 'GETUPVAL_TABLE'
    
    # SETGLOBAL: r[4][idx] = s[reg]
    if re.search(r'r\[(?:0[xX]4|4|0[bB]100)\]\s*\)\s*\[\w+\[y\]\]\s*=\s*s\[\w+\[y\]\]', h[:120]):
        return 'SETGLOBAL'
    if re.search(r'\(?\s*r\[(?:0[xX]4|4|0[bB]100)\]\s*\)?\s*\[\w+\[y\]\]', h[:120]):
        return 'SETGLOBAL'
    
    # SETUPVAL table write: (W[idx])[key] = val
    if re.search(r'\(?\s*W\[\w+\[y\]\]\s*\)?\s*\[s\[\w+\[y\]\]\]\s*=', h[:120]):
        return 'SETUPVAL_TABLE'
    if re.search(r'\(?\s*W\[\w+\[y\]\]\s*\)?\s*\[\w+\[y\]\]\s*=', h[:120]):
        return 'SETUPVAL_TABLE'
    
    # CLOSURE: function(
    if 'function(' in h[:100]:
        return 'CLOSURE'
    
    # FORLOOP: P+=I, P=P+I
    if re.search(r'P\s*\+\s*=\s*I|P\s*=\s*P\s*\+\s*I', h[:100]):
        return 'FORLOOP'
    # FORPREP
    if re.search(r'P\s*-\s*=\s*I|P\s*=\s*P\s*-\s*I', h[:100]):
        return 'FORPREP'
    
    # TFORLOOP
    if re.search(r'V\s*=\s*\(\s*\{', h[:100]):
        return 'TFORLOOP'
    
    # VARARG: s[reg] = N[idx]
    if re.search(r's\[\w+\[y\]\]\s*=\s*N\[\w+\]', h[:80]):
        return 'VARARG'
    if re.search(r'N\[\w+\]', h[:80]):
        return 'VARARG'
    
    # SETLIST: r[16](s,...) or r[0x10]
    if re.search(r'r\[(?:0[xX]1[0-9a-fA-F]|1[0-9]|0[bB]1\d+)\]\s*\(\s*s', h[:120]):
        return 'SETLIST'
    
    # Table operations with r[16] (table.move)
    if re.search(r'r\[0[xX]1\w*\]\(s', h[:80]):
        return 'TABLE_MOVE'
    
    # Assignment to loop variables
    if re.search(r'K\s*=\s*\(?\s*D\[y\]\s*\)?', h[:60]):
        return 'ASSIGN_OPERAND'
    if re.search(r'F\s*=\s*\(?\s*Z\[y\]\s*\)?;.*k\s*=\s*\(?\s*s\s*\)?', h[:80]):
        return 'PREP_CALL'
    if re.search(r'H\s*=\s*\(?\s*D\[y\]\s*\)?;.*F\s*=\s*\(?\s*a\[y\]\s*\)?', h[:80]):
        return 'RANGE_PREP'
    
    # Check for variable assignments used in multi-step operations
    if re.search(r'H\s*=\s*\(?\s*\w+\[y\]\s*\)?;?\s*F\s*=', h[:80]):
        return 'MULTI_STEP'
    if re.search(r'H\s*=\s*\(?\s*false\s*\)?', h[:40]):
        return 'SET_FALSE'
    
    # SETTABLE via upval: W[idx][key] = val
    if re.search(r'W\[\w+\[y\]\]\)\s*\[', h[:80]):
        return 'SETUPVAL_IDX'
    
    return 'UNKNOWN'

# Classify all T== handlers
opcode_map = {}
for val, handler in t_eq.items():
    cls = classify_handler(handler, val)
    opcode_map[val] = cls

# Classify T~= handlers (else branch)
for val, handler in t_ne.items():
    if val not in opcode_map and handler and not handler.startswith('T~='):
        cls = classify_handler(handler, val)
        opcode_map[val] = f'{cls}(~=)'

# For opcodes NOT found in any T comparison, classify by pattern
all_data_ops = set()
for p in all_protos:
    for op in p.get('C4', []):
        if op is not None: all_data_ops.add(op)

# Heuristic classification for uncovered opcodes
for op in sorted(all_data_ops):
    if op in opcode_map:
        continue
    
    # Use operand pattern and runtime trace
    top_pat = ''
    if op in op_patterns:
        top_pat = max(op_patterns[op].items(), key=lambda x: x[1])[0]
    
    k_pct = op_c2_pct.get(op, 0)
    c2_types = op_c2_types.get(op, {})
    c2_top = max(c2_types.items(), key=lambda x: x[1])[0] if c2_types else ('none', 0)
    
    rt = rt_trace.get(str(op), {})
    q_type = rt.get('q_type', 'nil')
    w_type = rt.get('w_type', 'nil')
    m_type = rt.get('m_type', 'nil')
    
    # Classify by pattern
    if k_pct > 0.9:
        if c2_top[0] == 'string':
            opcode_map[op] = 'GETTABLE_K*'  # likely GETTABLE with string key
        elif c2_top[0] == 'number':
            opcode_map[op] = 'LOADK*'  # likely LOADK or arithmetic with constant
        elif c2_top[0] == 'table':
            opcode_map[op] = 'CONST_TABLE*'
        else:
            opcode_map[op] = 'CONST_LOAD*'
    elif top_pat == 'A___':
        opcode_map[op] = 'REG_A*'  # MOVE, JMP, LOADNIL, or CLOSE
    elif top_pat == '_B__':
        opcode_map[op] = 'REG_B*'  # RETURN, JMP, or CLOSE
    elif top_pat == '__C_':
        opcode_map[op] = 'REG_C*'  # JMP target or SETLIST
    elif top_pat == 'AB__':
        opcode_map[op] = 'REG_AB*'  # MOVE, GETUPVAL, UNM, NOT, LEN
    elif top_pat == 'ABC_':
        opcode_map[op] = 'REG_ABC*'  # ARITH, GETTABLE, CALL, SELF
    elif top_pat == '_BC_':
        opcode_map[op] = 'REG_BC*'  # SETTABLE, TEST
    elif top_pat == 'A_C_':
        opcode_map[op] = 'REG_AC*'  # TEST, TESTSET, TFORLOOP
    elif top_pat == 'ABCK':
        opcode_map[op] = 'REG_ABCK*'
    elif top_pat == 'A_CK':
        opcode_map[op] = 'REG_ACK*'
    elif top_pat == '_BCK':
        opcode_map[op] = 'REG_BCK*'
    elif top_pat == '____':
        opcode_map[op] = 'NO_OPERANDS*'
    else:
        opcode_map[op] = f'PAT_{top_pat}*'

# Print final results
print(f"{'='*100}")
print(f"COMPLETE OPCODE MAP: {len(opcode_map)} opcodes classified")
print(f"{'='*100}")

# Group by classification
from collections import Counter
class_groups = defaultdict(list)
for op, cls in sorted(opcode_map.items()):
    class_groups[cls].append(op)

for cls in sorted(class_groups.keys()):
    ops = class_groups[cls]
    freq = sum(op_freq.get(op, 0) for op in ops)
    ops_str = ', '.join(str(o) for o in sorted(ops)[:15])
    if len(ops) > 15: ops_str += f' ... +{len(ops)-15} more'
    print(f"  {cls:>30s} ({len(ops):3d} ops, {freq:6d} inst): {ops_str}")

# Count classified vs unclassified
classified = sum(1 for c in opcode_map.values() if not c.endswith('*') and c != 'UNKNOWN')
heuristic = sum(1 for c in opcode_map.values() if c.endswith('*'))
unknown = sum(1 for c in opcode_map.values() if c == 'UNKNOWN')
print(f"\nClassified: {classified}, Heuristic: {heuristic}, Unknown: {unknown}")

# Save the complete map
with open('opcode_map_complete.json', 'w') as f:
    json.dump({
        'opcode_map': {str(k): v for k, v in opcode_map.items()},
        'class_groups': {k: sorted(v) for k, v in class_groups.items()},
        'opcode_freq': {str(k): v for k, v in op_freq.items()},
    }, f, indent=1, sort_keys=True)
print(f"Saved to opcode_map_complete.json")

# Map to standard Lua 5.1 operations
print(f"\n{'='*100}")
print(f"MAPPING TO LUA 5.1 OPERATIONS")
print(f"{'='*100}")

lua51_map = {
    'MOVE': ['MOVE'],
    'LOADK': ['LOADK_q', 'LOADK_w', 'LOADK_m', 'LOADK*'],
    'LOADBOOL': ['LOADBOOL', 'SET_FALSE'],
    'LOADNIL': ['LOADNIL'],
    'GETUPVAL': ['GETUPVAL', 'GETUPVAL_TABLE'],
    'GETGLOBAL': [c for c in class_groups if c.startswith('GETGLOBAL_')],
    'GETTABLE': ['GETTABLE', 'GETTABLE_K', 'GETTABLE_W', 'GETTABLE_M', 'GETTABLE_K*'],
    'SETGLOBAL': ['SETGLOBAL'],
    'SETUPVAL': ['SETUPVAL', 'SETUPVAL_TABLE', 'SETUPVAL_IDX'],
    'SETTABLE': ['SETTABLE', 'SETTABLE_K', 'SETTABLE_W', 'SETTABLE_KK', 'SETTABLE_KM'],
    'NEWTABLE': ['NEWTABLE'],
    'SELF': ['SELF'],
    'ADD': ['ADD', 'ADD_Kq', 'ADD_qK', 'ADD_Kw', 'ADD_Km', 'ADD_wK', 'ADD_mK'],
    'SUB': ['SUB', 'SUB_Kq', 'SUB_qK', 'SUB_Kw', 'SUB_Km', 'SUB_wK', 'SUB_mK'],
    'MUL': ['MUL', 'MUL_Kq', 'MUL_Kw'],
    'DIV': ['DIV', 'DIV_Kq', 'DIV_Kw'],
    'MOD': ['MOD'],
    'POW': ['POW', 'POW_Kq', 'POW_Kw'],
    'UNM': ['UNM'],
    'NOT': ['NOT'],
    'LEN': ['LEN'],
    'CONCAT': ['CONCAT', 'CONCAT_Kq', 'CONCAT_qK'],
    'JMP': ['JMP'],
    'EQ': ['EQ_JMP', 'EQ_STORE', 'EQ_K_JMP', 'EQ_K_STORE'],
    'LT': ['LT_JMP', 'LT_STORE', 'LT_K_JMP', 'LT_K_STORE'],
    'LE': ['LE_JMP', 'LE_STORE', 'LE_K_JMP', 'LE_K_STORE', 'LE_K_JMP2', 'LE_KK_STORE'],
    'GT': ['GT_JMP', 'GT_STORE', 'GT_K_JMP', 'GT_K_STORE', 'GT_K_JMP2', 'GT_K_CMP', 'GT_KK_STORE', 'GE_K_CMP'],
    'NE': ['NE_JMP', 'NE_STORE', 'NE_K_JMP', 'NE_K_STORE', 'NE_KK_STORE'],
    'TEST': ['TEST_FALSE', 'TEST_TRUE'],
    'CALL': ['CALL', 'CALL_0', 'CALL_1', 'CALL_SPREAD'],
    'RETURN': ['RETURN'],
    'FORLOOP': ['FORLOOP'],
    'FORPREP': ['FORPREP'],
    'TFORLOOP': ['TFORLOOP'],
    'SETLIST': ['SETLIST', 'TABLE_MOVE'],
    'CLOSURE': ['CLOSURE'],
    'VARARG': ['VARARG'],
    'ARITH_BUILTIN': ['ARITH_BUILTIN'],
}

for lua_op, classifications in lua51_map.items():
    ops = []
    for cls in classifications:
        if cls in class_groups:
            ops.extend(class_groups[cls])
    if ops:
        freq = sum(op_freq.get(op, 0) for op in ops)
        print(f"  {lua_op:>15s}: {len(ops):3d} variants, {freq:6d} instructions")
