"""
诊断工具 - 基于决策树和环境信息诊断问题根本原因
"""

import sys
import json
from pathlib import Path
from typing import Dict, Any, List
import logging

sys.path.insert(0, str(Path(__file__).parent.parent))

from genesis.core.base import Tool


logger = logging.getLogger(__name__)


class TroubleshootTool(Tool):
    """
    智能故障排查工具
    
    基于问题描述和环境信息，使用决策树诊断根本原因
    """
    
    def __init__(self):
        self.decision_trees = self._load_decision_trees()
    
    @property
    def name(self) -> str:
        return "troubleshoot"
    
    @property
    def description(self) -> str:
        return """诊断问题的根本原因。

基于问题描述和领域，使用决策树分析：
1. 识别问题模式
2. 收集相关环境信息
3. 分析根本原因
4. 给出解决建议

支持的领域：
- docker: Docker 容器问题
- python: Python 环境和依赖问题
- git: Git 版本控制问题
- linux: Linux 系统问题
- network: 网络连接问题
- database: 数据库问题"""
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "problem": {
                    "type": "string",
                    "description": "问题描述"
                },
                "domain": {
                    "type": "string",
                    "description": "问题域（docker, python, git, linux, network, database）"
                },
                "context": {
                    "type": "object",
                    "description": "额外的上下文信息（可选）",
                    "default": {}
                }
            },
            "required": ["problem", "domain"]
        }
    
    def _load_decision_trees(self) -> Dict[str, Any]:
        """加载决策树"""
        return {
            "docker": {
                "patterns": [
                    {
                        "keywords": ["permission denied", "权限"],
                        "root_cause": "UID/GID 映射不匹配",
                        "diagnosis": "容器内用户 UID 与宿主机文件 UID 不一致",
                        "solutions": [
                            "修改 docker-compose.yml 的 user 字段",
                            "使用 --user 参数指定 UID:GID",
                            "调整宿主机文件权限"
                        ],
                        "checks": [
                            "docker exec <container> id",
                            "ls -la <host_path>"
                        ]
                    },
                    {
                        "keywords": ["port", "端口", "already in use"],
                        "root_cause": "端口被占用",
                        "diagnosis": "目标端口已被其他进程使用",
                        "solutions": [
                            "更换端口号",
                            "停止占用端口的进程",
                            "使用 docker-compose down 清理"
                        ],
                        "checks": [
                            "netstat -tulpn | grep <port>",
                            "docker ps"
                        ]
                    },
                    {
                        "keywords": ["network", "网络", "connection refused"],
                        "root_cause": "网络配置问题",
                        "diagnosis": "容器网络配置或防火墙问题",
                        "solutions": [
                            "检查 network_mode 配置",
                            "检查防火墙规则",
                            "使用 bridge 网络模式"
                        ],
                        "checks": [
                            "docker network inspect <network>",
                            "docker exec <container> ping <target>"
                        ]
                    }
                ]
            },
            "python": {
                "patterns": [
                    {
                        "keywords": ["ModuleNotFoundError", "No module named"],
                        "root_cause": "模块未安装或路径问题",
                        "diagnosis": "Python 找不到指定的模块",
                        "solutions": [
                            "pip install <module>",
                            "检查虚拟环境是否激活",
                            "检查 PYTHONPATH"
                        ],
                        "checks": [
                            "pip list | grep <module>",
                            "which python",
                            "echo $PYTHONPATH"
                        ]
                    },
                    {
                        "keywords": ["version", "版本", "conflict"],
                        "root_cause": "依赖版本冲突",
                        "diagnosis": "不同包要求的依赖版本不兼容",
                        "solutions": [
                            "使用 pip install --upgrade",
                            "创建新的虚拟环境",
                            "使用 poetry 或 pipenv 管理依赖"
                        ],
                        "checks": [
                            "pip list",
                            "pip check"
                        ]
                    }
                ]
            },
            "git": {
                "patterns": [
                    {
                        "keywords": ["conflict", "冲突", "merge"],
                        "root_cause": "合并冲突",
                        "diagnosis": "多个分支修改了相同文件的相同部分",
                        "solutions": [
                            "手动解决冲突标记",
                            "使用 git mergetool",
                            "选择一方的更改（ours/theirs）"
                        ],
                        "checks": [
                            "git status",
                            "git diff"
                        ]
                    }
                ]
            },
            "linux": {
                "patterns": [
                    {
                        "keywords": ["permission denied", "权限"],
                        "root_cause": "文件权限不足",
                        "diagnosis": "当前用户没有访问文件的权限",
                        "solutions": [
                            "使用 chmod 修改权限",
                            "使用 sudo 提权",
                            "检查文件所有者"
                        ],
                        "checks": [
                            "ls -la <file>",
                            "id"
                        ]
                    }
                ]
            },
            "network": {
                "patterns": [
                    {
                        "keywords": ["connection refused", "连接拒绝"],
                        "root_cause": "服务未启动或端口未开放",
                        "diagnosis": "目标服务不可达",
                        "solutions": [
                            "检查服务是否运行",
                            "检查防火墙规则",
                            "检查端口是否监听"
                        ],
                        "checks": [
                            "systemctl status <service>",
                            "netstat -tulpn | grep <port>"
                        ]
                    }
                ]
            },
            "database": {
                "patterns": [
                    {
                        "keywords": ["connection", "连接", "refused"],
                        "root_cause": "数据库连接问题",
                        "diagnosis": "无法连接到数据库服务器",
                        "solutions": [
                            "检查数据库服务是否运行",
                            "检查连接字符串",
                            "检查防火墙和网络"
                        ],
                        "checks": [
                            "systemctl status <db_service>",
                            "telnet <host> <port>"
                        ]
                    }
                ]
            }
        }
    
    async def execute(
        self,
        problem: str,
        domain: str,
        context: Dict[str, Any] = None
    ) -> str:
        """执行诊断"""
        context = context or {}

        payload: Dict[str, Any] = {
            "problem": problem,
            "domain": domain,
            "matched": False,
            "root_cause": "",
            "diagnosis": "",
            "confidence": 0.0,
            "solutions": [],
            "checks": [],
            "env_info": context,
            "report": "",
            "error": None,
        }

        try:
            # 检查域是否支持
            if domain not in self.decision_trees:
                payload["error"] = f"不支持的领域 '{domain}'"
                payload["report"] = (
                    f"诊断失败: 不支持的领域 '{domain}'\n\n"
                    f"支持的领域: {', '.join(self.decision_trees.keys())}"
                )
                return json.dumps(payload, ensure_ascii=False)

            # 获取决策树
            tree = self.decision_trees[domain]

            # 匹配问题模式
            matched_pattern = None
            problem_lower = problem.lower()

            for pattern in tree.get("patterns", []):
                keywords = pattern.get("keywords", [])
                if any(str(keyword).lower() in problem_lower for keyword in keywords):
                    matched_pattern = pattern
                    break

            if not matched_pattern:
                payload["report"] = (
                    "诊断结果: 未找到匹配的问题模式\n\n"
                    f"问题: {problem}\n"
                    f"领域: {domain}\n\n"
                    "建议:\n"
                    "1. 提供更详细的错误信息\n"
                    "2. 尝试其他领域\n"
                    "3. 使用 shell 工具收集更多信息"
                )
                return json.dumps(payload, ensure_ascii=False)

            payload["matched"] = True
            payload["root_cause"] = matched_pattern.get("root_cause", "")
            payload["diagnosis"] = matched_pattern.get("diagnosis", "")
            payload["confidence"] = 0.85
            payload["solutions"] = matched_pattern.get("solutions", [])
            payload["checks"] = matched_pattern.get("checks", [])
            payload["report"] = (
                f"根本原因: {payload['root_cause']}\n"
                f"分析: {payload['diagnosis']}\n"
                f"置信度: {payload['confidence']:.0%}"
            )

            return json.dumps(payload, ensure_ascii=False)

        except Exception as e:
            payload["error"] = f"诊断失败 - {str(e)}"
            payload["report"] = f"Error: {payload['error']}"
            return json.dumps(payload, ensure_ascii=False)
