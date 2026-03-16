#!/usr/bin/env python3
"""
企业微信到PushDeer/Server酱迁移演示
"""

import json
import requests
from datetime import datetime

# ============================================================================
# 原企业微信代码示例
# ============================================================================

def original_wechat_example():
    """原企业微信代码示例"""
    print("=== 原企业微信代码示例 ===")
    
    # 企业微信配置
    CORP_ID = "ww17809bd1255d3ec9"
    SECRET = "tj3QXRgmj9sL2k2Rv-P79HnJB7sEjhtgKpXQrmYAY40"
    AGENT_ID = 1000002
    
    # 获取access_token
    def get_access_token():
        url = f"https://qyapi.weixin.qq.com/cgi-bin/gettoken?corpid={CORP_ID}&corpsecret={SECRET}"
        response = requests.get(url)
        result = response.json()
        if result.get("errcode") == 0:
            return result.get("access_token")
        return None
    
    # 发送消息
    def send_wechat_message(access_token, message):
        url = f"https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token={access_token}"
        response = requests.post(url, json=message)
        return response.json()
    
    # 创建早报消息
    def create_morning_report():
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return {
            "touser": "@all",
            "msgtype": "textcard",
            "agentid": AGENT_ID,
            "textcard": {
                "title": f"每日早报 {current_time}",
                "description": f"""<div class="gray">{current_time}</div>
<div class="normal">📊 系统状态：正常</div>
<div class="normal">📈 昨日访问：1,234次</div>
<div class="highlight">🔔 今日提醒：数据库备份10:00</div>""",
                "url": "https://work.weixin.qq.com/",
                "btntxt": "查看详情"
            }
        }
    
    print("企业微信配置:")
    print(f"企业ID: {CORP_ID}")
    print(f"AgentId: {AGENT_ID}")
    print()
    
    print("早报消息格式:")
    message = create_morning_report()
    print(json.dumps(message, indent=2, ensure_ascii=False))
    print()
    
    print("⚠️ 问题: 需要IP白名单配置")
    print("错误码 60020: IP不在白名单中")
    print()

# ============================================================================
# 迁移到PushDeer
# ============================================================================

def migrate_to_pushdeer():
    """迁移到PushDeer示例"""
    print("=== 迁移到PushDeer ===")
    
    # PushDeer配置
    PUSHKEY = "PDUxxxxx"  # 需要替换为实际的pushkey
    ENDPOINT = "https://api2.pushdeer.com"
    
    # 发送PushDeer消息
    def send_pushdeer_message(title, content=""):
        url = f"{ENDPOINT}/message/push"
        payload = {
            "pushkey": PUSHKEY,
            "text": title,
            "desp": content,
            "type": "markdown" if content else "text"
        }
        response = requests.post(url, data=payload)
        return response.json()
    
    # 创建Markdown格式早报
    def create_markdown_morning_report():
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        title = f"每日早报 {current_time}"
        
        content = f"""
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
*此消息通过PushDeer发送*
"""
        return title, content
    
    print("PushDeer配置:")
    print(f"Pushkey: {PUSHKEY}")
    print(f"Endpoint: {ENDPOINT}")
    print()
    
    print("Markdown格式早报:")
    title, content = create_markdown_morning_report()
    print(f"标题: {title}")
    print(f"内容:\n{content}")
    print()
    
    print("发送消息示例:")
    print("result = send_pushdeer_message(title, content)")
    print()
    
    print("✅ 优点:")
    print("1. 无需IP白名单")
    print("2. 开源可自建")
    print("3. 完全免费")
    print("4. 支持Markdown")
    print()

# ============================================================================
# 迁移到Server酱
# ============================================================================

def migrate_to_serverchan():
    """迁移到Server酱示例"""
    print("=== 迁移到Server酱 ===")
    
    # Server酱配置
    SENDKEY = "SCTxxxxx"  # 需要替换为实际的sendkey
    CHANNEL = 9  # 9=微信，66=企业微信，30=钉钉，18=飞书
    
    # 发送Server酱消息
    def send_serverchan_message(title, content="", channel=9):
        url = f"https://sctapi.ftqq.com/{SENDKEY}.send"
        payload = {
            "title": title,
            "desp": content,
            "channel": channel
        }
        response = requests.post(url, data=payload)
        return response.json()
    
    # 创建告警消息
    def create_alert_message():
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        title = "服务器告警"
        
        content = f"""
# 🚨 服务器告警

**时间**: {current_time}
**服务器**: web-server-01
**监控指标**: CPU使用率
**当前值**: 95%
**阈值**: 80%

## 建议操作
1. 登录服务器检查进程
2. 查看系统日志
3. 联系运维人员

[查看监控](https://monitor.example.com)
"""
        return title, content
    
    print("Server酱配置:")
    print(f"Sendkey: {SENDKEY}")
    print(f"Channel: {CHANNEL} (微信推送)")
    print()
    
    print("告警消息示例:")
    title, content = create_alert_message()
    print(f"标题: {title}")
    print(f"内容:\n{content}")
    print()
    
    print("发送消息示例:")
    print("result = send_serverchan_message(title, content, channel=9)")
    print()
    
    print("✅ 优点:")
    print("1. 无需IP白名单")
    print("2. 支持多种推送通道")
    print("3. 免费额度充足")
    print("4. 配置简单快速")
    print()

