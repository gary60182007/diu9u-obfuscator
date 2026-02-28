from __future__ import annotations
import argparse
import sys
import os
import time
from typing import Optional


def main():
    parser = argparse.ArgumentParser(
        prog='lua-unobfuscator',
        description='Universal Lua 5.1 Unobfuscator - Supports IronBrew2, PSU, Moonsec v3, Luraph',
    )
    parser.add_argument('input', help='Input Lua file to deobfuscate')
    parser.add_argument('-o', '--output', help='Output file (default: stdout)')
    parser.add_argument('-t', '--target', choices=['auto', 'ironbrew', 'ironbrew3', 'psu', 'moonsec', 'luraph', 'generic'],
                        default='auto', help='Target obfuscator type (default: auto-detect)')
    parser.add_argument('--no-rename', action='store_true', help='Skip variable rename recovery')
    parser.add_argument('--no-decrypt', action='store_true', help='Skip string decryption')
    parser.add_argument('--no-unwrap', action='store_true', help='Skip loadstring unwrapping')
    parser.add_argument('--no-junk', action='store_true', help='Skip junk code removal')
    parser.add_argument('--no-simplify', action='store_true', help='Skip expression simplification')
    parser.add_argument('--no-cf', action='store_true', help='Skip control flow restoration')
    parser.add_argument('--op-limit', type=int, default=20_000_000, help='Sandbox operation limit')
    parser.add_argument('--timeout', type=float, default=60.0, help='Sandbox timeout in seconds')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    parser.add_argument('--stats', action='store_true', help='Print pipeline statistics')
    parser.add_argument('--inspect', action='store_true',
                        help='Output intermediate analysis JSON (for Luraph: opcode map, prototypes, constants)')

    args = parser.parse_args()

    if not os.path.isfile(args.input):
        print(f"Error: File not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    with open(args.input, 'r', encoding='utf-8', errors='replace') as f:
        source = f.read()

    if args.verbose:
        print(f"[*] Read {len(source)} chars from {args.input}", file=sys.stderr)

    try:
        inspect_path = None
        if args.inspect:
            base = os.path.splitext(args.input)[0]
            inspect_path = base + '_inspect.json'

        result, stats = run_deobfuscation(
            source,
            target=args.target,
            no_rename=args.no_rename,
            no_decrypt=args.no_decrypt,
            no_unwrap=args.no_unwrap,
            no_junk=args.no_junk,
            no_simplify=args.no_simplify,
            no_cf=args.no_cf,
            op_limit=args.op_limit,
            timeout=args.timeout,
            verbose=args.verbose,
            inspect_path=inspect_path,
        )

        if inspect_path and os.path.isfile(inspect_path):
            print(f"[*] Inspect data saved to {inspect_path}", file=sys.stderr)
    except Exception as e:
        print(f"Error during deobfuscation: {type(e).__name__}: {e}", file=sys.stderr)
        if args.verbose:
            import traceback
            traceback.print_exc(file=sys.stderr)
        sys.exit(1)

    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(result)
        if args.verbose:
            print(f"[*] Wrote {len(result)} chars to {args.output}", file=sys.stderr)
    else:
        print(result)

    if args.stats or args.verbose:
        print(stats.summary(), file=sys.stderr)


def run_deobfuscation(source: str, target: str = 'auto',
                      no_rename: bool = False, no_decrypt: bool = False,
                      no_unwrap: bool = False, no_junk: bool = False,
                      no_simplify: bool = False, no_cf: bool = False,
                      op_limit: int = 20_000_000, timeout: float = 60.0,
                      verbose: bool = False, inspect_path: str = None):
    from .core.sandbox import LuaSandbox
    from .utils.pipeline import create_default_pipeline, create_vm_pipeline, PipelineStats

    sandbox = LuaSandbox(op_limit=op_limit, timeout=timeout)

    if target == 'auto':
        detected = _detect_target(source, sandbox)
        if verbose:
            print(f"[*] Auto-detected obfuscator: {detected or 'generic'}", file=sys.stderr)
        target_type = detected or 'generic'
    else:
        target_type = target

    if target_type in ('ironbrew', 'ironbrew3', 'psu', 'moonsec', 'luraph', 'generic_vm'):
        pipeline = create_vm_pipeline(target_type, sandbox, inspect_path=inspect_path)
    else:
        pipeline = create_default_pipeline(sandbox)

    disabled = set()
    if no_rename: disabled.add('rename_recovery')
    if no_decrypt: disabled.add('string_decrypt')
    if no_unwrap: disabled.add('loadstring_unwrap')
    if no_junk:
        disabled.add('junk_removal')
        disabled.add('dead_code_elimination')
        disabled.add('dead_code_final')
    if no_simplify:
        disabled.add('normalize')
        disabled.add('mba_simplify')
        disabled.add('expr_simplify')
        disabled.add('normalize_final')
        disabled.add('expr_simplify_final')
    if no_cf: disabled.add('control_flow_restore')

    for pc in pipeline.passes:
        if pc.name in disabled:
            pc.enabled = False

    if verbose:
        def progress(name, current, total):
            print(f"[*] Running pass {current}/{total}: {name}", file=sys.stderr)
        pipeline.set_progress_callback(progress)

    return pipeline.run(source)


def _detect_target(source: str, sandbox) -> Optional[str]:
    from .core.lua_parser import parse as lua_parse
    from .core.lua_emitter import emit
    from .targets.vm_lift import VMPatternMatcher

    try:
        tree = lua_parse(source)
    except Exception:
        return None

    pm = VMPatternMatcher()
    detected = pm.detect_vm_type(tree)
    if detected and detected != 'generic_vm':
        return detected

    from .targets.ironbrew3 import IronBrew3Deobfuscator
    if IronBrew3Deobfuscator.detect(source):
        return 'ironbrew3'

    markers = {
        'ironbrew': ['IronBrew', 'IBRW', 'IB2'],
        'psu': ['PSU', 'Prometheus'],
        'moonsec': ['MoonSec', 'moonsec', 'MSEC'],
        'luraph': ['Luraph', 'luraph', 'LRPH'],
    }
    for name, keywords in markers.items():
        for kw in keywords:
            if kw in source:
                return name

    if pm.is_vm_obfuscated(tree):
        return 'generic_vm'

    if 'loadstring' in source or 'load(' in source:
        return 'loadstring_wrapper'

    return None


if __name__ == '__main__':
    main()
