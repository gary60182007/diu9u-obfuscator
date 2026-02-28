"""
Parse the binary search dispatch tree in the i==3 VM executor.
Find ALL leaf handlers by tracing the if/elseif/else tree.
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

# Find the i==3 executor opcode fetch: local T=Y[y]
unpack_pat = re.compile(r'local\s+Q,i,O,a,q,D,Y,Z,w,m,J\s*=\s*C\[')
um = unpack_pat.search(src)
chunk = src[um.start():um.start() + 500000]

t_fetch = re.search(r'local\s+T\s*=\s*Y\[y\]', chunk)
i3_start = t_fetch.start()
print(f"i==3 opcode dispatch starts at chunk offset +{i3_start}")

# The dispatcher is a large if/elseif/else tree
# Let me extract it by tracking depth
# Starting from 'local T=Y[y];' the next thing is the dispatch tree

# Strategy: find all T comparisons and build the binary search tree
# For each comparison, determine the range of T values it handles

# Better approach: scan the dispatch tree sequentially and track the
# constraint on T at each point

# Extract the full i==3 executor body
# The executor is a function(...) ... end
# Find the function( before the T=Y[y]
func_search = chunk[:i3_start]
func_pos = func_search.rfind('function(')
print(f"i==3 function starts at chunk offset +{func_pos}")

# Now let's get the executor body
exec_body = chunk[func_pos:]

# Find the while loop that contains T=Y[y]
while_pos = exec_body.find('while true do')
if while_pos < 0:
    while_pos = exec_body.find('while 0B1 do')
if while_pos < 0:
    while_pos = exec_body.find('while')
print(f"While loop at offset +{while_pos} in executor")

# Alternative approach: since the binary search is hard to parse statically,
# let me instrument the VM to log opcodes at runtime.
# I'll inject a single line after 'local T=Y[y]' to log T values.

# Find the exact position of 'local T=Y[y]' in the full source
t_global_pos = um.start() + i3_start
t_end_pos = t_global_pos + len('local T=Y[y]')

# Check what comes after
after = src[t_end_pos:t_end_pos+5]
print(f"After 'local T=Y[y]': '{after}'")

# Inject logging after 'local T=Y[y];'
# We want to log: opcode T, registers before/after
# But we need to be careful not to break the executor

# Simple injection: log each unique opcode T to a table
inject_after_t = (
    'if not _G._op_seen then _G._op_seen={} end;'
    'if not _G._op_seen[T] then _G._op_seen[T]=true;'
    'if not _G._op_log then _G._op_log={} end;'
    'local _n=#_G._op_log+1;'
    '_G._op_log[_n]={T=T,D=D[y],a=a[y],Z=Z[y],q=q and q[y],w=w and w[y],m=m and m[y]};'
    'end;'
)

# Actually, that's too complex. Let me just log T values and then analyze
# what operations they correspond to by checking register state changes.

# Simpler: inject to build a frequency table of T values
inject_simple = (
    'if not _G._tlog then _G._tlog={} end;'
    '_G._tlog[T]=(_G._tlog[T] or 0)+1;'
)

# Find the semicolon after 'local T=Y[y]'
semicolon_pos = src.find(';', t_global_pos)
if semicolon_pos < t_global_pos + 50:
    # Inject after the semicolon
    modified = src[:semicolon_pos+1] + inject_simple + src[semicolon_pos+1:]
    print(f"Injected T logging at pos {semicolon_pos+1}")
else:
    print(f"Could not find semicolon after T=Y[y]")
    modified = src

# Also need to suppress the VM execution error
# And hook the proto capture
d9_pat = re.compile(r'(d9=function\((\w+),(\w+),(\w+),(\w+)\))')
d9_m = d9_pat.search(modified)
d9_C = d9_m.group(4)

# Hook to stop after first proto execution
inject_d9 = (
    f'do local _st={d9_C};'
    f'local _orig58=_st[58];'
    f'_st[58]=function() '
    f'local _r=_orig58();'
    f'local _n=(_G._pn or 0)+1;_G._pn=_n;'
    f'return _r end;end;'
)
modified = modified[:d9_m.end()] + inject_d9 + modified[d9_m.end():]

# Suppress the executor entry point error
pat = re.compile(
    r'(\)\[(?:\d+|0[xXbBoO][0-9a-fA-F_]+)\]=function\()'
    r'([A-Za-z_]\w*)' r',' r'([A-Za-z_]\w*)' r'\)'
    r'(local\s+[A-Za-z_]\w*(?:,[A-Za-z_]\w*){9,}=)'
    r'(\2\[)'
)
m2 = pat.search(modified)
if m2:
    p1 = m2.group(2)
    full_match = m2.group(0)
    lp = full_match.index('local')
    hook = f'if {p1}==nil then return function(...)return end end;'
    modified = modified[:m2.start()] + full_match[:lp] + hook + full_match[lp:] + modified[m2.end():]

from unobfuscator.utils.lua_runtime import LuaRuntimeWrapper, LuaRuntimeError
exec(open('run_luraph_test.py').read().split("print('Reading source...')")[0])
modified = preprocess_luau(modified)

runtime = LuaRuntimeWrapper(op_limit=15_000_000_000, timeout=600)
runtime._init_runtime()
runtime.lua.execute("_G._pn=0;_G._tlog={};_G._op_seen={}")
modified = runtime.suppress_vm_errors(modified)

print("\nExecuting VM with opcode tracing...")
import time
t0 = time.time()
try:
    runtime.execute(modified)
except LuaRuntimeError as e:
    print(f"Stopped after {time.time()-t0:.1f}s: {str(e)[:200]}")

runtime.lua.execute("_G._op_count=0;_G._op_limit=10000000000")

# Extract the T frequency log
runtime.lua.execute("""
local _p = {}
for k, v in pairs(_G._tlog or {}) do
    table.insert(_p, tostring(math.floor(k)) .. ":" .. tostring(v))
