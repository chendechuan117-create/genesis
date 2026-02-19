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
    preferences: Dict[str, str]  # 动态偏好 (Key-Value)
    interaction_count: int
    created_at: str
    updated_at: str


class UserProfileEvolution:
    """
    用户画像进化 (Dynamic Intelligence)
    
    功能：
    1. 动态偏好提取 (LLM) - 从对话中提取任意用户偏好
    2. 自动调整系统提示词 - 将偏好注入 Context
    """
    
    def __init__(self, user_id: str, profile_path: str = None, provider: Any = None):
        """初始化"""
        self.user_id = user_id
        self.provider = provider
        
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
                    # Backwards compatibility
                    if 'preferences' not in data:
                        data['preferences'] = {}
                    return UserProfile(**data)
            except Exception:
                pass
        
        # 创建新画像
        return UserProfile(
            user_id=self.user_id,
            expertise=[],
            problem_solving_style={
                'prefer_config_over_code': 0.5,
            },
            preferences={},
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
        self.evolution_log.append(interaction)
        if len(self.evolution_log) > 20:
            self.evolution_log = self.evolution_log[-20:]
            
    async def extract_dynamic_preferences(self, user_input: str) -> Dict[str, Any]:
        """使用 LLM 提取动态偏好"""
        if not self.provider:
            return {}
            
        prompt = f"""
        Analyze the user's input for EXPLICIT preferences or habits.
        
        User Input: "{user_input}"
        
        Extract any stating of:
        1. Language preference (e.g., "Speak Chinese")
        2. Personal tastes (e.g., "I like strawberries")
        3. Coding habits (e.g., "Use Python 3.10")
        
        Return JSON Key-Value pairs. Keys should be snake_case. 
        If no preference found, return {{}}.
        
        Example: 
        Input: "Please speak Chinese and I love strawberries."
        Output: {{"language": "Simplified Chinese", "favorite_fruit": "Strawberry"}}
        """
        
        try:
            response = await self.provider.chat([{"role": "user", "content": prompt}])
            content = response.content
            # Clean JSON
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
            
            new_prefs = json.loads(content)
            if new_prefs:
                # Merge into profile
                for k, v in new_prefs.items():
                    self.profile.preferences[k] = v
                    
                self.profile.updated_at = datetime.now().isoformat()
                self._save_profile()
                return new_prefs
        except Exception:
            pass
            
        return {}

    def get_profile_context(self) -> str:
        """生成用户画像上下文"""
        parts = ["【用户画像 (User Profile)】"]
        
        # 1. 动态偏好 (The core of dynamic intelligence)
        if self.profile.preferences:
            for k, v in self.profile.preferences.items():
                parts.append(f"- {k.replace('_', ' ').title()}: {v}")
                
        # 2. 专业领域 (Legacy but useful)
        if self.profile.expertise:
             parts.append(f"- Expertise: {', '.join(self.profile.expertise)}")

        # 3. Fallback Language Constraint if not Dynamic
        if 'language' not in self.profile.preferences:
             parts.append("- Language: Follow user's language (Default to English if unsure).")

        return '\n'.join(parts)

    def get_stats(self) -> Dict[str, Any]:
        return asdict(self.profile)
