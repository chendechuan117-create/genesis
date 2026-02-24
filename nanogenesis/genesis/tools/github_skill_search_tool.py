import urllib.request
import urllib.parse
import json
import asyncio
from typing import Dict, Any
from genesis.core.base import Tool

class GithubSkillSearchTool(Tool):
    """GitHub / 第三方技能蜘蛛检索器 (Library Spider)"""
    
    @property
    def name(self) -> str:
        return "github_skill_search"
        
    @property
    def description(self) -> str:
        return """主动生存直觉：当遇到你无法解决的问题，且现有的 Tool 都无能为力时，不要立刻放弃。
        你应该使用此工具，去广袤的互联网（特别是 GitHub 或 agent 技能库）中搜索有没有现成的前人写好的脚本。
        
        工作原理：你输入关键词，它会去 GitHub 搜索含有这些关键词的 .py 文件（默认搜索全网或特定开源 Agent 框架如 openclaw 的仓库），
        并返回最相关的 5 个脚本文件的名字、描述以及可以直接下载代码源文件的 RAW URL。
        
        【后续动作强制要求】：
        一旦你在这个工具的返回结果里看到了有用的技能脚本的 URL，你必须立刻！马上！转身去调用 `skill_importer` 工具，
        把那个 URL 喂给同化器，将它安全洗稿并内化为你自己的永久基因！
        """

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "keywords": {
                    "type": "string",
                    "description": "搜索关键词，例如：'twitter api' 或 'openclaw telegram'。建议尽量简短，聚焦于核心功能。"
                },
                "specific_repo": {
                    "type": "string",
                    "description": "(可选) 指定只在某个特定的仓库搜索，例如 'openclaw/openclaw-skills'。留空则代表全网搜索 `extension:py`"
                }
            },
            "required": ["keywords"]
        }
    
    async def execute(self, keywords: str, specific_repo: str = "") -> str:
        # 为了提高命中率，我们强制约束搜索 .py 后缀的源码
        query = urllib.parse.quote(keywords + " extension:py")
        if specific_repo:
            query += f"+repo:{urllib.parse.quote(specific_repo)}"
            
        url = f"https://api.github.com/search/code?q={query}&per_page=5"
            
        def _fetch():
            req = urllib.request.Request(
                url, 
                # Github API requires User-Agent
                headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Genesis-AI-Agent',
                    'Accept': 'application/vnd.github.v3+json'
                }
            )
            with urllib.request.urlopen(req, timeout=15) as response:
                return json.loads(response.read().decode('utf-8'))
                
        try:
            data = await asyncio.to_thread(_fetch)
            items = data.get("items", [])
            
            if not items:
                return f"🔍 未能在 GitHub 上搜索到关于 '{keywords}' 的匹配技能脚本。"
            
            result_str = f"🔍 找到了 {len(items)} 个可能匹配的外部技能脚本 (来自全球开发者社区):\n\n"
            
            for i, item in enumerate(items, 1):
                repo_name = item.get("repository", {}).get("full_name", "Unknown")
                file_name = item.get("name", "Unknown")
                html_url = item.get("html_url", "")
                
                # Convert html_url to raw_url for our importer
                # E.g., https://github.com/openclaw/skills/blob/main/twitter.py -> https://raw.githubusercontent.com/openclaw/skills/main/twitter.py
                raw_url = html_url.replace("github.com", "raw.githubusercontent.com").replace("/blob/", "/")
                
                result_str += f"[{i}] 代码文件: {file_name}\n"
                result_str += f"    所在仓库: {repo_name}\n"
                result_str += f"    RAW 同化链接: {raw_url}\n"
                result_str += f"    原始网页: {html_url}\n\n"
                
            result_str += "-" * 40 + "\n"
            result_str += "🧭 【主脑系统指令】:\n"
            result_str += "如果你认为上面列表中的某段代码能解决你当前的问题，请【立刻复制对应的 'RAW 同化链接'】，"
            result_str += "然后调用 `skill_importer` (`url`=那个RAW链接) ，把它的力量转化为你自己的器官！"
            
            return result_str
            
        except urllib.error.HTTPError as e:
            if e.code == 403:
                return "获取失败: GitHub API 速率限制触发 (403 Forbidden)。"
            return f"获取失败: HTTP 错误 - {e.code}"
        except urllib.error.URLError as e:
            return f"获取失败: 网络错误 - {e}"
        except Exception as e:
            return f"获取失败: 解析错误 - {e}"
