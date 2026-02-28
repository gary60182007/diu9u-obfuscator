"""Trace how Luraph VM resolves table keys — find proxy __index and string decryption."""
import re, json

text = open('unobfuscator/pending crack/bloxburg_script_preprocessed.lua', encoding='utf-8', errors='replace').read()
consts = json.load(open('luraph_strings_full.json', encoding='utf-8'))

print(f"Script length: {len(text)}")

# 1. Find __index references — proxy setup
print("=== __index references ===")
for m in re.finditer(r'__index', text):
    ctx = text[max(0,m.start()-30):m.start()+150]
    print(f"  pos {m.start()}: ...{ctx[:120]}...")

# 2. Find setmetatable calls — proxy creation
print("\n=== setmetatable references ===")
for m in re.finditer(r'setmetatable', text):
    ctx = text[max(0,m.start()-20):m.start()+200]
    print(f"  pos {m.start()}: ...{ctx[:150]}...")

# 3. Find XOR/decryption patterns near string operations
print("\n=== XOR/bxor near string operations ===")
for m in re.finditer(r'bxor.*string|string.*bxor', text[:100000]):
    ctx = text[max(0,m.start()-20):m.start()+100]
    print(f"  pos {m.start()}: {ctx[:80]}")

# 4. Find string.char patterns (often used in decryption)
print("\n=== string.char calls ===")
hits = list(re.finditer(r'string\.char', text[:100000]))
print(f"  {len(hits)} hits in first 100k chars")
for m in hits[:5]:
    ctx = text[max(0,m.start()-20):m.start()+100]
    print(f"  pos {m.start()}: {ctx[:80]}")

# 5. Check garbled strings — are they consistent length with known API names?
print("\n=== Garbled string analysis ===")
garbled = []
for k, v in sorted(consts.items(), key=lambda x: int(x[0])):
    if v['type'] != 's': continue
    t = v.get('text', '')
    if not t.isascii() or not all(c.isprintable() or c in '\r\n\t' for c in t):
        garbled.append((int(k), len(t), v.get('raw', '')))

print(f"Garbled strings: {len(garbled)}")
api_lens = {
    3: ['IsA', 'new'],
    4: ['Name', 'game', 'Text', 'Size', 'Part', 'Fire', 'Wait', 'Play', 'Stop'],
    5: ['Clone', 'Value', 'Color', 'Event', 'Print'],
    6: ['Parent', 'Player', 'String', 'Remove'],
    7: ['Destroy', 'Players', 'Enabled', 'Visible', 'Changed', 'Connect'],
    8: ['Instance', 'Humanoid', 'Position', 'Material', 'Anchored'],
    9: ['Character', 'Workspace', 'ClassName'],
    10: ['GetService', 'GetChildren'],
    11: ['LocalPlayer', 'FindFirstChild', 'WaitForChild'],
}
for idx, length, raw_hex in garbled:
    candidates = api_lens.get(length, [])
    if candidates:
        print(f"  const[{idx}] len={length} hex={raw_hex[:20]} → possible: {candidates}")
