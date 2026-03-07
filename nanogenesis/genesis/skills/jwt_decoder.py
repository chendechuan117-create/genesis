import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from genesis.core.base import Tool

import base64
import json
from typing import Dict, Any

class JwtDecoderTool(Tool):
    @property
    def name(self) -> str:
        return "jwt_decoder"
        
    @property
    def description(self) -> str:
        return "解码JWT令牌，提取头部和载荷信息"
        
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "jwt_token": {"type": "string", "description": "JWT令牌字符串"}
            },
            "required": ["jwt_token"]
        }
        
    async def execute(self, jwt_token: str) -> str:
        try:
            # JWT格式: header.payload.signature
            parts = jwt_token.split('.')
            if len(parts) != 3:
                return "错误: 无效的JWT格式，应该包含三部分"
            
            # 解码头部
            header_encoded = parts[0]
            # 添加填充
            header_encoded += '=' * (4 - len(header_encoded) % 4)
            header_decoded = base64.urlsafe_b64decode(header_encoded)
            header_json = json.loads(header_decoded)
            
            # 解码载荷
            payload_encoded = parts[1]
            # 添加填充
            payload_encoded += '=' * (4 - len(payload_encoded) % 4)
            payload_decoded = base64.urlsafe_b64decode(payload_encoded)
            payload_json = json.loads(payload_decoded)
            
            result = {
                "header": header_json,
                "payload": payload_json,
                "signature": parts[2][:20] + "..." if len(parts[2]) > 20 else parts[2]
            }
            
            return json.dumps(result, indent=2, ensure_ascii=False)
            
        except Exception as e:
            return f"解码JWT时出错: {str(e)}"