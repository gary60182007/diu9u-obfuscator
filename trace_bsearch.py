"""
Trace through the binary search dispatch tree for specific opcode values.
For each target opcode, follow the T comparisons to find the handler.
Uses the Lua VM itself to evaluate which branch is taken.
"""
import re, json

with open('i3_executor_chunk.lua', 'r', encoding='utf-8') as f:
    executor = f.read()

def parse_lua_num(s):
    s = s.replace('_', '').strip()
    if s.startswith('0x') or s.startswith('0X'): return int(s, 16)
    elif s.startswith('0b') or s.startswith('0B'): return int(s.replace('_',''), 2)
    return int(s)

# Find all T comparisons with positions
t_comps = []
# T <op> <number>
for m in re.finditer(r'\bT\s*([<>=~!]+)\s*(0[xXbBoO][\da-fA-F_]+|\d+)\b', executor):
    try:
        val = parse_lua_num(m.group(2))
        t_comps.append((m.start(), m.group(1), val, m.group(0)))
    except: pass

# not(T <op> <number>)
for m in re.finditer(r'not\s*\(\s*T\s*([<>=]+)\s*(0[xXbBoO][\da-fA-F_]+|\d+)\s*\)', executor):
    try:
        val = parse_lua_num(m.group(2))
        op = m.group(1)
        # not(T>=X) == T<X, not(T<X) == T>=X
        neg = {'>=': '<', '<': '>=', '>': '<=', '<=': '>'}
        t_comps.append((m.start(), neg.get(op, op), val, m.group(0)))
    except: pass

t_comps.sort(key=lambda x: x[0])
print(f"Found {len(t_comps)} T comparisons")

# For a given opcode value V, evaluate which branch each comparison takes
def eval_comp(op, val, target):
    """Returns True if the 'then' branch is taken for target opcode"""
    if op == '>=': return target >= val
    if op == '<': return target < val
    if op == '==': return target == val
    if op == '~=': return target != val
    if op == '>': return target > val
    if op == '<=': return target <= val
    return None

# Strategy: for each target opcode, find the sequence of comparisons
# that lead to its handler, then extract the handler code.
# 
# The binary search tree is laid out sequentially in the source:
# if cond1 then
#   [then-branch: more comparisons or handler]
# else
#   [else-branch: more comparisons or handler]
# end
#
# The "then" branch is BEFORE the "else" branch in source position.
# So if a comparison is at position P and we take the "then" branch,
# the next relevant comparison is at position > P (within the then-branch).
# If we take the "else" branch, we need to skip past the entire then-branch.
#
# The key challenge: determining where the then-branch ends.
# 
# Alternative approach: for each target opcode, find ALL comparisons
# whose conditions are satisfied, and take the LAST one (innermost).

# Actually, let me use a simpler approach:
# 1. For each comparison, determine if it's on the path to the target
# 2. The handler is the code AFTER the last comparison on the path

# The binary search narrows the range. At each step:
# - T >= X narrows to [X, ...) or [.., X)
# - T < X narrows to [.., X) or [X, ...)
# - T == X narrows to exactly X
# - T ~= X: then-branch excludes X, else-branch is exactly X

# Let me find the handler for specific opcodes by scanning the source
# and tracking which comparisons the opcode passes through.

# Method: tokenize the executor and build a simplified tree
# But for minified code, this is very hard.

# PRACTICAL method: use the runtime to extract handler code!
# I'll modify the trace to capture a SHORT string describing what the handler does.

# Better: let me instrument the executor to, for EACH unique opcode,
# capture the register state before AND after execution.
# Key: only capture the FIRST occurrence, and use a VERY compact format.

# Actually, the MOST practical approach:
# Extract handler by injecting a "marker" that records the handler position.
# I'll replace the T=Y[y] line with code that also captures
# which code path is taken.

# Let me try: for each of the top 30 unknown opcodes, manually search
# the source for the handler by evaluating the binary search path.

top_unknowns = [117, 194, 138, 55, 171, 99, 197, 196, 227, 164, 208, 122, 169, 
                309, 252, 229, 253, 278, 136, 103, 318, 1, 12, 47, 65, 170, 232,
                141, 152, 233, 304, 267]

