#!/usr/bin/env python3
"""
直接测试企业微信API，查看真实IP
"""

import requests
import json

# 企业微信配置
CORP_ID = "ww17809bd1255d3ec9"
SECRET = "tj3QXRgmj9sL2k2Rv-P79HnJB7sEjhtgKpXQrmYAY40"

# 尝试获取access_token，看看企业微信看到的IP
url = f"https://qyapi.weixin.qq.com/cgi-bin/gettoken?corpid={CORP_ID}&corpsecret={SECRET}"

print("尝试直接访问企业微信API（不使用代理）...")
try:
    # 方法1：不使用代理
    response1 = requests.get(url, timeout=10, proxies={})
    print(f"不使用代理 - 状态码: {response1.status_code}")
    if response1.status_code == 200:
        result = response1.json()
        print(f"响应: {json.dumps(result, indent=2, ensure_ascii=False)}")
    else:
        print(f"响应内容: {response1.text[:200]}")
except Exception as e:
    print(f"不使用代理访问失败: {e}")

print("\n" + "="*50 + "\n")

print("尝试通过代理访问企业微信API...")
try:
    # 方法2：使用代理
    proxies = {
        'http': 'http://127.0.0.1:20172',
        'https': 'http://127.0.0.1:20172'
    }
    response2 = requests.get(url, timeout=10, proxies=proxies)
    print(f"使用代理 - 状态码: {response2.status_code}")
    if response2.status_code == 200:
        result = response2.json()
        print(f"响应: {json.dumps(result, indent=2, ensure_ascii=False)}")
    else:
        print(f"响应内容: {response2.text[:200]}")
except Exception as e:
    print(f"使用代理访问失败: {e}")