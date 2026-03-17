#!/usr/bin/env python3
"""
最终IP测试 - 确认企业微信API看到的IP地址
"""

import requests
import json
import os

# 企业微信配置
CORP_ID = "ww17809bd1255d3ec9"
SECRET = "tj3QXRgmj9sL2k2Rv-P79HnJB7sEjhtgKpXQrmYAY40"
AGENT_ID = 1000002

def test_with_proxy_settings(use_proxy=True, proxy_url="http://127.0.0.1:20172"):
    """使用指定代理设置测试"""
    print(f"\n{'='*60}")
    if use_proxy:
        print("测试配置：使用代理")
        proxies = {
            'http': proxy_url,
            'https': proxy_url
        }
        # 设置环境变量
        os.environ['http_proxy'] = proxy_url
        os.environ['https_proxy'] = proxy_url
    else:
        print("测试配置：不使用代理")
        proxies = {}
        # 清除环境变量
        os.environ.pop('http_proxy', None)
        os.environ.pop('https_proxy', None)
    
    try:
        # 1. 获取access_token
        token_url = f"https://qyapi.weixin.qq.com/cgi-bin/gettoken?corpid={CORP_ID}&corpsecret={SECRET}"
        token_response = requests.get(token_url, timeout=10, proxies=proxies)
        token_result = token_response.json()
        
        if token_result.get("errcode") != 0:
            print(f"获取access_token失败: {token_result}")
            return None
        
        access_token = token_result.get("access_token")
        print(f"✓ access_token获取成功")
        
        # 2. 发送测试消息
        message_url = f"https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token={access_token}"
        message = {
            "touser": "@all",
            "msgtype": "text",
            "agentid": AGENT_ID,
            "text": {
                "content": f"IP测试消息 - 代理设置: {use_proxy}"
            }
        }
        
        msg_response = requests.post(message_url, json=message, timeout=10, proxies=proxies)
        msg_result = msg_response.json()
        
        print(f"消息发送结果:")
        print(json.dumps(msg_result, indent=2, ensure_ascii=False))
        
        return msg_result
        
    except Exception as e:
        print(f"测试过程中出现异常: {e}")
        return None

def main():
    print("企业微信IP白名单配置测试")
    print(f"企业ID: {CORP_ID}")
    print(f"AgentId: {AGENT_ID}")
    
    # 测试1：不使用代理
    print("\n测试1：不使用代理")
    result1 = test_with_proxy_settings(use_proxy=False)
    
    # 测试2：使用代理
    print("\n测试2：使用代理")
    result2 = test_with_proxy_settings(use_proxy=True)
    
    # 分析结果
    print("\n" + "="*60)
    print("分析结果:")
    
    if result1 and result1.get("errcode") == 60020:
        errmsg1 = result1.get("errmsg", "")
        if "from ip:" in errmsg1:
            ip_start = errmsg1.find("from ip:") + 8
            ip_end = errmsg1.find(",", ip_start)
            ip1 = errmsg1[ip_start:ip_end].strip()
            print(f"不使用代理时，企业微信看到的IP: {ip1}")
    
    if result2 and result2.get("errcode") == 60020:
        errmsg2 = result2.get("errmsg", "")
        if "from ip:" in errmsg2:
            ip_start = errmsg2.find("from ip:") + 8
            ip_end = errmsg2.find(",", ip_start)
            ip2 = errmsg2[ip_start:ip_end].strip()
            print(f"使用代理时，企业微信看到的IP: {ip2}")
    
    print("\n配置建议:")
    print("1. 登录企业微信管理后台 (work.weixin.qq.com)")
    print("2. 进入'我的企业' -> '安全与保密' -> 'IP白名单'")
    print("3. 添加上述IP地址到白名单中")
    print("4. 保存配置后重新测试")

if __name__ == "__main__":
    main()