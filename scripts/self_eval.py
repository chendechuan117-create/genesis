#!/usr/bin/env python3
"""让 Genesis 自证 auto 产出的价值。
直接调用 agent.process()，输出完整推理过程。
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

import logging
logging.basicConfig(level=logging.WARNING, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

from factory import create_agent

EVAL_PROMPT = """你的知识库在过去 12 小时内自动产出了 71 个新节点（全部来自 C-Phase reflection）。

请你现在做以下事情：

1. 搜索你最近创建的节点（关键词: Observation Sustainment, LLM物理定律, Field Core, guard chain）
2. 逐一审视搜索到的节点：
   - 内容是否有实际可执行的价值？还是纯粹的概念堆砌？
   - 是否存在大量重复（同一个"五段守护链"模板套在不同阶段上）？
   - LLM物理定律节点（Law3/Law4/Law5）有标题无正文——这是数据完整性问题。
3. 给出你的诚实判断：
   - 这 71 个节点中，有多少是真正有价值的（能在未来任务中被实际使用）？
   - 有多少是重复/低质量的垃圾？
   - 建议哪些应该保留，哪些应该清理？

不要客气，不要自我辩护。用事实说话。"""


async def main():
    print("=== Genesis Self-Evaluation ===")
    print("Initializing agent...")
    agent = create_agent()

    print(f"Sending evaluation task...\n")

    async def callback(event_type, data):
        if event_type == "tool_start":
            name = data.get("name", "") if isinstance(data, dict) else ""
            print(f"  🔧 [{name}] ...", flush=True)
        elif event_type == "tool_end":
            name = data.get("name", "") if isinstance(data, dict) else ""
            print(f"  ✅ [{name}] done", flush=True)

    result = await agent.process(EVAL_PROMPT, step_callback=callback)
    response = result.response if hasattr(result, 'response') else result.get("response", "...") if isinstance(result, dict) else str(result)

    print("\n" + "=" * 60)
    print("GENESIS SELF-EVALUATION RESULT:")
    print("=" * 60)
    print(response)
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
