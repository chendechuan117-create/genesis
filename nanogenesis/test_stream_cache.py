import os
import requests
import json

api_key = os.getenv("DEEPSEEK_API_KEY")
url = "https://api.deepseek.com/chat/completions"
headers = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {api_key}"
}

sys_text = "You are a helpful assistant. " * 800

tools = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get weather",
            "parameters": {
                "type": "object",
                "properties": {"location": {"type": "string"}},
                "required": ["location"]
            }
        }
    }
]

def test_cache_stream(messages):
    payload = {
        "model": "deepseek-chat",
        "messages": messages,
        "tools": tools,
        "stream": True,
        "tool_choice": "auto"
    }
    resp = requests.post(url, headers=headers, json=payload, stream=True)
    if resp.status_code == 200:
        for line in resp.iter_lines():
            if line:
                line_str = line.decode('utf-8')
                if line_str.startswith("data: ") and line_str != "data: [DONE]":
                    chunk = json.loads(line_str[6:])
                    if 'usage' in chunk and chunk['usage']:
                        usage = chunk['usage']
                        print(f"Input: {usage.get('prompt_tokens')} | Cache: {usage.get('prompt_cache_hit_tokens', 0)}")
    else:
        print(f"Error {resp.status_code}")

print("=== Run 1: Stream ===")
test_cache_stream([
    {"role": "system", "content": sys_text},
    {"role": "user", "content": "Question A"}
])

print("=== Run 2: Stream ===")
test_cache_stream([
    {"role": "system", "content": sys_text},
    {"role": "user", "content": "Question B"}
])
