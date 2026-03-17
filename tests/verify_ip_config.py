#!/usr/bin/env python3
"""
企业微信IP白名单配置验证脚本
在配置IP白名单后运行此脚本验证配置是否成功
"""

import requests
import json
import time
from datetime import datetime

# 企业微信配置
CORP_ID = "ww17809bd1255d3ec9"
SECRET = "tj3QXRgmj9sL2k2Rv-P79HnJB7sEjhtgKpXQrmYAY40"
AGENT_ID = 1000002

def test_connection():
    """测试企业微信API连接"""
    print("=" * 60)
    print("企业微信IP白名单配置验证")
    print(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"企业ID: {CORP_ID}")
    print(f"AgentId: {AGENT_ID}")
    print("=" * 60)
    
    # 步骤1：获取access_token
    print("\n[步骤1] 获取access_token...")
    token_url = f"https://qyapi.weixin.qq.com/cgi-bin/gettoken?corpid={CORP_ID}&corpsecret={SECRET}"
    
    try:
        token_response = requests.get(token_url, timeout=10)
        token_data = token_response.json()
        
        if token_data.get("errcode") == 0:
            access_token = token_data.get("access_token")
            expires_in = token_data.get("expires_in")
            print(f"✅ access_token获取成功")
            print(f"   Token: {access_token[:20]}...")
            print(f"   有效期: {expires_in}秒 ({expires_in/3600:.1f}小时)")
        else:
            print(f"❌ access_token获取失败")
            print(f"   错误码: {token_data.get('errcode')}")
            print(f"   错误信息: {token_data.get('errmsg')}")
            return False
            
    except Exception as e:
        print(f"❌ 连接失败: {e}")
        return False
    
    # 步骤2：发送测试消息
    print("\n[步骤2] 发送测试消息...")
    msg_url = f"https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token={access_token}"
    
    test_message = {
        "touser": "@all",
        "msgtype": "text",
        "agentid": AGENT_ID,
        "text": {
            "content": f"IP白名单配置测试\n时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n状态: 验证中"
        }
    }
    
    try:
        msg_response = requests.post(msg_url, json=test_message, timeout=10)
        msg_data = msg_response.json()
        
        print("响应结果:")
        print(json.dumps(msg_data, indent=2, ensure_ascii=False))
        print()
        
        if msg_data.get("errcode") == 0:
            print("✅ IP白名单配置成功！")
            print(f"   消息ID: {msg_data.get('msgid')}")
            print(f"   发送时间: {msg_data.get('created_at', 'N/A')}")
            return True
        elif msg_data.get("errcode") == 60020:
            print("❌ IP白名单配置失败")
            print(f"   错误码: 60020 (IP白名单限制)")
            errmsg = msg_data.get("errmsg", "")
            if "from ip:" in errmsg:
                ip_start = errmsg.find("from ip:") + 8
                ip_end = errmsg.find(",", ip_start)
                ip = errmsg[ip_start:ip_end].strip()
                print(f"   企业微信看到的IP: {ip}")
                print(f"   请将此IP添加到企业微信IP白名单")
            return False
        else:
            print(f"⚠️ 其他错误")
            print(f"   错误码: {msg_data.get('errcode')}")
            print(f"   错误信息: {msg_data.get('errmsg')}")
            return False
            
    except Exception as e:
        print(f"❌ 发送消息失败: {e}")
        return False

def main():
    print("开始验证企业微信IP白名单配置...")
    print("注意：请在配置IP白名单后等待1-2分钟再运行此脚本")
    print()
    
    # 尝试最多3次，每次间隔30秒
    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        print(f"\n尝试 #{attempt}/{max_attempts}")
        success = test_connection()
        
        if success:
            print("\n" + "=" * 60)
            print("🎉 验证成功！企业微信IP白名单配置正确。")
            print("=" * 60)
            break
        else:
            if attempt < max_attempts:
                wait_time = 30
                print(f"\n等待{wait_time}秒后重试...")
                time.sleep(wait_time)
            else:
                print("\n" + "=" * 60)
                print("😞 验证失败。请检查：")
                print("1. IP白名单是否配置正确")
                print("2. 配置是否已生效（等待1-2分钟）")
                print("3. IP地址是否正确")
                print("=" * 60)
    
    # 提供配置指南
    print("\n配置指南:")
    print("1. 登录企业微信管理后台: https://work.weixin.qq.com")
    print("2. 进入'我的企业' -> '安全与保密' -> 'IP白名单'")
    print("3. 添加IP地址: 218.85.164.181")
    print("4. 保存配置，等待1-2分钟后重新测试")

if __name__ == "__main__":
    main()