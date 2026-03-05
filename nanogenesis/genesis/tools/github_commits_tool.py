"""
GitHub Commits 查询工具
"""

import sys
from pathlib import Path
from typing import Dict, Any
import json
import logging
import urllib.request
import urllib.error

sys.path.insert(0, str(Path(__file__).parent.parent))

from genesis.core.base import Tool
from genesis.core.config import config

logger = logging.getLogger(__name__)

class GithubCommitsTool(Tool):
    """查询 GitHub 仓库提交历史工具"""
    
    @property
    def name(self) -> str:
        return "github_commits"
    
    @property
    def description(self) -> str:
        return """用于查询指定 GitHub 仓库的最新提交历史 (Commit Log)。
当用户询问“查一下 xxx 的最近提交”、“他们更新了什么”、“查看 Github 历史”时，使用此工具。
需要提供仓库的完整拥有者和名称格式，例如 'owner/repo'。返回最新的 10 条提交记录。"""
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "repo_name": {
                    "type": "string",
                    "description": "仓库名称，格式必须是 'owner/repo'，例如: 'facebook/react' 或 'chendechuan117-create/genesis'"
                },
                "branch": {
                    "type": "string",
                    "description": "(可选) 指定分支名称。不填则默认查询仓库的默认主分支。"
                },
                "max_results": {
                    "type": "integer",
                    "description": "返回的最多提交记录数，默认为 5，最大为 20。",
                    "default": 5
                }
            },
            "required": ["repo_name"]
        }
    
    async def execute(self, repo_name: str, branch: str = "", max_results: int = 5) -> str:
        """执行 GitHub api 请求"""
        try:
            # Enforce limits
            max_results = min(max_results, 20)
            
            url = f"https://api.github.com/repos/{repo_name}/commits?per_page={max_results}"
            if branch:
                url += f"&sha={branch}"
                
            headers = {
                "User-Agent": "NanoGenesis/1.0",
                "Accept": "application/vnd.github.v3+json"
            }
            
            if config.github_token:
                headers["Authorization"] = f"token {config.github_token}"
            
            # 使用 urllib 发送请求
            # 注意: 这里使用 asyncio.to_thread 防止阻塞主循环
            import asyncio
            
            def _fetch():
                req = urllib.request.Request(url, headers=headers)
                
                # Check for proxy support via environment variables
                import os
                proxy = os.environ.get("https_proxy") or os.environ.get("HTTPS_PROXY")
                if proxy:
                     from urllib.request import ProxyHandler, build_opener, install_opener
                     proxy_handler = ProxyHandler({'https': proxy})
                     opener = build_opener(proxy_handler)
                     install_opener(opener)
                     
                with urllib.request.urlopen(req, timeout=15) as response:
                    return json.loads(response.read().decode('utf-8'))
            
            commits = await asyncio.to_thread(_fetch)
            
            if not commits:
                return f"🔍 仓库 {repo_name} 没有找到任何提交记录或该仓库为空。"
                
            output = [f"📦 仓库 [{repo_name}] 的最新 {len(commits)} 条提交记录:"]
            
            for index, commit_data in enumerate(commits, 1):
                sha = commit_data.get("sha", "")[:7]
                commit_info = commit_data.get("commit", {})
                message = commit_info.get("message", "No message").split('\\n')[0] # Only take first line
                author = commit_info.get("author", {}).get("name", "Unknown")
                date = commit_info.get("author", {}).get("date", "Unknown")
                
                output.append(f"{index}. [{sha}] {message} - by {author} on {date}")
                
            return "\\n".join(output)
            
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return f"Error: 找不到仓库 '{repo_name}'。请确保格式是 'owner/repo' 并且仓库是公开的（或你的 API Token 拥有访问权限）。"
            elif e.code == 403:
                return "Error: GitHub API 速率限制已触发 (403 Forbidden)。"
            elif e.code == 401:
                return "Error: GitHub Token 鉴权失败 (401 Unauthorized)。请检查 .env 中的 GITHUB_TOKEN 是否有效。"
            return f"Error: GitHub API 返回了错误。状态码 {e.code}"
        except Exception as e:
            logger.error(f"GitHub Commits 获取失败: {e}", exc_info=True)
            return f"Error: 请求失败 - {str(e)}"
