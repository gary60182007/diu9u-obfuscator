"""
Simulate the binary search dispatch tree for EVERY opcode value.
For each target opcode V, trace through the T comparisons to find the handler.
Uses proper depth tracking to skip then/else branches.
"""
import re, json
from collections import defaultdict

def parse_lua_num(s):
    s = s.replace('_', '').strip()
    if s.startswith('0x') or s.startswith('0X'): return int(s, 16)
    elif s.startswith('0b') or s.startswith('0B'): return int(s, 2)
    elif s.startswith('0o') or s.startswith('0O'): return int(s, 8)
    return int(s)

with open('i3_executor_chunk.lua', 'r', encoding='utf-8') as f:
    executor = f.read()

# Build a list of all relevant tokens with positions
# We need: if, then, else, elseif, end, function, for, while, do, repeat, until
# Plus T comparisons

def tokenize_executor(text):
    """Tokenize executor for keyword and T-comparison tracking."""
    tokens = []
    i = 0
    n = len(text)
    
    while i < n:
        c = text[i]
        
        # Skip strings
        if c in ('"', "'"):
            q = c
            i += 1
            while i < n and text[i] != q:
                if text[i] == '\\': i += 1
                i += 1
            i += 1
            continue
        
        # Skip long strings
        if c == '[' and i + 1 < n and text[i+1] == '[':
            end = text.find(']]', i + 2)
            if end >= 0:
                i = end + 2
                continue
        
        # Skip comments
        if c == '-' and i + 1 < n and text[i+1] == '-':
            if i + 2 < n and text[i+2] == '[' and i + 3 < n and text[i+3] == '[':
                end = text.find(']]', i + 4)
                i = end + 2 if end >= 0 else n
            else:
                end = text.find('\n', i)
                i = end + 1 if end >= 0 else n
            continue
        
        # Identifiers and keywords
        if c.isalpha() or c == '_':
            j = i
            while j < n and (text[j].isalnum() or text[j] == '_'):
                j += 1
            word = text[i:j]
            
            if word in ('if', 'then', 'else', 'elseif', 'end', 'function',
                        'for', 'while', 'do', 'repeat', 'until', 'return', 'not'):
                tokens.append((i, word))
            elif word == 'T':
                # Check for T comparison
                k = j
                while k < n and text[k] == ' ': k += 1
                op = ''
                if k < n:
                    if text[k:k+2] == '>=': op = '>='
                    elif text[k:k+2] == '~=': op = '~='
                    elif text[k:k+2] == '==': op = '=='
                    elif text[k] == '<' and (k+1 >= n or text[k+1] != '='): op = '<'
                    elif text[k:k+2] == '<=': op = '<='
                    elif text[k] == '>' and (k+1 >= n or text[k+1] != '='): op = '>'
                
                if op:
                    k2 = k + len(op)
                    while k2 < n and text[k2] == ' ': k2 += 1
                    # Read number
                    num_start = k2
                    while k2 < n and (text[k2].isalnum() or text[k2] in '_xXbBoO'):
                        k2 += 1
                    num_str = text[num_start:k2]
                    try:
                        val = parse_lua_num(num_str)
                        tokens.append((i, 'T_CMP', op, val))
                    except:
                        pass
                elif word == 'T':
                    pass  # Just a variable reference, ignore
            
            i = j
        # Check for 'not(' followed by T comparison
        elif c == '(' and len(tokens) > 0 and tokens[-1][1] == 'not':
            # Look for T comparison inside not(...)
            j = i + 1
            while j < n and text[j] == ' ': j += 1
            if j < n and text[j] == 'T':
                k = j + 1
                while k < n and text[k] == ' ': k += 1
                op = ''
                if text[k:k+2] == '>=': op = '>='
                elif text[k] == '<' and (k+1 >= n or text[k+1] != '='): op = '<'
                elif text[k:k+2] == '<=': op = '<='
                elif text[k] == '>' and (k+1 >= n or text[k+1] != '='): op = '>'
                elif text[k:k+2] == '==': op = '=='
                elif text[k:k+2] == '~=': op = '~='
                
                if op:
                    k2 = k + len(op)
                    while k2 < n and text[k2] == ' ': k2 += 1
                    num_start = k2
                    while k2 < n and (text[k2].isalnum() or text[k2] in '_xXbBoO'):
                        k2 += 1
                    num_str = text[num_start:k2]
                    try:
                        val = parse_lua_num(num_str)
                        # Negate the operation
                        neg = {'>=': '<', '<': '>=', '>': '<=', '<=': '>',
                               '==': '~=', '~=': '=='}
                        tokens[-1] = (tokens[-1][0], 'T_CMP', neg[op], val)
                    except:
                        pass
            i += 1
        else:
            i += 1
    
    return tokens

print("Tokenizing executor...")
tokens = tokenize_executor(executor)
print(f"Found {len(tokens)} tokens")

# Count T comparisons
t_cmps = [t for t in tokens if t[1] == 'T_CMP']
print(f"T comparisons: {len(t_cmps)}")
# Count by type
for op_type in ['>=', '<', '==', '~=', '<=', '>']:
    count = sum(1 for t in t_cmps if t[2] == op_type)
    if count: print(f"  T {op_type}: {count}")

def eval_cmp(op, val, target):
    if op == '>=': return target >= val
    if op == '<': return target < val
    if op == '==': return target == val
    if op == '~=': return target != val
    if op == '>': return target > val
    if op == '<=': return target <= val
    return None

