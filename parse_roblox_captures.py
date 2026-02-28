"""
Parse bloxburg_api_map.json captured from Roblox executor hook.
Extracts unique API name mappings and updates VM_DISPATCH_MAP in rebuild_source2.py.

Usage: python parse_roblox_captures.py
  (after copying bloxburg_api_map.json from executor workspace)
"""
import json, re
from collections import Counter

try:
    data = json.load(open('bloxburg_api_map.json', encoding='utf-8'))
except FileNotFoundError:
    print("ERROR: bloxburg_api_map.json not found!")
    print("Steps:")
    print("  1. Run roblox_capture_combined.lua in your Roblox executor (in Bloxburg)")
    print("  2. Wait 10-30 seconds for the VM to execute")
    print("  3. Copy bloxburg_api_map.json from executor workspace to this folder")
    print("  4. Run this script again")
    exit(1)

if isinstance(data, list):
    captures = data
elif isinstance(data, dict):
    captures = data.get('captures', [])
else:
    print(f"Unexpected data format: {type(data)}")
    exit(1)

print(f"Total captures: {len(captures)}")

class_methods = {}
class_props = {}
all_keys = Counter()

for cap in captures:
    path = cap.get('path', cap.get('p', ''))
    key = cap.get('key', cap.get('k', ''))
    key_type = cap.get('key_type', cap.get('kt', ''))
    value_type = cap.get('value_type', cap.get('vt', ''))
    
    if not key or not path:
        continue
    
    all_keys[key] += 1
    
    if ':call' in path or ':method' in path:
        cls = path.split(':')[0]
        class_methods.setdefault(cls, Counter())[key] += 1
    else:
        cls = path
        class_props.setdefault(cls, Counter())[key] += 1

print(f"\nUnique keys: {len(all_keys)}")
print(f"Classes with methods: {len(class_methods)}")
print(f"Classes with properties: {len(class_props)}")

print("\n=== Method calls by class ===")
for cls in sorted(class_methods.keys()):
    methods = class_methods[cls]
    print(f"\n  {cls}:")
    for method, count in methods.most_common(20):
        print(f"    :{method}() ({count}x)")

print("\n=== Property accesses by class ===")
for cls in sorted(class_props.keys()):
    props = class_props[cls]
    print(f"\n  {cls}:")
    for prop, count in props.most_common(20):
        print(f"    .{prop} ({count}x)")

print("\n=== Most frequent API names ===")
for key, count in all_keys.most_common(50):
    print(f"  {key}: {count}x")

roblox_apis = sorted(set(k for k in all_keys if k[0].isupper() or ':' in k or len(k) > 3))
print(f"\n=== Roblox-style API names ({len(roblox_apis)}) ===")
for api in roblox_apis[:60]:
    print(f"  {api}")

with open('roblox_api_names.json', 'w', encoding='utf-8') as f:
    json.dump({
        'methods': {cls: dict(methods) for cls, methods in class_methods.items()},
        'properties': {cls: dict(props) for cls, props in class_props.items()},
        'all_keys': dict(all_keys),
        'roblox_apis': roblox_apis,
    }, f, indent=2, ensure_ascii=False, sort_keys=True)
print(f"\nSaved parsed API data to roblox_api_names.json")
