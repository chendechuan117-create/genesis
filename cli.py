
import sys
import asyncio
import logging
from pathlib import Path
from datetime import datetime

# 添加 nanabot 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from nanogenesis.agent import NanoGenesis

# 设置日志级别，避免干扰用户界面
logging.getLogger().setLevel(logging.WARNING)
# 单独为 agent 设置 info 级别以便看到关键步骤
logging.getLogger("nanogenesis.agent").setLevel(logging.INFO)

async def main():
    print("\n" + "=" * 60)
    print("🚀 NanoGenesis 2.0 - Interactive CLI")
    print("=" * 60)
    print("初始化系统中... (加载沙箱、记忆库、优化器)")
    
    try:
        # Zero-Conf 启动: 自动从 ConfigManager 读取 API Key 和 Proxy
        agent = NanoGenesis(
            enable_optimization=True
        )
        # 启动调度器 (注意：CLI 使用 input() 会阻塞主线程，导致 Heartbeat 在等待输入时暂停)
        if agent.scheduler:
            await agent.scheduler.start()
            
        print("✅ 系统就绪 (已自动加载 OpenClaw 配置)")
        
        # 显示记忆状态
        cursor = agent.memory.conn.execute("SELECT count(*) as count FROM documents")
        mem_count = cursor.fetchone()['count']
        print(f"🧠 已加载记忆: {mem_count} 条")
        
    except Exception as e:
        print(f"\n❌ 初始化失败: {e}")
        return

    print("\n💡 输入 '/exit' 退出, '/clear' 清除上下文, '/mem' 查看记忆")
    print("-" * 60)

    # Check for one-shot mode (command-line argument)
    if len(sys.argv) > 1:
        user_input = " ".join(sys.argv[1:])
        print(f"\n👤 你: {user_input}")
        print("\n🤖 NanoGenesis 思考中...")
        
        import time
        start_wall_time = time.time()
        result = await agent.process(user_input)
        end_wall_time = time.time()
        wall_time = end_wall_time - start_wall_time
        
        if result['success']:
            print("\n✅ 回复:")
            print("-" * 20)
            print(result['response'])
            print("-" * 20)
            metrics = result['metrics']
            print(f"📊 总耗时: {wall_time:.2f}s | Token: {metrics.total_tokens}")
        else:
            print(f"\n❌ 错误:\n{result['response']}")
        return  # Exit after one-shot

    # REPL 循环
    while True:
        try:
            user_input = input("\n👤 你: ").strip()
            
            if not user_input:
                continue
                
            if user_input.lower() in ['/exit', '/quit', 'exit', 'quit']:
                print("👋 再见！")
                break
                
            if user_input.lower() == '/clear':
                agent.context.clear()
                print("🧹 上下文已清除")
                continue
                
            if user_input.lower() == '/mem':
                print(f"🧠 当前记忆库 ({len(agent.memory.memories)} 条):")
                for i, m in enumerate(agent.memory.memories[-5:], 1):
                    print(f"  {i}. {m['content'][:50]}...")
                continue

            print("\n🤖 NanoGenesis 思考中...")
            
            import time
            start_wall_time = time.time()
            
            # 执行处理
            result = await agent.process(user_input)
            
            end_wall_time = time.time()
            wall_time = end_wall_time - start_wall_time
            
            # 显示结果
            if result['success']:
                print("\n✅ 回复:")
                print("-" * 20)
                print(result['response'])
                print("-" * 20)
                
                # 显示性能指标
                metrics = result['metrics']
                print(f"📊 总耗时: {wall_time:.2f}s (内核计算: {metrics.total_time:.2f}s) | Token: {metrics.total_tokens}")
                
                # 显示优化信息
                if result.get('optimization_info'):
                    opt = result['optimization_info']
                    if 'prompt_optimized' in opt:
                        print("✨ [自进化] System Prompt 已优化")
                    if 'profile_evolved' in opt:
                        print("👤 [自进化] 用户画像已更新")
            else:
                print(f"\n❌ 错误:\n{result['response']}")

        except KeyboardInterrupt:
            print("\n👋 中断")
            break
        except Exception as e:
            print(f"\n❌ 发生异常: {e}")

if __name__ == "__main__":
    asyncio.run(main())
