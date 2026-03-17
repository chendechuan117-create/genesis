#!/usr/bin/env python3
"""
PushDeer和Server酱消息推送测试脚本
作为企业微信的替代方案
"""

import json
import requests
import time
from datetime import datetime
from typing import Optional, Dict, Any

class PushDeerClient:
    """PushDeer客户端"""
    
    def __init__(self, pushkey: str, endpoint: str = "https://api2.pushdeer.com"):
        """
        初始化PushDeer客户端
        
        Args:
            pushkey: PushDeer的pushkey
            endpoint: API端点，默认为官方在线版
        """
        self.pushkey = pushkey
        self.endpoint = endpoint.rstrip('/')
    
    def send_text(self, text: str, desp: str = "", type: str = "markdown") -> Dict[str, Any]:
        """
        发送文本消息
        
        Args:
            text: 消息标题
            desp: 消息内容（支持markdown）
            type: 消息类型，支持text或markdown
        
        Returns:
            响应结果
        """
        url = f"{self.endpoint}/message/push"
        
        payload = {
            "pushkey": self.pushkey,
            "text": text,
            "desp": desp,
            "type": type
        }
        
        try:
            response = requests.post(url, data=payload, timeout=10)
            return response.json()
        except Exception as e:
            return {"code": -1, "error": str(e)}
    
    def send_markdown(self, title: str, content: str) -> Dict[str, Any]:
        """
        发送Markdown格式消息
        
        Args:
            title: 消息标题
            content: Markdown内容
        
        Returns:
            响应结果
        """
        return self.send_text(title, content, "markdown")


class ServerChanClient:
    """Server酱客户端"""
    
    def __init__(self, sendkey: str):
        """
        初始化Server酱客户端
        
        Args:
            sendkey: Server酱的sendkey
        """
        self.sendkey = sendkey
        self.base_url = "https://sctapi.ftqq.com"
    
    def send_message(self, title: str, desp: str = "", channel: int = 9) -> Dict[str, Any]:
        """
        发送消息到Server酱
        
        Args:
            title: 消息标题
            desp: 消息内容（支持markdown）
            channel: 推送通道，默认9（微信）
        
        Returns:
            响应结果
        """
        url = f"{self.base_url}/{self.sendkey}.send"
        
        payload = {
            "title": title,
            "desp": desp,
            "channel": channel
        }
        
        try:
            response = requests.post(url, data=payload, timeout=10)
            return response.json()
        except Exception as e:
            return {"code": -1, "error": str(e)}
    
    def send_markdown(self, title: str, content: str) -> Dict[str, Any]:
        """
        发送Markdown格式消息
        
        Args:
            title: 消息标题
            content: Markdown内容
        
        Returns:
            响应结果
        """
        return self.send_message(title, content)


def test_pushdeer():
    """测试PushDeer推送"""
    print("=== PushDeer测试 ===")
    
    # 注意：这里需要替换为实际的pushkey
    # 用户需要从PushDeer客户端获取pushkey
    pushkey = "PDUxxxxx"  # 示例，需要替换
    
    client = PushDeerClient(pushkey)
    
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # 测试文本消息
    print("1. 发送文本消息...")
    result = client.send_text(
        text=f"PushDeer测试消息 {current_time}",
        desp="这是一个来自Python脚本的PushDeer测试消息"
    )
    print(f"响应: {json.dumps(result, indent=2, ensure_ascii=False)}")
    
    # 测试Markdown消息
    print("\n2. 发送Markdown消息...")
    markdown_content = f"""
# PushDeer Markdown测试

**时间**: {current_time}

## 消息内容
这是一个Markdown格式的测试消息

### 功能列表
- ✅ 支持文本消息
- ✅ 支持Markdown格式
- ✅ 支持自定义API端点
- ✅ 开源可自建

### 代码示例
```python
client = PushDeerClient(pushkey="your_pushkey")
result = client.send_markdown("标题", "内容")
```

---
*来自测试脚本*
"""
    
    result = client.send_markdown(
        title="PushDeer Markdown测试",
        content=markdown_content
    )
    print(f"响应: {json.dumps(result, indent=2, ensure_ascii=False)}")
    
    return result


def test_serverchan():
    """测试Server酱推送"""
    print("\n=== Server酱测试 ===")
    
    # 注意：这里需要替换为实际的sendkey
    # 用户需要从Server酱官网获取sendkey
    sendkey = "SCTxxxxx"  # 示例，需要替换
    
    client = ServerChanClient(sendkey)
    
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # 测试基本消息
    print("1. 发送基本消息...")
    result = client.send_message(
        title=f"Server酱测试消息 {current_time}",
        desp="这是一个来自Python脚本的Server酱测试消息"
    )
    print(f"响应: {json.dumps(result, indent=2, ensure_ascii=False)}")
    
    # 测试Markdown消息
    print("\n2. 发送Markdown消息...")
    markdown_content = f"""
# Server酱 Markdown测试

**时间**: {current_time}

## 消息内容
这是一个Markdown格式的测试消息

### 功能特性
- ✅ 支持多种推送通道（微信、企业微信、钉钉、飞书等）
- ✅ 支持Markdown格式
- ✅ 免费额度充足
- ✅ 无需IP白名单

### 推送通道说明
| 通道 | 说明 |
|------|------|
| 9 | 微信（默认） |
| 66 | 企业微信 |
| 30 | 钉钉 |
| 18 | 飞书 |

### 使用示例
```python
client = ServerChanClient(sendkey="your_sendkey")
result = client.send_message("标题", "内容", channel=9)
```

---
*来自测试脚本*
"""
    
    result = client.send_markdown(
        title="Server酱 Markdown测试",
        content=markdown_content
    )
    print(f"响应: {json.dumps(result, indent=2, ensure_ascii=False)}")
    
    return result


