"""Test IB3 VM repackager on crew.lua"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from unobfuscator.targets.ironbrew3 import IronBrew3Deobfuscator

with open('unobfuscator/pending crack/crew.lua', 'r', encoding='utf-8', errors='replace') as f:
    source = f.read()

if not source.strip().startswith('--ironbrew3'):
    source = '--ironbrew3\n' + source

deobf = IronBrew3Deobfuscator()
result = deobf.repackage(source)

if result is None:
    print("ERROR: repackage returned None")
    sys.exit(1)

out_path = 'unobfuscator/cracked script/crew_repack.lua'
with open(out_path, 'w', encoding='utf-8') as f:
    f.write(result)

lines = result.split('\n')
print(f"Repackaged VM script: {len(lines)} lines, {len(result)} chars")
print(f"Bytecode hex size: {len(result.split('\"')[1]) if '\"' in result else 'N/A'} hex chars")
print(f"Written to: {out_path}")

# Verify structure
has_wrap = 'function wrap(' in result
has_main = 'main(' in result
has_env = '_env' in result
print(f"Has wrap(): {has_wrap}")
print(f"Has main(): {has_main}")
print(f"Has _env: {has_env}")

# Check opcode coverage
import re
ops_used = set()
for m in re.finditer(r'op == (\d+)', result):
    ops_used.add(int(m.group(1)))
print(f"VM opcodes handled: {sorted(ops_used)}")

# Check serialized data
chunk = deobf.chunk
print(f"\nBytecode stats:")
print(f"  Constants: {len(chunk.constants)}")
print(f"  Protos: {len(chunk.protos)}")
print(f"  Total instructions: {sum(len(p.instructions) for p in chunk.protos)}")
print(f"  Entry proto: {chunk.entry_proto_index}")

# Check opcode distribution
from collections import Counter
op_counts = Counter()
for p in chunk.protos:
    for inst in p.instructions:
        op_name = deobf.classifier.opcode_map.get(inst.opcode, 'UNKNOWN')
        op_counts[op_name] += 1
print(f"\nOpcode distribution:")
for name, cnt in op_counts.most_common():
    print(f"  {name}: {cnt}")