def skip_branch(tokens, start_idx):
    """Skip a then-branch or else-branch by tracking depth.
    Returns the index of the matching else/elseif (for then-branch) or end (for else-branch)."""
    depth = 1
    i = start_idx
    while i < len(tokens):
        t = tokens[i]
        word = t[1] if len(t) >= 2 else ''
        
        # Block openers paired with 'end': if, function, do
        # 'for' and 'while' are NOT block openers - their 'do' is
        if word in ('if', 'function', 'do'):
            depth += 1
        elif word == 'repeat':
            depth += 1
        elif word == 'until':
            depth -= 1
        elif word == 'end':
            depth -= 1
            if depth <= 0:
                return i, 'end'
        elif word == 'else' and depth == 1:
            return i, 'else'
        elif word == 'elseif' and depth == 1:
            return i, 'elseif'
        
        i += 1
    return len(tokens) - 1, 'eof'

def find_handler_for_opcode(tokens, target_value, executor_text, start_token=0):
    """Trace through the binary search tree for a specific opcode value.
    Returns the handler code snippet."""
    i = start_token
    max_depth = 0
    path = []
    
    while i < len(tokens):
        t = tokens[i]
        
        if len(t) >= 4 and t[1] == 'T_CMP':
            op, val = t[2], t[3]
            result = eval_cmp(op, val, target_value)
            
            # Find the 'then' after this comparison
            j = i + 1
            while j < len(tokens) and tokens[j][1] != 'then':
                j += 1
            
            if j >= len(tokens):
                break
            
            path.append((op, val, result))
            
            if result:
                # Take the then-branch: continue from after 'then'
                i = j + 1
                
                if op == '==' and result:
                    # Found exact match! Handler is right here.
                    handler_pos = tokens[j][0] + 4  # after 'then'
                    handler = executor_text[handler_pos:handler_pos+600]
                    return handler, path
            else:
                # Skip the then-branch, go to else/elseif/end
                skip_result, skip_type = skip_branch(tokens, j + 1)
                
                if op == '~=' and not result:
                    # T~=val is False, meaning T==val. Handler is in else branch.
                    if skip_type == 'else':
                        handler_pos = tokens[skip_result][0] + 4  # after 'else'
                        handler = executor_text[handler_pos:handler_pos+600]
                        return handler, path
                    elif skip_type == 'end':
                        # No else branch - implicit handler
                        return None, path
                
                if skip_type == 'else':
                    i = skip_result + 1
                elif skip_type == 'elseif':
                    i = skip_result  # Will process the elseif as a new comparison
                elif skip_type == 'end':
                    i = skip_result + 1
                else:
                    break
        elif t[1] == 'if':
            # Non-T comparison if block: could be anti-analysis junk or handler
            # Check if there's a T_CMP before the matching 'then'
            j = i + 1
            found_t = False
            while j < len(tokens) and tokens[j][1] != 'then':
                if tokens[j][1] == 'T_CMP':
                    found_t = True
                    break
                j += 1
            
            if found_t:
                i = j  # Process as T comparison
            else:
                # Non-T if block - this IS handler code
                # But first check if it's anti-analysis junk (r[X]~=r[Y])
                handler_pos = tokens[i][0]
                snippet = executor_text[handler_pos:handler_pos+50]
                if re.match(r'if\s+(?:r\[|not\s*\()', snippet):
                    # Anti-analysis junk - skip it
                    skip_result, skip_type = skip_branch(tokens, j + 1 if j < len(tokens) else i + 1)
                    if skip_type == 'elseif':
                        i = skip_result  # Process elseif
                    elif skip_type in ('else', 'end'):
                        i = skip_result + 1
                    else:
                        i += 1
                else:
                    handler = executor_text[handler_pos:handler_pos+600]
                    return handler, path
        elif t[1] == 'return':
            # Check if this is a junk return (return <value>;) or real RETURN handler
            pos = tokens[i][0]
            snippet = executor_text[pos:pos+60]
            junk_ret = re.match(r'return\s+[\w/.%*+\-()]+\s*;', snippet)
            if junk_ret:
                # Skip junk return
                j = i + 1
                while j < len(tokens) and tokens[j][0] < pos + junk_ret.end():
                    j += 1
                i = j
            else:
                handler = executor_text[pos:pos+600]
                return handler, path
        elif t[1] == 'while':
            # Check for junk while blocks: while-r[X]do...end; or while <const>do...end;
            pos = tokens[i][0]
            snippet = executor_text[pos:pos+200]
            junk_while = re.match(r'while\s*[-]?\s*(?:r\[\w+\]|0[bBxXoO][\w_]+|\d+)\s*do\b', snippet)
            if junk_while:
                # Skip the junk while block by finding matching end
                j = i + 1
                while j < len(tokens) and tokens[j][1] != 'do':
                    j += 1
                if j < len(tokens):
                    j += 1  # past 'do'
                    d = 1
                    while j < len(tokens) and d > 0:
                        if tokens[j][1] in ('if', 'function', 'do'):
                            d += 1
                        elif tokens[j][1] == 'end':
                            d -= 1
                        j += 1
                i = j
            else:
                handler = executor_text[pos:pos+600]
                return handler, path
        elif t[1] in ('for', 'do', 'function', 'repeat'):
            handler_pos = tokens[i][0]
            handler = executor_text[handler_pos:handler_pos+600]
            return handler, path
        elif t[1] == 'elseif':
            # Check if elseif contains a T comparison
            j = i + 1
            found_t = False
            while j < len(tokens) and tokens[j][1] != 'then':
                if tokens[j][1] == 'T_CMP':
                    found_t = True
                    break
                j += 1
            if found_t:
                i = j  # Process as T comparison
            else:
                # Non-T elseif (junk) - skip this branch
                if j < len(tokens) and tokens[j][1] == 'then':
                    skip_result, skip_type = skip_branch(tokens, j + 1)
                    if skip_type in ('else', 'elseif'):
                        i = skip_result
                    else:
                        i = skip_result + 1
                else:
                    i += 1
        elif t[1] == 'else':
            # Check if else is followed by 'if' with a T comparison
            j = i + 1
            if j < len(tokens) and tokens[j][1] == 'if':
                k = j + 1
                found_t = False
                while k < len(tokens) and tokens[k][1] != 'then':
                    if tokens[k][1] == 'T_CMP':
                        found_t = True
                        break
                    k += 1
                if found_t:
                    i = k  # Process as T comparison
                else:
                    i = j  # Process as non-T if
            else:
                i += 1
        elif t[1] in ('then', 'end', 'until', 'not'):
            i += 1
        else:
            # Check if we've reached handler code
            pos = tokens[i][0]
            snippet = executor_text[pos:pos+30]
            if re.match(r'[syHFkGKW(]', snippet):
                handler = executor_text[pos:pos+600]
                return handler, path
            i += 1
    
    return None, path

