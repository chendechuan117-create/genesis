"""
工具使用自优化器
学习最优工具组合和调用顺序
"""

import sys
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent))


class ToolUsageOptimizer:
    """
    工具使用自优化器
    
    功能：
    1. 记录工具调用序列
    2. 分析最优路径
    3. 推荐工具组合
    4. 预测下一步工具
    """
    
    def __init__(self):
        # 工具序列记录: {problem_type: [sequence, ...]}
        self.tool_sequences: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        
        # 最优序列缓存: {problem_type: tools_list}
        self.optimal_sequences: Dict[str, List[str]] = {}
        
        # 工具转移概率: {(tool1, tool2): count}
        self.tool_transitions: Dict[Tuple[str, str], int] = defaultdict(int)
        
        # Tool Evolution: Failure tracking
        self.tool_failure_counts: Dict[str, int] = defaultdict(int)
        self.deprecated_tools: set = set()
        self.failure_threshold: int = 5  # Mark deprecated after 5 consecutive failures
    
    def record_sequence(
        self,
        problem_type: str,
        tools_used: List[str],
        success: bool,
        metrics: Dict[str, Any]
    ):
        """记录工具调用序列"""
        sequence = {
            'tools': tools_used,
            'success': success,
            'tokens': metrics.get('tokens', 0),
            'time': metrics.get('time', 0),
            'iterations': metrics.get('iterations', 0)
        }
        
        self.tool_sequences[problem_type].append(sequence)
        
        # 更新转移概率
        if success and len(tools_used) > 1:
            for i in range(len(tools_used) - 1):
                transition = (tools_used[i], tools_used[i + 1])
                self.tool_transitions[transition] += 1
        
        # 保持每个类型最多 50 条记录
        if len(self.tool_sequences[problem_type]) > 50:
            self.tool_sequences[problem_type] = self.tool_sequences[problem_type][-50:]
    
    def get_optimal_sequence(self, problem_type: str) -> Optional[List[str]]:
        """获取最优工具序列"""
        # 检查缓存
        if problem_type in self.optimal_sequences:
            return self.optimal_sequences[problem_type]
        
        # 分析历史数据
        sequences = self.tool_sequences.get(problem_type, [])
        
        if not sequences:
            return None
        
        # 只考虑成功的序列
        successful = [s for s in sequences if s['success']]
        
        if not successful:
            return None
        
        # 找出 Token 最少的序列
        optimal = min(successful, key=lambda s: s['tokens'] + s['time'] * 10)
        
        # 缓存
        self.optimal_sequences[problem_type] = optimal['tools']
        
        return optimal['tools']
    
    def suggest_next_tool(
        self,
        problem_type: str,
        tools_used_so_far: List[str]
    ) -> Optional[str]:
        """建议下一个工具"""
        if not tools_used_so_far:
            # 第一个工具：基于历史最常用
            sequences = self.tool_sequences.get(problem_type, [])
            if not sequences:
                return None
            
            # 统计第一个工具的频率
            first_tools = defaultdict(int)
            for seq in sequences:
                if seq['success'] and seq['tools']:
                    first_tools[seq['tools'][0]] += 1
            
            if first_tools:
                return max(first_tools.items(), key=lambda x: x[1])[0]
            
            return None
        
        # 后续工具：基于转移概率
        last_tool = tools_used_so_far[-1]
        
        # 找出从 last_tool 转移的所有可能
        next_tools = defaultdict(int)
        for (from_tool, to_tool), count in self.tool_transitions.items():
            if from_tool == last_tool:
                next_tools[to_tool] += count
        
        if next_tools:
            return max(next_tools.items(), key=lambda x: x[1])[0]
        
        return None
    
    def get_tool_recommendations(
        self,
        problem_type: str
    ) -> Dict[str, Any]:
        """获取工具推荐"""
        optimal_seq = self.get_optimal_sequence(problem_type)
        
        if not optimal_seq:
            return {
                'has_recommendation': False,
                'message': f'暂无 {problem_type} 类型的工具使用记录'
            }
        
        return {
            'has_recommendation': True,
            'optimal_sequence': optimal_seq,
            'message': f'推荐工具序列: {" → ".join(optimal_seq)}'
        }
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        total_sequences = sum(len(seqs) for seqs in self.tool_sequences.values())
        total_successful = sum(
            sum(1 for s in seqs if s['success'])
            for seqs in self.tool_sequences.values()
        )
        
        return {
            'problem_types': len(self.tool_sequences),
            'total_sequences': total_sequences,
            'successful_sequences': total_successful,
            'success_rate': total_successful / total_sequences if total_sequences > 0 else 0,
            'tool_transitions': len(self.tool_transitions),
            'cached_optimal': len(self.optimal_sequences),
            'deprecated_tools': list(self.deprecated_tools)
        }
    
    def record_tool_result(self, tool_name: str, success: bool):
        """记录单个工具调用结果 (Tool Evolution)"""
        if success:
            # Reset failure count on success
            self.tool_failure_counts[tool_name] = 0
        else:
            # Increment failure count
            self.tool_failure_counts[tool_name] += 1
            
            # Check for deprecation threshold
            if self.tool_failure_counts[tool_name] >= self.failure_threshold:
                self.deprecated_tools.add(tool_name)
                import logging
                logging.getLogger(__name__).warning(f"⚠️ Tool '{tool_name}' marked as deprecated (failed {self.failure_threshold}+ times)")
    
    def prune_deprecated_tools(self, tool_registry) -> List[str]:
        """从 Registry 中移除废弃工具"""
        pruned = []
        for tool_name in list(self.deprecated_tools):
            if hasattr(tool_registry, 'tools') and tool_name in tool_registry.tools:
                del tool_registry.tools[tool_name]
                pruned.append(tool_name)
                import logging
                logging.getLogger(__name__).info(f"🗑️ Pruned deprecated tool: {tool_name}")
        return pruned
    
    def is_deprecated(self, tool_name: str) -> bool:
        """检查工具是否已废弃"""
        return tool_name in self.deprecated_tools
