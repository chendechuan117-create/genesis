"""
行为自优化器
学习成功模式，避免重复错误
"""

import sys
import json
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))


@dataclass
class Strategy:
    """策略"""
    id: str
    pattern: str
    domain: str
    root_cause: str
    solution: str
    dead_ends: List[str]
    success_count: int
    total_count: int
    avg_tokens: float
    avg_time: float
    created_at: str
    updated_at: str


class BehaviorOptimizer:
    """
    行为自优化器 (Real LLM Powered)
    
    功能：
    1. 从成功案例提取策略 (LLM 提取)
    2. 记录失败模式（死胡同）
    3. 策略去重、合并、泛化 (LLM 泛化)
    4. 策略质量评估
    """
    
    def __init__(self, provider=None, strategy_db_path: str = None):
        """初始化"""
        self.provider = provider
        
        if strategy_db_path:
            self.db_path = Path(strategy_db_path)
        else:
            self.db_path = Path.home() / ".nanogenesis" / "strategies.json"
        
        self.strategies: Dict[str, Strategy] = {}
        self.failure_patterns: List[Dict[str, Any]] = []
        
        self._load_strategies()
    
    def set_provider(self, provider):
        self.provider = provider
    
    def _load_strategies(self):
        """加载策略库"""
        if not self.db_path.exists():
            return
        
        try:
            with self.db_path.open('r', encoding='utf-8') as f:
                data = json.load(f)
                
                for item in data:
                    strategy = Strategy(**item)
                    self.strategies[strategy.id] = strategy
        except Exception:
            pass
    
    def _save_strategies(self):
        """保存策略库"""
        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            
            with self.db_path.open('w', encoding='utf-8') as f:
                json.dump(
                    [asdict(s) for s in self.strategies.values()],
                    f,
                    ensure_ascii=False,
                    indent=2
                )
        except Exception:
            pass
    
    async def learn_from_interaction(self, interaction: Dict[str, Any]):
        """从交互中学习"""
        if interaction.get('success'):
            await self._learn_success_pattern(interaction)
        else:
            self._learn_failure_pattern(interaction)
    
    async def _learn_success_pattern(self, interaction: Dict[str, Any]):
        """学习成功模式"""
        # 提取模式 (LLM)
        pattern = await self._extract_pattern(interaction)
        
        if not pattern:
            return
        
        # 查找相似策略
        similar = self._find_similar_strategy(pattern)
        
        if similar:
            # 更新现有策略
            similar.success_count += 1
            similar.total_count += 1
            similar.avg_tokens = (
                similar.avg_tokens * (similar.total_count - 1) +
                interaction.get('tokens', 0)
            ) / similar.total_count
            similar.updated_at = datetime.now().isoformat()
        else:
            # 创建新策略
            strategy_id = f"strategy_{len(self.strategies) + 1}"
            
            strategy = Strategy(
                id=strategy_id,
                pattern=pattern['problem_pattern'],
                domain=pattern.get('domain', 'general'),
                root_cause=pattern.get('root_cause', ''),
                solution=pattern.get('solution', ''),
                dead_ends=[],
                success_count=1,
                total_count=1,
                avg_tokens=interaction.get('tokens', 0),
                avg_time=interaction.get('time', 0),
                created_at=datetime.now().isoformat(),
                updated_at=datetime.now().isoformat()
            )
            
            self.strategies[strategy_id] = strategy
        
        self._save_strategies()
    
    def _learn_failure_pattern(self, interaction: Dict[str, Any]):
        """学习失败模式"""
        failure = {
            'problem': interaction.get('problem', ''),
            'attempted_solution': interaction.get('attempted_solution', ''),
            'error': interaction.get('error', ''),
            'timestamp': datetime.now().isoformat()
        }
        
        self.failure_patterns.append(failure)
        
        # 保持最近 50 条
        if len(self.failure_patterns) > 50:
            self.failure_patterns = self.failure_patterns[-50:]
    
    async def _extract_pattern(self, interaction: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """提取模式 (Real LLM)"""
        if not self.provider:
            # 降级到 Mock
            problem = interaction.get('problem', '')
            if not problem: return None
            keywords = problem.lower().split()[:5]
            return {
                'problem_pattern': ' '.join(keywords),
                'domain': interaction.get('domain', 'general'),
                'root_cause': interaction.get('root_cause', ''),
                'solution': interaction.get('solution', ''),
                'tools_used': interaction.get('tools_used', [])
            }

        # 构造提取 Prompt
        prompt = f"""
        请从以下交互中提取通用的【问题-解决方案】模式。
        
        用户问题: {interaction.get('problem')}
        最终回复: {interaction.get('response')[:500]}...
        工具使用: {interaction.get('tools_used')}
        
        请提取：
        1. 问题模式 (通用化描述，去除非关键信息)
        2. 领域 (如 docker, python, git)
        3. 根本原因 (一句话总结)
        4. 解决方案 (标准化步骤)
        
        返回 JSON:
        {{
            "problem_pattern": "...",
            "domain": "...",
            "root_cause": "...",
            "solution": "..."
        }}
        """
        
        try:
            response = await self.provider.chat([{"role": "user", "content": prompt}])
            content = response.content
            import re
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
            return None
        except Exception:
            return None

    def _find_similar_strategy(self, pattern: Dict[str, Any]) -> Optional[Strategy]:
        """查找相似策略"""
        problem_pattern = pattern['problem_pattern']
        domain = pattern.get('domain', 'general')
        
        for strategy in self.strategies.values():
            # 简单的相似度判断
            if strategy.domain == domain:
                # 关键词匹配
                pattern_words = set(problem_pattern.split())
                strategy_words = set(strategy.pattern.split())
                
                overlap = len(pattern_words & strategy_words)
                similarity = overlap / max(len(pattern_words), len(strategy_words))
                
                if similarity > 0.6:
                    return strategy
        
        return None
    
    def find_relevant_strategies(self, query: str, limit: int = 3) -> List[Strategy]:
        """查找相关策略（用于元认知反馈）"""
        if not self.strategies:
            return []
            
        query_words = set(query.lower().split())
        scored_strategies = []
        
        for strategy in self.strategies.values():
            # 简单的关键词重叠评分
            # 实际应用中应使用 Embedding 语义检索
            strategy_words = set(strategy.pattern.lower().split())
            overlap = len(query_words & strategy_words)
            
            if overlap > 0:
                score = overlap / len(query_words) + (strategy.success_count / (strategy.total_count + 1)) * 0.5
                scored_strategies.append((score, strategy))
        
        # 按分数降序排序
        scored_strategies.sort(key=lambda x: x[0], reverse=True)
        
        return [s for _, s in scored_strategies[:limit]]
    
    async def optimize_strategies(self):
        """优化策略库 (Generalize & Merge using LLM)"""
        # 1. 删除低效策略
        to_remove = []
        for strategy_id, strategy in self.strategies.items():
            if strategy.total_count >= 10:
                success_rate = strategy.success_count / strategy.total_count
                if success_rate < 0.3:
                    to_remove.append(strategy_id)
        
        for strategy_id in to_remove:
            del self.strategies[strategy_id]
        
        # 2. 泛化策略 (Real LLM)
        if self.provider and len(self.strategies) > 5:
            # 按领域聚类
            clusters = {}
            for s in self.strategies.values():
                if s.domain not in clusters: clusters[s.domain] = []
                clusters[s.domain].append(s)
            
            for domain, group in clusters.items():
                if len(group) >= 3:
                    # 尝试泛化
                    generalized = await self._generalize_group(group)
                    if generalized:
                         # 简单的策略：添加泛化策略，不删除旧的（或者根据相似度删除）
                         # 这里简单处理，只添加
                         new_id = f"gen_{datetime.now().timestamp()}"
                         generalized.id = new_id
                         self.strategies[new_id] = generalized

        self._save_strategies()

    async def _generalize_group(self, strategies: List[Strategy]) -> Optional[Strategy]:
        """对一组策略进行泛化"""
        prompt = f"""
        请分析以下 {len(strategies)} 个策略，尝试提取一个更通用的【元策略】。
        
        策略列表:
        {json.dumps([asdict(s) for s in strategies], ensure_ascii=False)}
        
        如果它们有共同模式，请返回一个通用策略 JSON。否则返回 null。
        JSON 格式与 Strategy 对象一致。
        """
        try:
            response = await self.provider.chat([{"role": "user", "content": prompt}])
            content = response.content
            import re
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                return Strategy(**data) # 注意：这里需要确保返回字段完整，实际上需要更健壮的 parsing
            return None
        except Exception:
            return None

