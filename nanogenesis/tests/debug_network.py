import urllib.request
import os
import ssl

print(f"Proxy Env: {os.environ.get('https_proxy')}")

url = "https://api.deepseek.com" # Just check connectivity
ssl_context = ssl._create_unverified_context()

try:
    print("Attempting urllib connection...")
    req = urllib.request.Request(url, headers={"User-Agent": "Test"})
    with urllib.request.urlopen(req, context=ssl_context, timeout=10) as response:
        print(f"✅ Success! Status: {response.status}")
except Exception as e:
    print(f"❌ Failed: {e}")
