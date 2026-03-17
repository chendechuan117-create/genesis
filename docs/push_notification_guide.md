# PushDeer/Server酱作为企业微信替代方案配置指南

## 概述

本文档介绍如何使用PushDeer和Server酱作为企业微信消息推送的替代方案，解决企业微信需要IP白名单配置的复杂性问题。

## 一、方案对比

### 1.1 企业微信方案
**优点：**
- 官方支持，稳定性高
- 与企业微信生态集成
- 支持丰富的消息格式

**缺点：**
- 需要IP白名单配置
- 配置复杂，需要企业认证
- 有调用频率限制
- 需要维护access_token

### 1.2 PushDeer方案
**优点：**
- 开源可自建，完全免费
- 无需IP白名单
- 支持Markdown格式
- 无调用频率限制（自建版）
- 支持多平台（iOS/MacOS/Android）

**缺点：**
- 需要安装客户端
- 自建需要服务器资源
- 官方在线版可能有稳定性问题

### 1.3 Server酱方案
**优点：**
- 无需安装客户端
- 支持多种推送通道（微信、企业微信、钉钉、飞书等）
- 免费额度充足
- 无需IP白名单
- 配置简单，快速集成

**缺点：**
- 依赖第三方服务
- 免费版可能有频率限制
- 需要注册获取sendkey

## 二、快速开始

### 2.1 PushDeer快速配置

#### 步骤1：获取PushDeer客户端
1. **iOS用户**：App Store搜索"PushDeer"安装
2. **Android用户**：从GitHub releases下载APK
3. **Mac用户**：Mac App Store搜索"PushDeer"安装

#### 步骤2：获取pushkey
1. 打开PushDeer客户端
2. 在设备页面找到"设备KEY"
3. 复制pushkey（格式如：PDUxxxxx）

#### 步骤3：Python代码集成
```python
import requests

def send_pushdeer(pushkey, title, content=""):
    url = "https://api2.pushdeer.com/message/push"
    
    payload = {
        "pushkey": pushkey,
        "text": title,
        "desp": content,
        "type": "markdown" if content else "text"
    }
    
    response = requests.post(url, data=payload)
    return response.json()

# 使用示例
result = send_pushdeer(
    pushkey="你的pushkey",
    title="服务器告警",
    content="CPU使用率超过90%"
)
```

### 2.2 Server酱快速配置

#### 步骤1：注册获取sendkey
1. 访问 https://sct.ftqq.com
2. 微信扫码登录
3. 在"Key&API"页面获取sendkey（格式如：SCTxxxxx）

#### 步骤2：Python代码集成
```python
import requests

def send_serverchan(sendkey, title, content="", channel=9):
    url = f"https://sctapi.ftqq.com/{sendkey}.send"
    
    payload = {
        "title": title,
        "desp": content,
        "channel": channel  # 9=微信，66=企业微信，30=钉钉，18=飞书
    }
    
    response = requests.post(url, data=payload)
    return response.json()

# 使用示例
result = send_serverchan(
    sendkey="你的sendkey",
    title="任务完成通知",
    content="数据库备份任务已完成",
    channel=9  # 推送到微信
)
```

## 三、从企业微信迁移

### 3.1 迁移步骤

#### 步骤1：分析现有代码
查找现有企业微信消息发送代码，通常包含：
- `get_access_token()` 函数
- `send_message()` 函数
- 企业ID、Secret、AgentId配置

#### 步骤2：替换消息发送逻辑
将企业微信的发送逻辑替换为PushDeer或Server酱：

**原企业微信代码：**
```python
def send_wechat_message(access_token, message):
    url = f"https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token={access_token}"
    response = requests.post(url, json=message)
    return response.json()
```

**替换为PushDeer：**
```python
def send_pushdeer_message(pushkey, title, content):
    url = "https://api2.pushdeer.com/message/push"
    payload = {
        "pushkey": pushkey,
        "text": title,
        "desp": content,
        "type": "markdown"
    }
    response = requests.post(url, data=payload)
    return response.json()
```

#### 步骤3：更新配置管理
将企业微信配置替换为新的配置：

**原配置：**
```python
CORP_ID = "ww17809bd1255d3ec9"
SECRET = "tj3QXRgmj9sL2k2Rv-P79HnJB7sEjhtgKpXQrmYAY40"
AGENT_ID = 1000002
```

