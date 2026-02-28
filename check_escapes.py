import re

with open('unobfuscator/target2.lua', 'r', encoding='utf-8', errors='replace') as f:
    src = f.read()

# Scan strings and find all escape sequences
i = 0
n = len(src)
escapes = {}

while i < n:
    # Skip long strings
    if src[i] == '[' and i + 1 < n and src[i+1] in ('=', '['):
        j = i + 1
        eq = 0
        while j < n and src[j] == '=':
            eq += 1
            j += 1
        if j < n and src[j] == '[':
            close = ']' + '=' * eq + ']'
            end = src.find(close, j + 1)
            if end >= 0:
                i = end + len(close)
                continue

    # Skip long comments
    if src[i:i+4] == '--[[' or (src[i:i+3] == '--[' and i+3 < n and src[i+3] == '='):
        j = i + 3
        eq = 0
        while j < n and src[j] == '=':
            eq += 1
            j += 1
        if j < n and src[j] == '[':
            close = ']' + '=' * eq + ']'
            end = src.find(close, j + 1)
            if end >= 0:
                i = end + len(close)
                continue

    # Skip line comments
    if src[i:i+2] == '--':
        while i < n and src[i] != '\n':
            i += 1
        continue

    # Process strings
    if src[i] in ('"', "'"):
        quote = src[i]
        i += 1
        while i < n and src[i] != quote:
            if src[i] == '\\' and i + 1 < n:
                esc_char = src[i+1]
                key = '\\' + esc_char
                if key not in escapes:
                    escapes[key] = 0
                escapes[key] += 1
                i += 2
                # Skip \z whitespace
                if esc_char == 'z':
                    while i < n and src[i] in ' \t\n\r':
                        i += 1
                continue
            i += 1
        if i < n:
            i += 1
        continue

    i += 1

print("Escape sequences found in strings:")
for k, v in sorted(escapes.items()):
    print(f"  {repr(k)}: {v}")

# Check for 'continue' usage
cont_count = len(re.findall(r'\bcontinue\b', src))
print(f"\n'continue' keyword: {cont_count}")

# Check for compound assignments (+=, -=, etc)
for op in ['+=', '-=', '*=', '/=', '..=']:
    cnt = src.count(op)
    if cnt:
        print(f"Compound assignment '{op}': {cnt}")

# Check for string interpolation
interp = src.count('`')
if interp:
    print(f"Backtick (string interpolation): {interp}")
