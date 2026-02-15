try:
    import aiohttp
    print("aiohttp: OK")
except ImportError:
    print("aiohttp: MISSING")

try:
    import requests
    print("requests: OK")
except ImportError:
    print("requests: MISSING")
