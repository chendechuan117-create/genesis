#!/usr/bin/env python3

import sys
import asyncio
import logging
from pathlib import Path
from datetime import datetime

# 添加 nanabot 路径
# 添加项目根目录到 sys.path
sys.path.insert(0, str(Path(__file__).parent))

from genesis.agent import NanoGenesis
from genesis.core.factory import GenesisFactory
from genesis.core.diagnostic import DiagnosticManager
from genesis.core.mission import MissionManager

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
        # Zero-Conf 启动: 自动从 ConfigManager 读取 API Key 和 Proxy
        # Refactored to use Factory
        agent = GenesisFactory.create_common(
            enable_optimization=True
        )
        # 启动调度器 (注意：CLI 使用 input() 会阻塞主线程，导致 Heartbeat 在等待输入时暂停)
        if agent.scheduler:
            await agent.scheduler.start()
            
        print("✅ 系统就绪 (已自动加载 OpenClaw 配置)")
        
        # 显示记忆状态
        try:
            conn = agent.memory._get_conn()
            cursor = conn.execute("SELECT count(*) as count FROM memories")
            mem_count = cursor.fetchone()['count']
            conn.close()
            print(f"🧠 已加载记忆: {mem_count} 条")
        except Exception as e:
            print(f"🧠 记忆库检查跳过: {e}")
        
    except Exception as e:
        print(f"\n❌ 初始化失败: {e}")
        return

    print("\n💡 输入 '/exit' 退出, '/clear' 清除上下文, '/mem' 查看记忆, '/doctor' 系统诊断, '/mission' 任务管理")
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
            metrics = result.get('metrics')
            if metrics:
                print(f"📊 总耗时: {wall_time:.2f}s | Token: {metrics.total_tokens}")
            else:
                print(f"📊 总耗时: {wall_time:.2f}s (无需内核计算)")
        else:
            print(f"\n❌ 错误:\n{result['response']}")
        return  # Exit after one-shot

    # REPL 循环
    while True:
        try:
            # 尝试使用 prompt_toolkit 来支持安全的多行粘贴和自动换行处理 (Bracketed Paste)
            try:
                from prompt_toolkit import PromptSession
                if not hasattr(agent, '_prompt_session'):
                    agent._prompt_session = PromptSession()
                user_input = agent._prompt_session.prompt("\n👤 你 (支持多行粘贴): ").strip()
            except ImportError:
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
                try:
                    conn = agent.memory._get_conn()
                    
                    # 1. 显示压缩块 (长期记忆)
                    print(f"\n🧠 长期记忆 (Compressed Blocks):")
                    cursor = conn.execute("SELECT id, summary FROM compressed_blocks WHERE session_id = ? ORDER BY start_index ASC", (agent.session_manager.session_id,))
                    blocks = cursor.fetchall()
                    if blocks:
                        for b in blocks:
                            print(f"  [{b['id']}] {b['summary'][:60]}...")
                    else:
                        print("  (暂无压缩记忆)")
                        
                    # 2. 显示最近记忆 (短期记忆)
                    cursor = conn.execute("SELECT content_hash, metadata FROM memories ORDER BY id DESC LIMIT 5")
                    rows = cursor.fetchall()
                    
                    print(f"\n🧠 短期记忆 (Recent 5):")
                    for i, row in enumerate(rows, 1):
                        # Fetch content from content table
                        c_hash = row['content_hash']
                        c_row = conn.execute("SELECT body FROM content WHERE hash = ?", (c_hash,)).fetchone()
                        content = c_row['body'] if c_row else "Unknown"
                        # Clean up newlines for display
                        content_clean = content.replace('\n', ' ')[:50]
                        print(f"  {i}. {content_clean}...")
                    conn.close()
                except Exception as e:
                    print(f"❌ 无法读取记忆: {e}")
                continue

            if user_input.lower() in ['/doctor', '/diag']:
                print("\n🚑 正在进行系统诊断 (System Health Check)...")
                try:
                    diag = DiagnosticManager(
                        provider_router=agent.provider_router,
                        memory_store=agent.memory
                    )
                    report = await diag.run_all_checks()
                    
                    print(f"\n诊断报告 (时间: {datetime.fromtimestamp(report['timestamp'])})")
                    print("=" * 40)
                    
                    # Network
                    net = report['checks'].get('network', {})
                    status_icon = "✅" if net.get('status') == 'ok' else "❌"
                    print(f"{status_icon} [网络连接] 状态: {net.get('status')}")
                    if net.get('details'):
                        for item in net['details']:
                            lat = f"{item.get('latency_ms', 0):.1f}ms" if 'latency_ms' in item else "N/A"
                            print(f"    - {item['target']}: {item['status']} ({lat})")
                            
                    # Provider
                    prov = report['checks'].get('provider', {})
                    status_icon = "✅" if prov.get('status') == 'ok' else "❌"
                    print(f"{status_icon} [模型服务] 状态: {prov.get('status')}")
                    if prov.get('status') == 'ok':
                        print(f"    - 服务商: {prov.get('provider')} ({prov.get('model')})")
                        print(f"    - 延迟: {prov.get('latency_ms', 0):.1f}ms")
                    else:
                        print(f"    - 错误: {prov.get('error')}")
                        
                    # Memory
                    mem = report['checks'].get('memory', {})
                    status_icon = "✅" if mem.get('status') == 'ok' else "❌"
                    print(f"{status_icon} [记忆系统] 状态: {mem.get('status')}")
                    if mem.get('status') == 'ok':
                        bc = mem.get('block_count', 0)
                        vc = mem.get('vector_count', -1)
                        enc = mem.get('encoder_status', 'unknown')
                        vec_str = f"{vc} 条" if vc >= 0 else "未启用"
                        
                        print(f"    - 记忆条目: {mem.get('item_count')} (短时)")
                        print(f"    - 压缩区块: {bc} (长时)")
                        print(f"    - 联想记忆: {vec_str} (模型: {enc})")
                        print(f"    - 延迟: {mem.get('latency_ms', 0):.1f}ms")
                    else:
                        print(f"    - 错误: {mem.get('error')}")
                        
                        print(f"    - 错误: {mem.get('error')}")

                    # Tools
                    tools = report['checks'].get('tools', {})
                    if tools.get('status') != 'skipped':
                        status_icon = "✅" if tools.get('status') == 'ok' else "⚠️" 
                        print(f"{status_icon} [工具组件] 已加载: {tools.get('count')} 个")
                        if tools.get('missing'):
                             print(f"    - ⚠️ 缺失核心工具: {tools.get('missing')}")
                        
                    # Disk
                    disk = report['checks'].get('disk', {})
                    status_icon = "✅" if disk.get('status') == 'ok' else "⚠️"
                    print(f"{status_icon} [磁盘空间] 剩余: {disk.get('free_gb')} GB")

                    print("=" * 40)
                    if report['status'] == 'healthy':
                        print("✨ 系统状态良好，可以继续对话。")
                    else:
                        print("⚠️ 系统存在问题，请检查上述错误。")
                        
                except Exception as e:
                    print(f"❌ 诊断失败: {e}")
                continue

            if user_input.lower().startswith('/mission'):
                args = user_input.split(" ", 2)
                subcmd = args[1].lower() if len(args) > 1 else "status"
                
                manager = MissionManager()
                
                if subcmd == "start":
                    if len(args) < 3:
                        print("❌ 用法: /mission start <任务目标>")
                        continue
                    objective = args[2]
                    mission = manager.create_mission(objective)
                    print(f"🎯 任务已启动 (ID: {mission.id[:8]})")
                    print(f"   目标: {mission.objective}")
                    print("   守护进程将在后台自动推进此任务。")
                    
                elif subcmd == "stop":
                    mission = manager.get_active_mission()
                    if mission:
                        manager.update_mission(mission.id, status="paused")
                        print(f"⏸️ 任务已暂停: {mission.objective}")
                    else:
                        print("⚠️ 当前没有运行中的任务")
                        
                elif subcmd == "status":
                    mission = manager.get_active_mission()
                    if mission:
                        print(f"\n🎯 当前任务 (Status: {mission.status})")
                        print(f"   ID: {mission.id}")
                        print(f"   目标: {mission.objective}")
                        print(f"   更新时间: {mission.updated_at}")
                        if mission.context_snapshot:
                            last_out = mission.context_snapshot.get('last_output', 'N/A')
                            print(f"   最新进展: {last_out}")
                        
                        if mission.error_count > 0:
                            print(f"   ⚠️ 错误计数: {mission.error_count} (上次错误: {mission.last_error})")
                    else:
                        print("💤 当前无活跃任务 (即使守护进程在运行)")
                        
                elif subcmd == "list":
                    missions = manager.list_missions()
                    print("\n📜 最近任务:")
                    for m in missions:
                        status_mark = "⚠️" if m.error_count > 0 else ""
                        print(f"   [{m.status.upper()}] {status_mark} {m.created_at[:16]} - {m.objective[:40]}...")
                
                else:
                    print(f"❌ 未知指令: {subcmd}")
                    
                continue

            print("\n🤖 NanoGenesis 思考中...")
            
            import time
            start_wall_time = time.time()
            
            # 定义流式输出状态
            class StreamState:
                last_was_stream = False
            
            # 定义流式输出回调
            async def print_stream(step_type, data):
                if step_type == "reasoning":
                    # Colorize reasoning (Grey)
                    print(f"\033[90m{data}\033[0m", end="", flush=True)
                    StreamState.last_was_stream = True
                elif step_type == "content":
                    # Standard content
                    print(data, end="", flush=True)
                    StreamState.last_was_stream = True
                elif step_type == "tool":
                    if StreamState.last_was_stream:
                        print() # Break the stream line
                        StreamState.last_was_stream = False
                    # Tool Call (Cyan)
                    print(f"\n\033[36m🛠️  调用工具: {data['name']} {json.dumps(data.get('args', {}), ensure_ascii=False)}\033[0m")
                elif step_type == "tool_result":
                    if StreamState.last_was_stream:
                        print()
                        StreamState.last_was_stream = False
                    # Tool Result (Green)
                    # Truncate long results
                    res = data.get('result', '')
                    if len(res) > 200: res = res[:200] + "..."
                    print(f"\033[32m✅ 结果: {res}\033[0m\n")
                elif step_type == "loop_start":
                    if StreamState.last_was_stream:
                        print()
                        StreamState.last_was_stream = False
                    print(f"\n🔄 思考第 {data} 步...", flush=True)

            # 执行处理
            import json
            result = await agent.process(user_input, step_callback=print_stream)
            
            end_wall_time = time.time()
            wall_time = end_wall_time - start_wall_time
            
            # 显示结果
            if result['success']:
                print("\n✅ 回复:")
                print("-" * 20)
                print(result['response'])
                print("-" * 20)
                
                # 显示性能指标
                metrics = result.get('metrics')
                if metrics:
                    print(f"📊 总耗时: {wall_time:.2f}s (内核计算: {metrics.total_time:.2f}s) | Token: {metrics.total_tokens}")
                else:
                    print(f"📊 总耗时: {wall_time:.2f}s (无需内核计算)")
                
                # 显示优化信息
                if result.get('optimization_info'):
                    opt = result['optimization_info']
                    if 'prompt_optimized' in opt:
                        print("✨ [自进化] System Prompt 已优化")
                    if 'profile_evolved' in opt:
                        print("👤 [自进化] 用户画像已更新")
            else:
                print(f"\n❌ 错误:\n{result['response']}")

        except (KeyboardInterrupt, EOFError):
            print("\n👋 再见")
            break
        except Exception as e:
            print(f"\n❌ 发生异常: {e}")

if __name__ == "__main__":
    asyncio.run(main())
