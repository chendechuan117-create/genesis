import json

with open('agent_loop_payload_dump.json', 'r', encoding='utf-8') as f:
    lines = [line for line in f.read().split('---\n') if line.strip()]

if len(lines) < 2:
    print('Not enough data to diff.')
    exit(1)

d1 = json.loads(lines[0])
d2 = json.loads(lines[1])

# Check tools
t1 = json.dumps(d1['tools'], sort_keys=True)
t2 = json.dumps(d2['tools'], sort_keys=True)
if t1 == t2:
    print('✅ Tools Match')
else:
    print('❌ Tools Diff!')
    for i, (tool1, tool2) in enumerate(zip(d1['tools'], d2['tools'])):
        if tool1 != tool2:
            print(f'   Tool {i} Differs: {tool1.get("function",{}).get("name")} vs {tool2.get("function",{}).get("name")}')
            break

# Check System messages (messages[0])
m1 = d1['messages']
m2 = d2['messages']

print(f"Messages count: {len(m1)} vs {len(m2)}")

s1 = m1[0]['content']
s2 = m2[0]['content']

if s1 == s2:
    print('✅ System Match')
else:
    print('❌ System Diff!')
    print(f'Length: {len(s1)} vs {len(s2)}')
    for i, (c1, c2) in enumerate(zip(s1, s2)):
        if c1 != c2:
            print(f'   First difference at pos {i}: "{c1}" vs "{c2}"')
            print(f'   1: ...{s1[max(0, i-20):i+20]}...')
            print(f'   2: ...{s2[max(0, i-20):i+20]}...')
            break
            
# Full object compare just in case there are hidden keys
def dict_diff(d1, d2, path=""):
    for k in d1:
        if k not in d2:
            print(f"Key {path}.{k} missing in v2")
        elif type(d1[k]) != type(d2[k]):
            print(f"Type mismatch {path}.{k}")
        else:
            if isinstance(d1[k], dict):
                dict_diff(d1[k], d2[k], path + "." + k)

dict_diff(d1, d2, "root")
dict_diff(d2, d1, "root")
