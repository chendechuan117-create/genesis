import os
import requests
import time

api_key = os.getenv("DEEPSEEK_API_KEY")
url = "https://api.deepseek.com/chat/completions"
headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}

with open('data1.json', 'rb') as f1:
    b1 = f1.read()
with open('data2.json', 'rb') as f2:
    b2 = f2.read()

def test_cache(payload_bytes):
    resp = requests.post(url, headers=headers, data=payload_bytes)
    if resp.status_code == 200:
        usage = resp.json().get('usage', {})
        print(f"Input: {usage.get('prompt_tokens')} | Cache: {usage.get('prompt_cache_hit_tokens', 0)}")
    else:
        print(f"Error {resp.status_code} - {resp.text[:100]}")

print("=== Sending raw Genesis bytes 1 ===")
test_cache(b1)

time.sleep(2)

print("=== Sending raw Genesis bytes 2 ===")
test_cache(b2)
