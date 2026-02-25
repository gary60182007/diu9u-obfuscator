import bytecode_vm
import sys, os

SCRIPTS = [
    (r"c:\Users\gary6\AppData\Local\Potassium\workspace\dump_Casual_13997264379\casual_esp.lua",
     "casual_esp_obf.lua"),
    (r"c:\Users\gary6\OneDrive\Desktop\code stuff\cursed tank\games\forest\forest_noclip.lua",
     "forest_noclip_obf.lua"),
    (r"c:\Users\gary6\AppData\Local\Potassium\workspace\dump_The_Final_Stand_2_-_Career_2899434514\tfs2_exploit.lua",
     "tfs2_exploit_obf.lua"),
]

OUT_DIR = r"c:\Users\gary6\OneDrive\Desktop\code stuff\diu9u_obfuscator\obfuscated"
os.makedirs(OUT_DIR, exist_ok=True)

for src_path, out_name in SCRIPTS:
    print(f"\n{'='*60}")
    print(f"Obfuscating: {os.path.basename(src_path)}")
    with open(src_path, 'r', encoding='utf-8') as f:
        source = f.read()
    print(f"  Source size: {len(source)} chars, {source.count(chr(10))} lines")
    try:
        result = bytecode_vm.compile_to_bytecode_vm(source, use_nsfw=True, junk_ops=15, vm_layers=1)
        out_path = os.path.join(OUT_DIR, out_name)
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write(result)
        print(f"  OK! Output: {len(result)} chars -> {out_name}")
    except Exception as e:
        print(f"  FAIL: {type(e).__name__}: {e}")
