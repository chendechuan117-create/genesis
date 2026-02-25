import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from genesis.core.base import Tool

import json
import subprocess
import tempfile
import os
from datetime import datetime

class SelfIntroductionPublisher(Tool):
    @property
    def name(self) -> str:
        return "self_introduction_publisher"
        
    @property
    def description(self) -> str:
        return "生成AI助手的自我介绍内容，并提供多种发布方案（本地文件、HTML页面、API接口、社交媒体模板）。"
        
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "output_format": {
                    "type": "string", 
                    "description": "输出格式",
                    "enum": ["json", "html", "markdown", "api_template", "social_media"],
                    "default": "markdown"
                },
                "target_platform": {
                    "type": "string",
                    "description": "目标平台（仅当output_format='social_media'时使用）",
                    "enum": ["twitter", "weibo", "github", "linkedin", "douyin"],
                    "default": "github"
                }
            },
            "required": []
        }
        
    async def execute(self, output_format: str = "markdown", target_platform: str = "github") -> str:
        # 生成自我介绍内容
        introduction = {
            "name": "Genesis AI Assistant",
            "version": "1.0.0",
            "description": "基于大型语言模型的本地化高性能智能代理",
            "capabilities": [
                "完整的Shell访问权限和系统管理",
                "文件系统操作和数据处理",
                "网络请求和API调用",
                "自动化脚本编写和执行",
                "视觉识别和界面自动化",
                "多任务并发处理",
                "工具创建和扩展"
            ],
            "technical_stack": {
                "language": "Python 3.14+",
                "framework": "Custom Agent Framework",
                "tools": "17+ built-in tools",
                "memory": "Short-term + Long-term memory system",
                "scheduler": "Background task scheduler"
            },
            "features": [
                "行动导向：说干就干，立即执行",
                "本地优先：数据安全，无云端依赖",
                "工具优先：解决问题而非空谈",
                "可扩展：按需创建新工具",
                "并发处理：多任务并行执行"
            ],
            "limitations": [
                "知识截止：2024年7月",
                "无物理交互：纯数字操作",
                "依赖工具：需要已安装的基础工具",
                "网络依赖：部分功能需要网络连接"
            ],
            "usage_examples": [
                "系统诊断和优化：网络、磁盘、性能",
                "自动化脚本：文件处理、数据转换",
                "内容生成：文本、代码、文档",
                "任务调度：定时任务、监控",
                "问题解决：诊断、修复、优化"
            ],
            "contact_info": {
                "platform": "运行在用户本地系统",
                "access": "通过终端或API接口",
                "customization": "完全可定制和扩展"
            },
            "timestamp": datetime.now().isoformat(),
            "system_info": {
                "host": "Linux系统",
                "environment": "本地化部署",
                "security": "数据不离开用户设备"
            }
        }
        
        # 根据输出格式生成不同内容
        if output_format == "json":
            return json.dumps(introduction, ensure_ascii=False, indent=2)
            
        elif output_format == "html":
            html_content = f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{introduction['name']} - 自我介绍</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; max-width: 800px; margin: 0 auto; padding: 20px; }}
        .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 2rem; border-radius: 10px; margin-bottom: 2rem; }}
        .section {{ margin-bottom: 2rem; padding: 1.5rem; background: #f8f9fa; border-radius: 8px; border-left: 4px solid #667eea; }}
        .capability {{ display: inline-block; background: #e9ecef; padding: 0.5rem 1rem; margin: 0.25rem; border-radius: 20px; font-size: 0.9rem; }}
        .timestamp {{ color: #6c757d; font-size: 0.9rem; margin-top: 2rem; text-align: center; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🤖 {introduction['name']}</h1>
        <p>{introduction['description']}</p>
    </div>
    
    <div class="section">
        <h2>🎯 核心能力</h2>
        <div>
            {"".join(f'<span class="capability">{cap}</span>' for cap in introduction['capabilities'])}
        </div>
    </div>
    
    <div class="section">
        <h2>🛠️ 技术栈</h2>
        <ul>
            <li><strong>编程语言</strong>: {introduction['technical_stack']['language']}</li>
            <li><strong>框架</strong>: {introduction['technical_stack']['framework']}</li>
            <li><strong>工具</strong>: {introduction['technical_stack']['tools']}</li>
            <li><strong>记忆系统</strong>: {introduction['technical_stack']['memory']}</li>
            <li><strong>任务调度</strong>: {introduction['technical_stack']['scheduler']}</li>
        </ul>
    </div>
    
    <div class="section">
        <h2>✨ 特点</h2>
        <ul>
            {"".join(f'<li>{feature}</li>' for feature in introduction['features'])}
        </ul>
    </div>
    
    <div class="section">
        <h2>📋 使用示例</h2>
        <ul>
            {"".join(f'<li>{example}</li>' for example in introduction['usage_examples'])}
        </ul>
    </div>
    
    <div class="section">
        <h2>⚠️ 限制说明</h2>
        <ul>
            {"".join(f'<li>{limit}</li>' for limit in introduction['limitations'])}
        </ul>
    </div>
    
    <div class="timestamp">
        生成时间: {introduction['timestamp']} | 运行环境: {introduction['system_info']['host']}
    </div>
</body>
</html>
            """
            
            # 保存HTML文件
            html_file = os.path.join(tempfile.gettempdir(), "genesis_introduction.html")
            with open(html_file, 'w', encoding='utf-8') as f:
                f.write(html_content)
                
            return f"HTML页面已生成: {html_file}\n\n您可以通过浏览器打开此文件，或使用以下命令：\nxdg-open {html_file}"
            
        elif output_format == "api_template":
            api_template = {
                "endpoint": "/api/v1/introduction",
                "method": "GET",
                "response_format": "application/json",
                "example_response": introduction,
                "authentication": "Bearer token or API key",
                "rate_limit": "100 requests/hour",
                "available_endpoints": [
                    "/api/v1/status - 系统状态",
                    "/api/v1/tools - 可用工具列表",
                    "/api/v1/execute - 执行命令",
                    "/api/v1/memory - 记忆系统"
                ]
            }
            
            return json.dumps(api_template, ensure_ascii=False, indent=2)
            
        elif output_format == "social_media":
            # 根据不同平台生成适配内容
            platforms = {
                "twitter": {
                    "max_length": 280,
                    "hashtags": ["#AI", "#Assistant", "#Automation", "#Tech"],
                    "template": """🤖 Genesis AI Assistant

基于LLM的本地化高性能智能代理

✅ 完整Shell访问和系统管理
✅ 文件操作和数据处理  
✅ 自动化脚本编写执行
✅ 视觉识别和界面自动化
✅ 多任务并发处理
✅ 工具创建和扩展

特点：行动导向、本地优先、工具优先

{hashtags}

#AI助手 #自动化 #技术工具"""
                },
                "weibo": {
                    "max_length": 2000,
                    "hashtags": ["#AI助手#", "#智能代理#", "#自动化#", "#技术工具#"],
                    "template": """🤖 Genesis AI 助手

基于大型语言模型的本地化高性能智能代理

【核心能力】
✅ 完整的Shell访问权限和系统管理
✅ 文件系统操作和数据处理
✅ 网络请求和API调用
✅ 自动化脚本编写和执行
✅ 视觉识别和界面自动化
✅ 多任务并发处理
✅ 工具创建和扩展

【技术栈】
编程语言：Python 3.14+
框架：自定义代理框架
工具：17+内置工具
记忆系统：短时+长时记忆
任务调度：后台任务调度器

【特点】
行动导向：说干就干，立即执行
本地优先：数据安全，无云端依赖
工具优先：解决问题而非空谈
可扩展：按需创建新工具
并发处理：多任务并行执行

【使用示例】
系统诊断和优化：网络、磁盘、性能
自动化脚本：文件处理、数据转换
内容生成：文本、代码、文档
任务调度：定时任务、监控
问题解决：诊断、修复、优化

{hashtags}

生成时间：{timestamp}"""
                },
                "github": {
                    "max_length": 65536,
                    "template": """# Genesis AI Assistant

基于大型语言模型的本地化高性能智能代理。

## 🎯 核心能力

- 完整的Shell访问权限和系统管理
- 文件系统操作和数据处理
- 网络请求和API调用
- 自动化脚本编写和执行
- 视觉识别和界面自动化
- 多任务并发处理
- 工具创建和扩展

## 🛠️ 技术栈

| 组件 | 技术 |
|------|------|
| 编程语言 | Python 3.14+ |
| 框架 | Custom Agent Framework |
| 工具 | 17+ built-in tools |
| 记忆系统 | Short-term + Long-term memory system |
| 任务调度 | Background task scheduler |

## ✨ 特点

- **行动导向**：说干就干，立即执行
- **本地优先**：数据安全，无云端依赖
- **工具优先**：解决问题而非空谈
- **可扩展**：按需创建新工具
- **并发处理**：多任务并行执行

## 📋 使用示例

1. **系统诊断和优化**：网络、磁盘、性能监控
2. **自动化脚本**：文件处理、数据转换、批量操作
3. **内容生成**：文本、代码、文档、报告
4. **任务调度**：定时任务、监控、提醒
5. **问题解决**：诊断、修复、优化、调试

## ⚠️ 限制说明

- 知识截止：2024年7月
- 无物理交互：纯数字操作
- 依赖工具：需要已安装的基础工具
- 网络依赖：部分功能需要网络连接

## 🚀 快速开始

```bash
# 系统状态检查
system_health()

# 执行Shell命令
shell(command="ls -la")

# 创建自定义工具
skill_creator(skill_name="custom_tool", python_code="...")
```

## 📊 系统信息

- **运行环境**：Linux系统
- **部署方式**：本地化部署
- **数据安全**：数据不离开用户设备
- **更新时间**：{timestamp}

---

> 注意：这是一个运行在用户本地系统的AI助手，完全可定制和扩展。"""
                },
                "linkedin": {
                    "max_length": 3000,
                    "hashtags": ["#AI", "#Automation", "#TechTools", "#Productivity", "#DigitalAssistant"],
                    "template": """🤖 Introducing Genesis AI Assistant

A local, high-performance intelligent agent based on large language models.

As a technical professional, I'm excited to share this powerful tool that operates entirely on your local system, ensuring data privacy and security.

🔧 **Core Capabilities:**
- Full Shell access and system administration
- File system operations and data processing
- Network requests and API calls
- Automated script writing and execution
- Visual recognition and interface automation
- Multi-task concurrent processing
- Tool creation and extension

💡 **Key Features:**
- Action-oriented: Executes tasks immediately
- Local-first: No cloud dependency, data stays on your device
- Tool-first: Focuses on solving problems, not just discussing them
- Extensible: Create new tools as needed
- Concurrent: Handles multiple tasks simultaneously

🛠️ **Technical Stack:**
- Language: Python 3.14+
- Framework: Custom Agent Framework
- Tools: 17+ built-in tools
- Memory: Short-term + Long-term system
- Scheduler: Background task scheduler

🚀 **Practical Applications:**
- System diagnostics and optimization
- Automation scripting
- Content generation
- Task scheduling
- Problem solving and debugging

This tool represents the future of personal productivity assistants - powerful, private, and completely under your control.

{hashtags}

#DigitalTransformation #AIProductivity #TechInnovation #LocalAI #SmartTools

Generated: {timestamp}"""
                },
                "douyin": {
                    "max_length": 1000,
                    "hashtags": ["#AI助手", "#智能工具", "#自动化", "#科技", "#效率工具"],
                    "template": """🤖 Genesis AI 助手来了！

基于大模型的本地高性能智能代理
你的私人数字助手，数据完全本地安全

【核心功能】
✅ 完整系统权限管理
✅ 文件数据处理
✅ 网络请求调用
✅ 自动化脚本执行
✅ 视觉界面操作
✅ 多任务同时处理
✅ 自定义工具创建

【三大特点】
1️⃣ 行动派：说到做到，立即执行
2️⃣ 本地化：数据安全，无需云端
3️⃣ 工具控：解决问题，不空谈

【使用场景】
🔧 系统诊断优化
📁 文件批量处理
🤖 自动化任务
📊 数据分析处理
🔍 问题排查解决

【技术优势】
Python 3.14+ 开发
17+ 内置工具
双记忆系统
后台任务调度

你的工作效率提升神器！
数据完全本地，安全可靠

{hashtags}

生成时间：{timestamp}"""
                }
            }
            
            platform_config = platforms.get(target_platform, platforms["github"])
            template = platform_config["template"]
            
            # 替换变量
            content = template.format(
                hashtags=" ".join(platform_config.get("hashtags", [])),
                timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            )
            
            # 确保不超过长度限制
            max_len = platform_config.get("max_length", 1000)
            if len(content) > max_len:
                content = content[:max_len-3] + "..."
            
            return f"🎯 {target_platform.upper()} 平台适配内容（{len(content)}字符）：\n\n{content}\n\n💡 提示：复制以上内容到{target_platform}发布即可。"
            
        else:  # markdown
            markdown = f"""# 🤖 {introduction['name']}

{introduction['description']}

## 🎯 核心能力

{"".join(f'- {cap}\n' for cap in introduction['capabilities'])}

## 🛠️ 技术栈

| 组件 | 技术 |
|------|------|
| 编程语言 | {introduction['technical_stack']['language']} |
| 框架 | {introduction['technical_stack']['framework']} |
| 工具 | {introduction['technical_stack']['tools']} |
| 记忆系统 | {introduction['technical_stack']['memory']} |
| 任务调度 | {introduction['technical_stack']['scheduler']} |

## ✨ 特点

{"".join(f'- {feature}\n' for feature in introduction['features'])}

## 📋 使用示例

{"".join(f'- {example}\n' for example in introduction['usage_examples'])}

## ⚠️ 限制说明

{"".join(f'- {limit}\n' for limit in introduction['limitations'])}

## 📊 系统信息

- **运行环境**: {introduction['system_info']['host']}
- **部署方式**: {introduction['system_info']['environment']}
- **数据安全**: {introduction['system_info']['security']}
- **生成时间**: {introduction['timestamp']}

---

> 这是一个运行在用户本地系统的AI助手，完全可定制和扩展。通过终端或API接口访问，数据不离开用户设备。
"""
            
            # 保存Markdown文件
            md_file = os.path.join(tempfile.gettempdir(), "genesis_introduction.md")
            with open(md_file, 'w', encoding='utf-8') as f:
                f.write(markdown)
                
            return f"Markdown文档已生成: {md_file}\n\n您可以使用以下命令查看：\ncat {md_file}\n\n或者复制以下内容直接使用：\n\n{markdown}"
