import json
from collections import Counter

ps = json.load(open('all_protos_data.json'))
om = json.load(open('opcode_map_final.json'))

for p in ps:
    ninst = len(p.get('C4', []))
    if 50 < ninst < 200:
        cats = Counter()
        for op in p.get('C4', []):
            cats[om.get(str(op), {}).get('lua51', '?')] += 1
        top = ', '.join(f'{c}:{n}' for c, n in cats.most_common(6))
        print(f"Proto {p['id']:>3} ({ninst} inst): {top}")
