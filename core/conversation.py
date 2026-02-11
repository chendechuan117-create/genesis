"""
对话历史管理 - Bot 的记忆系统
"""

from typing import List, Dict, Optional
from dataclasses import dataclass, field
from datetime import datetime
import json
from pathlib import Path
import logging


logger = logging.getLogger(__name__)


@dataclass
class Message:
    """消息"""
    role: str  # user/assistant/system/tool
    content: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: Dict = field(default_factory=dict)


@dataclass
class Conversation:
    """对话会话"""
    session_id: str
    user_id: str
    messages: List[Message] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: Dict = field(default_factory=dict)


class ConversationManager:
    """对话历史管理器"""
    
    def __init__(self, storage_path: str = "./data/conversations"):
        """
        初始化
        
        Args:
            storage_path: 对话存储路径
        """
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        
        # 当前活跃会话
        self.active_conversations: Dict[str, Conversation] = {}
    
    def create_conversation(self, session_id: str, user_id: str = "default") -> Conversation:
        """创建新对话"""
        conv = Conversation(session_id=session_id, user_id=user_id)
        self.active_conversations[session_id] = conv
        return conv
    
    def get_conversation(self, session_id: str) -> Optional[Conversation]:
        """获取对话"""
        # 先从内存查找
        if session_id in self.active_conversations:
            return self.active_conversations[session_id]
        
        # 从磁盘加载
        conv = self._load_from_disk(session_id)
        if conv:
            self.active_conversations[session_id] = conv
        
        return conv
    
    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: Optional[Dict] = None
    ):
        """添加消息"""
        conv = self.get_conversation(session_id)
        if not conv:
            conv = self.create_conversation(session_id)
        
        message = Message(
            role=role,
            content=content,
            metadata=metadata or {}
        )
        
        conv.messages.append(message)
        conv.updated_at = datetime.now().isoformat()
        
        # 自动保存
        self._save_to_disk(conv)
    
    def get_messages(
        self,
        session_id: str,
        limit: Optional[int] = None,
        role_filter: Optional[str] = None
    ) -> List[Message]:
        """获取消息列表"""
        conv = self.get_conversation(session_id)
        if not conv:
            return []
        
        messages = conv.messages
        
        # 角色过滤
        if role_filter:
            messages = [m for m in messages if m.role == role_filter]
        
        # 限制数量
        if limit:
            messages = messages[-limit:]
        
        return messages
    
    def get_context_messages(
        self,
        session_id: str,
        max_tokens: int = 4000
    ) -> List[Dict]:
        """
        获取上下文消息（用于 API 调用）
        
        根据 token 限制，智能截取最近的消息
        """
        conv = self.get_conversation(session_id)
        if not conv:
            return []
        
        messages = []
        total_tokens = 0
        
        # 从最新消息开始，向前累加
        for msg in reversed(conv.messages):
            # 简单估算 token（1 token ≈ 4 字符）
            msg_tokens = len(msg.content) // 4
            
            if total_tokens + msg_tokens > max_tokens:
                break
            
            messages.insert(0, {
                "role": msg.role,
                "content": msg.content
            })
            total_tokens += msg_tokens
        
        return messages
    
    def clear_conversation(self, session_id: str):
        """清空对话"""
        if session_id in self.active_conversations:
            del self.active_conversations[session_id]
        
        # 删除磁盘文件
        conv_file = self._get_conv_file(session_id)
        if conv_file.exists():
            conv_file.unlink()
    
    def list_conversations(self, user_id: Optional[str] = None) -> List[str]:
        """列出所有对话"""
        conv_files = self.storage_path.glob("*.json")
        
        conversations = []
        for f in conv_files:
            if user_id:
                # 加载并检查 user_id
                try:
                    with open(f, 'r', encoding='utf-8') as file:
                        data = json.load(file)
                        if data.get('user_id') == user_id:
                            conversations.append(f.stem)
                except Exception as e:
                    logger.debug(f"读取对话文件失败 {f}: {e}")
                    continue
            else:
                conversations.append(f.stem)
        
        return conversations
    
    def _save_to_disk(self, conv: Conversation):
        """保存到磁盘"""
        conv_file = self._get_conv_file(conv.session_id)
        
        data = {
            'session_id': conv.session_id,
            'user_id': conv.user_id,
            'created_at': conv.created_at,
            'updated_at': conv.updated_at,
            'metadata': conv.metadata,
            'messages': [
                {
                    'role': m.role,
                    'content': m.content,
                    'timestamp': m.timestamp,
                    'metadata': m.metadata
                }
                for m in conv.messages
            ]
        }
        
        with open(conv_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    def _load_from_disk(self, session_id: str) -> Optional[Conversation]:
        """从磁盘加载"""
        conv_file = self._get_conv_file(session_id)
        
        if not conv_file.exists():
            return None
        
        try:
            with open(conv_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            messages = [
                Message(
                    role=m['role'],
                    content=m['content'],
                    timestamp=m['timestamp'],
                    metadata=m.get('metadata', {})
                )
                for m in data['messages']
            ]
            
            return Conversation(
                session_id=data['session_id'],
                user_id=data['user_id'],
                messages=messages,
                created_at=data['created_at'],
                updated_at=data['updated_at'],
                metadata=data.get('metadata', {})
            )
        
        except Exception as e:
            logger.debug(f"加载对话失败: {e}")
            return None
    
    def _get_conv_file(self, session_id: str) -> Path:
        """获取对话文件路径"""
        return self.storage_path / f"{session_id}.json"
    
    def get_summary(self, session_id: str) -> Dict:
        """获取对话摘要"""
        conv = self.get_conversation(session_id)
        if not conv:
            return {}
        
        user_msgs = [m for m in conv.messages if m.role == 'user']
        assistant_msgs = [m for m in conv.messages if m.role == 'assistant']
        
        return {
            'session_id': session_id,
            'user_id': conv.user_id,
            'total_messages': len(conv.messages),
            'user_messages': len(user_msgs),
            'assistant_messages': len(assistant_msgs),
            'created_at': conv.created_at,
            'updated_at': conv.updated_at,
            'duration': self._calculate_duration(conv.created_at, conv.updated_at)
        }
    
    def _calculate_duration(self, start: str, end: str) -> str:
        """计算时长"""
        try:
            start_dt = datetime.fromisoformat(start)
            end_dt = datetime.fromisoformat(end)
            delta = end_dt - start_dt
            
            hours = delta.seconds // 3600
            minutes = (delta.seconds % 3600) // 60
            
            if hours > 0:
                return f"{hours}小时{minutes}分钟"
            else:
                return f"{minutes}分钟"
        except Exception:
            return "未知"


# 示例用法
if __name__ == '__main__':
    manager = ConversationManager()
    
    # 创建对话
    session_id = "test_session_001"
    
    # 添加消息
    manager.add_message(session_id, "user", "Docker 容器启动失败")
    manager.add_message(session_id, "assistant", "让我帮你诊断问题...")
    manager.add_message(session_id, "tool", "诊断结果：权限问题", {"tool": "diagnose"})
    manager.add_message(session_id, "assistant", "问题是权限不足，建议...")
    
    # 获取消息
    print("="*60)
    print("对话历史:")
    print("="*60)
    messages = manager.get_messages(session_id)
    for msg in messages:
        print(f"[{msg.role}] {msg.content[:50]}...")
    
    # 获取上下文
    print("\n" + "="*60)
    print("上下文消息（用于 API）:")
    print("="*60)
    context = manager.get_context_messages(session_id)
    print(json.dumps(context, indent=2, ensure_ascii=False))
    
    # 获取摘要
    print("\n" + "="*60)
    print("对话摘要:")
    print("="*60)
    summary = manager.get_summary(session_id)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    
    # 列出所有对话
    print("\n" + "="*60)
    print("所有对话:")
    print("="*60)
    conversations = manager.list_conversations()
    for conv_id in conversations:
        print(f"  - {conv_id}")
