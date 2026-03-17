#!/usr/bin/env python3
"""
agent-browser功能测试脚本
测试agent-browser的基本功能并与现有Playwright方案对比
"""

import subprocess
import time
import json
import os
import psutil
from pathlib import Path

def run_command(cmd, timeout=30):
    """运行命令并返回结果"""
    start_time = time.time()
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout
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
    
    # 测试1: 打开百度首页
    print("\n1. 打开百度首页...")
    cmd = 'agent-browser --url "https://www.baidu.com" --action "get_title"'
    result = run_command(cmd, timeout=15)
    tests.append({
        "name": "打开百度首页",
        "result": result
    })
    print(f"   耗时: {result['elapsed_time']:.2f}s")
    print(f"   成功: {result['success']}")
    if result['stdout']:
        print(f"   输出: {result['stdout'][:200]}...")
    
    # 测试2: 截图GitHub首页
    print("\n2. 截图GitHub首页...")
    screenshot_path = "/tmp/github_screenshot_agent.png"
    cmd = f'agent-browser --url "https://github.com" --action "screenshot" --output "{screenshot_path}"'
    result = run_command(cmd, timeout=20)
    tests.append({
        "name": "截图GitHub首页",
        "result": result
    })
    print(f"   耗时: {result['elapsed_time']:.2f}s")
    print(f"   成功: {result['success']}")
    if Path(screenshot_path).exists():
        size = Path(screenshot_path).stat().st_size
        print(f"   截图大小: {size} bytes")
    
    # 测试3: 搜索内容
    print("\n3. 搜索'Python programming'...")
    cmd = 'agent-browser --url "https://www.google.com" --action "search" --query "Python programming"'
    result = run_command(cmd, timeout=25)
    tests.append({
        "name": "搜索Python programming",
        "result": result
    })
    print(f"   耗时: {result['elapsed_time']:.2f}s")
    print(f"   成功: {result['success']}")
    
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
        
        # 测试3: 搜索测试
        page3 = await context.new_page()
        try:
            await page3.goto("https://www.google.com", timeout=10000)
            # 简单搜索测试 - 获取页面内容
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
    
    # 冷启动时间测试
    print("\n冷启动时间测试（重复3次取平均）:")
    
    # agent-browser冷启动
    agent_times = []
    for i in range(3):
        cmd = 'agent-browser --url "https://httpbin.org/get" --action "get_title"'
        start = time.time()
        result = run_command(cmd, timeout=10)
        if result['success']:
            agent_times.append(time.time() - start)
        time.sleep(1)  # 冷却
    
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
        await browser.close()
asyncio.run(test())
'''
        temp_file = f"/tmp/playwright_cold_{i}.py"
        with open(temp_file, "w") as f:
            f.write(script)
        
        start = time.time()
        result = run_command(f"python3 {temp_file}", timeout=10)
        if result['success']:
            playwright_times.append(time.time() - start)
        time.sleep(1)
    
    print(f"agent-browser冷启动: {sum(agent_times)/len(agent_times):.2f}s (平均)")
    print(f"Playwright冷启动: {sum(playwright_times)/len(playwright_times):.2f}s (平均)")
    
    return {
        "agent_browser_cold_start": sum(agent_times)/len(agent_times) if agent_times else None,
        "playwright_cold_start": sum(playwright_times)/len(playwright_times) if playwright_times else None
    }

def main():
    """主测试函数"""
    print("开始 agent-browser 功能测试与性能对比")
    print(f"测试时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"agent-browser版本: ", end="")
    version_result = run_command("agent-browser --version")
    print(version_result['stdout'].strip() if version_result['success'] else "未知")
    
    # 运行测试
    agent_tests = test_agent_browser_basic()
    playwright_test = test_playwright_basic()
    perf_results = performance_comparison()
    
    # 生成报告
    print("\n" + "=" * 60)
    print("测试报告摘要")
    print("=" * 60)
    
    # agent-browser测试结果
    print("\nagent-browser测试结果:")
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
    if perf_results['agent_browser_cold_start']:
        print(f"  agent-browser冷启动: {perf_results['agent_browser_cold_start']:.2f}s")
    if perf_results['playwright_cold_start']:
        print(f"  Playwright冷启动: {perf_results['playwright_cold_start']:.2f}s")
    
    # 保存详细结果
    report = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "agent_browser_tests": agent_tests,
        "playwright_test": playwright_test,
        "performance_comparison": perf_results
    }
    
    report_file = "/tmp/agent_browser_test_report.json"
    with open(report_file, "w") as f:
        json.dump(report, f, indent=2, default=str)
    
    print(f"\n详细测试报告已保存到: {report_file}")
    print("测试完成！")

if __name__ == "__main__":
    main()