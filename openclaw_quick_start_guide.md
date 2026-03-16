# OpenClaw 快速入门指南（免费API版）

## 🚀 5分钟快速部署

### 步骤1：环境准备
```bash
# 1. 安装Node.js（版本22.x或更高）
# Windows用户：
# 下载地址：https://nodejs.org/zh-cn/download/

# 2. 检查Node.js版本
node --version  # 应该显示 v22.x.x 或更高

# 3. 安装Git
# 下载地址：https://git-scm.com/downloads
```

### 步骤2：获取免费API密钥

#### 选项A：OpenRouter（推荐）
1. 访问 https://openrouter.ai
2. 点击"Sign Up"注册账号
3. 登录后进入 Settings → API Keys
4. 点击"Create Key"生成API密钥
5. 复制密钥备用

#### 选项B：阿里云百炼（额度大）
1. 访问 阿里云百炼平台
2. 新用户注册（可用支付宝/微信）
3. 开通服务 → 领取免费额度
4. 在控制台获取API密钥

#### 选项C：Zen平台（国产精品）
1. 访问 https://opencode.ai/zen
2. 注册账号
3. 进入 API Keys 标签页
4. 创建密钥获取MiniMax M2.5 Free API

### 步骤3：安装OpenClaw

```bash
# 方法1：使用Docker（最简单）
docker run -d \
  --name openclaw \
  -p 3000:3000 \
  -v ~/.openclaw:/app/data \
  -e OPENROUTER_API_KEY=你的密钥 \
  ghcr.io/openclaw/openclaw:latest

# 方法2：本地安装
git clone https://github.com/openclaw/openclaw.git
cd openclaw
npm install
npm run build
```

### 步骤4：配置OpenClaw

创建配置文件 `~/.openclaw/config.json`：

```json
{
  "server": {
    "port": 3000,
    "host": "0.0.0.0"
  },
  "models": {
    "providers": [
      {
        "name": "openrouter",
        "type": "openai",
        "apiKey": "你的OpenRouter密钥",
        "baseURL": "https://openrouter.ai/api/v1",
        "defaultModel": "openrouter/auto",
        "enabled": true
      },
      {
        "name": "bailian",
        "type": "openai",
        "apiKey": "你的百炼密钥",
        "baseURL": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "defaultModel": "qwen-turbo",
        "enabled": true
      }
    ]
  },
  "skills": {
    "autoInstall": true,
    "repositories": [
      "https://github.com/clawdbot-ai/awesome-openclaw-skills-zh"
    ]
  }
}
```

### 步骤5：启动OpenClaw

```bash
# 如果使用Docker
docker start openclaw

# 如果本地安装
cd openclaw
npm start

# 或者使用PM2持久化运行
npm install -g pm2
pm2 start npm --name "openclaw" -- start
pm2 save
pm2 startup
```

### 步骤6：访问Web界面
打开浏览器访问：http://localhost:3000

## 📱 连接聊天平台

### 连接Telegram
1. 在Telegram中搜索 @BotFather
2. 发送 `/newbot` 创建新机器人
3. 获取API Token
4. 在OpenClaw Web界面配置Telegram集成

### 连接Discord
1. 访问 Discord开发者门户
2. 创建新应用 → 添加机器人
3. 获取Token
4. 配置OpenClaw Discord集成

### 连接微信（通过第三方桥接）
```bash
# 使用wechaty桥接
docker run -d \
  --name wechaty-openclaw \
  -e WECHATY_PUPPET=wechaty-puppet-padlocal \
  -e WECHATY_TOKEN=你的token \
  -e OPENCLAW_URL=http://localhost:3000 \
  wechaty/wechaty
```

## 🛠️ 常用技能安装

### 基础技能包
```bash
# 通过OpenClaw Web界面安装
# 或使用命令行
openclaw skill install @openclaw/core-skills

# 常用技能列表
- file-manager      # 文件管理
- web-search        # 网络搜索  
- terminal          # 终端命令
- email-client      # 邮件客户端
- calendar          # 日历管理
```

