#!/usr/bin/env python3
"""
8====D~~~ diu9u Obfuscator v5.1 ~~~D====8

Luau-compatible Lua obfuscator with Bytecode VM, instruction fusion,
register remapping, anti-debug, control flow flattening, and more.

The core obfuscation engine is closed-source.
See obfuscated/ for output examples.

Contact: discord.gg/BzDz9bmKDP
"""
import sys
import os

def main():
    print("=" * 55)
    print("  8====D~~~ diu9u Obfuscator v5.1 ~~~D====8")
    print("=" * 55)
    print()

    try:
        import bytecode_vm
    except ImportError:
        print("[!] Core engine not found.")
        print()
        print("    This is the public showcase repository.")
        print("    The obfuscation engine (bytecode_vm) is closed-source.")
        print()
        print("    Check obfuscated/ for output examples.")
        print("    Contact: discord.gg/BzDz9bmKDP")
        print()
        sys.exit(1)

    if len(sys.argv) < 2:
        print("Usage: python obfuscate_scripts.py <input.lua> [output.lua]")
        print()
        print("Options:")
        print("  --debug    Enable debug mode with pcall tracing")
        print("  --nsfw     Use NSFW naming style (default: on)")
        print("  --junk N   Number of junk operations (default: 15)")
        sys.exit(0)

    debug_mode = '--debug' in sys.argv
    use_nsfw = '--no-nsfw' not in sys.argv
    junk_ops = 15
    for i, a in enumerate(sys.argv):
        if a == '--junk' and i + 1 < len(sys.argv):
            junk_ops = int(sys.argv[i + 1])

    args = [a for a in sys.argv[1:] if not a.startswith('--') and not (len(sys.argv) > 2 and sys.argv[sys.argv.index(a)-1] == '--junk')]
    if not args:
        print("[!] No input file specified.")
        sys.exit(1)

    src_path = args[0]
    out_path = args[1] if len(args) > 1 else os.path.splitext(src_path)[0] + '_obf.lua'

    print(f"Input:  {src_path}")
    print(f"Output: {out_path}")
    if debug_mode:
        print("[DEBUG MODE ENABLED]")

    with open(src_path, 'r', encoding='utf-8') as f:
        source = f.read()
    print(f"Source: {len(source)} chars, {source.count(chr(10))} lines")

    result = bytecode_vm.compile_to_bytecode_vm(
        source, use_nsfw=use_nsfw, junk_ops=junk_ops,
        vm_layers=1, debug_mode=debug_mode
    )

    os.makedirs(os.path.dirname(out_path) or '.', exist_ok=True)
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(result)
    print(f"OK! {len(result)} chars -> {out_path}")

if __name__ == '__main__':
    main()
