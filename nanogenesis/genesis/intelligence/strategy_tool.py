"""
策略搜索工具 - 搜索历史成功策略
"""

import sys
import json
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime
import logging

sys.path.insert(0, str(Path(__file__).parent.parent))

from genesis.core.base import Tool


logger = logging.getLogger(__name__)


class StrategySearchTool(Tool):
    """
    策略搜索工具
    
    从策略库中搜索相似的成功案例
    """
    
    def __init__(self, strategy_db_path: str = None):
        """
        初始化
        
        Args:
            strategy_db_path: 策略数据库路径
        """
        if strategy_db_path:
            self.db_path = Path(strategy_db_path)
        else:
            self.db_path = Path.home() / ".nanogenesis" / "strategies.json"
        
        self.strategies = self._load_strategies()
    
    @property
    def name(self) -> str:
        return "search_strategy"
    
    @property
    def description(self) -> str:
        return """搜索历史成功策略。

基于问题相似度，从策略库中查找：
1. 相似的问题模式
2. 成功的解决方案
3. 需要避免的死胡同

这可以帮助避免重复试错，直接应用已验证的解决方案。"""
    
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
                    "description": "问题域（可选）",
                    "default": None
                },
                "limit": {
                    "type": "integer",
                    "description": "返回策略数量，默认 3",
                    "default": 3
                }
            },
            "required": ["problem"]
        }
    
    def _load_strategies(self) -> List[Dict[str, Any]]:
        """加载策略库"""
        if not self.db_path.exists():
            # 返回示例策略
            return self._get_example_strategies()
        
        try:
            with self.db_path.open('r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return self._get_example_strategies()
    
    def _get_example_strategies(self) -> List[Dict[str, Any]]:
        """获取示例策略"""
        return [
            {
                "pattern": "Docker 容器权限问题",
                "domain": "docker",
                "root_cause": "UID/GID 映射不匹配",
                "solution": "修改 docker-compose.yml 的 user 字段为 ${UID}:${GID}",
                "dead_ends": ["chmod 777", "使用 root 用户"],
                "success_rate": 0.95,
                "use_count": 12,
                "keywords": ["docker", "permission", "denied", "权限"]
            },
            {
                "pattern": "Python 模块导入失败",
                "domain": "python",
                "root_cause": "虚拟环境未激活或模块未安装",
                "solution": "激活虚拟环境后 pip install <module>",
                "dead_ends": ["直接修改 sys.path", "全局安装"],
                "success_rate": 0.90,
                "use_count": 8,
                "keywords": ["python", "modulenotfounderror", "import", "模块"]
            },
            {
                "pattern": "端口被占用",
                "domain": "network",
                "root_cause": "目标端口已被其他进程使用",
                "solution": "使用 netstat 找到进程并 kill，或更换端口",
                "dead_ends": ["强制重启系统"],
                "success_rate": 0.88,
                "use_count": 15,
                "keywords": ["port", "already in use", "端口", "占用"]
            },
            {
                "pattern": "Git 合并冲突",
                "domain": "git",
                "root_cause": "多个分支修改了相同文件",
                "solution": "手动解决冲突标记，然后 git add 和 git commit",
                "dead_ends": ["git reset --hard", "删除分支重来"],
                "success_rate": 0.85,
                "use_count": 20,
                "keywords": ["git", "conflict", "merge", "冲突"]
            }
        ]
    
    def _calculate_similarity(self, problem: str, strategy: Dict[str, Any]) -> float:
        """计算问题与策略的相似度"""
        problem_lower = problem.lower()
        score = 0.0
        
        # 关键词匹配
        keyword_matches = sum(
            1 for keyword in strategy.get("keywords", [])
            if keyword in problem_lower
        )
        
        if keyword_matches > 0:
            score += keyword_matches * 0.3
        
        # 模式匹配
        if any(word in problem_lower for word in strategy["pattern"].lower().split()):
            score += 0.4
        
        # 成功率加权
        score *= strategy.get("success_rate", 0.5)
        
        return min(score, 1.0)
    
    async def execute(
        self,
        problem: str,
        domain: str = None,
        limit: int = 3
    ) -> str:
        """搜索策略"""
        payload: Dict[str, Any] = {
            "problem": problem,
            "domain": domain,
            "strategies": [],
            "report": "",
            "error": None,
        }

        try:
            # 过滤域
            candidates = self.strategies
            if domain:
                candidates = [s for s in candidates if s.get("domain") == domain]

            if not candidates:
                payload["report"] = (
                    "未找到相关策略\n\n"
                    f"问题: {problem}\n"
                    f"领域: {domain or '全部'}\n\n"
                    "策略库为空或没有匹配的领域。"
                )
                return json.dumps(payload, ensure_ascii=False)

            # 计算相似度并排序
            scored = [
                (self._calculate_similarity(problem, s), s)
                for s in candidates
            ]
            scored.sort(reverse=True, key=lambda x: x[0])

            # 取前 N 个
            top_strategies = scored[:limit]

            if not top_strategies or top_strategies[0][0] < 0.1:
                payload["report"] = (
                    "未找到相似的策略\n\n"
                    f"问题: {problem}\n"
                    f"领域: {domain or '全部'}\n\n"
                    "策略库中没有足够相似的案例。"
                )
                return json.dumps(payload, ensure_ascii=False)

            strategies: List[Dict[str, Any]] = []
            for similarity, strategy in top_strategies:
                item = dict(strategy)
                item["similarity"] = similarity
                strategies.append(item)

            payload["strategies"] = strategies
            payload["report"] = f"找到 {len(strategies)} 个相关策略"

            return json.dumps(payload, ensure_ascii=False)

        except Exception as e:
            logger.error(f"搜索策略失败: {e}", exc_info=True)
            payload["error"] = f"搜索策略失败 - {str(e)}"
            payload["report"] = f"Error: {payload['error']}"
            return json.dumps(payload, ensure_ascii=False)
    
    def add_strategy(self, strategy: Dict[str, Any]) -> bool:
        """添加新策略（用于学习）"""
        try:
            self.strategies.append(strategy)
            
            # 保存到文件
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            with self.db_path.open('w', encoding='utf-8') as f:
                json.dump(self.strategies, f, ensure_ascii=False, indent=2)
            
            return True
        except Exception:
            return False
