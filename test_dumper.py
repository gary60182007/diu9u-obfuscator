import sys, time, json
sys.path.insert(0, '.')

with open(r'unobfuscator\pending crack\bloxburg_script.lua', 'r', encoding='utf-8', errors='replace') as f:
    source = f.read()

exec(open('run_luraph_test.py').read().split("print('Reading source...')")[0])
source = preprocess_luau(source)
print(f"Preprocessed source: {len(source)} chars")

from unobfuscator.utils.lua_runtime import LuaRuntimeWrapper, LuaRuntimeError

runtime = LuaRuntimeWrapper(op_limit=2_000_000_000, timeout=120.0)
runtime._init_runtime()

print("Injecting bytecode dumper...")
modified = runtime.inject_bytecode_dumper(source)
if modified != source:
    diff_pos = next(i for i, (a, b) in enumerate(zip(source, modified)) if a != b)
    print(f"  Hook injected at position {diff_pos}")
    print(f"  Context: ...{modified[diff_pos:diff_pos+200]}...")
else:
    print("  WARNING: No hook injected!")
    sys.exit(1)

print("Suppressing VM errors...")
modified = runtime.suppress_vm_errors(modified)

print("Executing...")
t0 = time.time()
try:
    runtime.execute(modified)
    print(f"Completed in {time.time()-t0:.1f}s")
except LuaRuntimeError as e:
    print(f"Error after {time.time()-t0:.1f}s: {str(e)[:200]}")

print("\nExtracting prototypes...")
protos = runtime.extract_prototypes()
print(f"Extracted {len(protos)} prototypes")

for i, p in enumerate(protos[:20]):
    pid = p.get('id', '?')
    is_v14 = p.get('is_v14', False)
    if is_v14:
        raw = p.get('raw_fields', {})
        field_summary = []
        for fi in sorted(raw.keys()):
            val = raw[fi]
            if isinstance(val, list):
                field_summary.append(f"f{fi}:arr[{len(val)}]")
            elif isinstance(val, (int, float)):
                field_summary.append(f"f{fi}:{val}")
            else:
                field_summary.append(f"f{fi}:{type(val).__name__}")
        print(f"  Proto #{pid} (v14): {', '.join(field_summary)}")
    else:
        nops = p.get('num_instructions', 0)
        print(f"  Proto #{pid} (legacy): type={p.get('type',0)}, regs={p.get('numregs',0)}, ops={nops}")

if protos:
    with open('extracted_protos.json', 'w') as f:
        json.dump(protos, f, indent=2, default=str)
    print(f"\nSaved to extracted_protos.json")
