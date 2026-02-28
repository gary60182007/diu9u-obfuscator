import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from unobfuscator.core.lua_lexer import tokenize
from unobfuscator.core.lua_parser import parse
from unobfuscator.core.lua_emitter import emit

with open('unobfuscator/target1.lua', 'r', encoding='utf-8', errors='replace') as f:
    source = f.read()

print(f"[*] Source size: {len(source)} chars")

try:
    tree = parse(source)
    print(f"[*] Parse OK, {len(tree.stmts)} top-level statements")
    roundtrip = emit(tree)
    print(f"[*] Emit OK, {len(roundtrip)} chars")
except Exception as e:
    print(f"[!] Parse/emit error: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n--- Attempting deobfuscation ---")
try:
    from unobfuscator.unobfuscator import run_deobfuscation
    result, stats = run_deobfuscation(source, target='auto', verbose=True)
    print(f"\n[*] Result size: {len(result)} chars")
    print(stats.summary())
    print("\n--- DEOBFUSCATED OUTPUT ---")
    print(result[:5000])
    if len(result) > 5000:
        print(f"\n... ({len(result) - 5000} more chars)")
except Exception as e:
    print(f"[!] Deobfuscation error: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
