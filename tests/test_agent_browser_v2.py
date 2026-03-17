#!/usr/bin/env python3
"""
agent-browser功能测试脚本 v2
根据实际命令行参数调整测试
"""

import subprocess
import time
import json
import os
import psutil
from pathlib import Path

def run_command(cmd, timeout=30, env=None):
    """运行命令并返回结果"""
    if env is None:
        env = os.environ.copy()
        env['PATH'] = f"{os.environ.get('HOME')}/.cargo/bin:{env.get('PATH', '')}"
    
    start_time = time.time()
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env
        )
        elapsed = time.time() - start_time
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "elapsed_time": elapsed,
            "returncode": result.returncode
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Timeout after {timeout}s",
            "elapsed_time": timeout,
            "returncode": -1
        }

def get_memory_usage():
    """获取当前进程内存使用"""
    process = psutil.Process()
    return process.memory_info().rss / 1024 / 1024  # MB

def test_agent_browser_basic():
    """测试agent-browser基本功能"""
    print("=" * 60)
    print("测试 1: agent-browser 基本功能测试")
    print("=" * 60)
    
    tests = []
    
    # 设置环境变量
    env = os.environ.copy()
    env['PATH'] = f"{os.environ.get('HOME')}/.cargo/bin:{env.get('PATH', '')}"
    
    # 测试1: 打开百度首页并获取标题
    print("\n1. 打开百度首页并获取标题...")
    cmd = 'agent-browser open "https://www.baidu.com" && agent-browser wait --load networkidle && agent-browser get title'
    result = run_command(cmd, timeout=20, env=env)
    tests.append({
        "name": "打开百度首页并获取标题",
        "result": result
    })
    print(f"   耗时: {result['elapsed_time']:.2f}s")
    print(f"   成功: {result['success']}")
    if result['stdout']:
        print(f"   输出: {result['stdout'][:200]}")
    
    # 测试2: 截图GitHub首页
    print("\n2. 截图GitHub首页...")
    screenshot_path = "/tmp/github_screenshot_agent.png"
    cmd = f'agent-browser open "https://github.com" && agent-browser wait --load networkidle && agent-browser screenshot "{screenshot_path}" --full'
    result = run_command(cmd, timeout=25, env=env)
    tests.append({
        "name": "截图GitHub首页",
        "result": result
    })
    print(f"   耗时: {result['elapsed_time']:.2f}s")
    print(f"   成功: {result['success']}")
    if Path(screenshot_path).exists():
        size = Path(screenshot_path).stat().st_size
        print(f"   截图大小: {size} bytes")
    
    # 测试3: 获取页面快照（accessibility tree）
    print("\n3. 获取页面快照...")
    cmd = 'agent-browser open "https://www.google.com" && agent-browser wait --load networkidle && agent-browser snapshot -i'
    result = run_command(cmd, timeout=20, env=env)
    tests.append({
        "name": "获取Google页面快照",
        "result": result
    })
    print(f"   耗时: {result['elapsed_time']:.2f}s")
    print(f"   成功: {result['success']}")
    if result['stdout']:
        lines = result['stdout'].split('\n')
        print(f"   输出行数: {len(lines)}")
        print(f"   示例: {lines[0][:100]}..." if lines else "")
    
    return tests

def test_playwright_basic():
    """测试Playwright基本功能（现有方案）"""
    print("\n" + "=" * 60)
    print("测试 2: Playwright 基本功能测试（现有方案）")
    print("=" * 60)
    
    playwright_test = """
import asyncio
import time
from playwright.async_api import async_playwright

async def test_playwright():
    start_time = time.time()
    results = []
    
    async with async_playwright() as p:
        # 启动浏览器
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        
        # 测试1: 打开百度首页
        page1 = await context.new_page()
        try:
            response = await page1.goto("https://www.baidu.com", timeout=10000)
            title = await page1.title()
            results.append(f"百度标题: {title}")
            results.append(f"状态码: {response.status if response else 'N/A'}")
        except Exception as e:
            results.append(f"百度测试失败: {e}")
        finally:
            await page1.close()
        
        # 测试2: 截图GitHub首页
        page2 = await context.new_page()
        try:
            await page2.goto("https://github.com", timeout=10000)
            await page2.screenshot(path="/tmp/github_screenshot_playwright.png", full_page=True)
            results.append("GitHub截图成功")
        except Exception as e:
            results.append(f"GitHub截图失败: {e}")
        finally:
            await page2.close()
        
        # 测试3: 获取Google页面内容
        page3 = await context.new_page()
        try:
            await page3.goto("https://www.google.com", timeout=10000)
            content = await page3.content()
            results.append(f"Google页面大小: {len(content)} chars")
        except Exception as e:
            results.append(f"Google测试失败: {e}")
        finally:
            await page3.close()
        
        await browser.close()
    
    elapsed = time.time() - start_time
    results.append(f"总耗时: {elapsed:.2f}s")
    
    for r in results:
        print(r)

asyncio.run(test_playwright())
"""
    
    # 写入临时文件
    temp_file = "/tmp/test_playwright.py"
    with open(temp_file, "w") as f:
        f.write(playwright_test)
    
    print("\n运行Playwright测试...")
    start_mem = get_memory_usage()
    start_time = time.time()
    
    result = run_command(f"python3 {temp_file}", timeout=30)
    
    elapsed = time.time() - start_time
    end_mem = get_memory_usage()
    memory_diff = end_mem - start_mem
    
    print(f"   耗时: {elapsed:.2f}s")
    print(f"   内存变化: {memory_diff:.2f} MB")
    print(f"   成功: {result['success']}")
    
    return {
        "name": "Playwright综合测试",
        "result": result,
        "elapsed_time": elapsed,
        "memory_usage": memory_diff
    }

