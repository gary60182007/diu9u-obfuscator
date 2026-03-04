import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from unobfuscator.targets.ironbrew3 import IronBrew3Deobfuscator

with open('unobfuscator/pending crack/crew.lua', 'r', encoding='utf-8', errors='replace') as f:
    source = f.read()
if not source.strip().startswith('--ironbrew3'):
    source = '--ironbrew3\n' + source

deob = IronBrew3Deobfuscator()
deob.deobfuscate(source)

print("=== STDLIB MAP (VM params -> Lua stdlib) ===")
for k, v in sorted(deob.chunk.stdlib_map.items()):
    print(f"  {k} = {v}")

print(f"\n=== ENV MAP (obfuscated -> real) ===")
env_map = deob._build_env_map(deob.chunk.constants, deob.chunk.protos, deob.classifier.opcode_map)
for k, v in env_map.items():
    print(f"  {k} = {v}")

print(f"\n=== STRING CONSTANTS ({len(deob.chunk.constants)} total) ===")
for i, c in enumerate(deob.chunk.constants):
    if c.type == 'string':
        val = c.value[:100]
        print(f"  K[{i}] = \"{val}\"")

print(f"\n=== NON-STRING CONSTANTS ===")
for i, c in enumerate(deob.chunk.constants):
    if c.type != 'string':
        print(f"  K[{i}] = {c.type}:{c.value}")

print(f"\n=== PARAM NAMES ===")
print(f"  {deob.chunk.param_names}")

print(f"\n=== ENTRY PROTO ===")
print(f"  {deob.chunk.entry_proto_index}")

print(f"\n=== PROTO SUMMARY ===")
for i, p in enumerate(deob.chunk.protos):
    print(f"  Proto {i}: {len(p.instructions)} insts, {p.num_params} params, {p.num_upvals} upvals")
