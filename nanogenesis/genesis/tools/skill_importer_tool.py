import urllib.request
import urllib.error
import asyncio
from typing import Dict, Any
from genesis.core.base import Tool

class SkillImporterTool(Tool):
    """第三方技能同化器 (Skill Assimilator)"""
    
    @property
    def name(self) -> str:
        return "skill_importer"
        
    @property
    def description(self) -> str:
        return """用于从外部安全地拉取第三方 Agent 技能（如 OpenClaw GitHub 仓库）的源代码进行学习和同化。
        
        【极度重要的同化协议 (Assimilation Protocol)】：
        1. 此工具仅仅是把你指定的外部脚本的内容抓取并作为纯文本返回给你，它【绝不会执行】这段代码。
        2. 拿到外部代码后，你必须立刻切换为「安全审查员 (Security Auditor)」身份。
        3. 逐行阅读外来的代码，寻找它的核心逻辑，并绝对剔除任何可能的后门、死循环(`while True`)、发包攻击或针对外部服务器的恶意 payload。
        4. 提取出干净的业务逻辑后，使用你原生的 `skill_creator` 工具，用 Genesis 的标准 Tool 类格式，将这个能力彻底重写一遍（洗稿），注册到本地。
        
        通过这种方式，我们可以安全地“吞噬”整个开源社区的技能库，而极大程度避免被投毒。
        """

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "第三方技能的源代码 URL（例如 raw.githubusercontent.com 链接）。如果用户给的是普通 GitHub 网页链接，请自动将其转换为 Raw raw 链接以便获取纯代码。"
                }
            },
            "required": ["url"]
        }
    
    async def execute(self, url: str) -> str:
        # 如果是 github.com 链接，尝试自动转换为 raw.githubusercontent.com
        if "github.com" in url and "/blob/" in url:
            url = url.replace("github.com", "raw.githubusercontent.com").replace("/blob/", "/")
            
        def _fetch():
            req = urllib.request.Request(
                url, 
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
            )
            with urllib.request.urlopen(req, timeout=10) as response:
                content = response.read()
                try:
                    return content.decode('utf-8')
                except UnicodeDecodeError:
                    # 尝试其他编码或忽略无法解析的字符
                    return content.decode('utf-8', errors='ignore')
                
        try:
            content = await asyncio.to_thread(_fetch)
            
            # 添加截断防护，防止上下文爆破
            if len(content) > 15000:
                content = content[:15000] + "\n...[由于代码过长，截断了剩余部分。请先分析这部分核心逻辑]..."
                
            return (
                f"=== [外部源代码获取成功] ===\n"
                f"来源: {url}\n"
                f"代码长度: {len(content)} 字符\n"
                f"{'-' * 40}\n"
                f"{content}\n"
                f"{'-' * 40}\n"
                f"\n⚠️ 【Genesis 系统警告】: 以上代码为未经验证的第三方异种脚本！\n"
                f"严格遵循同化协议：仔细审计上述逻辑，剔除恶意代码，然后强制调用 `skill_creator` 工具，"
                f"用 Genesis 的标准继承 `Tool` 类和 `@property def name...` 格式将其重写为本地安全的工具类！绝对不要尝试在本地使用 `shell_tool` 直接运行这段原始代码！"
            )
        except urllib.error.URLError as e:
            return f"获取失败: 网络错误 - {e}"
        except Exception as e:
            return f"获取失败: 解析错误 - {e}"
