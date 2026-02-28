from unobfuscator.core.sandbox import LuaSandbox

sb = LuaSandbox()
sb.execute("""
local t = {1,2,3}
for i,v in ipairs(t) do
  print(i, v)
end
print(string.char(72,101,108,108,111))
print(string.byte("A"))
local f = loadstring("return 1+2")
print(f())
""")
print("Output:", sb.output)
print("Loads:", sb.intercepted_loads)