# Find all opcodes used in proto data
with open('all_protos_data.json', 'r') as f:
    all_protos = json.load(f)

all_used_ops = set()
op_freq = defaultdict(int)
for p in all_protos:
    for op in p.get('C4', []):
        if op is not None:
            all_used_ops.add(op)
            op_freq[op] += 1

# Find the start of the dispatch tree (first T comparison in executor)
first_t = None
for i, t in enumerate(tokens):
    if t[1] == 'T_CMP':
        first_t = i
        break

print(f"\nDispatch tree starts at token {first_t} (pos {tokens[first_t][0]})")

# Import classifier from final_opcode_map
# (inline the classifier here for independence)
def strip_junk(code):
    """Strip anti-analysis junk prefixes from handler code."""
    h = code
    changed = True
    max_iter = 20
    while changed and max_iter > 0:
        max_iter -= 1
        changed = False
        h = h.strip().lstrip(';').strip()
        
        # Pattern: while-r[X]do ... end; or while r[X]do ... end;
        m = re.match(r'while\s*-?\s*r\[[\w]+\]\s*do\s*(.*?)\s*end;', h, re.DOTALL)
        if m:
            h = h[m.end():].strip()
            changed = True
            continue
        
        # Pattern: if not(-r[X])then else...end; or if not(r[X])then else...end;
        m = re.match(r'if\s+not\s*\(\s*-?\s*r\[[\w]+\]\s*\)\s*then\b', h)
        if m:
            # Find matching else...end
            depth = 1
            i = m.end()
            while i < len(h) and depth > 0:
                rest = h[i:]
                kw = re.match(r'(if|function|do)\b', rest)
                if kw:
                    depth += 1
                    i += len(kw.group(0))
                    continue
                kw = re.match(r'end\b', rest)
                if kw:
                    depth -= 1
                    i += 3
                    continue
                if depth == 1:
                    kw = re.match(r'else\b', rest)
                    if kw:
                        # Skip to matching end
                        i += 4
                        d2 = 1
                        while i < len(h) and d2 > 0:
                            r2 = h[i:]
                            k2 = re.match(r'(if|function|do)\b', r2)
                            if k2: d2 += 1; i += len(k2.group(0)); continue
                            k2 = re.match(r'end\b', r2)
                            if k2: d2 -= 1; i += 3; continue
                            i += 1
                        h = h[i:].lstrip(';').strip()
                        changed = True
                        break
                i += 1
            continue
        
        # Pattern: if r[X]==r[Y]then...end; or if r[X]~=r[Y]then...end;
        m = re.match(r'if\s+r\[\w+\]\s*[~=!<>]=?\s*r\[\w+\]\s*then\b', h)
        if m:
            depth = 1
            i = m.end()
            while i < len(h) and depth > 0:
                rest = h[i:]
                kw = re.match(r'(if|function|do)\b', rest)
                if kw: depth += 1; i += len(kw.group(0)); continue
                kw = re.match(r'end\b', rest)
                if kw:
                    depth -= 1
                    if depth == 0:
                        i += 3
                        h = h[i:].lstrip(';').strip()
                        changed = True
                        break
                    i += 3
                    continue
                if depth == 1:
                    kw = re.match(r'else\b', rest)
                    if kw:
                        i += 4
                        d2 = 1
                        while i < len(h) and d2 > 0:
                            r2 = h[i:]
                            k2 = re.match(r'(if|function|do)\b', r2)
                            if k2: d2 += 1; i += len(k2.group(0)); continue
                            k2 = re.match(r'end\b', r2)
                            if k2: d2 -= 1; i += 3; continue
                            i += 1
                        h = h[i:].lstrip(';').strip()
                        changed = True
                        break
                i += 1
            continue
        
        # Pattern: if not(r[X])then else...end;
        m = re.match(r'if\s+not\s*\(\s*r\[\w+\]\s*\)\s*then\b', h)
        if m:
            depth = 1
            i = m.end()
            while i < len(h) and depth > 0:
                rest = h[i:]
                kw = re.match(r'(if|function|do)\b', rest)
                if kw: depth += 1; i += len(kw.group(0)); continue
                kw = re.match(r'end\b', rest)
                if kw:
                    depth -= 1
                    if depth == 0: i += 3; h = h[i:].lstrip(';').strip(); changed = True; break
                    i += 3; continue
                if depth == 1:
                    kw = re.match(r'else\b', rest)
                    if kw:
                        i += 4; d2 = 1
                        while i < len(h) and d2 > 0:
                            r2 = h[i:]; k2 = re.match(r'(if|function|do)\b', r2)
                            if k2: d2 += 1; i += len(k2.group(0)); continue
                            k2 = re.match(r'end\b', r2)
                            if k2: d2 -= 1; i += 3; continue
                            i += 1
                        h = h[i:].lstrip(';').strip(); changed = True; break
                i += 1
            continue
        
        # Pattern: if 0bXXXX then...end; (constant boolean junk)
        m = re.match(r'if\s+(?:0[bBxXoO][\w_]+|\d+)\s+then\b', h)
        if m:
            depth = 1
            i = m.end()
            while i < len(h) and depth > 0:
                rest = h[i:]
                kw = re.match(r'(if|function|do)\b', rest)
                if kw: depth += 1; i += len(kw.group(0)); continue
                kw = re.match(r'end\b', rest)
                if kw:
                    depth -= 1
                    if depth == 0: i += 3; h = h[i:].lstrip(';').strip(); changed = True; break
                    i += 3; continue
                if depth == 1:
                    kw = re.match(r'else\b', rest)
                    if kw:
                        i += 4; d2 = 1
                        while i < len(h) and d2 > 0:
                            r2 = h[i:]; k2 = re.match(r'(if|function|do)\b', r2)
                            if k2: d2 += 1; i += len(k2.group(0)); continue
                            k2 = re.match(r'end\b', r2)
                            if k2: d2 -= 1; i += 3; continue
                            i += 1
                        h = h[i:].lstrip(';').strip(); changed = True; break
                i += 1
            continue
        
        # Pattern: (r)[X]=...; standalone junk assignment
        m = re.match(r'\(r\)\[\w+\]\s*=\s*[^;]+;', h)
        if m:
            h = h[m.end():].strip()
            changed = True
            continue
        
        # Pattern: r[X]=...; standalone junk r[] assignment
        m = re.match(r'r\[\w+\]\s*=\s*[^;]+;', h)
        if m:
            h = h[m.end():].strip()
            changed = True
            continue
        
        # Pattern: return followed by junk value (return 0x9d; etc.)
        m = re.match(r'return\s+[\w/.%*+-]+\s*;', h)
        if m:
            h = h[m.end():].strip()
            changed = True
            continue
    
    return h

