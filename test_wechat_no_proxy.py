#!/usr/bin/env python3
"""
企业微信消息发送功能测试脚本（无代理版本）
"""

import json
import requests
import os
from datetime import datetime

# 清除代理环境变量
os.environ.pop('http_proxy', None)
os.environ.pop('https_proxy', None)
os.environ.pop('HTTP_PROXY', None)
os.environ.pop('HTTPS_PROXY', None)
os.environ.pop('all_proxy', None)
os.environ.pop('ALL_PROXY', None)

# 企业微信配置参数
CORP_ID = "ww17809bd1255d3ec9"
SECRET = "tj3QXRgmj9sL2k2Rv-P79HnJB7sEjhtgKpXQrmYAY40"
AGENT_ID = 1000002

def get_access_token():
    """获取企业微信access_token"""
    url = f"https://qyapi.weixin.qq.com/cgi-bin/gettoken?corpid={CORP_ID}&corpsecret={SECRET}"
    try:
        # 明确设置不使用代理
        response = requests.get(url, timeout=10, proxies={})
        result = response.json()
        if result.get("errcode") == 0:
            return result.get("access_token")
        else:
            print(f"获取access_token失败: {result}")
            return None
    except Exception as e:
        print(f"获取access_token异常: {e}")
        return None

def send_test_message(access_token):
    """发送测试消息"""
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    message = {
        "touser": "@all",
        "msgtype": "text",
        "agentid": AGENT_ID,
        "text": {
            "content": f"测试消息 - {current_time}\n这是一个测试消息，用于验证IP白名单配置。"
        }
    }
    
    url = f"https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token={access_token}"
    
    try:
        # 明确设置不使用代理
        response = requests.post(url, json=message, timeout=10, proxies={})
        result = response.json()
        return result
    except Exception as e:
        print(f"发送消息异常: {e}")
        return {"errcode": -1, "errmsg": str(e)}

def main():
    print("=== 企业微信测试（无代理版本） ===")
    print(f"当前代理设置: http_proxy={os.environ.get('http_proxy', '未设置')}")
    print(f"当前代理设置: https_proxy={os.environ.get('https_proxy', '未设置')}")
    print()
    
    # 1. 获取access_token
    print("1. 获取access_token...")
    access_token = get_access_token()
    if not access_token:
        print("❌ 获取access_token失败，测试终止")
        return
    
    print(f"✓ access_token获取成功: {access_token[:20]}...")
    print()
    
    # 2. 发送测试消息
    print("2. 发送测试消息...")
    result = send_test_message(access_token)
    
    print("响应结果:")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    print()
    
    # 3. 分析结果
    if result.get("errcode") == 0:
        print("✅ 测试成功！消息已发送")
    elif result.get("errcode") == 60020:
        print("⚠️ IP白名单限制")
        print("错误信息:", result.get("errmsg"))
        print("请将以下IP地址添加到企业微信IP白名单:")
        # 从错误信息中提取IP
        errmsg = result.get("errmsg", "")
        if "from ip:" in errmsg:
            ip_start = errmsg.find("from ip:") + 8
            ip_end = errmsg.find(",", ip_start)
            ip = errmsg[ip_start:ip_end].strip()
            print(f"IP地址: {ip}")
    else:
        print("❌ 测试失败")
        print(f"错误码: {result.get('errcode')}")
        print(f"错误信息: {result.get('errmsg')}")
    
    print()
    print("=== 测试完成 ===")

if __name__ == "__main__":
    main()