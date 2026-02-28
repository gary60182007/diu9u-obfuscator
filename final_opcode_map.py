"""
Build the FINAL comprehensive opcode map by combining:
1. Static T== handler analysis
2. T~= else-branch handler extraction (properly depth-tracked)
3. Runtime delta data
4. Instruction pattern & context analysis
5. Operand pattern heuristics
"""
import re, json, struct
from collections import defaultdict, Counter

def parse_lua_num(s):
    s = s.replace('_', '').strip()
    if s.startswith('0x') or s.startswith('0X'): return int(s, 16)
    elif s.startswith('0b') or s.startswith('0B'): return int(s, 2)
    elif s.startswith('0o') or s.startswith('0O'): return int(s, 8)
    return int(s)

# Load all data
with open('i3_executor_chunk.lua', 'r', encoding='utf-8') as f:
    executor = f.read()
with open('all_protos_data.json', 'r', encoding='utf-8') as f:
    all_protos = json.load(f)
with open('c2_full_data.json', 'r', encoding='utf-8') as f:
    c2_data = json.load(f)
try:
    with open('opcode_combined.json', 'r') as f:
        combined = json.load(f)
    rt_deltas = combined.get('deltas', {})
    rt_cls = combined.get('classifications', {})
except:
    rt_deltas, rt_cls = {}, {}

# Build opcode stats
op_freq = defaultdict(int)
op_patterns = defaultdict(lambda: defaultdict(int))
op_c2_info = defaultdict(lambda: {'count': 0, 'types': defaultdict(int)})
op_context_before = defaultdict(lambda: defaultdict(int))
op_context_after = defaultdict(lambda: defaultdict(int))
op_last_in_proto = defaultdict(int)
op_first_in_proto = defaultdict(int)
op_dest_regs = defaultdict(lambda: defaultdict(int))
op_jmp_targets = defaultdict(list)  # D[y] values that could be jump targets

for p in all_protos:
    pid = str(p['id'])
    opcodes = p.get('C4', [])
    c7 = p.get('C7', [])
    c8 = p.get('C8', [])
    c9 = p.get('C9', [])
    p_c2 = c2_data.get(pid, {})
    n = len(opcodes)
    
    for i, op in enumerate(opcodes):
        if op is None: continue
        op_freq[op] += 1
        
        a_val = c7[i] if i < len(c7) else 0
        b_val = c8[i] if i < len(c8) else 0
        c_val = c9[i] if i < len(c9) else 0
        has_k = str(i+1) in p_c2
        
        pat = ''
        pat += 'A' if (a_val is not None and a_val != 0) else '_'
        pat += 'B' if (b_val is not None and b_val != 0) else '_'
        pat += 'C' if (c_val is not None and c_val != 0) else '_'
        pat += 'K' if has_k else '_'
        op_patterns[op][pat] += 1
        
        if has_k:
            entry = p_c2[str(i+1)]
            if entry.startswith('n:'): op_c2_info[op]['types']['number'] += 1
            elif entry.startswith('s:'): op_c2_info[op]['types']['string'] += 1
            elif entry.startswith('t:'): op_c2_info[op]['types']['table'] += 1
            else: op_c2_info[op]['types']['other'] += 1
            op_c2_info[op]['count'] += 1
        
        op_dest_regs[op][a_val or 0] += 1
        
        if i > 0 and opcodes[i-1] is not None:
            op_context_before[op][opcodes[i-1]] += 1
        if i < n-1 and opcodes[i+1] is not None:
            op_context_after[op][opcodes[i+1]] += 1
        
        if i == n - 1: op_last_in_proto[op] += 1
        if i == 0: op_first_in_proto[op] += 1
        
        # Check if D[y] could be a valid jump target
        if a_val is not None and 0 < a_val <= n:
            op_jmp_targets[op].append(a_val)