end
table.sort(_p)
_G._tlog_str = table.concat(_p, ",")
""")
tlog_str = str(runtime.lua.eval('_G._tlog_str') or '')
print(f"\nRuntime opcode frequency ({len(tlog_str)} chars):")

# Parse the frequency data
runtime_freqs = {}
if tlog_str:
    for item in tlog_str.split(','):
        if ':' in item:
            parts = item.split(':')
            try:
                op = int(parts[0])
                cnt = int(parts[1])
                runtime_freqs[op] = cnt
            except:
                pass

# Sort by frequency
by_freq = sorted(runtime_freqs.items(), key=lambda x: -x[1])
print(f"\nRuntime opcode execution frequency ({len(runtime_freqs)} unique opcodes):")
for op, cnt in by_freq[:40]:
    print(f"  T={op:4d}: {cnt:8d}x")

total_exec = sum(runtime_freqs.values())
print(f"\nTotal instructions executed: {total_exec}")

# Compare with static extraction
with open('all_protos_data.json', 'r', encoding='utf-8') as f:
    all_protos = json.load(f)

static_freqs = {}
for p in all_protos:
    for op in p.get('C4', []):
        if op is not None:
            static_freqs[op] = static_freqs.get(op, 0) + 1

print(f"\nStatic opcodes: {len(static_freqs)} unique")
print(f"Runtime opcodes: {len(runtime_freqs)} unique")

# Check if runtime opcodes match static
runtime_set = set(runtime_freqs.keys())
static_set = set(static_freqs.keys())

only_runtime = runtime_set - static_set
only_static = static_set - runtime_set
both = runtime_set & static_set

print(f"In both: {len(both)}")
print(f"Only in runtime: {len(only_runtime)} - {sorted(only_runtime)[:20]}")
print(f"Only in static: {len(only_static)} - {sorted(only_static)[:20]}")

# Save runtime frequencies
with open('runtime_opcode_freqs.json', 'w') as f:
    json.dump(runtime_freqs, f, indent=1, sort_keys=True)
print(f"\nSaved to runtime_opcode_freqs.json")
