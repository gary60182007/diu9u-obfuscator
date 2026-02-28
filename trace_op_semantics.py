"""
Trace per-opcode register effects to determine operation semantics.
Inject a metatable proxy on the register table to log reads/writes.
"""
import sys, time, json, re
sys.path.insert(0, '.')

with open(r'unobfuscator\pending crack\bloxburg_script.lua', 'r', encoding='utf-8', errors='replace') as f:
    source = f.read()

exec(open('run_luraph_test.py').read().split("print('Reading source...')")[0])
source = preprocess_luau(source)
from unobfuscator.utils.lua_runtime import LuaRuntimeWrapper, LuaRuntimeError

modified = source

# Find the 'local T=Y[y]' position 
unpack_pat = re.compile(r'local\s+Q,i,O,a,q,D,Y,Z,w,m,J\s*=\s*C\[')
um = unpack_pat.search(modified)
t_fetch_pat = re.compile(r'local\s+T\s*=\s*Y\[y\]')
t_m = t_fetch_pat.search(modified, um.start())
t_pos = t_m.start()
t_end = t_m.end()
# Find the semicolon
semi = modified.find(';', t_end)

# Inject detailed tracing after 'local T=Y[y];'
# For each unique opcode, capture the operand values and first 3 register writes
trace_inject = r"""
do
if not _G._otrace then
  _G._otrace={}
  _G._ocount=0
  _G._omax=500
end
if _G._ocount<_G._omax then
  local _e=_G._otrace[T]
  if not _e then
    _G._otrace[T]={n=0,samples={}}
    _e=_G._otrace[T]
  end
  if _e.n<3 then
    _e.n=_e.n+1
    local _s={T=T,Dy=D[y],ay=a[y],Zy=Z[y]}
    if q then _s.qy=q[y] end
    if w then _s.wy=w[y] end
    if m then _s.my=m[y] end
    local _snap={}
    for _i=0,40 do
      if s[_i]~=nil then
        local _tp=type(s[_i])
        if _tp=="number" then _snap[_i]=s[_i]
        elseif _tp=="string" then _snap[_i]="S"..#s[_i]
        elseif _tp=="boolean" then _snap[_i]=tostring(s[_i])
        elseif _tp=="table" then _snap[_i]="T"
        elseif _tp=="function" then _snap[_i]="F"
        else _snap[_i]=_tp end
      end
    end
    _s.before=_snap
    _e.samples[_e.n]=_s
    _G._ocount=_G._ocount+1
  end
end
end;
"""

modified = modified[:semi+1] + trace_inject + modified[semi+1:]
print(f"Injected trace at pos {semi+1}")

# Suppress VM execution error at entry
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

modified = preprocess_luau(modified)
runtime = LuaRuntimeWrapper(op_limit=15_000_000_000, timeout=600)
runtime._init_runtime()
runtime.lua.execute("_G._pn=0")
modified = runtime.suppress_vm_errors(modified)

print("Executing VM with detailed opcode tracing...")
t0 = time.time()
try:
    runtime.execute(modified)
except LuaRuntimeError as e:
    print(f"Stopped after {time.time()-t0:.1f}s: {str(e)[:200]}")

runtime.lua.execute("_G._op_count=0;_G._op_limit=10000000000")

# Extract the trace data
runtime.lua.execute("""
local _out = {}
for _op, _data in pairs(_G._otrace or {}) do
    for _i = 1, _data.n do
        local _s = _data.samples[_i]
        if _s then
            local _parts = {tostring(math.floor(_op))}
            table.insert(_parts, "D=" .. tostring(_s.Dy or "nil"))
            table.insert(_parts, "a=" .. tostring(_s.ay or "nil"))
            table.insert(_parts, "Z=" .. tostring(_s.Zy or "nil"))
            if _s.qy ~= nil then
                if type(_s.qy) == "string" then
                    local _safe = string.gsub(string.sub(_s.qy, 1, 20), "[^%w%p ]", "?")
                    table.insert(_parts, "q=S:" .. _safe)
                elseif type(_s.qy) == "number" then
                    table.insert(_parts, "q=" .. tostring(_s.qy))
                elseif type(_s.qy) == "table" then
                    local _v1 = _s.qy[1]
                    local _v2 = _s.qy[2]
                    table.insert(_parts, "q={" .. tostring(_v1) .. "," .. tostring(_v2) .. "}")
                else
                    table.insert(_parts, "q=" .. type(_s.qy))
                end
            end
            if _s.wy ~= nil then table.insert(_parts, "w=" .. tostring(_s.wy)) end
            if _s.my ~= nil then table.insert(_parts, "m=" .. tostring(_s.my)) end
            
            local _regs = {}
            if _s.before then
                for _k, _v in pairs(_s.before) do
                    table.insert(_regs, tostring(_k) .. "=" .. tostring(_v))
                end
            end
            table.sort(_regs)
            table.insert(_parts, "regs:{" .. table.concat(_regs, ",") .. "}")
            
            table.insert(_out, table.concat(_parts, "|"))
        end
    end
end
table.sort(_out)
_G._trace_out = table.concat(_out, "\\n")
""")

trace_out = str(runtime.lua.eval('_G._trace_out') or '')
print(f"\nTrace output ({len(trace_out)} chars):")

# Parse and analyze
lines = trace_out.split('\n')
op_samples = {}

for line in lines:
    if not line.strip():
        continue
    parts = line.split('|')
    if len(parts) < 4:
        continue
    try:
        op = int(parts[0])
    except:
        continue
    
    sample = {}
    for p in parts[1:]:
        if '=' in p and not p.startswith('regs:'):
            k, v = p.split('=', 1)
            sample[k] = v
        elif p.startswith('regs:'):
            sample['regs'] = p[5:]
    
    if op not in op_samples:
        op_samples[op] = []
    op_samples[op].append(sample)

print(f"\nOpcodes with samples: {len(op_samples)}")

# Analyze each opcode's behavior
# Key: look at which operands are non-zero and what types are in registers
print(f"\n{'='*90}")
print(f"OPCODE SEMANTIC ANALYSIS")
print(f"{'='*90}")

# Load opcode profiles for frequency data
with open('opcode_profiles.json', 'r', encoding='utf-8') as f:
    profiles = json.load(f)

for op in sorted(op_samples.keys()):
    samples = op_samples[op]
    prof = profiles.get(str(op), {})
    count = prof.get('count', 0)
    top_pat = ''
    if prof.get('patterns'):
        top_pat = max(prof['patterns'].items(), key=lambda x: x[1])[0]
    
    print(f"\n  Op {op:4d} ({count:5d}x in data, pattern={top_pat}):")
    for i, s in enumerate(samples[:2]):
        d = s.get('D', '?')
        a = s.get('a', '?')
        z = s.get('Z', '?')
        q = s.get('q', '')
        w = s.get('w', '')
        m_val = s.get('m', '')
        regs = s.get('regs', '')
        
        ops_str = f"D={d:>4s} a={a:>4s} Z={z:>4s}"
        if q: ops_str += f" q={q}"
        if w: ops_str += f" w={w}"
        if m_val: ops_str += f" m={m_val}"
        
        # Truncate regs display
        regs_short = regs[:80] + ('...' if len(regs) > 80 else '')
        print(f"    [{i}] {ops_str}")
        print(f"        regs: {regs_short}")

# Save trace data
with open('opcode_trace_data.json', 'w') as f:
    json.dump(op_samples, f, indent=1, default=str)
print(f"\nSaved to opcode_trace_data.json")
