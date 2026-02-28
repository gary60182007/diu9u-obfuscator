import re

with open(r'unobfuscator\pending crack\bloxburg_script.lua', 'r', encoding='utf-8', errors='replace') as f:
    source = f.read()

# Show the overall structure - first 10 lines and last portion
lines = source.split('\n')
print(f"Total lines: {len(lines)}")
for i, line in enumerate(lines):
    print(f"Line {i+1}: len={len(line)}, start={line[:200]}")
    if i > 12:
        break

# The first few lines contain the outer code
# Let me pretty-print them
print(f"\n=== OUTER CODE (before return table) ===")
for i in range(min(len(lines), 11)):
    line = lines[i]
    if len(line) > 200:
        # Pretty print by splitting on semicolons
        parts = line.replace(';', ';\n').split('\n')
        print(f"\n-- Line {i+1} ({len(line)} chars, {len(parts)} statements) --")
        for j, part in enumerate(parts[:100]):
            part = part.strip()
            if part:
                print(f"  {j:3d}: {part[:200]}")
        if len(parts) > 100:
            print(f"  ... ({len(parts)-100} more statements)")
    else:
        print(f"Line {i+1}: {line}")

# Also check the END of the source
print(f"\n=== END OF SOURCE ===")
end_text = source[-2000:]
# Find where the return table ends
last_paren = end_text.rfind(')')
print(f"Last ')' at offset {len(source) - 2000 + last_paren}")
end_after_table = end_text[last_paren:]
print(f"After last ')': {repr(end_after_table[:200])}")

# Check if there's code after the return table
# The source might be: code; return(table); more_code
# Or: return(table)(...args)
# The latter would make the return table a function call

# Check the very end of the source
print(f"\nLast 500 chars:")
for part in source[-500:].replace(';', ';\n').split('\n'):
    part = part.strip()
    if part:
        print(f"  {part[:200]}")
