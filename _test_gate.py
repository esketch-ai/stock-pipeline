import script_gate, json
from pathlib import Path

t = Path('data/script_long_084670.txt').read_text()
facts = json.load(open('data/archive/2026-10-11/084670.json'))['facts']
r = script_gate.validate(t, facts, '3일 +65.22%', None, None, '동양고속', use_llm=False, max_rounds=1)
print(r.summary())
print('통과:', r.passed)
for i in r.issues[:3]:
    print(f'  [{i["level"]}] {i["kind"]:12} {i["message"][:60]}')