**新配置：**
```python
# PushDeer配置
PUSHDEER_KEY = "PDUxxxxx"
PUSHDEER_ENDPOINT = "https://api2.pushdeer.com"

# 或Server酱配置
SERVERCHAN_KEY = "SCTxxxxx"
SERVERCHAN_CHANNEL = 9  # 微信推送
```

### 3.2 消息格式转换

企业微信通常使用textcard格式，需要转换为Markdown：

**企业微信textcard：**
```python
message = {
    "touser": "@all",
    "msgtype": "textcard",
    "agentid": AGENT_ID,
    "textcard": {
        "title": "每日早报",
        "description": "<div class=\"gray\">2024-01-01</div><div class=\"normal\">内容</div>",
        "url": "https://example.com",
        "btntxt": "查看详情"
    }
}
```

**转换为Markdown：**
```python
markdown_content = f"""
# 每日早报

**时间**: 2024-01-01

## 内容
这里是消息内容

[查看详情](https://example.com)
"""
```

## 四、高级配置

### 4.1 自建PushDeer服务

对于需要更高稳定性和控制权的场景，可以自建PushDeer服务：

#### Docker部署：
```bash
# 克隆仓库
git clone https://gitee.com/easychen/pushdeer.git
cd pushdeer

# 使用Docker Compose部署
sudo docker-compose up -d
```

#### 配置自建端点：
```python
# 使用自建服务
PUSHDEER_ENDPOINT = "http://your-server.com:8800"  # 自建服务地址
```

### 4.2 Server酱多通道配置

Server酱支持多种推送通道，可以根据需要选择：

| 通道值 | 通道名称 | 说明 |
|--------|----------|------|
| 9 | 微信 | 默认通道，推送到个人微信 |
| 66 | 企业微信 | 推送到企业微信应用 |
| 30 | 钉钉 | 推送到钉钉群 |
| 18 | 飞书 | 推送到飞书群 |
| 100 | PushDeer | 通过Server酱推送到PushDeer |

```python
# 推送到不同通道
channels = {
    'wechat': 9,
    'wechat_work': 66,
    'dingtalk': 30,
    'feishu': 18,
    'pushdeer': 100
}

# 推送到企业微信
send_serverchan(sendkey, "消息标题", "消息内容", channel=66)
```

### 4.3 错误处理与重试

```python
import time
from typing import Optional

def send_with_retry(service: str, key: str, title: str, content: str = "", 
                   max_retries: int = 3, retry_delay: int = 5) -> Optional[dict]:
    """
    带重试的消息发送
    
    Args:
        service: 服务类型
        key: API密钥
        title: 消息标题
        content: 消息内容
        max_retries: 最大重试次数
        retry_delay: 重试延迟（秒）
    
    Returns:
        响应结果或None
    """
    for attempt in range(max_retries):
        try:
            if service == 'pushdeer':
                result = send_pushdeer(key, title, content)
            elif service == 'serverchan':
                result = send_serverchan(key, title, content)
            else:
                return None
            
            if result.get('code') == 0:
                return result
            
            print(f"第{attempt + 1}次尝试失败: {result}")
            
        except Exception as e:
            print(f"第{attempt + 1}次尝试异常: {e}")
        
        if attempt < max_retries - 1:
            time.sleep(retry_delay)
    
    return None
```

## 五、最佳实践

### 5.1 配置管理
- 将API密钥存储在环境变量中
- 使用配置文件管理不同环境的配置
- 定期更新和轮换密钥

### 5.2 消息模板
创建可复用的消息模板：

```python
class MessageTemplates:
    """消息模板"""
    
    @staticmethod
    def server_alert(server_name, metric, value, threshold):
        return f"""
# 🚨 服务器告警

**服务器**: {server_name}
**监控指标**: {metric}
**当前值**: {value}
**阈值**: {threshold}
**时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## 建议操作
1. 登录服务器检查
2. 查看相关日志
3. 联系运维人员
"""
    
    @staticmethod
    def task_complete(task_name, duration, status="成功"):
        return f"""
# ✅ 任务完成通知

**任务名称**: {task_name}
**执行状态**: {status}
**耗时**: {duration}
**完成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## 详细信息
- 任务ID: {hash(task_name)}
- 执行主机: {socket.gethostname()}
- 执行用户: {getpass.getuser()}
"""
```