def create_enterprise_wechat_alternative():
    """创建企业微信替代方案示例"""
    print("\n=== 企业微信替代方案示例 ===")
    
    # 模拟企业微信早报功能
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # 创建早报内容
    morning_report = f"""
# 每日早报 {current_time}

## 📊 系统状态
- **服务器状态**: ✅ 正常
- **网络连接**: ✅ 稳定
- **服务运行**: 24/7

## 📈 昨日数据
- 用户访问: 1,234 次
- API调用: 5,678 次
- 错误率: 0.12%

## 🔔 今日提醒
1. 数据库备份计划于 10:00 执行
2. 系统维护窗口: 02:00-04:00
3. 新功能上线评审: 14:00

## 🎯 重点关注
- 监控告警阈值调整
- 用户反馈收集
- 性能优化测试

---
*此消息通过PushDeer/Server酱发送，替代企业微信方案*
"""
    
    print("早报内容示例:")
    print(morning_report)
    
    return morning_report


def compare_services():
    """比较PushDeer和Server酱"""
    print("\n=== 服务对比 ===")
    
    comparison = {
        "PushDeer": {
            "优点": [
                "开源可自建，完全免费",
                "无需注册，直接使用",
                "支持iOS/MacOS/Android",
                "无IP白名单限制",
                "支持Markdown格式"
            ],
            "缺点": [
                "需要安装客户端",
                "自建需要服务器",
                "官方在线版可能有稳定性问题"
            ],
            "适用场景": [
                "个人开发者",
                "需要完全控制权的项目",
                "对隐私要求高的场景"
            ]
        },
        "Server酱": {
            "优点": [
                "无需安装客户端",
                "支持多种推送通道",
                "免费额度充足",
                "稳定可靠",
                "无需IP白名单"
            ],
            "缺点": [
                "需要注册获取sendkey",
                "依赖第三方服务",
                "免费版可能有频率限制"
            ],
            "适用场景": [
                "快速集成",
                "多平台推送需求",
                "企业级应用"
            ]
        }
    }
    
    for service, info in comparison.items():
        print(f"\n{service}:")
        print(f"  优点:")
        for advantage in info["优点"]:
            print(f"    • {advantage}")
        print(f"  缺点:")
        for disadvantage in info["缺点"]:
            print(f"    • {disadvantage}")
        print(f"  适用场景:")
        for scenario in info["适用场景"]:
            print(f"    • {scenario}")


def main():
    """主函数"""
    print("=" * 60)
    print("PushDeer/Server酱作为企业微信替代方案测试")
    print("=" * 60)
    
    # 1. 创建早报示例
    morning_report = create_enterprise_wechat_alternative()
    
    # 2. 比较服务
    compare_services()
    
    # 3. 测试PushDeer（需要实际pushkey）
    print("\n" + "=" * 60)
    print("注意：以下测试需要实际的API密钥")
    print("请先获取PushDeer的pushkey或Server酱的sendkey")
    print("=" * 60)
    
    choice = input("\n是否进行实际API测试？(y/n): ")
    
    if choice.lower() == 'y':
        service = input("选择测试的服务 (1=PushDeer, 2=Server酱): ")
        
        if service == '1':
            pushkey = input("请输入PushDeer的pushkey: ")
            if pushkey and pushkey != "PDUxxxxx":
                client = PushDeerClient(pushkey)
                result = client.send_markdown("测试消息", morning_report)
                print(f"\n测试结果: {json.dumps(result, indent=2, ensure_ascii=False)}")
            else:
                print("无效的pushkey，跳过测试")
        elif service == '2':
            sendkey = input("请输入Server酱的sendkey: ")
            if sendkey and sendkey != "SCTxxxxx":
                client = ServerChanClient(sendkey)
                result = client.send_markdown("测试消息", morning_report)
                print(f"\n测试结果: {json.dumps(result, indent=2, ensure_ascii=False)}")
            else:
                print("无效的sendkey，跳过测试")
    
    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)
    
    # 提供配置指南
    print("\n📋 配置指南:")
    print("1. PushDeer配置:")
    print("   - 下载PushDeer客户端")
    print("   - 获取pushkey")
    print("   - 在代码中替换pushkey")
    print("   - 可选：自建服务器提高稳定性")
    
    print("\n2. Server酱配置:")
    print("   - 访问 https://sct.ftqq.com")
    print("   - 微信扫码登录")
    print("   - 获取sendkey")
    print("   - 在代码中替换sendkey")
    print("   - 配置推送通道（默认微信）")


if __name__ == "__main__":
    main()