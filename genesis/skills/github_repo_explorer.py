import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from genesis.core.base import Tool

class GithubRepoExplorer(Tool):
    @property
    def name(self) -> str:
        return "github_repo_explorer"
        
    @property
    def description(self) -> str:
        return "GitHub仓库探索工具，支持查看仓库结构、读取文件内容、获取仓库信息等操作"
        
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string", 
                    "enum": ["get_repo_info", "list_contents", "read_file", "search_repo"],
                    "description": "操作类型：get_repo_info(获取仓库信息), list_contents(列出目录内容), read_file(读取文件), search_repo(搜索仓库)"
                },
                "owner": {
                    "type": "string",
                    "description": "仓库所有者用户名"
                },
                "repo": {
                    "type": "string", 
                    "description": "仓库名称"
                },
                "path": {
                    "type": "string",
                    "description": "文件或目录路径（对于list_contents和read_file操作）",
                    "default": ""
                },
                "query": {
                    "type": "string",
                    "description": "搜索查询（对于search_repo操作）",
                    "default": ""
                }
            },
            "required": ["action", "owner", "repo"]
        }
        
    async def execute(self, action: str, owner: str, repo: str, path: str = "", query: str = "") -> str:
        import subprocess
        import json
        import os
        
        # 构建GitHub API URL
        base_url = f"https://api.github.com/repos/{owner}/{repo}"
        
        try:
            if action == "get_repo_info":
                # 获取仓库基本信息
                cmd = f"curl -s -H 'Accept: application/vnd.github.v3+json' '{base_url}'"
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
                
                if result.returncode != 0:
                    return f"❌ 获取仓库信息失败: {result.stderr}"
                    
                repo_data = json.loads(result.stdout)
                
                if "message" in repo_data and "Not Found" in repo_data["message"]:
                    return f"❌ 仓库不存在: {owner}/{repo}"
                
                info = f"""
## 📦 仓库信息: {owner}/{repo}

### 基本信息
- **仓库名称**: {repo_data.get('name', 'N/A')}
- **描述**: {repo_data.get('description', '无描述')}
- **语言**: {repo_data.get('language', 'N/A')}
- **星标数**: {repo_data.get('stargazers_count', 0)}
- **分支数**: {repo_data.get('forks_count', 0)}
- **关注数**: {repo_data.get('watchers_count', 0)}
- **问题数**: {repo_data.get('open_issues_count', 0)}
- **许可证**: {repo_data.get('license', {}).get('name', '无') if repo_data.get('license') else '无'}

### 时间信息
- **创建时间**: {repo_data.get('created_at', 'N/A')}
- **最后更新**: {repo_data.get('updated_at', 'N/A')}
- **最后推送**: {repo_data.get('pushed_at', 'N/A')}

### 链接
- **GitHub地址**: {repo_data.get('html_url', 'N/A')}
- **主页**: {repo_data.get('homepage', '无')}
- **克隆地址**: {repo_data.get('clone_url', 'N/A')}
- **SSH地址**: {repo_data.get('ssh_url', 'N/A')}

### 仓库状态
- **私有**: {'是' if repo_data.get('private') else '否'}
- **已归档**: {'是' if repo_data.get('archived') else '否'}
- **禁用问题**: {'是' if repo_data.get('has_issues') else '否'}
- **禁用Wiki**: {'是' if repo_data.get('has_wiki') else '否'}
- **禁用下载**: {'是' if repo_data.get('has_downloads') else '否'}
- **禁用页面**: {'是' if repo_data.get('has_pages') else '否'}
- **禁用项目**: {'是' if repo_data.get('has_projects') else '否'}
- **禁用讨论**: {'是' if repo_data.get('has_discussions') else '否'}
                """
                return info
                
            elif action == "list_contents":
                # 列出目录内容
                if path:
                    api_url = f"{base_url}/contents/{path}"
                else:
                    api_url = f"{base_url}/contents"
                    
                cmd = f"curl -s -H 'Accept: application/vnd.github.v3+json' '{api_url}'"
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
                
                if result.returncode != 0:
                    return f"❌ 列出目录内容失败: {result.stderr}"
                    
                contents = json.loads(result.stdout)
                
                if isinstance(contents, dict) and "message" in contents:
                    return f"❌ 错误: {contents['message']}"
                
                output = f"## 📁 目录内容: {owner}/{repo}/{path if path else '根目录'}\n\n"
                
                if not contents:
                    output += "📭 目录为空\n"
                else:
                    for item in contents:
                        item_type = "📄 文件" if item["type"] == "file" else "📁 目录"
                        size = f" ({item.get('size', 0)} bytes)" if item["type"] == "file" else ""
                        output += f"- {item_type} `{item['name']}`{size}\n"
                        if item["type"] == "file":
                            output += f"  - 下载链接: {item.get('download_url', 'N/A')}\n"
                
                return output
                
            elif action == "read_file":
                # 读取文件内容
                if not path:
                    return "❌ 需要指定文件路径"
                    
                api_url = f"{base_url}/contents/{path}"
                cmd = f"curl -s -H 'Accept: application/vnd.github.v3+json' '{api_url}'"
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
                
                if result.returncode != 0:
                    return f"❌ 读取文件失败: {result.stderr}"
                    
                file_data = json.loads(result.stdout)
                
                if "message" in file_data:
                    return f"❌ 错误: {file_data['message']}"
                
                # 获取文件内容（如果是文本文件）
                if file_data.get("encoding") == "base64":
                    import base64
                    content = base64.b64decode(file_data["content"]).decode("utf-8", errors="ignore")
                else:
                    content = file_data.get("content", "")
                
                info = f"""
## 📄 文件内容: {owner}/{repo}/{path}

### 文件信息
- **文件名**: {file_data.get('name', 'N/A')}
- **路径**: {file_data.get('path', 'N/A')}
- **大小**: {file_data.get('size', 0)} bytes
- **SHA**: {file_data.get('sha', 'N/A')[:8]}...
- **下载链接**: {file_data.get('download_url', 'N/A')}

### 内容预览
```
{content[:2000]}{'...' if len(content) > 2000 else ''}
```
"""
                return info
                
            elif action == "search_repo":
                # 搜索仓库内容
                if not query:
                    return "❌ 需要指定搜索查询"
                    
                search_url = f"https://api.github.com/search/code?q={query}+repo:{owner}/{repo}"
                cmd = f"curl -s -H 'Accept: application/vnd.github.v3+json' '{search_url}'"
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
                
                if result.returncode != 0:
                    return f"❌ 搜索失败: {result.stderr}"
                    
                search_data = json.loads(result.stdout)
                
                if "message" in search_data:
                    return f"❌ 错误: {search_data['message']}"
                
                output = f"## 🔍 搜索结果: '{query}' 在 {owner}/{repo}\n\n"
                output += f"**找到 {search_data.get('total_count', 0)} 个结果**\n\n"
                
                if search_data.get("items"):
                    for i, item in enumerate(search_data["items"][:10], 1):
                        output += f"{i}. **文件**: `{item['path']}`\n"
                        output += f"   - **仓库**: {item['repository']['full_name']}\n"
                        output += f"   - **分数**: {item.get('score', 0):.2f}\n"
                        output += f"   - **链接**: {item['html_url']}\n\n"
                
                return output
                
            else:
                return f"❌ 不支持的操作: {action}"
                
        except json.JSONDecodeError as e:
            return f"❌ JSON解析错误: {str(e)}"
        except Exception as e:
            return f"❌ 执行错误: {str(e)}"