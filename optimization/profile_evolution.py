"""
用户画像进化
持续学习用户习惯，自动调整交互方式
"""

import sys
import json
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict
from datetime import datetime
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent))


@dataclass
class UserProfile:
    """用户画像"""
    user_id: str
    expertise: List[str]  # 专业领域
    problem_solving_style: Dict[str, float]  # 解题风格
    first_reactions: Dict[str, str]  # 第一反应
    preferred_tools: List[str]  # 偏好工具
    interaction_count: int
    created_at: str
    updated_at: str


class UserProfileEvolution:
    """
    用户画像进化
    
    功能：
    1. 检测专业领域变化
    2. 检测解题风格变化
    3. 检测偏好变化
    4. 自动调整系统提示词
    """
    
    def __init__(self, user_id: str, profile_path: str = None):
        """初始化"""
        self.user_id = user_id
        
        if profile_path:
            self.profile_path = Path(profile_path)
        else:
            self.profile_path = Path.home() / ".nanogenesis" / f"profile_{user_id}.json"
        
        self.profile = self._load_or_create_profile()
        self.evolution_log: List[Dict[str, Any]] = []
    
    def _load_or_create_profile(self) -> UserProfile:
        """加载或创建用户画像"""
        if self.profile_path.exists():
            try:
                with self.profile_path.open('r', encoding='utf-8') as f:
                    data = json.load(f)
                    return UserProfile(**data)
            except Exception:
                pass
        
        # 创建新画像
        return UserProfile(
            user_id=self.user_id,
            expertise=[],
            problem_solving_style={
                'prefer_config_over_code': 0.5,
                'prefer_understanding_first': 0.5,
                'prefer_quick_fix': 0.5
            },
            first_reactions={},
            preferred_tools=[],
            interaction_count=0,
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat()
        )
    
    def _save_profile(self):
        """保存用户画像"""
        try:
            self.profile_path.parent.mkdir(parents=True, exist_ok=True)
            
            with self.profile_path.open('w', encoding='utf-8') as f:
                json.dump(asdict(self.profile), f, ensure_ascii=False, indent=2)
        except Exception:
            pass
    
    def log_interaction(self, interaction: Dict[str, Any]):
        """记录交互"""
        self.profile.interaction_count += 1
        
        self.evolution_log.append({
            'timestamp': datetime.now().isoformat(),
            'domain': interaction.get('domain', 'general'),
            'solution_type': interaction.get('solution_type', 'unknown'),
            'tools_used': interaction.get('tools_used', []),
            'success': interaction.get('success', False)
        })
        
        # 保持最近 100 条
        if len(self.evolution_log) > 100:
            self.evolution_log = self.evolution_log[-100:]
    
    def detect_changes(self) -> Dict[str, Any]:
        """检测变化"""
        if len(self.evolution_log) < 20:
            return {}
        
        recent = self.evolution_log[-20:]
        changes = {}
        
        # 1. 检测专业领域变化
        domain_counts = defaultdict(int)
        for log in recent:
            domain_counts[log['domain']] += 1
        
        for domain, count in domain_counts.items():
            if domain not in self.profile.expertise and count / len(recent) > 0.3:
                changes['new_expertise'] = {
                    'domain': domain,
                    'confidence': count / len(recent)
                }
        
        # 2. 检测解题风格变化
        config_count = sum(
            1 for log in recent
            if log['solution_type'] == 'config'
        )
        code_count = sum(
            1 for log in recent
            if log['solution_type'] == 'code'
        )
        
        if config_count + code_count > 0:
            new_prefer_config = config_count / (config_count + code_count)
            old_prefer_config = self.profile.problem_solving_style['prefer_config_over_code']
            
            if abs(new_prefer_config - old_prefer_config) > 0.2:
                changes['style_shift'] = {
                    'old': old_prefer_config,
                    'new': new_prefer_config,
                    'shift': new_prefer_config - old_prefer_config
                }
        
        # 3. 检测工具偏好
        tool_counts = defaultdict(int)
        for log in recent:
            for tool in log['tools_used']:
                tool_counts[tool] += 1
        
        if tool_counts:
            top_tools = sorted(tool_counts.items(), key=lambda x: x[1], reverse=True)[:3]
            new_preferred = [t[0] for t in top_tools]
            
            if new_preferred != self.profile.preferred_tools:
                changes['tool_preference'] = {
                    'old': self.profile.preferred_tools,
                    'new': new_preferred
                }
        
        return changes
    
    def evolve(self) -> Optional[Dict[str, Any]]:
        """进化用户画像"""
        changes = self.detect_changes()
        
        if not changes:
            return None
        
        # 应用变化
        if 'new_expertise' in changes:
            domain = changes['new_expertise']['domain']
            if domain not in self.profile.expertise:
                self.profile.expertise.append(domain)
        
        if 'style_shift' in changes:
            self.profile.problem_solving_style['prefer_config_over_code'] = \
                changes['style_shift']['new']
        
        if 'tool_preference' in changes:
            self.profile.preferred_tools = changes['tool_preference']['new']
        
        self.profile.updated_at = datetime.now().isoformat()
        self._save_profile()
        
        return changes
    
    def generate_adaptive_prompt(self) -> str:
        """生成自适应系统提示词"""
        parts = ["你是 NanoGenesis，一个智能 AI 助手。"]
        
        # 添加专业领域
        if self.profile.expertise:
            parts.append(f"\n用户专业领域: {', '.join(self.profile.expertise)}")
        
        # 添加解题风格
        if self.profile.problem_solving_style['prefer_config_over_code'] > 0.6:
            parts.append("\n用户偏好: 优先使用配置文件解决问题")
        elif self.profile.problem_solving_style['prefer_config_over_code'] < 0.4:
            parts.append("\n用户偏好: 优先使用代码解决问题")
        
        # 添加偏好工具
        if self.profile.preferred_tools:
            parts.append(f"\n常用工具: {', '.join(self.profile.preferred_tools)}")
        
        return '\n'.join(parts)
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            'user_id': self.profile.user_id,
            'interaction_count': self.profile.interaction_count,
            'expertise_count': len(self.profile.expertise),
            'expertise': self.profile.expertise,
            'preferred_tools': self.profile.preferred_tools,
            'style': self.profile.problem_solving_style
        }
