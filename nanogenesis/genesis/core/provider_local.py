
import json
import logging
import subprocess
from typing import List, Dict, Any, Optional
from .base import LLMProvider, Message

logger = logging.getLogger(__name__)

class OllamaProvider(LLMProvider):
    """
    本地 LLM 提供者 (Ollama) - 零依赖实现 (curl)
    """
    
    def __init__(self, model: str = "deepseek-r1:latest", base_url: str = "http://localhost:11434"):
        self.model = model
        self.base_url = base_url
        self.available = self._check_availability()
        
    def _check_availability(self) -> bool:
        """检查 Ollama 是否可用"""
        try:
            cmd = ["curl", "-s", f"{self.base_url}/api/tags"]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=2)
            if result.returncode == 0 and "models" in result.stdout:
                logger.info(f"✓ 本地大脑已连接: {self.model}")
                return True
        except Exception:
            pass
        logger.warning("⚠️ 本地大脑 (Ollama) 未连接，将仅使用云端大脑")
        return False

    def get_default_model(self) -> str:
        """获取默认模型"""
        return self.model

    async def chat(self, messages: List[Dict[str, str]], **kwargs) -> Any:
        """调用本地 LLM"""
        if not self.available:
            raise RuntimeError("Local LLM not available")
            
        # 转换消息格式
        prompt = ""
        for m in messages:
            role = m.get("role", "user")
            content = m.get("content", "")
            # 简单的 ChatML 格式模拟 (Ollama /api/chat 支持 messages 数组，更好)
            pass

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": kwargs.get("temperature", 0.7)
            }
        }
        
        try:
            # 使用 curl 调用 /api/chat
            # 使用 --data-binary @- 从 stdin 读取数据
            cmd = [
                "curl", "-s", "-X", "POST",
                f"{self.base_url}/api/chat",
                "-H", "Content-Type: application/json",
                "--data-binary", "@-"
            ]
            
            # 这里的 timeout 取决于任务，本地推理可能较慢
            result = subprocess.run(
                cmd, 
                input=json.dumps(payload), # Pass data via stdin
                capture_output=True, 
                text=True, 
                timeout=120
            )
            
            if result.returncode != 0:
                raise Exception(f"Curl failed: {result.stderr}")
                
            response = json.loads(result.stdout)
            content = response.get("message", {}).get("content", "")
            
            # 模拟 LiteLLM 的响应结构
            class MockResponse:
                def __init__(self, content):
                    self.content = content
                    
            return MockResponse(content)
            
        except Exception as e:
            logger.error(f"本地大脑思考失败: {e}")
            raise e

    async def embed(self, text: str) -> List[float]:
        """获取文本向量 (Embeddings)"""
        if not self.available:
            # 返回零向量作为 Mock (1024维)
            return [0.0] * 1024
            
        # 强制使用专业的 Embedding 模型 (nomic-embed-text)
        # DeepSeek-R1 是生成模型，不擅长或不支持 Embedding
        embedding_model = "nomic-embed-text"
        
        payload = {
            "model": embedding_model, 
            "prompt": text
        }
        
        try:
            cmd = [
                "curl", "-s", "-X", "POST",
                f"{self.base_url}/api/embeddings",
                "-H", "Content-Type: application/json",
                "-d", json.dumps(payload)
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            
            if result.returncode != 0:
                raise Exception(f"Embed failed: {result.stderr}")
                
            response = json.loads(result.stdout)
            embedding = response.get("embedding", [])
            
            if not embedding:
                 # 尝试 fallback 到 generate 接口 (有些 Ollama 版本 API 不同)
                 # 但这里假设 /api/embeddings 可用
                 logger.warning("未获取到向量，可能模型不支持 embeddings")
                 return [0.0] * 1024
                 
            return embedding
            
        except Exception as e:
            logger.error(f"向量化失败: {e}")
            return [0.0] * 1024
