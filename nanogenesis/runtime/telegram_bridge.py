
import sys
import json
import time
import urllib.request
import urllib.parse
import urllib.error
import logging
import os
import asyncio
from pathlib import Path

# 添加 nanabot 路径
# 添加 nanabot 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from genesis.agent import NanoGenesis
from genesis.core.factory import GenesisFactory
from genesis.core.config import config

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("telegram_bridge")

# 全局 Agent
agent = None

class TelegramBot:
    """
    极简 Telegram Bot 客户端 (零依赖，基于 urllib)
    """
    def __init__(self, token: str):
        self.token = token
        self.base_url = f"https://api.telegram.org/bot{token}"
        self.offset = 0
        
    def _request(self, method: str, params: dict = None):
        """发送请求 (带 curl 降级支持)"""
        url = f"{self.base_url}/{method}"
        
        # 1. 尝试 urllib (标准方式)
        try:
            # ConfigManager 已自动设置 os.environ['https_proxy']，urllib 会自动读取
            if params:
                data = json.dumps(params).encode('utf-8')
                headers = {'Content-Type': 'application/json'}
                req = urllib.request.Request(url, data=data, headers=headers)
            else:
                req = urllib.request.Request(url)
                
            # 设置较短超时，以便快速切换到 curl
            with urllib.request.urlopen(req, timeout=5) as response:
                return json.loads(response.read().decode('utf-8'))
                
        except Exception as e:
            logger.warning(f"urllib 请求失败 ({str(e)})，尝试使用 curl 降级...")
            return self._request_curl(url, params)

    def _request_curl(self, url: str, params: dict = None):
        """使用 curl 发送请求"""
        import subprocess
        
        cmd = ["curl", "-s", "-L"]  # -s 静默, -L 跟随重定向
        
        if params:
            cmd.extend([
                "-X", "POST",
                "-H", "Content-Type: application/json",
                "-d", json.dumps(params)
            ])
        else:
            cmd.extend(["-X", "GET"])
            
        cmd.append(url)
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode != 0:
                logger.error(f"curl 执行失败: {result.stderr}")
                return None
                
            if not result.stdout.strip():
                logger.error("curl 返回空内容")
                return None
                
            return json.loads(result.stdout)
            
        except Exception as e:
            logger.error(f"curl 降级失败: {e}")
            return None

    def get_updates(self):
        """获取新消息"""
        params = {
            "offset": self.offset,
            "timeout": 30,
            "allowed_updates": ["message"]
        }
        result = self._request("getUpdates", params)
        if result and result.get("ok"):
            updates = result.get("result", [])
            if updates:
                # 更新 offset，避免重复获取
                self.offset = updates[-1]["update_id"] + 1
            return updates
        return []

    def send_message(self, chat_id: int, text: str):
        """发送消息"""
        # Telegram 消息长度限制 4096
        max_len = 4000
        if len(text) > max_len:
            # 分段发送
            for i in range(0, len(text), max_len):
                chunk = text[i:i+max_len]
                self._send_single_message(chat_id, chunk)
        else:
            self._send_single_message(chat_id, text)

    def _send_single_message(self, chat_id: int, text: str):
        self._request("sendMessage", {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown"
        })

async def process_message(bot: TelegramBot, update: dict):
    """处理单条消息"""
    message = update.get("message", {})
    chat_id = message.get("chat", {}).get("id")
    text = message.get("text", "")
    user = message.get("from", {}).get("username", "Unknown")
    
    if not text or not chat_id:
        return

    logger.info(f"收到消息 [{user}]: {text[:50]}...")
    
    # 特殊指令：抢占模式
    if text.strip() == "/hijack":
        msg = kill_openclaw_processes()
        bot.send_message(chat_id, msg)
        return

    # 发送"思考中"状态 (Telegram sendChatAction)
    bot._request("sendChatAction", {"chat_id": chat_id, "action": "typing"})
    
    try:
        # 调用 NanoGenesis
        # 注意：这里会阻塞 polling 循环，直到处理完成
        # 在生产环境中应该放入任务队列，但作为个人助手，单线程也可以
        result = await agent.process(text)
        
        response = result.get('response', '无响应')
        
        # 附加性能信息
        metrics = result.get('metrics')
        if metrics:
            footer = f"\n\n`⏱️ {metrics.total_time:.2f}s | 🪙 {metrics.total_tokens}`"
            response += footer
            
        bot.send_message(chat_id, response)
        
    except Exception as e:
        logger.error(f"处理异常: {e}")
        bot.send_message(chat_id, f"❌ 处理出错: {str(e)}")

def kill_openclaw_processes():
    """杀掉 OpenClaw 相关进程"""
    import subprocess
    try:
        # 查找包含 'openclaw' 的 node 进程
        # pgrep -f "openclaw" 可能不太准，因为它是 node 运行的 js
        # 尝试杀掉 node 进程（稍微暴力一点，但用户要求 'hijack'）
        # 更安全的做法是查找 cwd 在 openclaw 目录下的进程，但这比较复杂
        # 这里尝试 pkill -f "openclaw"
        
        cmd = ["pkill", "-f", "openclaw"]
        subprocess.run(cmd, check=False)
        
        # 再次检查
        check = subprocess.run(["pgrep", "-f", "openclaw"], capture_output=True)
        if not check.stdout:
            return "🏴‍☠️ 已执行 Hijack：OpenClaw 进程已被终止。现在我是唯一的 Master。"
        else:
            return "⚠️ Hijack 部分失败：仍有 OpenClaw 进程存活，请手动检查。"
            
    except Exception as e:
        return f"❌ Hijack 失败: {str(e)}"

async def main():
    global agent
    
    print("\n" + "=" * 60)
    print("🚀 NanoGenesis Telegram Bridge (Hijack Mode)")
    print("=" * 60)
    
    # 1. 获取 Token (优先环境变量，其次询问)
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        print("⚠️  未检测到 TELEGRAM_BOT_TOKEN 环境变量")
        print("请粘贴你的 OpenClaw Telegram Token (或直接回车尝试手动输入):")
        token = input("Token: ").strip()
    
    if not token:
        print("❌ 未提供 Token，无法启动。")
        return

    # 2. 初始化 Agent
    print("初始化 NanoGenesis...")
    try:
        # Use Factory to create agent with all components
        agent = GenesisFactory.create_common(
            enable_optimization=True
        )
        # 启动调度器 (Heartbeat)
        if agent.scheduler:
            await agent.scheduler.start()
            
        print("✅ Agent 就绪 (Heartbeat Active)")
    except Exception as e:
        print(f"❌ Agent 初始化失败: {e}")
        return

    # 3. 启动 Bot
    bot = TelegramBot(token)
    print(f"🤖 Bot 启动中... (正在轮询 Telegram)")
    print("💡 提示: 如果 OpenClaw 也在运行，可能会抢消息。建议先停止 OpenClaw。")
    
    while True:
        try:
            updates = bot.get_updates()
            for update in updates:
                await process_message(bot, update)
            
            # 短暂休眠避免空转过快
            if not updates:
                await asyncio.sleep(1)
                
        except KeyboardInterrupt:
            print("\n👋 停止服务")
            if agent and agent.scheduler:
                await agent.scheduler.stop()
            break
        except Exception as e:
            logger.error(f"轮询异常: {e}")
            await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(main())
