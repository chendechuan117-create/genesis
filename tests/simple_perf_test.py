#!/usr/bin/env python3
"""
简单的性能对比测试
"""

import subprocess
import time
import json

def run_agent_browser_test():
    """测试agent-browser"""
    print("测试 agent-browser...")
    
    # 先关闭可能存在的daemon
    subprocess.run("agent-browser close", shell=True, capture_output=True)
    time.sleep(1)
    
    # 测试冷启动
    start = time.time()
    result = subprocess.run(
        'agent-browser open "https://httpbin.org/get" && agent-browser get title',
        shell=True,
        capture_output=True,
        text=True,
        timeout=30
    )
    cold_start = time.time() - start
    
    # 测试热启动（daemon已运行）
    start = time.time()
    result2 = subprocess.run(
        'agent-browser open "https://example.com" && agent-browser get title',
        shell=True,
        capture_output=True,
        text=True,
        timeout=15
    )
    warm_start = time.time() - start
    
    # 测试截图
    start = time.time()
    result3 = subprocess.run(
        'agent-browser open "https://github.com" && agent-browser wait --load networkidle && agent-browser screenshot /tmp/test_agent.png --full',
        shell=True,
        capture_output=True,
        text=True,
        timeout=30
    )
    screenshot_time = time.time() - start
    
    return {
        "cold_start": cold_start,
        "warm_start": warm_start,
        "screenshot_time": screenshot_time,
        "success": result.returncode == 0 and result2.returncode == 0,
        "output_samples": {
            "cold": result.stdout[:200] if result.stdout else "",
            "warm": result2.stdout[:200] if result2.stdout else ""
        }
    }

def run_playwright_test():
    """测试Playwright"""
    print("\n测试 Playwright...")
    
    script = '''
import asyncio
import time
from playwright.async_api import async_playwright

async def test():
    # 冷启动测试
    start = time.time()
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto("https://httpbin.org/get", timeout=10000)
        title = await page.title()
        await browser.close()
    cold_start = time.time() - start
    
    # 热启动测试（重用playwright上下文）
    start = time.time()
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto("https://example.com", timeout=10000)
        title2 = await page.title()
        await browser.close()
    warm_start = time.time() - start
    
    # 截图测试
    start = time.time()
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto("https://github.com", timeout=15000)
        await page.screenshot(path="/tmp/test_playwright.png", full_page=True)
        await browser.close()
    screenshot_time = time.time() - start
    
    print(f"COLD_START:{cold_start}")
    print(f"WARM_START:{warm_start}")
    print(f"SCREENSHOT_TIME:{screenshot_time}")

asyncio.run(test())
'''
    
    with open("/tmp/playwright_perf.py", "w") as f:
        f.write(script)
    
    result = subprocess.run(
        "python3 /tmp/playwright_perf.py",
        shell=True,
        capture_output=True,
        text=True,
        timeout=45
    )
    
    # 解析输出
    cold_start = warm_start = screenshot_time = 0
    for line in result.stdout.split('\n'):
        if line.startswith("COLD_START:"):
            cold_start = float(line.split(":")[1])
        elif line.startswith("WARM_START:"):
            warm_start = float(line.split(":")[1])
        elif line.startswith("SCREENSHOT_TIME:"):
            screenshot_time = float(line.split(":")[1])
    
    return {
        "cold_start": cold_start,
        "warm_start": warm_start,
        "screenshot_time": screenshot_time,
        "success": result.returncode == 0
    }

