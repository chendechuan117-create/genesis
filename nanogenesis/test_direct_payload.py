import os
import requests
import json
import time

api_key = os.getenv("DEEPSEEK_API_KEY")
url = "https://api.deepseek.com/chat/completions"
headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}

with open('data1.json', 'r', encoding='utf-8') as f1:
    d1 = json.load(f1)
with open('data2.json', 'r', encoding='utf-8') as f2:
    d2 = json.load(f2)

def test_cache(payload):
    resp = requests.post(url, headers=headers, json=payload)
    if resp.status_code == 200:
        usage = resp.json().get('usage', {})
        print(f"Input: {usage.get('prompt_tokens')} | Cache: {usage.get('prompt_cache_hit_tokens', 0)}")
    else:
        print(f"Error {resp.status_code} - {resp.text[:100]}")

print("=== Sending NanoGenesis Payload 1 ===")
test_cache(d1)

time.sleep(1)

print("=== Sending NanoGenesis Payload 2 ===")
test_cache(d2)
