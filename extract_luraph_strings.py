import re
import json
from collections import Counter

with open(r'unobfuscator\pending crack\bloxburg_script.lua', 'r', encoding='utf-8', errors='replace') as f:
    source = f.read()

print(f"Script size: {len(source):,} chars")

strings = []
i = 0
n = len(source)
while i < n:
    if source[i] in ('"', "'"):
        quote = source[i]
        j = i + 1
        while j < n and source[j] != quote:
            if source[j] == '\\':
                j += 1
            j += 1
        if j < n:
            raw = source[i+1:j]
            try:
                s = raw.encode('utf-8').decode('unicode_escape')
            except:
                s = raw
            if len(s) >= 2:
                strings.append(s)
        i = j + 1
    else:
        i += 1

print(f"\nTotal strings extracted: {len(strings)}")
print(f"Unique strings: {len(set(strings))}")

roblox_services = []
api_calls = []
urls = []
events = []
property_names = []
interesting = []

for s in set(strings):
    if 'http' in s.lower() or 'www.' in s.lower() or '.gg' in s or '.com' in s:
        urls.append(s)
    if s in ('Players', 'Workspace', 'ReplicatedStorage', 'ServerStorage',
             'StarterGui', 'StarterPack', 'Lighting', 'SoundService',
             'TweenService', 'UserInputService', 'RunService', 'HttpService',
             'MarketplaceService', 'DataStoreService', 'Teams', 'Chat',
             'TextChatService', 'ProximityPromptService', 'CollectionService',
             'PathfindingService', 'PhysicsService', 'GuiService',
             'VirtualInputManager', 'CoreGui', 'StarterPlayer',
             'NetworkClient', 'ReplicatedFirst'):
        roblox_services.append(s)
    if 'Changed' in s or 'Added' in s or 'Removing' in s or 'Event' in s or \
       'Touched' in s or 'Activated' in s or 'InputBegan' in s or 'Heartbeat' in s or \
       'Stepped' in s or 'RenderStepped' in s or 'ChildAdded' in s:
        events.append(s)
    if any(kw in s for kw in ['Remote', 'Fire', 'Invoke', 'Bindable', 'Signal',
                               'function', 'Instance', 'pcall', 'spawn', 'coroutine',
                               'GetService', 'FindFirstChild', 'WaitForChild']):
        api_calls.append(s)
    if any(kw in s.lower() for kw in ['plot', 'build', 'place', 'furniture', 'room',
                                        'wall', 'floor', 'roof', 'door', 'window',
                                        'stair', 'pool', 'garden', 'house',
                                        'save', 'load', 'position', 'rotation',
                                        'serialize', 'deserialize', 'json',
                                        'bloxburg', 'auto', 'speed', 'money',
                                        'gamepass', 'premium', 'mood', 'skill',
                                        'job', 'work', 'cook', 'pizza', 'delivery',
                                        'hunger', 'energy', 'hygiene', 'fun',
                                        'blockbux', 'employee', 'cashier',
                                        'exploit', 'hack', 'cheat', 'bypass',
                                        'anti', 'detect', 'kick', 'ban',
                                        'teleport', 'noclip', 'fly', 'speed',
                                        'infinite', 'god', 'esp', 'aimbot',
                                        'webhook', 'discord', 'key', 'license',
                                        'obfuscat', 'encrypt', 'decrypt',
                                        'whitelist', 'blacklist', 'hwid']):
        interesting.append(s)

print("\n" + "="*60)
print("ROBLOX SERVICES REFERENCED:")
print("="*60)
for s in sorted(set(roblox_services)):
    print(f"  - {s}")

print("\n" + "="*60)
print("URLS FOUND:")
print("="*60)
for s in sorted(set(urls)):
    print(f"  - {s}")

print("\n" + "="*60)
print("EVENTS:")
print("="*60)
for s in sorted(set(events)):
    print(f"  - {s}")

print("\n" + "="*60)
print("API/FUNCTION REFERENCES:")
print("="*60)
for s in sorted(set(api_calls)):
    print(f"  - {s}")

print("\n" + "="*60)
print("INTERESTING STRINGS (game/exploit related):")
print("="*60)
for s in sorted(set(interesting)):
    if len(s) < 200:
        print(f"  - {s}")

print("\n" + "="*60)
print("ALL UNIQUE STRINGS (len >= 3, sorted by length):")
print("="*60)
all_unique = sorted(set(s for s in strings if len(s) >= 3), key=lambda x: (-len(x), x))
for s in all_unique[:300]:
    if len(s) < 300:
        print(f"  [{len(s):4d}] {s}")

with open(r'unobfuscator\cracked script\bloxburg_strings.json', 'w', encoding='utf-8') as f:
    json.dump({
        'total_strings': len(strings),
        'unique_strings': len(set(strings)),
        'services': sorted(set(roblox_services)),
        'urls': sorted(set(urls)),
        'events': sorted(set(events)),
        'api_calls': sorted(set(api_calls)),
        'interesting': sorted(set(interesting)),
        'all_unique': sorted(set(strings)),
    }, f, indent=2, ensure_ascii=False)
print("\nSaved string analysis to bloxburg_strings.json")