def classify_handler(code, op_val):
    h = strip_junk(code.strip() if code else '')
    # Normalize (s)[...] -> s[...] and (r)[...] -> r[...]
    h = re.sub(r'\(s\)\s*\[', 's[', h)
    h = re.sub(r'\(r\)\s*\[', 'r[', h)
    if not h: return 'EMPTY'
    
    # Detect dispatch tree fragments (handler starts with temp ops + end;end;)
    frag = re.match(r'[kKHFc]=\(?[sDaZqwm\[\]y0-9xXbBoO_]+\)?;', h[:60])
    if frag:
        rest = h[frag.end():].lstrip()
        if re.match(r'(?:end;){2,}', rest):
            return 'DISPATCH_FRAGMENT'
    
    # GETGLOBAL - only match at the START of the handler (first 80 chars)
    gm = re.search(r's\)?\s*\[\s*(\w+)\s*\[y\]\s*\]\s*=\s*\(?\s*([A-Za-z_]\w*)\s*\)?;', h[:80])
    if gm:
        gname = gm.group(2)
        skip = {'s','q','w','m','D','a','Z','Y','y','H','k','x','n','b','F','K','G',
                'true','false','nil','not','and','or','type','end','do','local','then',
                'else','if','while','for','repeat','until','return','function','in',
                'S','C','c','f','o','_','L','P','I','X','J','V','N'}
        if gname not in skip:
            return f'GETGLOBAL({gname})'
    
    # MOVE
    if re.search(r's\)?\s*\[\s*\w+\[y\]\s*\]\s*=\s*\(?\s*s\s*\[\s*\w+\[y\]\s*\]\s*\)?;', h[:150]):
        if not re.search(r's\[\w+\[y\]\]\[', h[:150]):
            return 'MOVE'
    
    # LOADK
    for cv, suf in [('q','q'),('w','w'),('m','m')]:
        if re.search(rf's\)?\s*\[\s*\w+\[y\]\s*\]\s*=\s*\(?\s*{cv}\s*\[y\]\s*\)?;', h[:120]):
            return f'LOADK_{suf}'
    
    # LOADNIL, LOADBOOL
    if re.search(r's\)?\s*\[\s*\w+\[y\]\s*\]\s*=\s*nil', h[:80]): return 'LOADNIL'
    if re.search(r's\)?\s*\[\s*\w+\[y\]\s*\]\s*=\s*\(?\s*true\s*\)?', h[:80]): return 'LOADBOOL_TRUE'
    if re.search(r's\)?\s*\[\s*\w+\[y\]\s*\]\s*=\s*\(?\s*false\s*\)?', h[:80]): return 'LOADBOOL_FALSE'
    
    # NEWTABLE
    if re.search(r's\)?\s*\[\s*\w+\[y\]\s*\]\s*=\s*\{\s*\}', h[:80]): return 'NEWTABLE'
    
    # GETTABLE
    for ks, suf in [('s[\\w+\\[y\\]]',''),('q\\[y\\]','_Kq'),('w\\[y\\]','_Kw'),('m\\[y\\]','_Km')]:
        if re.search(rf's\[\w+\[y\]\]\s*=\s*\(?s\[\w+\[y\]\]\[{ks}\]\)?', h[:180]):
            return f'GETTABLE{suf}'
    
    # SETTABLE
    for ks, vs, suf in [
        ('s[\\w+\\[y\\]]','s[\\w+\\[y\\]]',''),('q\\[y\\]','s[\\w+\\[y\\]]','_Kq'),
        ('w\\[y\\]','s[\\w+\\[y\\]]','_Kw'),('m\\[y\\]','s[\\w+\\[y\\]]','_Km'),
        ('q\\[y\\]','q\\[y\\]','_KqKq'),('q\\[y\\]','w\\[y\\]','_KqKw'),('q\\[y\\]','m\\[y\\]','_KqKm'),
        ('w\\[y\\]','q\\[y\\]','_KwKq'),('w\\[y\\]','w\\[y\\]','_KwKw'),('w\\[y\\]','m\\[y\\]','_KwKm'),
        ('m\\[y\\]','q\\[y\\]','_KmKq'),('m\\[y\\]','w\\[y\\]','_KmKw'),('m\\[y\\]','m\\[y\\]','_KmKm'),
        ('m\\[y\\]','s[\\w+\\[y\\]]','_Km_V'),
        ('s[\\w+\\[y\\]]','q\\[y\\]','_Vq'),
        ('s[\\w+\\[y\\]]','w\\[y\\]','_Vw'),('s[\\w+\\[y\\]]','m\\[y\\]','_Vm'),
    ]:
        if re.search(rf's\[\w+\[y\]\]\[{ks}\]\s*=\s*\(?{vs}\)?', h[:200]):
            return f'SETTABLE{suf}'
    if re.search(r's\[\w+\[y\]\]\[q\[y\]\]\s*=\s*(?:true|false)', h[:150]): return 'SETTABLE_Kq_BOOL'
    if re.search(r's\[\w+\[y\]\]\[q\[y\]\]\s*=\s*nil', h[:150]): return 'SETTABLE_Kq_NIL'
    if re.search(r's\[\w+\[y\]\]\[w\[y\]\]\s*=\s*(?:true|false)', h[:150]): return 'SETTABLE_Kw_BOOL'
    if re.search(r's\[\w+\[y\]\]\[w\[y\]\]\s*=\s*nil', h[:150]): return 'SETTABLE_Kw_NIL'
    
    # Arithmetic
    arith = [(r'\+','ADD'),(r'\s-\s','SUB'),(r'\*','MUL'),(r'/','DIV'),(r'%','MOD'),(r'\^','POW')]
    for rx, nm in arith:
        for l,r2,sf in [('s[\\w+\\[y\\]]','s[\\w+\\[y\\]]',''),
                        ('s[\\w+\\[y\\]]','q\\[y\\]','_Kq'),('q\\[y\\]','s[\\w+\\[y\\]]','_qK'),
                        ('s[\\w+\\[y\\]]','w\\[y\\]','_Kw'),('w\\[y\\]','s[\\w+\\[y\\]]','_wK'),
                        ('s[\\w+\\[y\\]]','m\\[y\\]','_Km'),('m\\[y\\]','s[\\w+\\[y\\]]','_mK')]:
            if re.search(rf's\[\w+\[y\]\]\s*=\s*\(?{l}{rx}{r2}\)?', h[:200]):
                return f'{nm}{sf}'
    
    # CONCAT
    if re.search(r's\[\w+\[y\]\]\s*=\s*s\[\w+\[y\]\]\s*\.\.\s*s\[\w+\[y\]\]', h[:150]): return 'CONCAT'
    for v,sf in [('q','_Kq'),('w','_Kw'),('m','_Km')]:
        if re.search(rf's\[\w+\[y\]\]\s*=\s*s\[\w+\[y\]\]\s*\.\.\s*{v}\[y\]', h[:150]): return f'CONCAT{sf}'
        if re.search(rf's\[\w+\[y\]\]\s*=\s*{v}\[y\]\s*\.\.\s*s\[\w+\[y\]\]', h[:150]): return f'CONCAT{sf}R'
    
    # UNM, NOT, LEN
    if re.search(r's\[\w+\[y\]\]\s*=\s*\(?\s*-\s*s\[\w+\[y\]\]\s*\)?', h[:100]): return 'UNM'
    if re.search(r's\[\w+\[y\]\]\s*=\s*not\s+s\[\w+\[y\]\]', h[:100]): return 'NOT'
    if re.search(r's\[\w+\[y\]\]\s*=\s*\(?\s*#\s*s\[\w+\[y\]\]\s*\)?', h[:100]): return 'LEN'
    
    # Comparison + jump
    cmp_jmp = [
        (r'if\s+s\[\w+\[y\]\]\s*==\s*s\[\w+\[y\]\]\s*then','EQ_JMP'),
        (r'if\s+s\[\w+\[y\]\]\s*~=\s*s\[\w+\[y\]\]\s*then','NE_JMP'),
        (r'if\s+s\[\w+\[y\]\]\s*<\s*s\[\w+\[y\]\]\s*then','LT_JMP'),
        (r'if\s+s\[\w+\[y\]\]\s*<=\s*s\[\w+\[y\]\]\s*then','LE_JMP'),
        (r'if\s+s\[\w+\[y\]\]\s*>\s*s\[\w+\[y\]\]\s*then','GT_JMP'),
        (r'if\s+s\[\w+\[y\]\]\s*>=\s*s\[\w+\[y\]\]\s*then','GE_JMP'),
        (r'if\s+s\[D\[y\]\]\s*~=\s*s\[Z\[y\]\]','NE_JMP'),
        (r'if\s+s\[D\[y\]\]\s*==\s*s\[Z\[y\]\]','EQ_JMP'),
        (r'if\s+s\[\w+\[y\]\]\s*==\s*[qwm]\[y\]','EQ_K_JMP'),
        (r'if\s+s\[\w+\[y\]\]\s*~=\s*[qwm]\[y\]','NE_K_JMP'),
        (r'if\s+s\[\w+\[y\]\]\s*<\s*[qwm]\[y\]','LT_K_JMP'),
        (r'if\s+s\[\w+\[y\]\]\s*<=\s*[qwm]\[y\]','LE_K_JMP'),
        (r'if\s+s\[\w+\[y\]\]\s*>\s*[qwm]\[y\]','GT_K_JMP'),
        (r'if\s+s\[\w+\[y\]\]\s*>=\s*[qwm]\[y\]','GE_K_JMP'),
        (r'if\s+[qwm]\[y\]\s*<\s*s\[\w+\[y\]\]','GT_K_JMP'),
        (r'if\s+[qwm]\[y\]\s*<=\s*s\[\w+\[y\]\]','GE_K_JMP'),
        (r'if\s+not\s*\(\s*s\[\w+\[y\]\]\s*<=\s*s\[\w+\[y\]\]\s*\)','GT_JMP'),
        (r'if\s+not\s*\(\s*s\[\w+\[y\]\]\s*<\s*s\[\w+\[y\]\]\s*\)','GE_JMP'),
        (r'if\s+not\s*\(\s*s\[\w+\[y\]\]\s*<=\s*[qwm]\[y\]\s*\)','GT_K_JMP'),
        (r'if\s+not\s*\(\s*[qwm]\[y\]\s*<\s*s\[\w+\[y\]\]\s*\)','LE_K_JMP'),
        (r'if\s+not\s+s\[\w+\[y\]\]\s*then.*?y\s*=','TEST_FALSE'),
        (r'if\s+s\[\w+\[y\]\]\s*then.*?y\s*=','TEST_TRUE'),
        (r'if\s+s\[D\[y\]\]\s*then.*?y\s*=','TEST_TRUE'),
        (r'if\s+not\s+s\[D\[y\]\]\s*then.*?y\s*=','TEST_FALSE'),
        (r'if\s+s\[\w+\[y\]\]\s*==\s*nil\s*then.*?y\s*=','TEST_NIL'),
        (r'if\s+s\[\w+\[y\]\]\s*~=\s*nil\s*then.*?y\s*=','TEST_NOT_NIL'),
    ]
    for pat, name in cmp_jmp:
        if re.search(pat, h[:350]): return name
    
    # CMP store
    cmp_st = [
        (r's\[\w+\[y\]\]\s*=\s*\(?s\[\w+\[y\]\]\s*==\s*s\[\w+\[y\]\]\)?','EQ_STORE'),
        (r's\[\w+\[y\]\]\s*=\s*\(?s\[\w+\[y\]\]\s*~=\s*s\[\w+\[y\]\]\)?','NE_STORE'),
        (r's\[\w+\[y\]\]\s*=\s*\(?s\[\w+\[y\]\]\s*<\s*s\[\w+\[y\]\]\)?','LT_STORE'),
        (r's\[\w+\[y\]\]\s*=\s*\(?s\[\w+\[y\]\]\s*<=\s*s\[\w+\[y\]\]\)?','LE_STORE'),
        (r's\[\w+\[y\]\]\s*=\s*\(?s\[\w+\[y\]\]\s*>\s*s\[\w+\[y\]\]\)?','GT_STORE'),
        (r's\[\w+\[y\]\]\s*=\s*\(?s\[\w+\[y\]\]\s*>=\s*s\[\w+\[y\]\]\)?','GE_STORE'),
        (r's\[\w+\[y\]\]\s*=\s*s\[\w+\[y\]\]\s*==\s*[qwm]\[y\]','EQ_K_STORE'),
        (r's\[\w+\[y\]\]\s*=\s*s\[\w+\[y\]\]\s*~=\s*[qwm]\[y\]','NE_K_STORE'),
        (r's\[\w+\[y\]\]\s*=\s*s\[\w+\[y\]\]\s*<\s*[qwm]\[y\]','LT_K_STORE'),
        (r's\[\w+\[y\]\]\s*=\s*s\[\w+\[y\]\]\s*<=\s*[qwm]\[y\]','LE_K_STORE'),
        (r's\[\w+\[y\]\]\s*=\s*s\[\w+\[y\]\]\s*>\s*[qwm]\[y\]','GT_K_STORE'),
        (r's\[\w+\[y\]\]\s*=\s*s\[\w+\[y\]\]\s*>=\s*[qwm]\[y\]','GE_K_STORE'),
        (r's\[\w+\[y\]\]\s*=\s*[qwm]\[y\]\s*[<>=~]+\s*[qwm]\[y\]','CMP_KK_STORE'),
    ]
    for pat, name in cmp_st:
        if re.search(pat, h[:250]): return name
    
    # JMP
    if re.match(r'\s*y\s*=\s*\(?\s*[DaZ]\[y\]\s*\)?;', h[:40]): return 'JMP'
    
    # CLOSE (upvalue closing) - multiple patterns
    if re.search(r'for\s+C\s*,\s*o\s*(?:,\s*S)?\s+in\s+L\s+do', h[:80]): return 'CLOSE'
    if re.search(r'if\s+K\s+then\s+for\s+C\s*=', h[:60]): return 'CLOSE'
    if re.search(r'if\s+k\s+then.*?for\s+C\s*=', h[:100]): return 'CLOSE'
    if re.search(r'local\s+C\s*=\s*\(?[DaZ]\[y\]\)?\s*;\s*if\s+L\s+then', h[:80]): return 'CLOSE'
    
    # LOADNIL_RANGE variants
    if re.search(r'for\s+S\s*=\s*H\s*,\s*F\s+do.*?nil', h[:200]): return 'LOADNIL_RANGE'
    if re.search(r'for\s+S\s*=\s*a\[y\]\s*,\s*D\[y\].*?nil', h[:200]): return 'LOADNIL_RANGE'
    if re.search(r'for\s+S\s*=\s*D\[y\]\s*,\s*a\[y\].*?nil', h[:200]): return 'LOADNIL_RANGE'
    
    # CALL
    if re.search(r'H\s*=\s*\w+\[y\].*s\[H\]\s*=\s*s\[H\]', h[:400]): return 'CALL'
    if re.search(r'r\[(?:0[xX]1[dD]|29|0[bB]\d+)\]\(', h[:300]): return 'CALL_SPREAD'
    if re.search(r's\[\w+\[y\]\]\s*=\s*s\[\w+\[y\]\]\s*\(\s*\)', h[:150]): return 'CALL_0'
    # CALL_1_0: H=D[y];s[H](s[H+1]);X=(H-1);
    if re.search(r'H\s*=\s*\w+\[y\]\s*;\s*s\[H\]\s*\(\s*s\[H\s*\+\s*1\]\s*\)', h[:150]): return 'CALL_1_0'
    # CALL with unpack
    if re.search(r's\[H\]\s*\(\s*r\[', h[:200]): return 'CALL_UNPACK'
    
    # SELF
    if re.search(r'G\s*=\s*\(?s\[\w+\[y\]\]\)?.*G\[', h[:300]): return 'SELF'
    
    # RETURN
    if re.match(r'\s*return\s', h[:20]): return 'RETURN'
    if re.search(r'return\s+s\[\w+\[y\]\]', h[:150]): return 'RETURN_VAL'
    
    # UPVAL
    if re.search(r's\[\w+\[y\]\]\s*=\s*W\[\w+\[y\]\]', h[:100]): return 'GETUPVAL'
    if re.search(r'W\[\w+\[y\]\]\s*=\s*s\[\w+\[y\]\]', h[:100]): return 'SETUPVAL'
    if re.search(r'H\s*=\s*W\[\w+\[y\]\]', h[:100]): return 'UPVAL_ACCESS'
    if re.search(r'W\[\w+\[y\]\]', h[:100]): return 'UPVAL_OP'
    
    # SETGLOBAL - must write TO r[4][key] = value
    if re.search(r'r\[(?:0[xX]4|4|0[bB]100)\]\[.*?\]\s*=', h[:120]): return 'SETGLOBAL'
    # GETGLOBAL via environment: s[reg] = r[4][key]
    if re.search(r's\[\w+\[y\]\]\s*=\s*\(?r\[(?:0[xX]4|4|0[bB]100)\]\[', h[:120]): return 'GETGLOBAL_ENV'
    
    # CLOSURE
    if re.search(r'function\s*\(', h[:150]): return 'CLOSURE'
    if re.search(r'r\[56\]\s*\(', h[:200]): return 'CLOSURE'
    # LOADK_VM: s[reg]=z.XXXX (VM internal property)
    if re.search(r's\)?\s*\[\s*\w+\[y\]\s*\]\s*=\s*z\.\w+', h[:80]): return 'LOADK_VM'
    
    # FORLOOP/FORPREP
    if re.search(r'P\s*=\s*P\s*\+\s*I', h[:100]) or re.search(r'P\s*\+=\s*I', h[:100]): return 'FORLOOP'
    if re.search(r'P\s*=\s*P\s*-\s*I', h[:100]) or re.search(r'P\s*-=\s*I', h[:100]): return 'FORPREP'
    
    # TFORLOOP
    if re.search(r'V\s*=\s*\(?\s*\{', h[:100]): return 'TFORLOOP'
    
    # VARARG
    if re.search(r'N\[', h[:100]): return 'VARARG'
    
    # SETLIST
    if re.search(r'r\[(?:0[xX]10|16|0[bB]10000)\]', h[:100]): return 'SETLIST'
    
    # ARITH_BUILTIN
    if re.search(r'r\[(?:0[xX]25|37|0[bB]100101)\]', h[:150]): return 'ARITH_BUILTIN'
    
    # Computed dispatch variants
    if re.search(r'while\s+true\s+do\s+if\s+not\s*\(\s*K\s*>', h[:80]): return 'COMPUTED_DISPATCH'
    if re.search(r'while\s+true\s+do\s+if\s+not\s*\(\s*f\s*>=', h[:80]): return 'COMPUTED_DISPATCH'
    if re.search(r'while\s+true\s+do\s+if\s+K\s*==\s*0[xX]32', h[:80]): return 'COMPUTED_DISPATCH'
    if re.search(r'while\s+true\s+do\s+if\s+K\s*>\s*0[bB]', h[:80]): return 'COMPUTED_DISPATCH'
    if re.search(r'while\s+true\s+do\s+if\s+r\[', h[:80]): return 'COMPUTED_DISPATCH'
    if re.search(r'while\s+true\s+do\s+if\s+c\s*==', h[:80]): return 'COMPUTED_DISPATCH'
    if re.search(r'while\s+true\s+do\s+if\s+not\s*\(\s*c\s*>', h[:80]): return 'COMPUTED_DISPATCH'
    if re.search(r'H\s*=\s*nil\s*;\s*F\s*=\s*nil.*?while\s+true\s+do', h[:100]): return 'COMPUTED_DISPATCH'
    
    # Multi-step handlers
    if re.search(r'H\s*=\s*\w+\[y\].*F\s*=.*k\s*=', h[:150]): return 'CALL_SETUP'
    if re.search(r'H\s*=\s*\(?\s*D\[y\]\s*\)?\s*;?\s*F\s*=', h[:100]): return 'RANGE_SETUP'
    if re.search(r'K\s*=\s*\(?\s*D\[y\]\s*\)?', h[:60]): return 'ASSIGN_K'
    
    # Handler fragments with H/F/k/K operations
    if re.search(r'\(H\)\[F\]\s*=\s*\(?k\)?', h[:60]): return 'SETTABLE_HFK'
    if re.search(r'k\s*-=\s*K', h[:40]): return 'SUB_kK'
    if re.search(r'F\s*=\s*F\s*\[\s*k\s*\]', h[:60]): return 'GETTABLE_Fk'
    # RANGE_OP: H=Z[y];F=D[y];X=H+F-1
    if re.search(r'H\s*=\s*[DaZ]\[y\]\s*;\s*F\s*=\s*[DaZ]\[y\]\s*;\s*X\s*=\s*H\s*\+\s*F', h[:100]): return 'RANGE_OP'
    # k=(k[K]) - gettable on temp
    if re.match(r'\s*k\s*=\s*\(?k\[K\]\)?\s*;', h[:30]): return 'GETTABLE_kK'
    # K=s;c=(D[y]) - reading register into temp for multi-step
    if re.match(r'\s*K\s*=\s*s\s*;\s*c\s*=\s*\(?[DaZ]\[y\]\)?', h[:40]): return 'REG_READ'
    # enc=s[Z[y]] or similar var=s[operand] (temp var assign from register)
    if re.match(r'\s*\w+\s*=\s*s\[\w+\[y\]\]\s*;', h[:40]): return 'REG_ASSIGN'
    
    # GETTABLE via temp vars: k=(s);K=(Z[y]);k=(k[K]); patterns
    if re.search(r'k\s*=\s*\(?s\)?\s*;\s*K\s*=\s*\(?[DaZ]\[y\]\)?\s*;\s*k\s*=\s*\(?k\[K\]\)?', h[:100]):
        return 'GETTABLE_TEMP'
    
    # Deeper search for s[] patterns in first 150 chars only
    if re.search(r's\[\w+\[y\]\]\s*=', h[:150]):
        gm2 = re.search(r's\[\w+\[y\]\]\s*=\s*\(?\s*([A-Za-z_]\w*)\s*\)?;', h[:100])
        if gm2:
            gname = gm2.group(1)
            skip = {'s','q','w','m','D','a','Z','Y','y','H','k','x','n','b','F','K','G',
                    'true','false','nil','not','and','or','type','end','do','local','then',
                    'else','if','while','for','repeat','until','return','function','in',
                    'S','C','c','f','o','_','L','P','I','X','J','V','N'}
            if gname not in skip:
                return f'GETGLOBAL({gname})'
        return 'REG_ASSIGN'
    
    # Anti-analysis junk
    stripped = re.sub(r'if\s+r\[\w+\]\s*[~=]=\s*r\[\w+\]\s*then\s+.*?end;', '', h[:500])
    stripped = stripped.strip()
    if not stripped or stripped == ';': return 'JUNK'
    
    return 'UNKNOWN'

