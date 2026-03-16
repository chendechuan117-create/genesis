#!/usr/bin/env python3
"""
检查真实出口IP地址
"""

import requests
import os

# 方法1：不使用代理
print("=== 方法1：不使用代理 ===")
os.environ.pop('http_proxy', None)
os.environ.pop('https_proxy', None)
os.environ.pop('HTTP_PROXY', None)
os.environ.pop('HTTPS_PROXY', None)

try:
    response = requests.get('https://api.ipify.org?format=json', timeout=10, proxies={})
    print(f"IP地址: {response.json()['ip']}")
except Exception as e:
    print(f"错误: {e}")

print()

# 方法2：使用代理
print("=== 方法2：使用代理 ===")
os.environ['http_proxy'] = 'http://127.0.0.1:20172'
os.environ['https_proxy'] = 'http://127.0.0.1:20172'

try:
    response = requests.get('https://api.ipify.org?format=json', timeout=10)
    print(f"IP地址: {response.json()['ip']}")
except Exception as e:
    print(f"错误: {e}")

print()

# 方法3：检查多个IP查询服务
print("=== 方法3：检查多个IP查询服务 ===")
services = [
    'https://api.ipify.org?format=json',
    'https://api.myip.com',
    'https://ipinfo.io/json',
    'https://ifconfig.me/all.json'
]

for service in services:
    try:
        response = requests.get(service, timeout=5, proxies={})
        if service == 'https://api.ipify.org?format=json':
            print(f"ipify.org: {response.json()['ip']}")
        elif service == 'https://api.myip.com':
            print(f"myip.com: {response.json()['ip']}")
        elif service == 'https://ipinfo.io/json':
            print(f"ipinfo.io: {response.json()['ip']}")
        elif service == 'https://ifconfig.me/all.json':
            print(f"ifconfig.me: {response.json()['ip_addr']}")
    except Exception as e:
        print(f"{service}: 查询失败 - {e}")