def performance_comparison():
    """性能对比测试"""
    print("\n" + "=" * 60)
    print("测试 3: 性能对比测试")
    print("=" * 60)
    
    # 设置环境变量
    env = os.environ.copy()
    env['PATH'] = f"{os.environ.get('HOME')}/.cargo/bin:{env.get('PATH', '')}"
    
    # 冷启动时间测试
    print("\n冷启动时间测试（重复3次取平均）:")
    
    # agent-browser冷启动
    agent_times = []
    for i in range(3):
        cmd = 'agent-browser open "https://httpbin.org/get" && agent-browser get title'
        start = time.time()
        result = run_command(cmd, timeout=15, env=env)
        if result['success']:
            agent_times.append(result['elapsed_time'])
        time.sleep(2)  # 冷却
    
    # Playwright冷启动
    playwright_times = []
    for i in range(3):
        script = '''
import asyncio
from playwright.async_api import async_playwright
async def test():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto("https://httpbin.org/get", timeout=5000)
        title = await page.title()
        await browser.close()
asyncio.run(test())
'''
        temp_file = f"/tmp/playwright_cold_{i}.py"
        with open(temp_file, "w") as f:
            f.write(script)
        
        start = time.time()
        result = run_command(f"python3 {temp_file}", timeout=15)
        if result['success']:
            playwright_times.append(time.time() - start)
        time.sleep(2)
    
    agent_avg = sum(agent_times)/len(agent_times) if agent_times else 0
    playwright_avg = sum(playwright_times)/len(playwright_times) if playwright_times else 0
    
    print(f"agent-browser冷启动: {agent_avg:.2f}s (平均, 样本: {len(agent_times)})")
    print(f"Playwright冷启动: {playwright_avg:.2f}s (平均, 样本: {len(playwright_times)})")
    
    # 内存使用测试
    print("\n内存使用测试:")
    
    # agent-browser内存测试
    agent_memory = []
    for i in range(2):
        start_mem = get_memory_usage()
        cmd = 'agent-browser open "https://example.com" && agent-browser get title && agent-browser close'
        result = run_command(cmd, timeout=10, env=env)
        end_mem = get_memory_usage()
        if result['success']:
            agent_memory.append(end_mem - start_mem)
        time.sleep(2)
    
    agent_mem_avg = sum(agent_memory)/len(agent_memory) if agent_memory else 0
    print(f"agent-browser内存增量: {agent_mem_avg:.2f} MB (平均)")
    
    return {
        "agent_browser_cold_start": agent_avg,
        "playwright_cold_start": playwright_avg,
        "agent_browser_memory": agent_mem_avg
    }

