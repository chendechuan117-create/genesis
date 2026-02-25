import json

with open('data1.json', 'rb') as f1, open('data2.json', 'rb') as f2:
    b1 = f1.read()
    b2 = f2.read()

if b1 == b2:
    print('✅ Byte-for-byte MATCH!')
else:
    print('❌ Bytes differ!')
    print(f'Length 1: {len(b1)}')
    print(f'Length 2: {len(b2)}')
    
    d1 = json.loads(b1.decode('utf-8'))
    d2 = json.loads(b2.decode('utf-8'))
    
    # Check top-level keys
    print(f"Top-level keys 1: {list(d1.keys())}")
    print(f"Top-level keys 2: {list(d2.keys())}")
    
    # Check messages array length
    print(f"Messages count: {len(d1.get('messages', []))} vs {len(d2.get('messages', []))}")
    
    # Compare each message
    for i, (m1, m2) in enumerate(zip(d1.get('messages', []), d2.get('messages', []))):
        if m1 != m2:
            print(f"Message {i} differs!")
            for k in m1:
                if m1.get(k) != m2.get(k):
                    v1 = str(m1.get(k))
                    v2 = str(m2.get(k))
                    if len(v1) == len(v2):
                        print(f"  Field '{k}' differs in content but same length ({len(v1)} chars)")
                        # Find the first char difference
                        for pos, (c1, c2) in enumerate(zip(v1, v2)):
                            if c1 != c2:
                                print(f"    First diff at pos {pos}: '{c1}' vs '{c2}'")
                                print(f"    Context 1: ...{v1[max(0, pos-10):pos+10]}...")
                                print(f"    Context 2: ...{v2[max(0, pos-10):pos+10]}...")
                                break
                    else:
                        print(f"  Field '{k}' differs in length: {len(v1)} vs {len(v2)} chars")
                        
    # Check tools
    t1 = d1.get('tools', [])
    t2 = d2.get('tools', [])
    if t1 != t2:
        print(f"Tools differ! lengths: {len(t1)} vs {len(t2)}")
        for i, (tool1, tool2) in enumerate(zip(t1, t2)):
            if tool1 != tool2:
                print(f"  Tool {i} differs!")
                print(f"    Name 1: {tool1.get('function', {}).get('name')}")
                print(f"    Name 2: {tool2.get('function', {}).get('name')}")
                break
