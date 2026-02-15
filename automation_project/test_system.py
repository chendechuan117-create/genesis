#!/usr/bin/env python3
"""
测试自动化系统
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.basic_automator import BasicAutomator, MaterialCollector

def test_basic_automation():
    """测试基础自动化功能"""
    print("🧪 测试基础自动化功能...")
    
    # 创建测试实例
    automator = BasicAutomator(headless=True, slow_mo=100)
    collector = MaterialCollector()
    
    # 简单的测试任务
    test_url = "https://httpbin.org/html"
    test_actions = [
        {"type": "extract", "selector": "h1", "wait": 1},
        {"type": "extract", "selector": "p", "wait": 1}
    ]
    
    print(f"🌐 测试URL: {test_url}")
    print(f"📋 测试操作: {len(test_actions)} 个")
    
    # 执行测试
    results = automator.automate_website(test_url, test_actions)
    
    if results:
        print(f"✅ 测试成功！获取到 {len(results)} 条结果")
        
        # 保存结果
        result_file = automator.save_result(results, "test_run")
        
        # 收集素材
        for i, result in enumerate(results):
            filename = collector.collect_text(
                result["content"],
                source="test",
                tags=["automation", "test"]
            )
            if filename:
                print(f"  📝 素材 {i+1} 已保存: {os.path.basename(filename)}")
        
        return True
    else:
        print("❌ 测试失败，未获取到结果")
        return False

def test_material_collection():
    """测试素材收集功能"""
    print("\n📦 测试素材收集功能...")
    
    collector = MaterialCollector()
    
    # 测试文本收集
    test_text = "这是一个测试文本，用于验证素材收集功能。自动化系统应该能够正确处理各种文本内容。"
    
    filename = collector.collect_text(
        test_text,
        source="test_function",
        tags=["test", "material", "collection"]
    )
    
    if filename and os.path.exists(filename):
        print(f"✅ 文本素材收集成功: {os.path.basename(filename)}")
        
        # 读取验证
        with open(filename, "r", encoding="utf-8") as f:
            content = f.read()
            if test_text in content:
                print("✅ 内容验证通过")
            else:
                print("❌ 内容验证失败")
        
        return True
    else:
        print("❌ 文本素材收集失败")
        return False

def test_directory_structure():
    """测试目录结构"""
    print("\n📁 测试目录结构...")
    
    required_dirs = [
        "data",
        "data/results", 
        "data/materials",
        "logs",
        "config"
    ]
    
    all_exist = True
    for dir_path in required_dirs:
        if os.path.exists(dir_path):
            print(f"  ✅ {dir_path}/")
        else:
            print(f"  ❌ {dir_path}/ (缺失)")
            all_exist = False
    
    return all_exist

def test_dependencies():
    """测试依赖包"""
    print("\n📦 测试Python依赖...")
    
    required_packages = [
        "playwright",
        "beautifulsoup4", 
        "requests",
        "schedule"
    ]
    
    import importlib.util
    
    all_installed = True
    for package in required_packages:
        try:
            importlib.import_module(package)
            print(f"  ✅ {package}")
        except ImportError:
            print(f"  ❌ {package} (未安装)")
            all_installed = False
    
    return all_installed

def main():
    """主测试函数"""
    print("🤖 自动化赚钱系统 - 功能测试")
    print("="*50)
    
    test_results = []
    
    # 运行各项测试
    test_results.append(("目录结构", test_directory_structure()))
    test_results.append(("依赖包", test_dependencies()))
    test_results.append(("素材收集", test_material_collection()))
    test_results.append(("基础自动化", test_basic_automation()))
    
    # 汇总结果
    print("\n" + "="*50)
    print("📊 测试结果汇总")
    print("="*50)
    
    passed = 0
    total = len(test_results)
    
    for test_name, result in test_results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{test_name:20} {status}")
        if result:
            passed += 1
    
    print("="*50)
    success_rate = (passed / total) * 100
    print(f"通过率: {passed}/{total} ({success_rate:.1f}%)")
    
    if passed == total:
        print("🎉 所有测试通过！系统可以正常运行。")
        print("\n🚀 下一步：运行 ./start.sh 启动自动化系统")
        return True
    else:
        print("⚠️  部分测试失败，请检查问题。")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)