def analyze_genesis_integration():
    """分析Genesis集成可行性"""
    print("\n" + "=" * 60)
    print("分析 4: Genesis架构集成可行性分析")
    print("=" * 60)
    
    # 检查现有浏览器工具
    genesis_skills_dir = "/home/chendechusn/Genesis/Genesis/genesis/skills"
    browser_tools = []
    
    if Path(genesis_skills_dir).exists():
        for file in Path(genesis_skills_dir).glob("*.py"):
            content = file.read_text()
            if any(keyword in content.lower() for keyword in ["browser", "playwright", "selenium", "chromium"]):
                browser_tools.append(file.name)
    
    print(f"\n现有浏览器相关工具 ({len(browser_tools)}个):")
    for tool in sorted(browser_tools)[:10]:  # 显示前10个
        print(f"  - {tool}")
    if len(browser_tools) > 10:
        print(f"  ... 还有 {len(browser_tools)-10} 个")
    
    # 分析集成方案
    print("\n集成方案分析:")
    print("1. 直接替换方案:")
    print("   - 优点: 架构简单，维护成本低")
    print("   - 缺点: 需要重写现有工具，风险较高")
    
    print("\n2. 并行支持方案:")
    print("   - 优点: 渐进式迁移，风险可控")
    print("   - 缺点: 需要维护两套代码，复杂度增加")
    
    print("\n3. 渐进迁移方案:")
    print("   - 优点: 按需迁移，灵活性高")
    print("   - 缺点: 迁移周期长，需要兼容层")
    
    # 识别技术障碍
    print("\n技术障碍识别:")
    print("1. API兼容性: agent-browser使用命令行接口，而现有工具使用Python API")
    print("2. 异步处理: agent-browser是同步CLI，需要适配异步架构")
    print("3. 错误处理: 需要统一的错误处理机制")
    print("4. 状态管理: agent-browser有daemon模式，需要管理浏览器生命周期")
    
    return {
        "existing_tools": browser_tools,
        "integration_options": ["直接替换", "并行支持", "渐进迁移"],
        "technical_challenges": [
            "API兼容性差异",
            "异步架构适配",
            "错误处理统一",
            "状态管理"
        ]
    }

def main():
    """主测试函数"""
    print("开始 agent-browser 功能测试与性能对比 v2")
    print(f"测试时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 检查agent-browser版本
    env = os.environ.copy()
    env['PATH'] = f"{os.environ.get('HOME')}/.cargo/bin:{env.get('PATH', '')}"
    version_result = run_command("agent-browser --version", env=env)
    print(f"agent-browser版本: {version_result['stdout'].strip() if version_result['success'] else '检查失败'}")
    
    # 运行测试
    agent_tests = test_agent_browser_basic()
    playwright_test = test_playwright_basic()
    perf_results = performance_comparison()
    integration_analysis = analyze_genesis_integration()
    
    # 生成报告
    print("\n" + "=" * 60)
    print("测试报告摘要")
    print("=" * 60)
    
    # agent-browser测试结果
    print("\nagent-browser测试结果:")
    success_count = sum(1 for test in agent_tests if test['result']['success'])
    total_count = len(agent_tests)
    print(f"  通过率: {success_count}/{total_count} ({success_count/total_count*100:.1f}%)")
    
    for test in agent_tests:
        status = "✅ 通过" if test['result']['success'] else "❌ 失败"
        print(f"  {test['name']}: {status} ({test['result']['elapsed_time']:.2f}s)")
    
    # Playwright测试结果
    print(f"\nPlaywright测试结果:")
    status = "✅ 通过" if playwright_test['result']['success'] else "❌ 失败"
    print(f"  {playwright_test['name']}: {status} ({playwright_test['elapsed_time']:.2f}s)")
    print(f"  内存使用: {playwright_test['memory_usage']:.2f} MB")
    
    # 性能对比
    print("\n性能对比:")
    print(f"  agent-browser冷启动: {perf_results['agent_browser_cold_start']:.2f}s")
    print(f"  Playwright冷启动: {perf_results['playwright_cold_start']:.2f}s")
    print(f"  agent-browser内存增量: {perf_results['agent_browser_memory']:.2f} MB")
    
    # 集成分析
    print(f"\n集成分析:")
    print(f"  现有浏览器工具数量: {len(integration_analysis['existing_tools'])}")
    print(f"  推荐集成方案: {integration_analysis['integration_options'][1]} (并行支持)")
    
    # 保存详细结果
    report = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "agent_browser_version": version_result['stdout'].strip() if version_result['success'] else "unknown",
        "agent_browser_tests": [
            {
                "name": test['name'],
                "success": test['result']['success'],
                "elapsed_time": test['result']['elapsed_time'],
                "stdout_preview": test['result']['stdout'][:500] if test['result']['stdout'] else ""
            }
            for test in agent_tests
        ],
        "playwright_test": playwright_test,
        "performance_comparison": perf_results,
        "integration_analysis": integration_analysis,
        "recommendations": [
            "采用并行支持方案，逐步迁移",
            "创建agent-browser适配层工具",
            "保持现有Playwright工具的兼容性",
            "优先在新功能中使用agent-browser"
        ]
    }
    
    report_file = "/tmp/agent_browser_test_report_v2.json"
    with open(report_file, "w") as f:
        json.dump(report, f, indent=2, default=str)
    
    print(f"\n详细测试报告已保存到: {report_file}")
    print("测试完成！")

if __name__ == "__main__":
    main()