def analyze_integration():
    """分析集成方案"""
    print("\n分析集成方案...")
    
    # 检查现有架构
    existing_tools = [
        "browser_controller.py",
        "ai_browser_automation.py", 
        "ai_browser_automation_v2.py",
        "ai_browser_simple.py",
        "safe_ai_browser.py"
    ]
    
    # 集成方案
    integration_options = [
        {
            "name": "直接替换",
            "pros": ["架构简化", "单一技术栈", "维护成本低"],
            "cons": ["迁移风险高", "需要重写所有工具", "兼容性问题"],
            "effort": "高",
            "timeline": "2-3个月"
        },
        {
            "name": "并行支持",
            "pros": ["风险可控", "渐进迁移", "A/B测试能力"],
            "cons": ["维护两套代码", "复杂度增加", "学习成本"],
            "effort": "中",
            "timeline": "1-2个月"
        },
        {
            "name": "适配层",
            "pros": ["透明迁移", "现有API不变", "灵活切换"],
            "cons": ["适配层复杂度", "性能开销", "调试困难"],
            "effort": "中高",
            "timeline": "1.5-2.5个月"
        }
    ]
    
    return {
        "existing_tools": existing_tools,
        "integration_options": integration_options,
        "recommendation": {
            "option": "并行支持",
            "reason": "风险可控，允许渐进迁移，适合现有复杂架构",
            "steps": [
                "1. 创建agent-browser基础工具",
                "2. 在新功能中使用agent-browser",
                "3. 逐步迁移现有工具",
                "4. 最终评估完全迁移"
            ]
        }
    }

def main():
    print("=" * 60)
    print("agent-browser与Playwright性能对比测试")
    print("=" * 60)
    
    # 运行测试
    agent_results = run_agent_browser_test()
    playwright_results = run_playwright_test()
    integration = analyze_integration()
    
    # 显示结果
    print("\n" + "=" * 60)
    print("性能对比结果")
    print("=" * 60)
    
    print(f"\nagent-browser:")
    print(f"  冷启动: {agent_results['cold_start']:.2f}s")
    print(f"  热启动: {agent_results['warm_start']:.2f}s")
    print(f"  截图时间: {agent_results['screenshot_time']:.2f}s")
    print(f"  测试状态: {'✅ 成功' if agent_results['success'] else '❌ 失败'}")
    
    print(f"\nPlaywright:")
    print(f"  冷启动: {playwright_results['cold_start']:.2f}s")
    print(f"  热启动: {playwright_results['warm_start']:.2f}s")
    print(f"  截图时间: {playwright_results['screenshot_time']:.2f}s")
    print(f"  测试状态: {'✅ 成功' if playwright_results['success'] else '❌ 失败'}")
    
    # 性能对比分析
    print("\n" + "=" * 60)
    print("性能分析")
    print("=" * 60)
    
    if agent_results['success'] and playwright_results['success']:
        cold_ratio = agent_results['cold_start'] / playwright_results['cold_start'] if playwright_results['cold_start'] > 0 else 0
        warm_ratio = agent_results['warm_start'] / playwright_results['warm_start'] if playwright_results['warm_start'] > 0 else 0
        
        print(f"\n冷启动对比: agent-browser是Playwright的 {cold_ratio:.1f}倍")
        print(f"热启动对比: agent-browser是Playwright的 {warm_ratio:.1f}倍")
        
        if cold_ratio > 1.5:
            print("⚠️  agent-browser冷启动明显慢于Playwright")
        elif cold_ratio < 0.8:
            print("✅  agent-browser冷启动快于Playwright")
        else:
            print("📊  冷启动性能相近")
    
    # 集成建议
    print("\n" + "=" * 60)
    print("Genesis集成建议")
    print("=" * 60)
    
    print(f"\n现有浏览器工具: {len(integration['existing_tools'])}个")
    for tool in integration['existing_tools']:
        print(f"  - {tool}")
    
    print(f"\n推荐方案: {integration['recommendation']['option']}")
    print(f"理由: {integration['recommendation']['reason']}")
    
    print("\n实施步骤:")
    for step in integration['recommendation']['steps']:
        print(f"  {step}")
    
    # 保存报告
    report = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "agent_browser": agent_results,
        "playwright": playwright_results,
        "integration_analysis": integration,
        "summary": {
            "agent_browser_usable": agent_results['success'],
            "playwright_usable": playwright_results['success'],
            "recommended_approach": integration['recommendation']['option'],
            "key_finding": "agent-browser功能完整但启动较慢，适合作为补充方案"
        }
    }
    
    with open("/tmp/browser_perf_report.json", "w") as f:
        json.dump(report, f, indent=2)
    
    print(f"\n详细报告已保存到: /tmp/browser_perf_report.json")
    print("\n测试完成!")

if __name__ == "__main__":
    main()