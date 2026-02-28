import struct, json, re

with open(r'unobfuscator/cracked script/buffer_1_1064652.bin', 'rb') as f:
    data = f.read()

print(f"Buffer size: {len(data):,} bytes")
print(f"Non-zero bytes: {sum(1 for b in data if b != 0):,}")

strings = []
i = 0
while i < len(data) - 3:
    if 32 <= data[i] < 127:
        j = i
        while j < len(data) and 32 <= data[j] < 127:
            j += 1
        if j - i >= 3:
            s = data[i:j].decode('ascii', errors='replace')
            strings.append((i, s))
        i = j
    else:
        i += 1

print(f"\nTotal ASCII strings (len>=3): {len(strings)}")

roblox_kw = ['game', 'workspace', 'Instance', 'Players', 'GetService', 'FindFirstChild',
             'WaitForChild', 'GetChildren', 'Character', 'Humanoid', 'LocalPlayer',
             'RemoteEvent', 'RemoteFunction', 'Fire', 'Invoke', 'Connect',
             'Touched', 'Changed', 'Added', 'Removing', 'RenderStepped', 'Heartbeat',
             'UserInputService', 'RunService', 'TweenService', 'HttpService',
             'ReplicatedStorage', 'StarterGui', 'CoreGui', 'Lighting',
             'ScreenGui', 'Frame', 'TextLabel', 'TextButton', 'ImageLabel',
             'Part', 'Model', 'Folder', 'Tool', 'Script',
             'Position', 'CFrame', 'Size', 'Color', 'Transparency',
             'Teleport', 'Kick', 'Ban', 'Destroy', 'Clone',
             'Enabled', 'Visible', 'Text', 'BackgroundColor',
             'Plot', 'Build', 'Place', 'Furniture', 'Room', 'Wall', 'Floor',
             'Roof', 'Door', 'Window', 'Stair', 'Pool', 'Garden',
             'Save', 'Load', 'Serialize', 'Deserialize',
             'Money', 'Cash', 'Blockbux', 'Gamepass', 'Premium',
             'Job', 'Work', 'Cook', 'Pizza', 'Delivery', 'Employee',
             'Mood', 'Hunger', 'Energy', 'Hygiene', 'Fun',
             'Speed', 'Fly', 'Noclip', 'ESP', 'Aimbot', 'Infinite',
             'Anti', 'Detect', 'Bypass', 'Exploit', 'Hack', 'Cheat',
             'Webhook', 'Discord', 'Key', 'License', 'HWID', 'Whitelist',
             'http', 'https', 'api', '.gg', '.com', '.io', '.xyz',
             'pcall', 'xpcall', 'loadstring', 'require', 'spawn', 'coroutine',
             'setmetatable', 'getmetatable', 'rawget', 'rawset',
             'string', 'table', 'math', 'bit32', 'debug', 'os',
             'print', 'warn', 'error', 'assert', 'select', 'pairs', 'ipairs',
             'tostring', 'tonumber', 'type', 'typeof',
             'getfenv', 'setfenv', 'newproxy',
             'Drawing', 'Raycast', 'WorldToViewportPoint',
             'Mouse', 'Keyboard', 'InputBegan', 'InputEnded',
             'PointToWorldSpace', 'fakePlot',
             'auto', 'build', 'place', 'grid', 'snap', 'rotate', 'move']

print("\n" + "="*70)
print("CATEGORIZED STRINGS FROM BYTECODE BUFFER")
print("="*70)

game_related = []
lua_stdlib = []
urls = []
interesting = []
short_tokens = []

for offset, s in strings:
    s_lower = s.lower()
    
    matched = False
    for kw in roblox_kw:
        if kw.lower() in s_lower:
            interesting.append((offset, s))
            matched = True
            break
    
    if 'http' in s_lower or '://' in s or '.gg' in s or '.com' in s:
        urls.append((offset, s))
        matched = True
    
    if not matched and len(s) >= 4:
        if s[0].isupper() and any(c.islower() for c in s):
            game_related.append((offset, s))
        elif len(s) >= 6:
            interesting.append((offset, s))

print("\n--- URLS ---")
for o, s in urls:
    print(f"  @{o:8d}: {s[:200]}")

print("\n--- ROBLOX/GAME KEYWORDS ---")
for o, s in sorted(set(interesting), key=lambda x: x[0]):
    if len(s) >= 3 and len(s) < 200:
        print(f"  @{o:8d}: {s}")

print("\n--- CAMELCASE / CLASS NAMES ---")
for o, s in sorted(set(game_related), key=lambda x: x[0]):
    if len(s) >= 4 and len(s) < 200:
        print(f"  @{o:8d}: {s}")

print("\n--- ALL STRINGS SORTED BY LENGTH (top 200) ---")
by_len = sorted(set(s for _, s in strings if len(s) >= 5), key=lambda x: -len(x))
for s in by_len[:200]:
    if len(s) < 500:
        print(f"  [{len(s):4d}] {s}")

with open(r'unobfuscator/cracked script/buffer_strings.json', 'w', encoding='utf-8') as f:
    json.dump({
        'total_strings': len(strings),
        'urls': [(o, s) for o, s in urls],
        'interesting': [(o, s) for o, s in interesting if len(s) < 500],
        'game_related': [(o, s) for o, s in game_related if len(s) < 500],
        'all_strings': [(o, s) for o, s in strings if len(s) >= 4 and len(s) < 500],
    }, f, indent=2, ensure_ascii=False)

print("\n\nSaved analysis to buffer_strings.json")
