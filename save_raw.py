import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from unobfuscator.core.sandbox import LuaSandbox
from unobfuscator.passes.state_machine_deobf import _looks_like_state_machine

with open('unobfuscator/target1.lua', 'r', encoding='utf-8', errors='replace') as f:
    source = f.read()

if not _looks_like_state_machine(source):
    print("Not a state machine pattern")
    sys.exit(1)

sb = LuaSandbox(op_limit=50_000_000, timeout=60.0)
try:
    sb.execute(source)
except Exception:
    pass

if sb.intercepted_loads:
    raw = max(sb.intercepted_loads, key=len)
    out_path = 'unobfuscator/target1_raw.lua'
    raw_bytes = raw.encode('latin-1', errors='replace')
    with open(out_path, 'wb') as f:
        f.write(raw_bytes)
    print(f"Saved raw loadstring content: {len(raw)} chars, {len(raw_bytes)} bytes -> {out_path}")
else:
    print("No loadstring intercepted")
