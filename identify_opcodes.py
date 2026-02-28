"""Identify unknown opcodes by runtime instrumentation.
Inject tracing that captures register changes for specific opcodes."""
import sys, os, time
from lupa import LuaRuntime

with open('unobfuscator/target2_lua51.lua', 'r', encoding='utf-8') as f:
    converted = f.read()

lua = LuaRuntime(unpack_returned_tuples=True)

# Load all the shims from deobf_t2_lupa.py (copy the shim setup)
lua.execute(open('deobf_t2_lupa.py', 'r').read().split('lua.execute("""')[1].split('"""')[0])
lua.execute(open('deobf_t2_lupa.py', 'r').read().split('lua.execute("""')[2].split('"""')[0])
lua.execute(open('deobf_t2_lupa.py', 'r').read().split('lua.execute("""')[3].split('"""')[0])
print("Shims loaded, this approach is too fragile. Using direct approach instead.")
