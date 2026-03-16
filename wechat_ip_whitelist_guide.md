# 企业微信IP白名单配置指南

## 当前服务器IP地址
根据测试结果，企业微信API看到的服务器IP地址为：
**218.85.164.181**

## 配置步骤

### 步骤1：登录企业微信管理后台
1. 访问 https://work.weixin.qq.com
2. 使用企业微信管理员账号登录

### 步骤2：进入IP白名单配置页面
根据企业微信版本不同，有以下两种路径：

**路径A（新版界面）：**
1. 点击左侧菜单栏的「我的企业」
2. 选择「安全与保密」
3. 找到「IP白名单」选项

**路径B（旧版界面）：**
1. 点击「应用管理」
2. 选择对应的应用（AgentId: 1000002）
3. 找到「可信IP」或「IP白名单」设置

### 步骤3：添加IP地址
1. 点击「添加IP」或「修改」按钮
2. 输入IP地址：`218.85.164.181`
3. 点击「保存」或「确认」

### 步骤4：验证配置
配置完成后，等待1-2分钟让配置生效，然后运行测试脚本验证：

```bash
python3 test_wechat_message.py
```

## 自动化配置建议

### 方案1：使用企业微信API管理IP白名单
目前企业微信官方API**不支持**动态管理IP白名单。IP白名单必须通过管理后台手动配置。

### 方案2：监控IP变化并提醒
创建监控脚本，当服务器IP发生变化时发送通知：

```python
#!/usr/bin/env python3
"""
IP变化监控脚本
"""

import requests
import time
import smtplib
from email.mime.text import MIMEText

def get_current_ip():
    """获取当前公网IP"""
    try:
        response = requests.get('https://api.ipify.org?format=json', timeout=5)
        return response.json()['ip']
    except:
        try:
            response = requests.get('https://ipinfo.io/ip', timeout=5)
            return response.text.strip()
        except:
            return None

def send_notification(old_ip, new_ip):
    """发送IP变化通知"""
    # 这里可以集成邮件、短信、企业微信消息等通知方式
    print(f"⚠️ IP地址发生变化！")
    print(f"旧IP: {old_ip}")
    print(f"新IP: {new_ip}")
    print(f"请及时更新企业微信IP白名单配置")

def main():
    # 记录初始IP
    current_ip = get_current_ip()
    if current_ip:
        print(f"初始IP地址: {current_ip}")
        last_ip = current_ip
        
        # 定期检查IP变化
        while True:
            time.sleep(3600)  # 每小时检查一次
            
            new_ip = get_current_ip()
            if new_ip and new_ip != last_ip:
                send_notification(last_ip, new_ip)
                last_ip = new_ip
    else:
        print("无法获取当前IP地址")

if __name__ == "__main__":
    main()
```

### 方案3：使用固定IP服务
对于生产环境，建议：
1. **购买云服务器固定IP**：使用阿里云、腾讯云等云服务商的固定公网IP
2. **使用VPN/专线**：通过VPN或专线连接，使用固定出口IP
3. **代理服务器**：配置固定的代理服务器作为出口

## 测试脚本

### 基础测试脚本
```python
# test_wechat_basic.py
import requests

CORP_ID = "ww17809bd1255d3ec9"
SECRET = "tj3QXRgmj9sL2k2Rv-P79HnJB7sEjhtgKpXQrmYAY40"
AGENT_ID = 1000002

def test_ip_whitelist():
    # 获取access_token
    token_url = f"https://qyapi.weixin.qq.com/cgi-bin/gettoken?corpid={CORP_ID}&corpsecret={SECRET}"
    token_resp = requests.get(token_url, timeout=10)
    token_data = token_resp.json()
    
    if token_data.get("errcode") != 0:
        print(f"获取token失败: {token_data}")
        return False
    
    # 发送测试消息
    msg_url = f"https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token={token_data['access_token']}"
    message = {
        "touser": "@all",
        "msgtype": "text",
        "agentid": AGENT_ID,
        "text": {"content": "IP白名单配置测试"}
    }
    
    msg_resp = requests.post(msg_url, json=message, timeout=10)
    msg_data = msg_resp.json()
    
    if msg_data.get("errcode") == 0:
        print("✅ IP白名单配置成功！")
        return True
    elif msg_data.get("errcode") == 60020:
        print("❌ IP白名单配置失败")
        print(f"错误信息: {msg_data.get('errmsg')}")
        return False
    else:
        print(f"其他错误: {msg_data}")
        return False

if __name__ == "__main__":
    test_ip_whitelist()
```

## 常见问题

### Q1：配置后仍然报错60020
1. **等待时间不足**：配置生效需要1-2分钟，请稍后重试
2. **IP地址错误**：确认添加的IP地址是否正确
3. **配置位置错误**：确保在正确的应用或企业级别配置

### Q2：服务器IP经常变化
1. 联系网络服务商申请固定IP
2. 使用云服务器的弹性公网IP服务
3. 配置DDNS（动态域名解析）服务

### Q3：需要添加多个IP地址
1. 如果有多个服务器或出口，需要将所有IP添加到白名单
2. 可以使用IP段格式（如：192.168.1.0/24）

## 联系支持
如果遇到问题，可以：
1. 查看企业微信官方文档：https://developer.work.weixin.qq.com/document
2. 联系企业微信客服
3. 在企业微信社区提问