# Find T== and T~= handlers in executor with proper depth tracking
def find_else_handler(source, after_then_pos, max_search=10000):
    """Find the else branch handler after a then block, tracking depth properly."""
    i = 0
    depth = 1
    text = source[after_then_pos:after_then_pos + max_search]
    in_string = False
    str_char = None
    
    while i < len(text):
        c = text[i]
        
        # Handle strings
        if not in_string and (c == '"' or c == "'"):
            in_string = True
            str_char = c
            i += 1
            continue
        if in_string:
            if c == '\\':
                i += 2
                continue
            if c == str_char:
                in_string = False
            i += 1
            continue
        
        # Handle long strings [[...]]
        if c == '[' and i + 1 < len(text) and text[i+1] == '[':
            end = text.find(']]', i + 2)
            if end >= 0:
                i = end + 2
                continue
        
        # Check for keywords
        if c.isalpha() or c == '_':
            j = i
            while j < len(text) and (text[j].isalnum() or text[j] == '_'):
                j += 1
            word = text[i:j]
            
            if word in ('if', 'function', 'for', 'while', 'repeat'):
                depth += 1
            elif word == 'do':
                # 'do' only increases depth if not preceded by 'while' or 'for'
                # In minified code, this is tricky; just increase depth
                depth += 1
            elif word == 'until':
                depth -= 1
            elif word == 'end':
                depth -= 1
                if depth <= 0:
                    return None  # Reached end without finding else
            elif word == 'else' and depth == 1:
                return text[j:j+500]
            elif word == 'elseif' and depth == 1:
                return text[i:i+500]
            
            i = j
        else:
            i += 1
    
    return None

# Extract all T comparisons
t_eq_handlers = {}  # opcode -> handler code
t_ne_handlers = {}  # opcode -> handler code (from else branch)

for m in re.finditer(r'(?:if\s+|elseif\s+)T\s*(==|~=)\s*(0[xXbBoO][\da-fA-F_]+|\d+)\s*then\b', executor):
    try: val = parse_lua_num(m.group(2))
    except: continue
    op_type = m.group(1)
    handler_start = m.end()
    
    if op_type == '==':
        if val not in t_eq_handlers:
            t_eq_handlers[val] = executor[handler_start:handler_start+600]
    else:
        # T~=val: else branch is the handler for val
        if val not in t_ne_handlers:
            else_handler = find_else_handler(executor, handler_start)
            if else_handler:
                t_ne_handlers[val] = else_handler

# Also handle: not(T==X) and not(T~=X)
for m in re.finditer(r'not\s*\(\s*T\s*(==|~=)\s*(0[xXbBoO][\da-fA-F_]+|\d+)\s*\)\s*then\b', executor):
    try: val = parse_lua_num(m.group(2))
    except: continue
    op_type = m.group(1)
    handler_start = m.end()
    
    if op_type == '==':
        # not(T==X) is same as T~=X: else branch is handler for X
        if val not in t_ne_handlers:
            else_handler = find_else_handler(executor, handler_start)
            if else_handler:
                t_ne_handlers[val] = else_handler
    else:
        # not(T~=X) is same as T==X: then branch is handler for X
        if val not in t_eq_handlers:
            t_eq_handlers[val] = executor[handler_start:handler_start+600]

print(f"T== handlers: {len(t_eq_handlers)}")
print(f"T~= handlers: {len(t_ne_handlers)}")

