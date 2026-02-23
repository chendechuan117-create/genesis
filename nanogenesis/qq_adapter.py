"""
Genesis QQ Bot 适配器
========================
使用腾讯官方 QQ 开放平台 API (q.qq.com) 接入 Genesis。

原理：
  QQ平台 → WebSocket 推送消息 → qq_adapter.py → Genesis.process() → 回复到频道/私聊

凭证配置（从 q.qq.com 控制台获取）:
  APP_ID     : 机器人 AppID
  APP_SECRET : 机器人 Secret（即 token/密码）

支持的消息场景：
  1. 频道 @机器人 消息（AT_MESSAGES）
  2. 私聊消息（DIRECT_MESSAGE）
  3. 群聊 @机器人 消息（GROUP_AT_MESSAGES）

运行方法：
  ./venv/bin/python qq_adapter.py

依赖：
  pip install qq-botpy
"""

import asyncio
import logging
import botpy
from botpy import logging as botpy_logging
from botpy.message import Message, DirectMessage, GroupMessage
from genesis.core.factory import GenesisFactory

# ============================================================
# 配置区 (Configuration)
# ============================================================
APP_ID     = "102864752"
APP_SECRET = "bmyANbp4JZp6NfxGauFawIf2QpEe4VwO"

# 全局 Genesis Agent（懒初始化，所有 QQ 用户共用一个 agent 实例）
# 如需多用户隔离，改为 per-user_id 的字典
_agent = None

logger = logging.getLogger("QQAdapter")


def get_agent():
    """获取或初始化 Genesis Agent（单例模式）"""
    global _agent
    if _agent is None:
        logger.info("🌱 Initializing Genesis Agent for QQ Adapter...")
        _agent = GenesisFactory.create_common(user_id="qq_bot")
        logger.info("✅ Genesis Agent ready.")
    return _agent


async def prewarm_agent():
    """
    异步预热：在接受 QQ 消息前，先跑一次 process() 让 BERT 和 LLM 完成初始化。
    结果被丢弃，只是为了加热。
    """
    logger.info("🔥 预热 Genesis (异步热身请求中...)")
    try:
        agent = get_agent()
        await asyncio.wait_for(
            agent.process("你好，系统热身测试。"),
            timeout=180.0
        )
        logger.info("✅ Genesis 预热完成，可以接收 QQ 消息了！")
    except Exception as e:
        logger.warning(f"⚠️ 预热未完成（{e}），首条消息可能稍慢。")


# ============================================================
# QQ Bot 客户端
# ============================================================
class GenesisQQBot(botpy.Client):

    async def on_ready(self):
        logger.info(f"✅ QQ Bot 上线: {self.robot.name} (ID: {self.robot.id})")
        # bot 上线后立即异步预热 Genesis，不阻塞心跳
        asyncio.create_task(prewarm_agent())

    # --------------------------------------------------------
    # 频道 @ 消息
    # --------------------------------------------------------
    async def on_at_message_create(self, message: Message):
        user_id   = message.author.id
        user_name = message.author.username
        # 去掉 <@!bot_id> 前缀
        raw_text = message.content.strip()
        clean_text = _strip_at_prefix(raw_text)
        logger.info(f"📩 [频道] @{user_name}({user_id}): {clean_text}")

        reply_text = await _ask_genesis(clean_text, user_id)
        await message.reply(content=reply_text)

    # --------------------------------------------------------
    # 私聊消息
    # --------------------------------------------------------
    async def on_direct_message_create(self, message: DirectMessage):
        user_id   = message.author.id
        user_name = message.author.username
        clean_text = message.content.strip()
        logger.info(f"📩 [私聊] {user_name}({user_id}): {clean_text}")

        reply_text = await _ask_genesis(clean_text, user_id)
        await self.api.post_dms(
            guild_id=message.guild_id,
            content=reply_text,
            msg_id=message.id,
        )

    # --------------------------------------------------------
    # 群聊 @ 消息（新版群机器人）
    # --------------------------------------------------------
    async def on_group_at_message_create(self, message: GroupMessage):
        user_id   = message.author.member_openid
        clean_text = _strip_at_prefix(message.content.strip())
        logger.info(f"📩 [群聊] user={user_id}: {clean_text}")

        reply_text = await _ask_genesis(clean_text, user_id)
        await self.api.post_group_message(
            group_openid=message.group_openid,
            msg_type=0,                   # 文本
            msg_id=message.id,
            content=reply_text,
        )


# ============================================================
# 辅助函数
# ============================================================
def _strip_at_prefix(text: str) -> str:
    """去掉 <@!xxxxxxxx> 之类的 @ 前缀"""
    import re
    return re.sub(r"<@!?\d+>", "", text).strip()


async def _ask_genesis(user_input: str, user_id: str) -> str:
    """
    将消息交给 Genesis 处理，返回文本回复。
    超时保护：60 秒内没有回复则返回提示。
    """
    if not user_input:
        return "你好！有什么可以帮你的？"

    try:
        agent = get_agent()
        result = await asyncio.wait_for(
            agent.process(user_input),
            timeout=300.0  # 5分钟，第一次初始化较慢
        )
        # 提取最终回复文本
        if isinstance(result, dict):
            msgs = result.get("messages", [])
            if msgs:
                last = msgs[-1]
                return last.content if isinstance(last.content, str) else str(last.content)
            return result.get("response", str(result))
        return str(result)

    except asyncio.TimeoutError:
        logger.warning(f"⏰ Genesis 响应超时 (user={user_id})")
        return "⏰ 思考时间太长了，请稍后再问或简化一下问题。"
    except Exception as e:
        logger.error(f"❌ Genesis 处理异常: {e}", exc_info=True)
        return f"❗ 系统出现了一点问题：{type(e).__name__}"


# ============================================================
# 入口
# ============================================================
def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s"
    )

    # Python 3.10+ 不再自动创建事件循环，需要手动设置
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # 预热 Genesis（在 QQ 连接前完成初始化，避免第一条消息超时）
    logger.info("🔥 预热 Genesis Agent，请等待约30-60秒...")
    get_agent()
    logger.info("✅ Genesis 预热完成，开始连接 QQ...")

    # 订阅的事件意图
    intents = botpy.Intents(
        public_guild_messages=True,   # 频道 @ 消息
        direct_message=True,          # 私聊
        public_messages=True,         # 群聊 @ 消息
    )

    client = GenesisQQBot(intents=intents)
    client.run(appid=APP_ID, secret=APP_SECRET)


if __name__ == "__main__":
    main()
