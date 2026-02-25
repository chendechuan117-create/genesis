import json
with open('debug_payload.json', 'r') as f:
    lines = f.read().split('---')
    for idx, block in enumerate(lines):
        if not block.strip(): continue
        try:
            data = json.loads(block)
            msgs = data.get('messages', [])
            if len(msgs) > 0:
                print(f'\n--- Request {idx+1} ---')
                print(f'Total messages: {len(msgs)}')
                print(f'System (msg 0) length: {len(msgs[0]["content"])}')
                sys_content = msgs[0]["content"]
                # Look for the dynamic tokens
                import re
                time_match = re.search(r'\[System Time: .*?\]', sys_content)
                session_match = re.search(r'\[Session State\].*?User:.*?\n', sys_content, re.DOTALL)
                print(f"Contains System Time: {bool(time_match)}")
                if time_match: print(f"  -> {time_match.group(0)}")
                print(f"Contains Session State: {bool(session_match)}")
                
                if len(msgs) > 1:
                    last = msgs[-1]
                    print(f'Last User (msg -1) length: {len(last["content"])}')
        except Exception as e:
            print(f"Error parsing block {idx+1}: {e}")
