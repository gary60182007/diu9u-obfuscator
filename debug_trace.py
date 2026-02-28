import bytecode_vm, random, re, sys, io, copy, time, struct
from bytecode_vm import *

src = open('unobfuscated/tfs2_exploit.lua','r',encoding='utf-8').read()

print("=== Testing junk opcode fix (200 seeds) ===")
errors = 0
t0 = time.time()
for seed in range(200):
    random.seed(seed)
    old_stdout = sys.stdout
    sys.stdout = io.StringIO()
    try:
        output = generate_bytecode_vm(src, use_nsfw=True, junk_ops=15, debug_mode=False)
        captured = sys.stdout.getvalue()
    except Exception as e:
        sys.stdout = old_stdout
        print(f"  SEED={seed}: EXCEPTION: {e}")
        errors += 1
        continue
    finally:
        sys.stdout = old_stdout

    if 'VERIFIER' in captured:
        for line in captured.strip().split('\n'):
            if 'VERIFIER' in line or 'issue' in line.lower():
                print(f"  SEED={seed}: {line.strip()}")
        errors += 1

    if len(output) < 500:
        print(f"  SEED={seed}: suspiciously short output ({len(output)} chars)")
        errors += 1

elapsed = time.time() - t0
print(f"\n{errors} errors out of 200 seeds ({elapsed:.1f}s)")
if errors == 0:
    print("ALL 200 SEEDS PASSED")

print("\n=== Regenerating obfuscated output (debug_mode=False) ===")
random.seed(42)
output = generate_bytecode_vm(src, use_nsfw=True, junk_ops=15, debug_mode=False)
with open('obfuscated/tfs2_exploit_obf.lua', 'w', encoding='utf-8') as f:
    f.write(output)
print(f"Written {len(output)} chars to obfuscated/tfs2_exploit_obf.lua")
