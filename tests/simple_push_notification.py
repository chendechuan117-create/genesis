#!/usr/bin/env python3
"""
简单的消息推送脚本
支持PushDeer和Server酱，作为企业微信的简单替代方案
"""

import requests
import sys
from typing import Optional

def send_pushdeer(pushkey: str, title: str, content: str = "", endpoint: str = "https://api2.pushdeer.com") -> bool:
    """
    使用PushDeer发送消息
    
    Args:
        pushkey: PushDeer的pushkey
        title: 消息标题
        content: 消息内容（可选）
        endpoint: API端点
    
    Returns:
        bool: 是否发送成功
    """
    url = f"{endpoint.rstrip('/')}/message/push"
    
    payload = {
        "pushkey": pushkey,
        "text": title,
        "desp": content,
        "type": "markdown" if content else "text"
    }
    
    try:
        response = requests.post(url, data=payload, timeout=10)
        result = response.json()
        
        if result.get("code") == 0:
            print(f"✅ PushDeer消息发送成功: {result.get('content', {}).get('result', [{}])[0].get('success', '未知')}")
            return True
        else:
            print(f"❌ PushDeer消息发送失败: {result}")
            return False
    except Exception as e:
        print(f"❌ PushDeer请求异常: {e}")
        return False


def send_serverchan(sendkey: str, title: str, content: str = "", channel: int = 9) -> bool:
    """
    使用Server酱发送消息
    
    Args:
        sendkey: Server酱的sendkey
        title: 消息标题
        content: 消息内容（可选）
        channel: 推送通道（9=微信，66=企业微信，30=钉钉，18=飞书）
    
    Returns:
        bool: 是否发送成功
    """
    url = f"https://sctapi.ftqq.com/{sendkey}.send"
    
    payload = {
        "title": title,
        "desp": content,
        "channel": channel
    }
    
    try:
        response = requests.post(url, data=payload, timeout=10)
        result = response.json()
        
        if result.get("code") == 0:
            print(f"✅ Server酱消息发送成功: {result.get('message', '成功')}")
            return True
        elif result.get("code") == 40001:
            print("❌ Server酱: 错误的Key，请检查sendkey")
            return False
        else:
            print(f"❌ Server酱消息发送失败: {result}")
            return False
    except Exception as e:
        print(f"❌ Server酱请求异常: {e}")
        return False


def send_notification(service: str, key: str, title: str, content: str = "", **kwargs) -> bool:
    """
    统一的消息发送接口
    
    Args:
        service: 服务类型 ('pushdeer' 或 'serverchan')
        key: API密钥
        title: 消息标题
        content: 消息内容
        **kwargs: 其他参数
    
    Returns:
        bool: 是否发送成功
    """
    if service.lower() == 'pushdeer':
        endpoint = kwargs.get('endpoint', 'https://api2.pushdeer.com')
        return send_pushdeer(key, title, content, endpoint)
    elif service.lower() == 'serverchan':
        channel = kwargs.get('channel', 9)
        return send_serverchan(key, title, content, channel)
    else:
        print(f"❌ 不支持的服务类型: {service}")
        return False


# 示例配置类
class NotificationConfig:
    """消息推送配置"""
    
    def __init__(self):
        self.pushdeer_key = None
        self.serverchan_key = None
        self.preferred_service = None
    
    def load_from_env(self):
        """从环境变量加载配置"""
        import os
        
        self.pushdeer_key = os.getenv('PUSHDEER_KEY')
        self.serverchan_key = os.getenv('SERVERCHAN_KEY')
        self.preferred_service = os.getenv('PREFERRED_NOTIFICATION_SERVICE', 'serverchan')
        
        return self
    
    def validate(self):
        """验证配置"""
        if self.preferred_service == 'pushdeer' and not self.pushdeer_key:
            return False, "未配置PushDeer Key"
        elif self.preferred_service == 'serverchan' and not self.serverchan_key:
            return False, "未配置Server酱 Key"
        return True, "配置有效"


def main():
    """命令行入口"""
    if len(sys.argv) < 4:
        print("用法:")
        print("  python simple_push_notification.py <service> <key> <title> [content]")
        print()
        print("参数:")
        print("  service: pushdeer 或 serverchan")
        print("  key: API密钥")
        print("  title: 消息标题")
        print("  content: 消息内容（可选）")
        print()
        print("示例:")
        print("  python simple_push_notification.py pushdeer PDUxxxxx '服务器告警' 'CPU使用率过高'")
        print("  python simple_push_notification.py serverchan SCTxxxxx '任务完成' '备份任务已完成'")
        print()
        
        # 演示示例
        print("演示模式（使用示例key）:")
        
        # PushDeer示例
        print("\n1. PushDeer示例:")
        success = send_notification(
            service='pushdeer',
            key='PDUxxxxx',  # 示例key
            title='演示消息',
            content='这是一个PushDeer演示消息'
        )
        
        # Server酱示例
        print("\n2. Server酱示例:")
        success = send_notification(
            service='serverchan',
            key='SCTxxxxx',  # 示例key
            title='演示消息',
            content='这是一个Server酱演示消息'
        )
        
        return
    
    service = sys.argv[1]
    key = sys.argv[2]
    title = sys.argv[3]
    content = sys.argv[4] if len(sys.argv) > 4 else ""
    
    success = send_notification(service, key, title, content)
    
    if success:
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()