# For each target, find the comparisons on the path
for target in top_unknowns:
    # Find all comparisons and evaluate them
    path = []
    for pos, op, val, raw in t_comps:
        result = eval_comp(op, val, target)
        path.append((pos, op, val, result, raw))
    
    # The last comparison that evaluates to True and has == or ~= is the handler
    eq_matches = [(pos, op, val) for pos, op, val, result, raw in path if op == '==' and result]
    ne_matches = [(pos, op, val) for pos, op, val, result, raw in path if op == '~=' and not result]
    
    handler_code = ''
    handler_type = ''
    
    if eq_matches:
        # Handler is after T==target then
        for pos, op, val in eq_matches:
            then_search = executor[pos:pos+60]
            then_idx = then_search.find('then')
            if then_idx >= 0:
                h_start = pos + then_idx + 4
                handler_code = executor[h_start:h_start+300]
                handler_type = f'T=={val}'
                break
    elif ne_matches:
        # Handler is in the else branch of T~=target
        for pos, op, val in ne_matches:
            # T~=target evaluates to False, so we go to else branch
            # Need to find the else after the then block
            handler_type = f'T~={val} (else)'
            # Find the handler in else branch
            then_search = executor[pos:pos+60]
            then_idx = then_search.find('then')
            if then_idx >= 0:
                # The else branch handler - need to skip the then block
                # Simple heuristic: search for 'else' after the comparison
                rest = executor[pos + then_idx + 4:]
                # Track depth to find the matching else
                depth = 1
                i = 0
                while i < len(rest) and i < 5000:
                    if rest[i] == '"' or rest[i] == "'":
                        q = rest[i]
                        i += 1
                        while i < len(rest) and rest[i] != q:
                            if rest[i] == '\\': i += 1
                            i += 1
                        i += 1
                        continue
                    
                    # Check keywords
                    word = ''
                    if rest[i].isalpha():
                        j = i
                        while j < len(rest) and (rest[j].isalnum() or rest[j] == '_'):
                            j += 1
                        word = rest[i:j]
                    
                    if word in ('if', 'function', 'for', 'while', 'do', 'repeat'):
                        depth += 1
                        i += len(word)
                    elif word == 'end':
                        depth -= 1
                        if depth <= 0:
                            break
                        i += len(word)
                    elif word == 'else' and depth == 1:
                        # Found the matching else!
                        handler_code = rest[i+4:i+304]
                        break
                    elif word == 'elseif' and depth == 1:
                        handler_code = rest[i:][:300]
                        break
                    elif word:
                        i += len(word)
                    else:
                        i += 1
    else:
        # No direct == or ~= match found
        # This opcode is handled by an implicit else branch
        # Find the narrowest range containing target
        handler_type = 'implicit else'
        
        # Find comparisons that bracket the target
        ge_lower = 0
        lt_upper = 999
        for pos, op, val, result, raw in path:
            if op == '>=' and result and val > ge_lower:
                ge_lower = val
            if op == '<' and result and val < lt_upper:
                lt_upper = val
        
        handler_type = f'range [{ge_lower}, {lt_upper})'
        
        # Find the innermost T~=X in this range
        for pos, op, val, result, raw in path:
            if op == '~=' and ge_lower <= val < lt_upper and val != target:
                # This T~=X is in our range and X!=target
                # If X is the only OTHER value in range, then else is our handler
                # If range has more values, this is just one split
                pass
    
    # Clean up handler
    h = handler_code.strip()[:200] if handler_code else '(not found)'
    
    # Try to classify
    from build_opcode_map import classify_handler
    if handler_code:
        cls = classify_handler(handler_code, target)
    else:
        cls = 'NOT_FOUND'
    
    freq_data = {}
    try:
        with open('opcode_profiles.json', 'r') as f:
            freq_data = json.load(f)
    except: pass
    
    count = freq_data.get(str(target), {}).get('count', 0)
    
    print(f"\nOp {target:4d} ({count:5d}x) [{handler_type}] -> {cls}")
    if handler_code:
        print(f"  Handler: {h}")
