"""Extract opcode handlers from Luraph VM interpreter dispatch tree."""
import re

with open('unobfuscator/target2_lua51.lua', 'r') as f:
    lines = f.readlines()

# Find the VM interpreter dispatch start
dispatch_start = None
for i, line in enumerate(lines):
    if 'while true do' in line and i+1 < len(lines) and 'local E = r[V]' in lines[i+1]:
        dispatch_start = i + 2  # line after "local E = r[V]"
        break

if dispatch_start is None:
    print("Dispatch block not found")
    exit(1)

print(f"Dispatch starts at line {dispatch_start + 1}")

# Parse the if/elseif/else tree to extract opcode handlers
# Track the E value constraints at each nesting level
# Each leaf in the tree corresponds to one opcode

def extract_handler(lines, start, indent_level):
    """Extract the handler code starting from 'start' until the next if/elseif/else/end at same indent."""
    handler_lines = []
    i = start
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        curr_indent = len(line) - len(line.lstrip())
        
        if curr_indent <= indent_level and stripped in ('end', 'else', 'elseif', ''):
            break
        if stripped.startswith('if ') or stripped.startswith('elseif '):
            break
        if curr_indent <= indent_level and stripped == 'end':
            break
            
        handler_lines.append(stripped)
        i += 1
    return '\n'.join(handler_lines)

# Parse all opcodes by walking through the dispatch tree
opcodes = {}

def parse_dispatch(lines, start, end_line, lo=0, hi=200):
    """Recursively parse the if/elseif dispatch tree."""
    i = start
    while i < min(end_line, len(lines)):
        line = lines[i]
        stripped = line.strip()
        
        # Skip empty lines
        if not stripped:
            i += 1
            continue
            
        # Check for E comparisons
        # Pattern: if E < N then / if not (E < N) then / if E >= N then / if E == N then / if E ~= N then
        
        eq_match = re.search(r'if\s+E\s*==\s*(\d+\.?\d*)\s*then', stripped)
        ne_match = re.search(r'if\s+E\s*~=\s*(\d+\.?\d*)\s*then', stripped)
        lt_match = re.search(r'if\s+E\s*<\s*(\d+\.?\d*)\s*then', stripped)
        ge_match = re.search(r'if\s+E\s*>=\s*(\d+\.?\d*)\s*then', stripped)
        not_lt_match = re.search(r'if\s+not\s*\(E\s*<\s*(\d+\.?\d*)\)\s*then', stripped)
        not_gt_match = re.search(r'if\s+not\s*\(E\s*>\s*(\d+\.?\d*)\)\s*then', stripped)
        
        if eq_match or ne_match or lt_match or ge_match or not_lt_match or not_gt_match:
            pass  # Will process below
        elif stripped.startswith('p[') or stripped.startswith('V =') or stripped.startswith('I[') or stripped.startswith('local ') or stripped.startswith('do') or stripped.startswith('q[') or stripped.startswith('d =') or stripped.startswith('return') or stripped.startswith('if p[') or stripped.startswith('if not') or stripped.startswith('if g[') or stripped.startswith('if d') or stripped.startswith('R ') or stripped.startswith('j ') or stripped.startswith('N ') or stripped.startswith('k ') or stripped.startswith('for ') or stripped.startswith('d,') or stripped.startswith('Y =') or stripped.startswith('U =') or stripped.startswith('h =') or stripped.startswith('z =') or stripped.startswith('F =') or stripped.startswith('K =') or stripped.startswith('O =') or stripped.startswith('m =') or stripped.startswith('x =') or stripped.startswith('w ='):
            # This is handler code - find the opcode for this handler
            pass
        
        i += 1

# Instead of recursive parsing, let me use a simpler approach:
# Find all lines that match E == N patterns and extract the handler that follows

print("\n=== Opcode Handlers ===\n")

in_dispatch = False
for i in range(dispatch_start, min(dispatch_start + 2500, len(lines))):
    line = lines[i]
    stripped = line.strip()
    
    # Look for E == N patterns
    eq_match = re.search(r'(?:if|elseif)\s+E\s*==\s*(\d+\.?\d*)\s*then', stripped)
    ne_match = re.search(r'(?:if|elseif)\s+E\s*~=\s*(\d+\.?\d*)\s*then', stripped)
    
    if eq_match:
        opcode = int(float(eq_match.group(1)))
        # Get the next few lines as handler
        handler = []
        for j in range(i+1, min(i+8, len(lines))):
            h = lines[j].strip()
            if h.startswith('if E') or h.startswith('elseif E') or h.startswith('else') or h == 'end':
                break
            if h and h != 'end':
                handler.append(h)
        if handler:
            code = '; '.join(handler[:3])
            opcodes[opcode] = code
    
    if ne_match:
        opcode_ne = int(float(ne_match.group(1)))
        # E ~= N means this branch handles all opcodes in range EXCEPT N
        # The else branch handles N
        # Get the else branch handler
        pass

# Also extract handlers from "else" branches by looking at context
# For the binary search tree, the else branch handles the remaining opcode

# Print all found opcode handlers
for op in sorted(opcodes.keys()):
    code = opcodes[op][:150]
    print(f"  OP {op:3d}: {code}")

print(f"\nTotal opcodes with == handlers: {len(opcodes)}")

# Now extract handlers for opcodes identified only by range (not ==)
# These are at the leaves of the binary search tree where only 2 opcodes remain
# and E ~= N is used to distinguish them
print("\n=== E ~= N handlers (2-way branch) ===\n")
for i in range(dispatch_start, min(dispatch_start + 2500, len(lines))):
    line = lines[i]
    stripped = line.strip()
    ne_match = re.search(r'(?:if|elseif)\s+E\s*~=\s*(\d+\.?\d*)\s*then', stripped)
    if ne_match:
        opcode = int(float(ne_match.group(1)))
        # The if branch handles everything EXCEPT opcode
        # The else branch handles opcode
        # Get else handler
        for j in range(i+1, min(i+20, len(lines))):
            if lines[j].strip() == 'else':
                handler = []
                for k in range(j+1, min(j+5, len(lines))):
                    h = lines[k].strip()
                    if h == 'end' or h.startswith('if ') or h.startswith('elseif'):
                        break
                    if h:
                        handler.append(h)
                if handler:
                    code = '; '.join(handler[:3])
                    print(f"  OP {opcode:3d} (else of ~=): {code[:150]}")
                break
