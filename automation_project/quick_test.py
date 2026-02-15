#!/usr/bin/env python3
"""
快速测试系统核心功能（不依赖浏览器）
"""

import os
import json
import sys
from datetime import datetime

def test_file_operations():
    """测试文件操作功能"""
    print("📁 测试文件操作...")
    
    # 测试目录创建
    test_dirs = ["test_data", "test_logs"]
    for dir_name in test_dirs:
        os.makedirs(dir_name, exist_ok=True)
        print(f"  ✅ 创建目录: {dir_name}")
    
    # 测试文件写入
    test_file = "test_data/sample.json"
    test_data = {
        "test": "success",
        "timestamp": datetime.now().isoformat(),
        "system": "automation_money_maker"
    }
    
    with open(test_file, "w", encoding="utf-8") as f:
        json.dump(test_data, f, indent=2)
    
    print(f"  ✅ 写入文件: {test_file}")
    
    # 测试文件读取
    with open(test_file, "r", encoding="utf-8") as f:
        loaded_data = json.load(f)
    
    if loaded_data["test"] == "success":
        print("  ✅ 读取验证通过")
    else:
        print("  ❌ 读取验证失败")
    
    # 清理
    os.remove(test_file)
    for dir_name in test_dirs:
        os.rmdir(dir_name)
    
    print("  ✅ 清理完成")
    return True

def test_dependencies():
    """测试Python依赖"""
    print("\n📦 测试Python依赖...")
    
    required_packages = [
        "requests",
        "schedule",
        "beautifulsoup4"
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

def test_config_loading():
    """测试配置文件加载"""
    print("\n⚙️  测试配置文件...")
    
    config_file = "config/settings.json"
    
    if os.path.exists(config_file):
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                config = json.load(f)
            
            system_name = config.get("system", {}).get("name", "未知")
            version = config.get("system", {}).get("version", "未知")
            
            print(f"  ✅ 配置文件加载成功")
            print(f"     系统: {system_name}")
            print(f"     版本: {version}")
            
            # 检查赚钱策略
            strategies = config.get("monetization", {}).get("strategies", [])
            print(f"     赚钱策略: {len(strategies)} 种")
            
            return True
            
        except Exception as e:
            print(f"  ❌ 配置文件加载失败: {e}")
            return False
    else:
        print(f"  ❌ 配置文件不存在: {config_file}")
        return False

def test_material_collection_simple():
    """测试简单的素材收集"""
    print("\n📝 测试素材收集...")
    
    # 创建简单的收集器
    save_dir = "test_materials"
    os.makedirs(save_dir, exist_ok=True)
    
    # 收集测试文本
    test_text = "自动化赚钱系统测试 - " + datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{save_dir}/test_{timestamp}.txt"
    
    with open(filename, "w", encoding="utf-8") as f:
        f.write(test_text)
    
    if os.path.exists(filename):
        print(f"  ✅ 素材保存成功: {os.path.basename(filename)}")
        
        # 验证内容
        with open(filename, "r", encoding="utf-8") as f:
            content = f.read()
        
        if test_text in content:
            print("  ✅ 内容验证通过")
        else:
            print("  ❌ 内容验证失败")
        
        # 清理
        os.remove(filename)
        os.rmdir(save_dir)
        
        return True
    else:
        print("  ❌ 素材保存失败")
        return False

def main():
    """主测试函数"""
    print("🤖 自动化赚钱系统 - 核心功能测试")
    print("="*50)
    
    test_results = []
    
    # 运行各项测试
    test_results.append(("文件操作", test_file_operations()))
    test_results.append(("Python依赖", test_dependencies()))
    test_results.append(("配置文件", test_config_loading()))
    test_results.append(("素材收集", test_material_collection_simple()))
    
    # 汇总结果
    print("\n" + "="*50)
    print("📊 测试结果汇总")
    print("="*50)
    
    passed = 0
    total = len(test_results)
    
    for test_name, result in test_results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{test_name:15} {status}")
        if result:
            passed += 1
    
    print("="*50)
    success_rate = (passed / total) * 100
    print(f"通过率: {passed}/{total} ({success_rate:.1f}%)")
    
    if passed == total:
        print("\n🎉 所有核心功能测试通过！")
        print("\n📋 系统状态:")
        print(f"  工作目录: {os.getcwd()}")
        print(f"  配置文件: config/settings.json")
        print(f"  数据目录: data/")
        print(f"  日志目录: logs/")
        
        print("\n🚀 下一步操作:")
        print("  1. 安装浏览器: playwright install chromium")
        print("  2. 启动系统: ./start.sh")
        print("  3. 查看赚钱策略: 查看 config/settings.json")
        
        return True
    else:
        print("\n⚠️  部分测试失败，需要修复:")
        for i, (test_name, result) in enumerate(test_results):
            if not result:
                print(f"  {i+1}. {test_name}")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)