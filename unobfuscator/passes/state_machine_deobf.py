from __future__ import annotations
import re
from typing import List, Optional, Tuple
from ..core import lua_ast as ast
from ..core.lua_parser import parse as lua_parse
from ..core.sandbox import LuaSandbox, LuaError


def deobfuscate_state_machine(tree: ast.Block, original_source: str = None,
                              sandbox: LuaSandbox = None) -> Tuple[ast.Block, int]:
    source = original_source
    if not source:
        from ..core.lua_emitter import emit
        source = emit(tree)

    if not _looks_like_state_machine(source):
        return tree, 0

    result = _sandbox_execute(source, sandbox)
    if result:
        try:
            new_tree = lua_parse(result)
            return new_tree, 1
        except Exception:
            pass
    return tree, 0


def _looks_like_state_machine(source: str) -> bool:
    if len(source) < 5000:
        return False
    has_decoder = bool(re.search(r'string\.byte\([^)]+\)\s*[+-]\s*[\d(]', source[:10000]))
    has_table = bool(re.search(r'local\s+\w+\s*=\s*\{\s*\}', source[:10000]))
    has_while = 'while' in source[:20000]
    has_concat = 'table.concat' in source
    return has_decoder and has_table and has_while and has_concat


def _sandbox_execute(source: str, sandbox: LuaSandbox = None) -> Optional[str]:
    sb = sandbox or LuaSandbox(op_limit=50_000_000, timeout=60.0)
    sb.intercepted_loads.clear()
    try:
        sb.execute(source)
    except LuaError:
        pass
    except Exception:
        pass

    if sb.intercepted_loads:
        longest = max(sb.intercepted_loads, key=len)
        if len(longest) > 50:
            return longest
    return None
