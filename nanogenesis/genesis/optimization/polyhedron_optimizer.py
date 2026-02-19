"""
多面体框架下的自优化系统

基于多面体坍缩框架，优化：
1. 提示词自优化 - 融入多面体框架
2. 策略自优化 - 基于约束坍缩
3. 用户画像自适应 - 向量 0 持续学习
"""

from typing import Dict, List, Optional
import json
from pathlib import Path
from datetime import datetime


class PolyhedronOptimizer:
    """多面体框架优化器"""
    
    def __init__(self, storage_path: Optional[str] = None):
        """
        初始化
        
        Args:
            storage_path: 优化数据存储路径
        """
        self.storage_path = storage_path or './data/optimization'
        Path(self.storage_path).mkdir(parents=True, exist_ok=True)
        
        self.optimization_history = []
        self.performance_metrics = {
            'token_savings': [],
            'cache_hit_rates': [],
            'response_quality': [],
            'user_satisfaction': []
        }
        
        self._load_history()
    
    def record_interaction(
        self,
        user_input: str,
        response: str,
        metrics: Dict,
        use_polyhedron: bool,
        user_feedback: Optional[Dict] = None
    ):
        """
        记录交互，用于优化
        
        Args:
            user_input: 用户输入
            response: AI 响应
            metrics: 性能指标
            use_polyhedron: 是否使用了多面体框架
            user_feedback: 用户反馈（可选）
        """
        interaction = {
            'timestamp': datetime.now().isoformat(),
            'user_input': user_input,
            'response': response,
            'metrics': metrics,
            'use_polyhedron': use_polyhedron,
            'user_feedback': user_feedback or {}
        }
        
        self.optimization_history.append(interaction)
        
        # 更新性能指标
        if 'token_saved' in metrics:
            self.performance_metrics['token_savings'].append(metrics['token_saved'])
        
        if 'cache_hit_rate' in metrics:
            self.performance_metrics['cache_hit_rates'].append(metrics['cache_hit_rate'])
        
        # 每 10 次交互分析一次
        if len(self.optimization_history) % 10 == 0:
            self._analyze_and_optimize()
        
        self._save_history()
    
    def _analyze_and_optimize(self):
        """分析并优化"""
        print("\n" + "="*60)
        print("自优化分析")
        print("="*60)
        
        # 分析多面体使用效果
        self._analyze_polyhedron_effectiveness()
        
        # 分析 Token 节省
        self._analyze_token_savings()
        
        # 分析缓存命中率
        self._analyze_cache_performance()
        
        # 生成优化建议
        suggestions = self._generate_optimization_suggestions()
        
        if suggestions:
            print("\n优化建议:")
            for i, suggestion in enumerate(suggestions, 1):
                print(f"{i}. {suggestion}")
    
    def _analyze_polyhedron_effectiveness(self):
        """分析多面体框架使用效果"""
        if not self.optimization_history:
            return
        
        recent = self.optimization_history[-10:]
        
        with_polyhedron = [i for i in recent if i['use_polyhedron']]
        without_polyhedron = [i for i in recent if not i['use_polyhedron']]
        
        print(f"\n多面体使用情况:")
        print(f"  使用: {len(with_polyhedron)}/{len(recent)} 次")
        print(f"  未使用: {len(without_polyhedron)}/{len(recent)} 次")
        
        # 分析使用多面体时的效果
        if with_polyhedron:
            avg_tokens_with = sum(i['metrics'].get('total_tokens', 0) for i in with_polyhedron) / len(with_polyhedron)
            print(f"  平均 tokens（使用多面体）: {avg_tokens_with:.0f}")
        
        if without_polyhedron:
            avg_tokens_without = sum(i['metrics'].get('total_tokens', 0) for i in without_polyhedron) / len(without_polyhedron)
            print(f"  平均 tokens（未使用）: {avg_tokens_without:.0f}")
    
    def _analyze_token_savings(self):
        """分析 Token 节省"""
        if not self.performance_metrics['token_savings']:
            return
        
        recent_savings = self.performance_metrics['token_savings'][-10:]
        avg_saving = sum(recent_savings) / len(recent_savings)
        
        print(f"\nToken 节省:")
        print(f"  平均节省: {avg_saving:.1f}%")
        print(f"  最近 10 次: {[f'{s:.1f}%' for s in recent_savings[-5:]]}")
    
    def _analyze_cache_performance(self):
        """分析缓存性能"""
        if not self.performance_metrics['cache_hit_rates']:
            return
        
        recent_rates = self.performance_metrics['cache_hit_rates'][-10:]
        avg_rate = sum(recent_rates) / len(recent_rates)
        
        print(f"\n缓存命中率:")
        print(f"  平均命中率: {avg_rate:.1f}%")
        print(f"  最近 10 次: {[f'{r:.1f}%' for r in recent_rates[-5:]]}")
    
    def _generate_optimization_suggestions(self) -> List[str]:
        """生成优化建议"""
        suggestions = []
        
        # 检查多面体使用频率
        if len(self.optimization_history) >= 10:
            recent = self.optimization_history[-10:]
            polyhedron_usage = sum(1 for i in recent if i['use_polyhedron']) / len(recent)
            
            if polyhedron_usage < 0.3:
                suggestions.append("多面体使用频率较低（<30%），考虑降低复杂度阈值")
            elif polyhedron_usage > 0.8:
                suggestions.append("多面体使用频率较高（>80%），考虑提高复杂度阈值以节省 tokens")
        
        # 检查缓存命中率
        if self.performance_metrics['cache_hit_rates']:
            recent_rates = self.performance_metrics['cache_hit_rates'][-5:]
            avg_rate = sum(recent_rates) / len(recent_rates)
            
            if avg_rate < 0.7:
                suggestions.append(f"缓存命中率较低（{avg_rate:.1%}），检查 system prompt 是否频繁变化")
        
        # 检查 Token 使用趋势
        if len(self.optimization_history) >= 10:
            recent_tokens = [i['metrics'].get('total_tokens', 0) for i in self.optimization_history[-10:]]
            if recent_tokens:
                avg_tokens = sum(recent_tokens) / len(recent_tokens)
                if avg_tokens > 2000:
                    suggestions.append(f"平均 token 使用较高（{avg_tokens:.0f}），考虑增强协议编码规则")
        
        return suggestions
    
    def get_optimization_report(self) -> Dict:
        """获取优化报告"""
        if not self.optimization_history:
            return {'message': '暂无数据'}
        
        total_interactions = len(self.optimization_history)
        polyhedron_usage = sum(1 for i in self.optimization_history if i['use_polyhedron'])
        
        report = {
            'total_interactions': total_interactions,
            'polyhedron_usage': {
                'count': polyhedron_usage,
                'percentage': polyhedron_usage / total_interactions * 100
            },
            'performance': {}
        }
        
        # Token 节省
        if self.performance_metrics['token_savings']:
            report['performance']['avg_token_saving'] = sum(self.performance_metrics['token_savings']) / len(self.performance_metrics['token_savings'])
        
        # 缓存命中率
        if self.performance_metrics['cache_hit_rates']:
            report['performance']['avg_cache_hit_rate'] = sum(self.performance_metrics['cache_hit_rates']) / len(self.performance_metrics['cache_hit_rates'])
        
        return report
    
    def _save_history(self):
        """保存历史记录"""
        history_file = Path(self.storage_path) / 'optimization_history.json'
        
        # 只保存最近 100 条
        recent_history = self.optimization_history[-100:]
        
        with open(history_file, 'w', encoding='utf-8') as f:
            json.dump({
                'history': recent_history,
                'metrics': self.performance_metrics
            }, f, indent=2, ensure_ascii=False)
    
    def _load_history(self):
        """加载历史记录"""
        history_file = Path(self.storage_path) / 'optimization_history.json'
        
        if not history_file.exists():
            return
        
        try:
            with open(history_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            self.optimization_history = data.get('history', [])
            self.performance_metrics = data.get('metrics', self.performance_metrics)
        
        except Exception as e:
            print(f"加载历史记录失败: {e}")


# 示例用法
if __name__ == '__main__':
    optimizer = PolyhedronOptimizer()
    
    # 模拟 10 次交互
    for i in range(10):
        optimizer.record_interaction(
            user_input=f"测试问题 {i+1}",
            response=f"测试响应 {i+1}",
            metrics={
                'total_tokens': 1500 + i * 50,
                'token_saved': 25 + i % 5,
                'cache_hit_rate': 90 + i % 10
            },
            use_polyhedron=(i % 3 == 0)  # 每 3 次使用一次多面体
        )
    
    # 获取报告
    print("\n" + "="*60)
    print("优化报告")
    print("="*60)
    report = optimizer.get_optimization_report()
    print(json.dumps(report, indent=2, ensure_ascii=False))