# Comprehensive classifier
def classify_handler(code, op_val):
    h = code.strip()
    if not h: return 'EMPTY'
    
    # GETGLOBAL: s[reg] = <GlobalName>
    gm = re.search(r's\s*\)?\s*\[\s*(\w+)\s*\[y\]\s*\]\s*=\s*\(?\s*([A-Za-z_]\w*)\s*\)?;', h[:250])
    if gm:
        gname = gm.group(2)
        if gname not in ('s', 'q', 'w', 'm', 'D', 'a', 'Z', 'Y', 'y', 'H', 'k', 'x', 'n', 'b', 'F', 'K',
                          'G', 'true', 'false', 'nil', 'not', 'and', 'or', 'type', 'end'):
            return f'GETGLOBAL({gname})'
    
    # MOVE: s[X[y]] = s[Y[y]]
    if re.search(r's\)?\s*\[\s*\w+\[y\]\s*\]\s*=\s*\(?\s*s\s*\[\s*\w+\[y\]\s*\]\s*\)?;', h[:120]):
        # Check it's not GETTABLE (s[x] = s[y][z])
        if not re.search(r's\[\w+\[y\]\]\[', h[:120]):
            return 'MOVE'
    
    # LOADK
    for const_var, suffix in [('q', 'q'), ('w', 'w'), ('m', 'm')]:
        if re.search(rf's\)?\s*\[\s*\w+\[y\]\s*\]\s*=\s*\(?\s*{const_var}\s*\[y\]\s*\)?;', h[:100]):
            return f'LOADK_{suffix}'
    
    # LOADNIL
    if re.search(r's\)?\s*\[\s*\w+\[y\]\s*\]\s*=\s*nil', h[:80]):
        return 'LOADNIL'
    
    # LOADBOOL
    if re.search(r's\)?\s*\[\s*\w+\[y\]\s*\]\s*=\s*\(?\s*true\s*\)?', h[:80]):
        return 'LOADBOOL_TRUE'
    if re.search(r's\)?\s*\[\s*\w+\[y\]\s*\]\s*=\s*\(?\s*false\s*\)?', h[:80]):
        return 'LOADBOOL_FALSE'
    
    # NEWTABLE
    if re.search(r's\)?\s*\[\s*\w+\[y\]\s*\]\s*=\s*\{\s*\}', h[:80]):
        return 'NEWTABLE'
    
    # GETTABLE variants: s[dst] = s[tbl][key]
    for key_src, suffix in [('s[\\w+\\[y\\]]', ''), ('q\\[y\\]', '_Kq'), ('w\\[y\\]', '_Kw'), ('m\\[y\\]', '_Km')]:
        if re.search(rf's\[\w+\[y\]\]\s*=\s*\(?s\[\w+\[y\]\]\[{key_src}\]\)?', h[:150]):
            return f'GETTABLE{suffix}'
    
    # SETTABLE variants: s[tbl][key] = val
    for key_src, val_src, suffix in [
        ('s[\\w+\\[y\\]]', 's[\\w+\\[y\\]]', ''),
        ('q\\[y\\]', 's[\\w+\\[y\\]]', '_Kq'),
        ('w\\[y\\]', 's[\\w+\\[y\\]]', '_Kw'),
        ('m\\[y\\]', 's[\\w+\\[y\\]]', '_Km'),
        ('q\\[y\\]', 'q\\[y\\]', '_KqKq'),
        ('q\\[y\\]', 'w\\[y\\]', '_KqKw'),
        ('q\\[y\\]', 'm\\[y\\]', '_KqKm'),
        ('w\\[y\\]', 'q\\[y\\]', '_KwKq'),
        ('s[\\w+\\[y\\]]', 'q\\[y\\]', '_Vq'),
        ('s[\\w+\\[y\\]]', 'w\\[y\\]', '_Vw'),
        ('s[\\w+\\[y\\]]', 'm\\[y\\]', '_Vm'),
    ]:
        if re.search(rf's\[\w+\[y\]\]\[{key_src}\]\s*=\s*\(?{val_src}\)?', h[:200]):
            return f'SETTABLE{suffix}'
    # SETTABLE with constant key and value from table: s[D[y]][q[y]] = true/false/nil/number
    if re.search(r's\[\w+\[y\]\]\[q\[y\]\]\s*=\s*(?:true|false)', h[:150]):
        return 'SETTABLE_Kq_BOOL'
    if re.search(r's\[\w+\[y\]\]\[q\[y\]\]\s*=\s*nil', h[:150]):
        return 'SETTABLE_Kq_NIL'
    
    # Arithmetic
    arith_ops = [(r'\+', 'ADD'), (r'\s-\s', 'SUB'), (r'\*', 'MUL'), (r'/', 'DIV'), (r'%', 'MOD'), (r'\^', 'POW')]
    for regex_op, name in arith_ops:
        for l, r_src, suffix in [
            ('s[\\w+\\[y\\]]', 's[\\w+\\[y\\]]', ''),
            ('s[\\w+\\[y\\]]', 'q\\[y\\]', '_Kq'), ('q\\[y\\]', 's[\\w+\\[y\\]]', '_qK'),
            ('s[\\w+\\[y\\]]', 'w\\[y\\]', '_Kw'), ('w\\[y\\]', 's[\\w+\\[y\\]]', '_wK'),
            ('s[\\w+\\[y\\]]', 'm\\[y\\]', '_Km'), ('m\\[y\\]', 's[\\w+\\[y\\]]', '_mK'),
        ]:
            if re.search(rf's\[\w+\[y\]\]\s*=\s*\(?{l}{regex_op}{r_src}\)?', h[:200]):
                return f'{name}{suffix}'
    
    # CONCAT
    if re.search(r's\[\w+\[y\]\]\s*=\s*s\[\w+\[y\]\]\s*\.\.\s*s\[\w+\[y\]\]', h[:150]):
        return 'CONCAT'
    for v, suffix in [('q', '_Kq'), ('w', '_Kw')]:
        if re.search(rf's\[\w+\[y\]\]\s*=\s*s\[\w+\[y\]\]\s*\.\.\s*{v}\[y\]', h[:150]):
            return f'CONCAT{suffix}'
        if re.search(rf's\[\w+\[y\]\]\s*=\s*{v}\[y\]\s*\.\.\s*s\[\w+\[y\]\]', h[:150]):
            return f'CONCAT{suffix}R'
    
    # UNM, NOT, LEN
    if re.search(r's\[\w+\[y\]\]\s*=\s*\(?\s*-\s*s\[\w+\[y\]\]\s*\)?', h[:100]):
        return 'UNM'
    if re.search(r's\[\w+\[y\]\]\s*=\s*not\s+s\[\w+\[y\]\]', h[:100]):
        return 'NOT'
    if re.search(r's\[\w+\[y\]\]\s*=\s*\(?\s*#\s*s\[\w+\[y\]\]\s*\)?', h[:100]):
        return 'LEN'
    
    # Comparison + jump: if s[x] <op> s[y] then y=target
    cmp_jmp = [
        (r'if\s+s\[\w+\[y\]\]\s*==\s*s\[\w+\[y\]\]\s*then', 'EQ_JMP'),
        (r'if\s+s\[\w+\[y\]\]\s*~=\s*s\[\w+\[y\]\]\s*then', 'NE_JMP'),
        (r'if\s+s\[\w+\[y\]\]\s*<\s*s\[\w+\[y\]\]\s*then', 'LT_JMP'),
        (r'if\s+s\[\w+\[y\]\]\s*<=\s*s\[\w+\[y\]\]\s*then', 'LE_JMP'),
        (r'if\s+s\[\w+\[y\]\]\s*>\s*s\[\w+\[y\]\]\s*then', 'GT_JMP'),
        (r'if\s+s\[\w+\[y\]\]\s*>=\s*s\[\w+\[y\]\]\s*then', 'GE_JMP'),
        (r'if\s+s\[D\[y\]\]\s*~=\s*s\[Z\[y\]\]', 'NE_JMP'),
        (r'if\s+s\[D\[y\]\]\s*==\s*s\[Z\[y\]\]', 'EQ_JMP'),
        # Comparison with constants
        (r'if\s+s\[\w+\[y\]\]\s*==\s*[qwm]\[y\]', 'EQ_K_JMP'),
        (r'if\s+s\[\w+\[y\]\]\s*~=\s*[qwm]\[y\]', 'NE_K_JMP'),
        (r'if\s+s\[\w+\[y\]\]\s*<\s*[qwm]\[y\]', 'LT_K_JMP'),
        (r'if\s+s\[\w+\[y\]\]\s*<=\s*[qwm]\[y\]', 'LE_K_JMP'),
        (r'if\s+s\[\w+\[y\]\]\s*>\s*[qwm]\[y\]', 'GT_K_JMP'),
        (r'if\s+s\[\w+\[y\]\]\s*>=\s*[qwm]\[y\]', 'GE_K_JMP'),
        (r'if\s+[qwm]\[y\]\s*<\s*s\[\w+\[y\]\]', 'GT_K_JMP'),
        (r'if\s+[qwm]\[y\]\s*<=\s*s\[\w+\[y\]\]', 'GE_K_JMP'),
        # Negated comparisons
        (r'if\s+not\s*\(\s*s\[\w+\[y\]\]\s*<=\s*s\[\w+\[y\]\]\s*\)', 'GT_JMP'),
        (r'if\s+not\s*\(\s*s\[\w+\[y\]\]\s*<\s*s\[\w+\[y\]\]\s*\)', 'GE_JMP'),
        (r'if\s+not\s*\(\s*s\[\w+\[y\]\]\s*<=\s*[qwm]\[y\]\s*\)', 'GT_K_JMP'),
        (r'if\s+not\s*\(\s*[qwm]\[y\]\s*<\s*s\[\w+\[y\]\]\s*\)', 'LE_K_JMP'),
        (r'if\s+not\s*\(\s*not\s*\(\s*s\[\w+\[y\]\]\s*<=\s*[qwm]\[y\]', 'LE_K_JMP'),
        (r'if\s+not\s*\(\s*not\s*\(\s*[qwm]\[y\]\s*<\s*s\[\w+\[y\]\]', 'GE_K_JMP'),
        # Test operations
        (r'if\s+not\s+s\[\w+\[y\]\]\s*then.*y\s*=', 'TEST_FALSE'),
        (r'if\s+s\[\w+\[y\]\]\s*then.*y\s*=', 'TEST_TRUE'),
        (r'if\s+s\[D\[y\]\]\s*then.*y\s*=', 'TEST_TRUE'),
        (r'if\s+not\s+s\[D\[y\]\]\s*then.*y\s*=', 'TEST_FALSE'),
        # Nil check
        (r'if\s+s\[\w+\[y\]\]\s*==\s*nil\s*then.*y\s*=', 'TEST_NIL'),
        (r'if\s+s\[\w+\[y\]\]\s*~=\s*nil\s*then.*y\s*=', 'TEST_NOT_NIL'),
    ]
    for pat, name in cmp_jmp:
        if re.search(pat, h[:300]):
            return name
    
    # Comparison store (result stored in register)
    cmp_store = [
        (r's\[\w+\[y\]\]\s*=\s*\(?s\[\w+\[y\]\]\s*==\s*s\[\w+\[y\]\]\)?', 'EQ_STORE'),
        (r's\[\w+\[y\]\]\s*=\s*\(?s\[\w+\[y\]\]\s*~=\s*s\[\w+\[y\]\]\)?', 'NE_STORE'),
        (r's\[\w+\[y\]\]\s*=\s*\(?s\[\w+\[y\]\]\s*<\s*s\[\w+\[y\]\]\)?', 'LT_STORE'),
        (r's\[\w+\[y\]\]\s*=\s*\(?s\[\w+\[y\]\]\s*<=\s*s\[\w+\[y\]\]\)?', 'LE_STORE'),
        (r's\[\w+\[y\]\]\s*=\s*\(?s\[\w+\[y\]\]\s*>\s*s\[\w+\[y\]\]\)?', 'GT_STORE'),
        (r's\[\w+\[y\]\]\s*=\s*\(?s\[\w+\[y\]\]\s*>=\s*s\[\w+\[y\]\]\)?', 'GE_STORE'),
        (r's\[\w+\[y\]\]\s*=\s*s\[\w+\[y\]\]\s*==\s*[qwm]\[y\]', 'EQ_K_STORE'),
        (r's\[\w+\[y\]\]\s*=\s*s\[\w+\[y\]\]\s*~=\s*[qwm]\[y\]', 'NE_K_STORE'),
        (r's\[\w+\[y\]\]\s*=\s*s\[\w+\[y\]\]\s*<\s*[qwm]\[y\]', 'LT_K_STORE'),
        (r's\[\w+\[y\]\]\s*=\s*s\[\w+\[y\]\]\s*<=\s*[qwm]\[y\]', 'LE_K_STORE'),
        (r's\[\w+\[y\]\]\s*=\s*s\[\w+\[y\]\]\s*>\s*[qwm]\[y\]', 'GT_K_STORE'),
        (r's\[\w+\[y\]\]\s*=\s*s\[\w+\[y\]\]\s*>=\s*[qwm]\[y\]', 'GE_K_STORE'),
        (r's\[\w+\[y\]\]\s*=\s*[qwm]\[y\]\s*[<>=~]+\s*[qwm]\[y\]', 'CMP_KK_STORE'),
    ]
    for pat, name in cmp_store:
        if re.search(pat, h[:250]):
            return name
    
    # JMP: y = D[y] or y = a[y] or y = Z[y]
    if re.match(r'\s*y\s*=\s*\(?\s*[DaZ]\[y\]\s*\)?;', h[:40]):
        return 'JMP'
    
    # CALL patterns
    if re.search(r'H\s*=\s*\w+\[y\].*F\s*=.*k\s*=.*s\[H\]\s*=\s*s\[H\]', h[:400]):
        return 'CALL'
    if re.search(r'H\s*=\s*\w+\[y\].*s\[H\]\s*=\s*s\[H\]\s*\(', h[:300]):
        return 'CALL'
    if re.search(r'r\[(?:0[xX]1[dD]|29|0[bB]\d+)\]\(', h[:300]):
        return 'CALL_SPREAD'
    if re.search(r's\[\w+\[y\]\]\s*=\s*s\[\w+\[y\]\]\s*\(\s*\)', h[:150]):
        return 'CALL_0ARG'
    if re.search(r's\[\w+\]\s*=\s*s\[\w+\]\s*\(s\[', h[:150]):
        return 'CALL_ARGS'
    
    # SELF: G=s[tbl]; s[dst+1]=G; s[dst]=G[key]
    if re.search(r'G\s*=\s*\(?s\[\w+\[y\]\]\)?', h[:200]) and re.search(r's\[\w+\[y\]\]\s*=.*G\[', h[:300]):
        return 'SELF'
    if re.search(r'G\s*=\s*\(?s\[\w+\[y\]\]\)?.*G\[', h[:300]):
        return 'SELF'
    
    # RETURN
    if re.match(r'\s*return\s', h[:20]):
        return 'RETURN'
    if re.search(r'return\s+s\[\w+\[y\]\]', h[:150]):
        return 'RETURN_VAL'
    
    # GETUPVAL / SETUPVAL
    if re.search(r's\[\w+\[y\]\]\s*=\s*W\[\w+\[y\]\]', h[:100]):
        return 'GETUPVAL'
    if re.search(r'W\[\w+\[y\]\]\s*=\s*s\[\w+\[y\]\]', h[:100]):
        return 'SETUPVAL'
    if re.search(r'H\s*=\s*W\[\w+\[y\]\]', h[:100]):
        if re.search(r's\[\w+\[y\]\]\s*=\s*\(?H\[', h[:200]):
            return 'GETUPVAL_TBL_GET'
        if re.search(r'H\[.*\]\s*=\s*s\[\w+\[y\]\]', h[:200]):
            return 'SETUPVAL_TBL_SET'
        return 'UPVAL_ACCESS'
    if re.search(r'W\[\w+\[y\]\]\[', h[:100]) or re.search(r'\(W\[\w+\[y\]\]\)', h[:100]):
        return 'UPVAL_TABLE_OP'
    
    # SETGLOBAL
    if re.search(r'r\[(?:0[xX]4|4|0[bB]100)\]', h[:100]):
        return 'SETGLOBAL'
    
    # CLOSURE
    if re.search(r'function\s*\(', h[:150]):
        return 'CLOSURE'
    
    # FORLOOP / FORPREP
    if re.search(r'P\s*[+=]', h[:100]) or re.search(r'P\s*=\s*P\s*\+', h[:100]):
        return 'FORLOOP'
    if re.search(r'P\s*=\s*P\s*-', h[:100]) or re.search(r'P\s*-=', h[:100]):
        return 'FORPREP'
    
    # TFORLOOP
    if re.search(r'V\s*=\s*\(?\s*\{', h[:100]):
        return 'TFORLOOP'
    
    # VARARG
    if re.search(r'N\[', h[:100]):
        return 'VARARG'
    
    # SETLIST
    if re.search(r'r\[(?:0[xX]10|16|0[bB]10000)\]', h[:100]):
        return 'SETLIST'
    
    # Multi-step operations (CALL setup, RETURN setup, etc.)
    if re.search(r'H\s*=\s*\w+\[y\].*F\s*=.*k\s*=', h[:150]):
        return 'CALL_SETUP'
    if re.search(r'H\s*=\s*\(?\s*D\[y\]\s*\)?\s*;?\s*F\s*=', h[:100]):
        return 'RANGE_SETUP'
    if re.search(r'K\s*=\s*\(?\s*D\[y\]\s*\)?', h[:60]):
        return 'ASSIGN_K'
    
    # ARITH_BUILTIN (using r[37])
    if re.search(r'r\[(?:0[xX]25|37|0[bB]100101)\]', h[:150]):
        return 'ARITH_BUILTIN'
    
    # Anti-analysis junk: check if handler ONLY contains r[X] comparisons
    stripped = re.sub(r'if\s+r\[\w+\]\s*[~=]=\s*r\[\w+\]\s*then\s+.*?(?:end;|return[^;]*;)', '', h[:400])
    stripped = stripped.strip()
    if not stripped or stripped == ';':
        return 'JUNK'
    
    return 'UNKNOWN'