# Trace each used opcode through the dispatch tree
print(f"\nTracing {len(all_used_ops)} opcodes through dispatch tree...")

handler_map = {}
handler_code = {}
trace_failures = []

for target in sorted(all_used_ops):
    handler, path = find_handler_for_opcode(tokens, target, executor, start_token=first_t)
    if handler:
        cls = classify_handler(handler, target)
        handler_map[target] = cls
        handler_code[target] = handler[:200]
    else:
        handler_map[target] = 'NOT_FOUND'
        trace_failures.append(target)

# Print results
print(f"\n{'='*110}")
print(f"DISPATCH TREE TRACE RESULTS: {len(handler_map)} opcodes")
print(f"{'='*110}")

class_groups = defaultdict(list)
for op, cls in sorted(handler_map.items()):
    class_groups[cls].append(op)

for cls in sorted(class_groups.keys()):
    ops = class_groups[cls]
    freq = sum(op_freq.get(op, 0) for op in ops)
    ops_str = ', '.join(str(o) for o in sorted(ops)[:15])
    if len(ops) > 15: ops_str += f' +{len(ops)-15}'
    print(f"  {cls:>25s} ({len(ops):3d} ops, {freq:6d} inst): {ops_str}")

confirmed = sum(1 for v in handler_map.values() if v not in ('UNKNOWN', 'NOT_FOUND', 'EMPTY', 'JUNK'))
unknown = sum(1 for v in handler_map.values() if v in ('UNKNOWN', 'NOT_FOUND', 'EMPTY'))
junk = sum(1 for v in handler_map.values() if v == 'JUNK')
print(f"\nConfirmed: {confirmed}, Unknown: {unknown}, Junk: {junk}, Trace failures: {len(trace_failures)}")

if trace_failures:
    print(f"Failed to trace: {trace_failures[:20]}")

# Show UNKNOWN handlers for debugging
unknowns = [(op, handler_code.get(op, '')) for op, cls in handler_map.items() 
            if cls == 'UNKNOWN' and op_freq.get(op, 0) > 10]
unknowns.sort(key=lambda x: op_freq.get(x[0], 0), reverse=True)
if unknowns:
    print(f"\nTop UNKNOWN handlers (freq > 10):")
    for op, code in unknowns[:30]:
        print(f"  Op {op:4d} ({op_freq[op]:5d}x): {code[:120]}")

# Save
with open('opcode_dispatch_map.json', 'w') as f:
    json.dump({
        'handler_map': {str(k): v for k, v in handler_map.items()},
        'handler_code': {str(k): v[:200] for k, v in handler_code.items()},
        'class_groups': {k: sorted(v) for k, v in class_groups.items()},
        'trace_failures': trace_failures,
    }, f, indent=1, sort_keys=True)
print(f"\nSaved to opcode_dispatch_map.json")
