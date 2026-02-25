import os
import requests
import time

api_key = os.getenv("DEEPSEEK_API_KEY")
url = "https://api.deepseek.com/chat/completions"
headers = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {api_key}"
}

sys_text = "You are a helpful assistant. " * 800

def test_cache(messages):
    payload = {
        "model": "deepseek-chat",
        "messages": messages
    }
    resp = requests.post(url, headers=headers, json=payload)
    if resp.status_code == 200:
        usage = resp.json().get('usage', {})
        print(f"Status 200 | Input: {usage.get('prompt_tokens')} | Cache: {usage.get('prompt_cache_hit_tokens', 0)}")
    else:
        print(f"Error {resp.status_code}")

print("=== Run 1: System + User A ===")
test_cache([
    {"role": "system", "content": sys_text},
    {"role": "user", "content": "Question A"}
])

time.sleep(1)

print("=== Run 2: System + User B (Should hit System part) ===")
test_cache([
    {"role": "system", "content": sys_text},
    {"role": "user", "content": "Question B"}
])
