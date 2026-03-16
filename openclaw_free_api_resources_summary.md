# OpenClaw 免费API资源速查表

## 📊 免费API资源对比

| 平台 | 免费额度 | 模型数量 | 获取难度 | 推荐指数 | 特点 |
|------|----------|----------|----------|----------|------|
| **OpenRouter** | 30+免费模型 | 300+ | ⭐⭐ | ★★★★★ | 一个API Key调用所有主流模型 |
| **Zen平台** | MiniMax M2.5免费 | 多个 | ⭐⭐ | ★★★★☆ | 国产顶尖模型，OpenAI兼容 |
| **阿里云百炼** | 100万Tokens/模型 | 多个 | ⭐ | ★★★★☆ | 新用户福利，额度大 |
| **MiniMax M2.5** | 无限量 | 1个 | ⭐⭐ | ★★★★☆ | 作者推荐，真免费 |
| **Nvidia API** | 免费 | 多个 | ⭐⭐⭐ | ★★★☆☆ | 技术向，适合开发者 |

## 🔑 快速获取指南

### 1. OpenRouter（首选推荐）
**获取步骤**：
1. 访问：https://openrouter.ai
2. 注册账号
3. Settings → API Keys → Create Key
4. 复制API Key

**配置OpenClaw**：
```bash
# 配置文件位置：~/.openclaw/openclaw.json
{
  "model_provider": "openrouter",
  "api_key": "sk-or-v1-xxxxxxxx",
  "base_url": "https://openrouter.ai/api/v1",
  "model": "openrouter/auto"
}
```

### 2. 阿里云百炼（额度最大）
**获取步骤**：
1. 访问：阿里云百炼平台
2. 新用户注册
3. 开通服务 → 领取免费额度
4. 获取API Key

**免费额度**：
- 每个模型100万Tokens
- 总免费额度超5000万Tokens
- 有效期180天

### 3. Zen平台（国产精品）
**获取步骤**：
1. 访问：https://opencode.ai/zen
2. 注册账号
3. API Keys标签页创建密钥
4. 获取MiniMax M2.5 Free API

## ⚡ 一键配置脚本

```bash
#!/bin/bash
# OpenClaw多免费API自动配置脚本

echo "正在配置OpenClaw免费API资源..."

# 创建配置目录
mkdir -p ~/.openclaw

# 生成配置文件
cat > ~/.openclaw/openclaw.json << EOF
{
  "model_providers": {
    "openrouter": {
      "api_key": "YOUR_OPENROUTER_KEY",
      "base_url": "https://openrouter.ai/api/v1",
      "enabled": true,
      "priority": 1
    },
    "bailian": {
      "api_key": "YOUR_BAILIAN_KEY",
      "endpoint": "https://dashscope.aliyuncs.com/compatible-mode/v1",
      "enabled": true,
      "priority": 2
    },
    "zen": {
      "api_key": "YOUR_ZEN_KEY",
      "base_url": "https://opencode.ai/zen/v1",
      "enabled": true,
      "priority": 3
    }
  },
  "model_router": {
    "strategy": "fallback",
    "default": "openrouter/auto",
    "fallback_order": ["openrouter", "bailian", "zen"]
  }
}
EOF

echo "配置文件已生成！"
echo "请将YOUR_*_KEY替换为实际的API密钥"
```

## 🎯 使用技巧

### 1. 模型选择策略
- **日常聊天**：OpenRouter免费模型
- **代码编写**：Zen平台的GPT Codex
- **长文本处理**：阿里云百炼
- **创意写作**：MiniMax M2.5

### 2. 避免限流
```python
# Python示例：API轮换策略
import random

apis = [
    {"key": "openrouter_key", "url": "https://openrouter.ai/api/v1"},
    {"key": "bailian_key", "url": "https://dashscope.aliyuncs.com/v1"},
    {"key": "zen_key", "url": "https://opencode.ai/zen/v1"}
]

def get_random_api():
    return random.choice(apis)
```

### 3. 监控使用情况
```bash
# 查看API使用统计
curl -H "Authorization: Bearer YOUR_API_KEY" \
  https://openrouter.ai/api/v1/usage
```

## 🚀 高级薅羊毛方案

### 方案一：家庭套餐
1. 注册多个平台的免费账号
2. 每个账号获取免费额度
3. 使用负载均衡轮询调用

### 方案二：企业试用
1. 使用企业邮箱注册
2. 申请企业试用额度（通常更大）
3. 多个员工共享使用

### 方案三：教育优惠
1. 使用.edu邮箱注册
2. 申请教育版免费额度
3. 享受学生/教师专属资源

## ⚠️ 注意事项

1. **遵守服务条款**：不要滥用免费资源
2. **数据安全**：敏感数据建议本地处理
3. **服务稳定性**：免费API可能有波动
4. **额度监控**：定期检查剩余额度

## 🔗 有用链接

- OpenClaw官方GitHub：https://github.com/openclaw
- OpenRouter免费模型列表：https://openrouter.ai/models
- 阿里云百炼免费额度：https://www.aliyun.com/product/ai/bailian
- Zen平台：https://opencode.ai/zen
- OpenClaw中文社区：https://github.com/yeuxuan/openclaw-docs

---

**最后更新**：2026年3月
**适用版本**：OpenClaw 2026.3.x
**推荐配置**：8GB内存 + 20GB存储空间