# ============================================================================
# 迁移对比
# ============================================================================

def migration_comparison():
    """迁移方案对比"""
    print("=== 迁移方案对比 ===")
    
    comparison = {
        "企业微信": {
            "配置复杂度": "高",
            "IP白名单": "需要",
            "成本": "免费（但有频率限制）",
            "推送渠道": "企业微信",
            "消息格式": "textcard、文本、图片等",
            "稳定性": "高",
            "适用场景": "企业内部通知"
        },
        "PushDeer": {
            "配置复杂度": "低",
            "IP白名单": "不需要",
            "成本": "完全免费",
            "推送渠道": "iOS/MacOS/Android",
            "消息格式": "文本、Markdown",
            "稳定性": "中等（自建可提高）",
            "适用场景": "个人项目、开发者"
        },
        "Server酱": {
            "配置复杂度": "很低",
            "IP白名单": "不需要",
            "成本": "免费（有额度限制）",
            "推送渠道": "微信、企业微信、钉钉、飞书等",
            "消息格式": "文本、Markdown",
            "稳定性": "高",
            "适用场景": "快速集成、多平台推送"
        }
    }
    
    print("| 特性 | 企业微信 | PushDeer | Server酱 |")
    print("|------|----------|----------|----------|")
    for key in comparison["企业微信"].keys():
        wechat = comparison["企业微信"][key]
        pushdeer = comparison["PushDeer"][key]
        serverchan = comparison["Server酱"][key]
        print(f"| {key} | {wechat} | {pushdeer} | {serverchan} |")
    
    print()
    print("📋 迁移建议:")
    print("1. 个人项目 → 推荐 PushDeer（完全免费，可自建）")
    print("2. 快速集成 → 推荐 Server酱（配置简单，多通道）")
    print("3. 企业环境 → 可考虑 Server酱企业微信通道")
    print("4. 对隐私要求高 → 推荐 PushDeer自建")
    print()

# ============================================================================
# 迁移步骤
# ============================================================================

def migration_steps():
    """迁移步骤"""
    print("=== 迁移步骤 ===")
    
    steps = [
        {
            "步骤": "1. 评估需求",
            "任务": [
                "确定消息推送频率",
                "评估消息格式要求",
                "考虑接收端平台",
                "评估隐私和安全需求"
            ]
        },
        {
            "步骤": "2. 选择替代方案",
            "任务": [
                "PushDeer: 适合个人项目、开源可自建",
                "Server酱: 适合快速集成、多平台支持",
                "根据需求选择合适的方案"
            ]
        },
        {
            "步骤": "3. 获取API密钥",
            "任务": [
                "PushDeer: 安装客户端获取pushkey",
                "Server酱: 访问sct.ftqq.com获取sendkey",
                "将密钥存储在安全位置"
            ]
        },
        {
            "步骤": "4. 修改代码",
            "任务": [
                "替换企业微信API调用",
                "转换消息格式（如需要）",
                "更新错误处理逻辑",
                "添加重试机制"
            ]
        },
        {
            "步骤": "5. 测试",
            "任务": [
                "测试消息发送功能",
                "验证消息格式",
                "测试错误处理",
                "性能测试"
            ]
        },
        {
            "步骤": "6. 部署",
            "任务": [
                "更新配置文件",
                "部署到测试环境",
                "监控运行状态",
                "逐步迁移到生产环境"
            ]
        }
    ]
    
    for step in steps:
        print(f"\n{step['步骤']}:")
        for task in step["任务"]:
            print(f"  • {task}")
    
    print()
    print("⏱️ 预计时间:")
    print("简单迁移: 1-2小时")
    print("完整迁移（含测试）: 1-2天")
    print("复杂系统迁移: 1-2周")
    print()

# ============================================================================
# 主函数
# ============================================================================

def main():
    """主函数"""
    print("=" * 60)
    print("企业微信到PushDeer/Server酱迁移指南")
    print("=" * 60)
    print()
    
    # 1. 原企业微信示例
    original_wechat_example()
    
    # 2. 迁移到PushDeer
    migrate_to_pushdeer()
    
    # 3. 迁移到Server酱
    migrate_to_serverchan()
    
    # 4. 方案对比
    migration_comparison()
    
    # 5. 迁移步骤
    migration_steps()
    
    print("=" * 60)
    print("迁移完成！")
    print("=" * 60)
    
    print("\n📚 相关文件:")
    print("1. test_pushdeer_serverchan.py - 完整的测试脚本")
    print("2. simple_push_notification.py - 简单的推送脚本")
    print("3. push_notification_guide.md - 详细配置指南")
    print()
    
    print("🚀 快速开始:")
    print("1. 获取PushDeer pushkey或Server酱 sendkey")
    print("2. 运行测试脚本验证配置")
    print("3. 集成到现有代码中")
    print("4. 测试并部署")

if __name__ == "__main__":
    main()