# Build final map
final_map = {}
handler_sources = {}

# Phase 1: T== handlers
for val, handler in t_eq_handlers.items():
    cls = classify_handler(handler, val)
    if cls != 'UNKNOWN':
        final_map[val] = cls
        handler_sources[val] = 'T=='

# Phase 2: T~= else-branch handlers (only if not already classified)
for val, handler in t_ne_handlers.items():
    if val not in final_map or final_map[val] == 'UNKNOWN':
        cls = classify_handler(handler, val)
        if cls != 'UNKNOWN':
            final_map[val] = cls
            handler_sources[val] = 'T~='

# Phase 3: Instruction context analysis for remaining unclassified
all_used_ops = set()
for p in all_protos:
    for op in p.get('C4', []):
        if op is not None: all_used_ops.add(op)

for op in sorted(all_used_ops):
    if op in final_map and final_map[op] != 'UNKNOWN':
        continue
    
    freq = op_freq[op]
    top_pat = max(op_patterns[op].items(), key=lambda x: x[1])[0] if op_patterns[op] else '____'
    c2_info = op_c2_info.get(op, {'count': 0, 'types': {}})
    k_pct = c2_info['count'] / freq if freq > 0 else 0
    c2_types = c2_info['types']
    c2_top = max(c2_types.items(), key=lambda x: x[1])[0] if c2_types else ('none', 0)
    
    rt_delta = rt_deltas.get(str(op))
    rt_class = rt_cls.get(str(op), '')
    
    is_last = op_last_in_proto.get(op, 0)
    is_first = op_first_in_proto.get(op, 0)
    
    # Context-based classification
    if is_last > 0 and is_last >= freq * 0.3:
        final_map[op] = 'RETURN'
        handler_sources[op] = 'context(last_in_proto)'
        continue
    
    # Use runtime delta if available
    if rt_delta:
        bd = rt_delta.get('before_D', 'nil')[:3]
        ba = rt_delta.get('before_A', 'nil')[:3]
        bz = rt_delta.get('before_Z', 'nil')[:3]
        ad = rt_delta.get('after_D', 'nil')[:3]
        aa = rt_delta.get('after_A', 'nil')[:3]
        az = rt_delta.get('after_Z', 'nil')[:3]
        qt = rt_delta.get('q_type', 'nil')[:3]
        wt = rt_delta.get('w_type', 'nil')[:3]
        mt = rt_delta.get('m_type', 'nil')[:3]
        
        d_ch = bd != ad
        a_ch = ba != aa
        z_ch = bz != az
        
        if d_ch and ad == 'num' and qt == 'num':
            final_map[op] = 'LOADK'
            handler_sources[op] = 'delta+const'
            continue
        elif d_ch and ad == 'str' and qt == 'str':
            final_map[op] = 'LOADK_STR'
            handler_sources[op] = 'delta+const'
            continue
        elif d_ch and ad == 'nil':
            final_map[op] = 'LOADNIL'
            handler_sources[op] = 'delta'
            continue
        elif d_ch and ad == 'tab' and bd != 'tab':
            final_map[op] = 'NEWTABLE'
            handler_sources[op] = 'delta'
            continue
        elif d_ch and ad == 'fun':
            final_map[op] = 'CLOSURE_OR_GETGLOBAL'
            handler_sources[op] = 'delta'
            continue
        elif d_ch and ad == 'boo':
            final_map[op] = 'LOADBOOL_OR_CMP'
            handler_sources[op] = 'delta'
            continue
        elif a_ch and aa == 'tab' and qt == 'str':
            final_map[op] = 'GETTABLE_K_STR'
            handler_sources[op] = 'delta+const'
            continue
    
    # Use operand pattern + constant type
    if k_pct > 0.8:
        if c2_top[0] == 'string':
            final_map[op] = 'GETTABLE_K_STR?'
        elif c2_top[0] == 'number':
            final_map[op] = 'LOADK_NUM?'
        elif c2_top[0] == 'table':
            final_map[op] = 'CONST_TABLE?'
        else:
            final_map[op] = 'CONST_OP?'
        handler_sources[op] = 'pattern+const'
    elif top_pat == 'A___':
        final_map[op] = 'REG_A_OP?'
        handler_sources[op] = 'pattern'
    elif top_pat == 'AB__':
        final_map[op] = 'REG_AB_OP?'
        handler_sources[op] = 'pattern'
    elif top_pat == 'ABC_':
        final_map[op] = 'REG_ABC_OP?'
        handler_sources[op] = 'pattern'
    elif top_pat == '_BC_':
        final_map[op] = 'REG_BC_OP?'
        handler_sources[op] = 'pattern'
    elif top_pat == 'A_C_':
        final_map[op] = 'REG_AC_OP?'
        handler_sources[op] = 'pattern'
    elif top_pat == '____':
        final_map[op] = 'NO_OPS?'
        handler_sources[op] = 'pattern'
    else:
        final_map[op] = f'PAT_{top_pat}?'
        handler_sources[op] = 'pattern'

