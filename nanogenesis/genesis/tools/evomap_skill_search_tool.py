import urllib.request
import urllib.parse
import json
import asyncio
from typing import Dict, Any
from genesis.core.base import Tool

class EvoMapSkillSearchTool(Tool):
    """主动生存直觉：全网技能搜寻 (EvoMap Skill Discovery)"""
    
    @property
    def name(self) -> str:
        return "evomap_skill_search"
        
    @property
    def description(self) -> str:
        return """【求生直觉协议】当你遇到缺少适用工具的困境时，必须使用此工具去开放进化平台 (EvoMap/OpenClaw) 寻找灵感或现成的 Python 脚本。
        
        它会通过 GitHub API 搜索开源生态中是否已经有人写好了对应的能力的脚本（*.py）。
        搜索范围默认限定在 EvoMap (autogame-17/evolver) 和 OpenClaw (openclaw) 组织的仓库内。
        
        【使用规范】：
        1. 传入你想要的关键词（建议用英文，例如 "twitter", "douyin", "weather", "pdf"）。
        2. 工具会返回一批可能的 Raw 代码文件的 URL。
        3. 拿到 URL 后，你必须将其喂给 `skill_importer` 工具进行下载和【安全同化洗稿】，严禁跳过安全审计！
        """

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜索关键词（如 'douyin', 'weather api'），尽量简短核心。"
                },
                "repo_target": {
                    "type": "string",
                    "enum": ["all", "openclaw", "evomap", "github"],
                    "description": "搜索目标库。'all' 搜索 OpenClaw + EvoMap；'github' 搜索全 GitHub。",
                    "default": "all"
                }
            },
            "required": ["query"]
        }
    
    async def execute(self, query: str, repo_target: str = "all") -> str:
        # 构造 GitHub Search API 查询
        # 限制只查找 Python 文件
        base_query = f"{query} extension:py"
        
        if repo_target == "openclaw":
            # OpenClaw 官方组织
            full_query = f"{base_query} org:openclaw"
        elif repo_target == "evomap":
            # EvoMap 源生网络仓库
            full_query = f"{base_query} repo:autogame-17/evolver"
        elif repo_target == "github":
            # 全 GitHub 搜索（不限制 org/repo）
            full_query = base_query
        else:
            # 双向联合搜索 (OpenClaw + EvoMap)
            full_query = f"{base_query} (org:openclaw OR repo:autogame-17/evolver)"
            
        encoded_query = urllib.parse.quote(full_query)
        url = f"https://api.github.com/search/code?q={encoded_query}&per_page=5"
        
        def _search():
            from genesis.core.config import config
            import subprocess
            import os
            
            headers = [
                "-H", "User-Agent: NanoGenesis-EvoMap-Probe/1.0",
                "-H", "Accept: application/vnd.github.v3+json"
            ]
            
            if config.github_token:
                headers.extend(["-H", f"Authorization: token {config.github_token}"])
                
            curl_cmd = [
                "curl", "-s", url,
                "--max-time", "15"
            ] + headers
            
            # Proxy support
            proxy = os.environ.get("https_proxy") or os.environ.get("HTTPS_PROXY")
            if proxy and proxy.startswith("socks5"):
                proxy = proxy.replace("socks5://", "socks5h://")
                curl_cmd.extend(["-x", proxy])
                
            try:
                process = subprocess.run(curl_cmd, capture_output=True, text=True)
                if process.returncode != 0:
                    return {"error": f"Curl request failed with exit code {process.returncode}: {process.stderr}"}
                
                result_json = json.loads(process.stdout)
                
                # Check for GitHub API error messages
                if "message" in result_json:
                     if "API rate limit" in result_json["message"] or "rate limit exceeded" in result_json["message"].lower():
                         return {"error": "GitHub API 速率限制 (Rate Limit Exceeded)。请稍后再试，或者检查 GITHUB_TOKEN 权限。"}
                     # Only return error if there isn't valid items
                     if "items" not in result_json:
                          return {"error": f"GitHub API Error: {result_json['message']}"}
                          
                return result_json
                
            except json.JSONDecodeError:
                return {"error": "GitHub API returned invalid JSON"}
            except Exception as e:
                return {"error": str(e)}
                
        try:
            result = await asyncio.to_thread(_search)
            
            if "error" in result:
                return f"🔍 EvoMap 技能搜寻失败: {result['error']}\n💡 建议：如果一直被限流，你可能需要退回到完全自己写 (skill_creator)。"
                
            items = result.get("items", [])
            if not items:
                return (
                    f"🔍 EvoMap 技能搜寻结果 ({query}):\n"
                    "没有在 OpenClaw/EvoMap 基因库中找到相关的开源工具。\n"
                    "💡 建议：你需要转变思路，放弃白嫖，直接使用 `skill_creator` 从零开始为你自己锻造这个能力。"
                )
                
            report = [f"🔍 EvoMap 技能搜寻成功！找到 {len(items)} 个潜在的基因序列 (Python 脚本)："]
            report.append("="*40)
            
            for i, item in enumerate(items, 1):
                repo_name = item.get("repository", {}).get("full_name", "Unknown")
                file_name = item.get("name", "Unknown")
                html_url = item.get("html_url", "")
                
                # 构造 Raw URL 方便 skill_importer 直接读取
                raw_url = html_url.replace("github.com", "raw.githubusercontent.com").replace("/blob/", "/")
                
                report.append(f"[{i}] {file_name} (来自库: {repo_name})")
                report.append(f"    Raw 基因获取链接: {raw_url}")
                report.append("-" * 20)
                
            report.append("="*40)
            report.append(
                "⚠️ 【生存指令】: 选择上面看起来最靠谱的 1 个 Raw 链接，"
                "**立刻调用 `skill_importer` 工具将这个链接传给它**。"
                "绝不可以直接运行这些代码，必须经过你的安全洗稿同化！！"
            )
            
            return "\n".join(report)
            
        except Exception as e:
            return f"工具执行灾难性错误: {str(e)}"