### 5.3 监控与日志
```python
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def send_notification_with_log(service, key, title, content):
    """带日志记录的消息发送"""
    logger.info(f"发送{service}消息: {title}")
    
    try:
        result = send_notification(service, key, title, content)
        
        if result and result.get('code') == 0:
            logger.info(f"{service}消息发送成功")
            return True
        else:
            logger.error(f"{service}消息发送失败: {result}")
            return False
            
    except Exception as e:
        logger.exception(f"{service}消息发送异常")
        return False
```

## 六、故障排除

### 6.1 常见问题

#### 问题1：PushDeer消息发送失败
**可能原因：**
- pushkey错误或过期
- 网络连接问题
- 官方服务不稳定

**解决方案：**
1. 检查pushkey是否正确
2. 测试网络连接：`curl -I https://api2.pushdeer.com`
3. 考虑自建PushDeer服务

#### 问题2：Server酱返回"错误的Key"
**可能原因：**
- sendkey错误
- sendkey已失效
- 输入错误

**解决方案：**
1. 重新登录Server酱获取新的sendkey
2. 检查sendkey是否包含特殊字符
3. 确认sendkey格式：SCTxxxxx

#### 问题3：消息未收到
**可能原因：**
- 客户端未正确配置
- 消息被过滤
- 网络延迟

**解决方案：**
1. 检查客户端通知权限
2. 查看客户端消息记录
3. 测试简单消息确认通道正常

### 6.2 调试工具
```python
def debug_notification_service(service, key):
    """调试通知服务"""
    print(f"调试{service}服务...")
    
    # 测试网络连接
    if service == 'pushdeer':
        test_url = "https://api2.pushdeer.com/message/push"
    elif service == 'serverchan':
        test_url = f"https://sctapi.ftqq.com/{key}.send"
    
    print(f"测试URL: {test_url}")
    
    try:
        response = requests.get(test_url.split('?')[0], timeout=5)
        print(f"服务可达: HTTP {response.status_code}")
    except Exception as e:
        print(f"服务不可达: {e}")
    
    # 发送测试消息
    test_result = send_notification(
        service=service,
        key=key,
        title="测试消息",
        content="这是一个调试测试消息"
    )
    
    print(f"测试结果: {test_result}")
    return test_result
```

## 七、性能优化

### 7.1 批量发送
```python
def send_batch_messages(service, key, messages):
    """批量发送消息"""
    results = []
    
    for msg in messages:
        result = send_notification(
            service=service,
            key=key,
            title=msg.get('title'),
            content=msg.get('content')
        )
        results.append(result)
        
        # 避免频率限制
        time.sleep(0.5)
    
    return results
```

### 7.2 异步发送
```python
import asyncio
import aiohttp

async def send_async_notification(service, key, title, content):
    """异步发送消息"""
    if service == 'pushdeer':
        url = "https://api2.pushdeer.com/message/push"
        payload = {
            "pushkey": key,
            "text": title,
            "desp": content,
            "type": "markdown"
        }
    elif service == 'serverchan':
        url = f"https://sctapi.ftqq.com/{key}.send"
        payload = {
            "title": title,
            "desp": content,
            "channel": 9
        }
    
    async with aiohttp.ClientSession() as session:
        async with session.post(url, data=payload) as response:
            return await response.json()

# 使用示例
async def main():
    tasks = [
        send_async_notification('serverchan', 'SCTxxxxx', '消息1', '内容1'),
        send_async_notification('serverchan', 'SCTxxxxx', '消息2', '内容2'),
    ]
    results = await asyncio.gather(*tasks)
    print(results)
```

## 八、迁移检查清单

- [ ] 获取PushDeer pushkey或Server酱 sendkey
- [ ] 更新配置文件和环境变量
- [ ] 替换消息发送代码
- [ ] 转换消息格式（如需要）
- [ ] 测试消息发送功能
- [ ] 配置错误处理和重试机制
- [ ] 更新相关文档
- [ ] 通知相关人员配置变更

## 九、总结

PushDeer和Server酱都是优秀的企业微信替代方案，特别适合以下场景：

1. **快速原型开发**：Server酱配置简单，快速集成
2. **个人项目**：PushDeer完全免费，无需注册
3. **对隐私要求高**：PushDeer可自建，数据完全可控
4. **多平台推送**：Server酱支持微信、企业微信、钉钉、飞书等多种通道

通过本文档的指导，您可以顺利从企业微信迁移到更简单、更灵活的消息推送方案。