# Print comprehensive results
print(f"\n{'='*110}")
print(f"FINAL OPCODE MAP: {len(final_map)} opcodes")
print(f"{'='*110}")

# Group by classification for summary
class_groups = defaultdict(list)
for op, cls in sorted(final_map.items()):
    class_groups[cls].append(op)

# Normalize classifications to Lua 5.1 categories
lua51_categories = {
    'LOAD': [],
    'TABLE_GET': [],
    'TABLE_SET': [],
    'GLOBAL_GET': [],
    'GLOBAL_SET': [],
    'UPVAL': [],
    'ARITH': [],
    'CMP_JMP': [],
    'CMP_STORE': [],
    'CONTROL': [],
    'CALL': [],
    'MISC': [],
    'UNKNOWN': [],
}

for cls, ops in sorted(class_groups.items()):
    freq = sum(op_freq.get(op, 0) for op in ops)
    ops_str = ', '.join(str(o) for o in sorted(ops)[:12])
    if len(ops) > 12: ops_str += f' +{len(ops)-12}'
    print(f"  {cls:>30s} ({len(ops):3d} ops, {freq:6d} inst): {ops_str}")
    
    # Categorize
    cl = cls.upper()
    if 'GETGLOBAL' in cl: lua51_categories['GLOBAL_GET'].extend(ops)
    elif 'SETGLOBAL' in cl: lua51_categories['GLOBAL_SET'].extend(ops)
    elif 'GETTABLE' in cl: lua51_categories['TABLE_GET'].extend(ops)
    elif 'SETTABLE' in cl: lua51_categories['TABLE_SET'].extend(ops)
    elif 'LOADK' in cl or 'LOADNIL' in cl or 'LOADBOOL' in cl or 'NEWTABLE' in cl or 'MOVE' in cl:
        lua51_categories['LOAD'].extend(ops)
    elif 'UPVAL' in cl: lua51_categories['UPVAL'].extend(ops)
    elif any(x in cl for x in ['ADD', 'SUB', 'MUL', 'DIV', 'MOD', 'POW', 'UNM', 'NOT', 'LEN', 'CONCAT', 'ARITH']):
        lua51_categories['ARITH'].extend(ops)
    elif '_JMP' in cl or 'TEST' in cl: lua51_categories['CMP_JMP'].extend(ops)
    elif '_STORE' in cl: lua51_categories['CMP_STORE'].extend(ops)
    elif any(x in cl for x in ['JMP', 'RETURN', 'FORLOOP', 'FORPREP', 'TFORLOOP', 'CLOSURE', 'VARARG', 'SETLIST', 'JUNK', 'ASSIGN']):
        lua51_categories['CONTROL'].extend(ops)
    elif 'CALL' in cl or 'SELF' in cl: lua51_categories['CALL'].extend(ops)
    elif '?' in cl or 'UNKNOWN' in cl or 'EMPTY' in cl or 'REG_' in cl or 'PAT_' in cl or 'NO_OPS' in cl:
        lua51_categories['UNKNOWN'].extend(ops)
    else: lua51_categories['MISC'].extend(ops)

