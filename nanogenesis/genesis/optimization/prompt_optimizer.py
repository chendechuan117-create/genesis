"""
提示词自优化器
每 N 次交互后，自动分析并优化系统提示词
"""

import sys
import json
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from genesis.core.base import PerformanceMetrics


@dataclass
class OptimizationResult:
    """优化结果"""
    timestamp: str
    old_prompt: str
    new_prompt: str
    improvement: Dict[str, float]
    reason: str
    adopted: bool


class PromptOptimizer:
    """
    提示词自优化器 (Real LLM Powered)
    
    功能：
    1. 收集性能数据
    2. 使用 LLM 分析性能瓶颈
    3. 生成优化后的系统提示词
    """
    
    def __init__(
        self,
        provider=None,
        optimize_interval: int = 50,
        ab_test_samples: int = 10,
        history_path: str = None
    ):
        """
        初始化
        
        Args:
            provider: LLM Provider (用于执行元认知分析)
            optimize_interval: 优化间隔（交互次数）
            ab_test_samples: A/B 测试样本数
            history_path: 优化历史保存路径
        """
        self.provider = provider
        self.optimize_interval = optimize_interval
        self.ab_test_samples = ab_test_samples
        
        if history_path:
            self.history_path = Path(history_path)
        else:
            self.history_path = Path.home() / ".nanogenesis" / "prompt_optimization_history.json"
        
        self.interaction_count = 0
        self.performance_log: List[Dict[str, Any]] = []
        self.optimization_history: List[OptimizationResult] = []
        self.current_system_prompt = ""
    
    def set_provider(self, provider):
        self.provider = provider

    def log_interaction(
        self,
        metrics: PerformanceMetrics,
        user_input: str,
        response: str,
        success: bool
    ):
        """记录交互数据"""
        self.interaction_count += 1
        
        self.performance_log.append({
            'timestamp': datetime.now().isoformat(),
            'tokens': metrics.total_tokens,
            'time': metrics.total_time,
            'iterations': metrics.iterations,
            'tools_used': metrics.tools_used,
            'success': success,
            'user_input_length': len(user_input),
            'response_length': len(response),
            'error': response if not success else None
        })
        
        # 保持最近 100 条记录
        if len(self.performance_log) > 100:
            self.performance_log = self.performance_log[-100:]
    
    def should_optimize(self) -> bool:
        """是否应该优化"""
        return (
            self.interaction_count > 0 and
            self.interaction_count % self.optimize_interval == 0 and
            len(self.performance_log) >= self.optimize_interval
        )
    
    def analyze_performance(self) -> Dict[str, Any]:
        """分析性能指标"""
        if not self.performance_log:
            return {}
        
        recent = self.performance_log[-self.optimize_interval:]
        
        # 计算平均值
        avg_tokens = sum(log['tokens'] for log in recent) / len(recent)
        avg_time = sum(log['time'] for log in recent) / len(recent)
        avg_iterations = sum(log['iterations'] for log in recent) / len(recent)
        success_rate = sum(1 for log in recent if log['success']) / len(recent)
        
        # 工具使用频率
        tool_usage = {}
        for log in recent:
            for tool in log['tools_used']:
                tool_usage[tool] = tool_usage.get(tool, 0) + 1
        
        # 常见错误
        errors = [log['error'] for log in recent if not log['success'] and log['error']]
        
        return {
            'avg_tokens': avg_tokens,
            'avg_time': avg_time,
            'avg_iterations': avg_iterations,
            'success_rate': success_rate,
            'tool_usage': tool_usage,
            'recent_errors': errors[:5], # 取最近5个错误作为样本
            'total_interactions': len(recent)
        }
    
    async def generate_optimization_suggestions(
        self,
        current_prompt: str,
        metrics: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        生成优化建议 (Real LLM Analysis)
        """
        if not self.provider:
            return {'suggestions': [], 'new_prompt': current_prompt, 'reason': 'No provider'}

        # 构造分析 Prompt
        analysis_prompt = f"""
        作为 AI 系统架构师，请分析以下 Agent 的性能数据，并优化其 System Prompt。
        
        【目标】
        1. 降低 Token 消耗 (当前平均: {metrics['avg_tokens']:.1f})
        2. 提高成功率 (当前: {metrics['success_rate']:.1%})
        3. 解决常见错误
        
        【数据】
        - 常用工具: {json.dumps(metrics['tool_usage'], ensure_ascii=False)}
        - 最近错误样本: {json.dumps(metrics['recent_errors'], ensure_ascii=False)}
        
        【当前 System Prompt】
        {current_prompt}
        
        【约束】
        1. 必须保留 System Prompt 的第一行（核心身份定义），这对于 Cache 命中至关重要。
        2. 仅优化指令部分、工具描述部分。
        3. 输出完整的、优化后的 System Prompt。
        
        请返回 JSON 格式：
        {{
            "analysis": "分析结论...",
            "optimized_prompt": "完整的优化后Prompt..."
        }}
        """
        
        try:
            response = await self.provider.chat([{"role": "user", "content": analysis_prompt}])
            content = response.content
            
            # 解析 JSON
            import re
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
                new_prompt = result.get('optimized_prompt', current_prompt)
                reason = result.get('analysis', 'LLM Optimized')
                
                # 强制检查前缀是否一致 (Cache Protection)
                old_prefix = current_prompt.split('\n')[0]
                new_prefix = new_prompt.split('\n')[0]
                if old_prefix != new_prefix:
                    # 如果 LLM 修改了前缀，强制恢复
                    new_prompt = old_prefix + '\n' + '\n'.join(new_prompt.split('\n')[1:])
                    reason += " (Prefix restored for cache)"
                
                return {
                    'suggestions': [reason],
                    'new_prompt': new_prompt,
                    'reason': reason
                }
            else:
                return {'suggestions': [], 'new_prompt': current_prompt, 'reason': 'Parse Error'}
                
        except Exception as e:
            return {'suggestions': [], 'new_prompt': current_prompt, 'reason': str(e)}

    def rollback(self) -> Optional[str]:
        """回滚到上一个版本（防止劣化）"""
        if not self.optimization_history:
            return None
            
        # 找到最近一次采用的优化
        for i in range(len(self.optimization_history) - 1, -1, -1):
            result = self.optimization_history[i]
            if result.adopted:
                # 将其标记为未采用（逻辑删除）
                result.adopted = False
                self._save_history()
                return result.old_prompt
        
        return None
    
    async def optimize(self, current_prompt: str) -> Optional[OptimizationResult]:
        """执行优化"""
        if not self.should_optimize():
            return None
        
        # 1. 分析性能
        metrics = self.analyze_performance()
        if not metrics:
            return None
        
        # 2. 生成优化建议 (Real LLM)
        suggestions = await self.generate_optimization_suggestions(current_prompt, metrics)
        new_prompt = suggestions['new_prompt']
        
        # 如果提示词没有变化，跳过
        if new_prompt == current_prompt:
            return None
        
        # 3. 直接采用 (省去昂贵的 A/B 测试，依赖回滚机制)
        # 在实际生产中，这里应该部署到灰度环境。
        # 这里我们假设 LLM 的优化是正向的，并记录以备回滚。
        
        result = OptimizationResult(
            timestamp=datetime.now().isoformat(),
            old_prompt=current_prompt,
            new_prompt=new_prompt,
            improvement={
                'token_saved': 0, # 暂无实测数据
                'success_rate_improvement': 0
            },
            reason=suggestions['reason'],
            adopted=True
        )
        
        self.optimization_history.append(result)
        self._save_history()
        
        return result

    
    def get_latest_optimized_prompt(self) -> Optional[str]:
        """获取最新的已采用优化提示词"""
        # 加载历史
        if not self.optimization_history and self.history_path.exists():
            try:
                with self.history_path.open('r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.optimization_history = [OptimizationResult(**item) for item in data]
            except Exception:
                pass
        
        # 倒序查找最近的 adopted
        for i in range(len(self.optimization_history) - 1, -1, -1):
            result = self.optimization_history[i]
            if result.adopted:
                return result.new_prompt
        
        return None

    def _save_history(self):
        """保存优化历史"""
        try:
            self.history_path.parent.mkdir(parents=True, exist_ok=True)
            
            with self.history_path.open('w', encoding='utf-8') as f:
                json.dump(
                    [asdict(r) for r in self.optimization_history],
                    f,
                    ensure_ascii=False,
                    indent=2
                )
        except Exception:
            pass
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        if not self.optimization_history:
            return {
                'total_optimizations': 0,
                'adopted_count': 0,
                'avg_token_saved': 0,
                'avg_success_improvement': 0
            }
        
        adopted = [r for r in self.optimization_history if r.adopted]
        
        return {
            'total_optimizations': len(self.optimization_history),
            'adopted_count': len(adopted),
            'avg_token_saved': sum(
                r.improvement['token_saved'] for r in adopted
            ) / len(adopted) if adopted else 0,
            'avg_success_improvement': sum(
                r.improvement['success_rate_improvement'] for r in adopted
            ) / len(adopted) if adopted else 0
        }
