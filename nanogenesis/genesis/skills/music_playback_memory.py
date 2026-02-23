import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from genesis.core.base import Tool

class MusicPlaybackMemory(Tool):
    @property
    def name(self) -> str:
        return "music_playback_memory"
        
    @property
    def description(self) -> str:
        return "记录用户要求播放音乐的记忆，并管理音乐播放偏好"
        
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {"type": "string", "description": "操作类型：record(记录播放请求), get_preference(获取偏好), list_history(列出历史)"},
                "music_info": {"type": "string", "description": "音乐信息（仅record时需要）", "default": ""},
                "preference_key": {"type": "string", "description": "偏好键名（仅get_preference时需要）", "default": ""}
            },
            "required": ["action"]
        }
        
    async def execute(self, action: str, music_info: str = "", preference_key: str = "") -> str:
        import json
        import os
        from datetime import datetime
        
        memory_file = "/home/chendechusn/music_memory.json"
        
        # 初始化记忆文件
        if not os.path.exists(memory_file):
            base_data = {
                "playback_requests": [],
                "preferences": {
                    "last_playback_time": None,
                    "favorite_genre": None,
                    "volume_level": 70
                },
                "history": []
            }
            with open(memory_file, 'w', encoding='utf-8') as f:
                json.dump(base_data, f, ensure_ascii=False, indent=2)
        
        # 读取现有数据
        with open(memory_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        if action == "record":
            # 记录播放请求
            record = {
                "timestamp": datetime.now().isoformat(),
                "music_info": music_info,
                "user_request": "播放音乐"
            }
            data["playback_requests"].append(record)
            data["preferences"]["last_playback_time"] = datetime.now().isoformat()
            
            with open(memory_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            return f"已记录播放请求：{music_info}"
            
        elif action == "get_preference":
            if preference_key and preference_key in data["preferences"]:
                return f"{preference_key}: {data['preferences'][preference_key]}"
            else:
                return json.dumps(data["preferences"], ensure_ascii=False, indent=2)
                
        elif action == "list_history":
            return json.dumps(data["playback_requests"], ensure_ascii=False, indent=2)
        
        return "未知操作"