print(f"\n{'='*110}")
print(f"LUA 5.1 CATEGORY SUMMARY")
print(f"{'='*110}")
for cat, ops in sorted(lua51_categories.items()):
    freq = sum(op_freq.get(op, 0) for op in ops)
    print(f"  {cat:>15s}: {len(ops):3d} ops, {freq:6d} inst")

confirmed = sum(1 for v in final_map.values() if '?' not in v and v != 'UNKNOWN' and v != 'EMPTY')
uncertain = sum(1 for v in final_map.values() if '?' in v)
unknown = sum(1 for v in final_map.values() if v in ('UNKNOWN', 'EMPTY'))
print(f"\nConfirmed: {confirmed}, Uncertain: {uncertain}, Unknown: {unknown}")
print(f"Coverage: {len(final_map)}/{len(all_used_ops)} used opcodes")

# Save
save_data = {
    'final_map': {str(k): v for k, v in final_map.items()},
    'handler_sources': {str(k): v for k, v in handler_sources.items()},
    'lua51_categories': {k: sorted(v) for k, v in lua51_categories.items()},
    'opcode_freq': {str(k): v for k, v in op_freq.items()},
    'class_groups': {k: sorted(v) for k, v in class_groups.items()},
}
with open('opcode_map_final.json', 'w') as f:
    json.dump(save_data, f, indent=1, sort_keys=True)
print(f"\nSaved to opcode_map_final.json")
