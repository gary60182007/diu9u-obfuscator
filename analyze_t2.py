import sys, os, traceback
sys.path.insert(0, os.path.dirname(__file__))

from unobfuscator.core.sandbox import LuaSandbox, LuaError, LuaTable, LuaClosure, Environment
from unobfuscator.core import lua_ast as ast

with open('unobfuscator/target2.lua', 'r', encoding='utf-8', errors='replace') as f:
    src = f.read()

print(f"Size: {len(src)} chars")

sb = LuaSandbox(op_limit=200_000_000, timeout=120.0)

# Trace the If body stmt-by-stmt to find where it fails
orig_exec_block = sb._exec_block
traced_block = [False]

def patched_exec_block(block, env):
    if traced_block[0]:
        return orig_exec_block(block, env)
    # Check if this is the If body (T[33]~=T[12]) by checking parent env
    e = env
    depth = 0
    found_B = False
    while e and depth < 5:
        if '_' in e.vars and 'C' in e.vars and 'I' in e.vars:
            found_B = True
            break
        depth += 1
        e = e.parent
    if found_B and len(block.stmts) == 7 and sb.ops > 5500:
        traced_block[0] = True
        print(f"\n=== Executing If body (7 stmts) at ops={sb.ops} ===")
        for i, stmt in enumerate(block.stmts):
            print(f"  About to run stmt[{i}]: {type(stmt).__name__} at ops={sb.ops}")
            try:
                sb._exec_stmt(stmt, env)
            except LuaError as le:
                print(f"  ERROR in stmt[{i}]: {le}")
                raise
            except Exception as ex:
                print(f"  EXCEPTION in stmt[{i}]: {type(ex).__name__}: {ex}")
                raise
        return
    return orig_exec_block(block, env)

sb._exec_block = patched_exec_block

try:
    result = sb.execute(src)
    print(f"\nExecute returned: {type(result)} len={len(result) if result else 0}")
except LuaError as e:
    print(f"\nLuaError: {e}")
except Exception as e:
    print(f"\nError: {type(e).__name__}: {e}")
    traceback.print_exc()

print(f"\nIntercepted loads: {len(sb.intercepted_loads)}")
print(f"Ops used: {sb.ops}")