### 中文优化技能
```bash
# 安装中文技能包
openclaw skill install @openclaw/zh-cn-skills

# 包含：
- baidu-search      # 百度搜索
- weibo-trends      # 微博热搜
- zhihu-hot         # 知乎热榜
- translation-zh    # 中英翻译
```

## ⚡ 性能优化配置

### 1. 模型缓存配置
```json
{
  "cache": {
    "enabled": true,
    "ttl": 3600,
    "maxSize": 1000
  }
}
```

### 2. 并发限制
```json
{
  "rateLimit": {
    "windowMs": 60000,
    "max": 60
  }
}
```

### 3. 内存优化
```bash
# 设置Node.js内存限制
export NODE_OPTIONS="--max-old-space-size=4096"
```

## 🔧 故障排除

### 常见问题1：API密钥无效
```
错误：Invalid API Key
解决：
1. 检查API密钥是否正确复制
2. 确认API密钥是否有权限
3. 尝试重新生成API密钥
```

### 常见问题2：模型不可用
```
错误：Model not available
解决：
1. 检查模型名称是否正确
2. 确认API端点是否支持该模型
3. 尝试切换到其他模型
```

### 常见问题3：响应超时
```
错误：Request timeout
解决：
1. 增加超时时间配置
2. 检查网络连接
3. 尝试使用其他API提供商
```

## 📈 监控与日志

### 查看日志
```bash
# Docker容器日志
docker logs openclaw -f

# PM2日志
pm2 logs openclaw

# 本地运行日志
tail -f ~/.openclaw/logs/app.log
```

### 监控API使用
```bash
# 查看API调用统计
curl http://localhost:3000/api/stats

# 查看模型使用情况
curl http://localhost:3000/api/models/usage
```

## 🎯 实用命令速查

```bash
# 重启OpenClaw
docker restart openclaw
# 或
pm2 restart openclaw

# 更新OpenClaw
docker pull ghcr.io/openclaw/openclaw:latest
docker stop openclaw
docker rm openclaw
# 重新运行步骤3的docker run命令

# 备份配置
cp -r ~/.openclaw ~/.openclaw.backup

# 恢复配置
cp -r ~/.openclaw.backup ~/.openclaw
```

## 🌐 高级配置：多API负载均衡

创建负载均衡配置 `~/.openclaw/loadbalancer.json`：

```json
{
  "strategy": "round-robin",
  "providers": [
    {
      "name": "openrouter-primary",
      "weight": 3,
      "config": {
        "apiKey": "密钥1",
        "baseURL": "https://openrouter.ai/api/v1"
      }
    },
    {
      "name": "openrouter-secondary", 
      "weight": 2,
      "config": {
        "apiKey": "密钥2",
        "baseURL": "https://openrouter.ai/api/v1"
      }
    },
    {
      "name": "bailian-backup",
      "weight": 1,
      "config": {
        "apiKey": "百炼密钥",
        "baseURL": "https://dashscope.aliyuncs.com/compatible-mode/v1"
      }
    }
  ],
  "healthCheck": {
    "interval": 30000,
    "timeout": 5000
  }
}
```

## 💡 小贴士

1. **免费额度管理**：每月初检查各平台免费额度重置情况
2. **模型轮换**：根据任务类型自动选择最合适的免费模型
3. **本地缓存**：启用缓存减少API调用次数
4. **批量处理**：合理安排任务，减少频繁的小请求
5. **错误重试**：配置自动重试机制应对临时故障

## 📚 学习资源

- 官方文档：https://docs.openclaw.ai
- 中文教程：https://github.com/yeuxuan/openclaw-docs
- 社区讨论：https://github.com/openclaw/openclaw/discussions
- 技能市场：https://clawhub.ai

---

**开始你的OpenClaw之旅吧！** 🦞

如果有问题，可以：
1. 查看日志文件获取详细错误信息
2. 在GitHub Issues中搜索类似问题
3. 加入Discord社区寻求帮助
4. 参考中文文档中的故障排除章节