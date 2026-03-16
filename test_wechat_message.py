#!/usr/bin/env python3
"""
企业微信消息发送功能测试脚本
测试早报功能
"""

import json
import requests
import time
from datetime import datetime

# 企业微信配置参数
CORP_ID = "ww17809bd1255d3ec9"
SECRET = "tj3QXRgmj9sL2k2Rv-P79HnJB7sEjhtgKpXQrmYAY40"
AGENT_ID = 1000002

def get_access_token():
    """获取企业微信access_token"""
    url = f"https://qyapi.weixin.qq.com/cgi-bin/gettoken?corpid={CORP_ID}&corpsecret={SECRET}"
    try:
        response = requests.get(url, timeout=10)
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
    """发送测试早报消息"""
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # 创建测试早报消息
    message = {
        "touser": "@all",  # 发送给所有人
        "msgtype": "textcard",
        "agentid": AGENT_ID,
        "textcard": {
            "title": "测试早报",
            "description": f"<div class=\"gray\">{current_time}</div> <div class=\"normal\">这是一个企业微信早报功能测试</div><div class=\"highlight\">状态：测试中</div>",
            "url": "https://work.weixin.qq.com/",
            "btntxt": "查看详情"
        }
    }
    
    url = f"https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token={access_token}"
    
    try:
        response = requests.post(url, json=message, timeout=10)
        result = response.json()
        return result
    except Exception as e:
        print(f"发送消息异常: {e}")
        return {"errcode": -1, "errmsg": str(e)}

def main():
    print("=== 企业微信早报功能测试 ===")
    print(f"企业ID: {CORP_ID}")
    print(f"AgentId: {AGENT_ID}")
    print(f"当前时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
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
    print("2. 发送测试早报消息...")
    result = send_test_message(access_token)
    
    print("响应结果:")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    print()
    
    # 3. 分析结果
    if result.get("errcode") == 0:
        print("✅ 测试成功！消息已发送")
        print(f"消息ID: {result.get('msgid')}")
        print(f"无效用户: {result.get('invaliduser', '无')}")
        print(f"无效部门: {result.get('invalidparty', '无')}")
        print(f"无效标签: {result.get('invalidtag', '无')}")
    elif result.get("errcode") == 60020:
        print("⚠️ IP白名单限制")
        print("错误信息:", result.get("errmsg"))
        print("解决方案:")
        print("1. 登录企业微信管理后台")
        print("2. 进入应用管理 -> 找到对应应用")
        print("3. 在'可信IP'中配置当前服务器IP: 218.85.164.181")
        print("4. 保存配置后重试")
    else:
        print("❌ 测试失败")
        print(f"错误码: {result.get('errcode')}")
        print(f"错误信息: {result.get('errmsg')}")
    
    print()
    print("=== 测试完成 ===")

if __name__ == "__main__":
    main()