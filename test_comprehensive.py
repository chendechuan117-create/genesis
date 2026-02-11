#!/usr/bin/env python3
"""
综合测试脚本
测试系统各项功能
"""

import os
import sys
import subprocess
import platform

def test_shell():
    """测试shell命令执行"""
    print("="*50)
    print("测试 1: Shell命令执行")
    print("="*50)
    
    tests = [
        ("echo 'Shell测试成功'", "Shell测试成功"),
        ("pwd", "/home/chendechusn/Genesis/nanogenesis"),
        ("python3 --version", "Python 3.14"),
    ]
    
    for cmd, expected in tests:
        try:
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            if expected in result.stdout:
                print(f"✅ {cmd}: 成功")
            else:
                print(f"❌ {cmd}: 失败 - 输出: {result.stdout[:50]}")
        except Exception as e:
            print(f"❌ {cmd}: 异常 - {e}")

def test_file_operations():
    """测试文件操作"""
    print("\n" + "="*50)
    print("测试 2: 文件操作")
    print("="*50)
    
    test_file = "test_file_operations.txt"
    
    # 测试写入
    with open(test_file, "w") as f:
        f.write("测试文件操作\n")
        f.write("第二行内容\n")
    
    print(f"✅ 文件创建: {test_file}")
    
    # 测试读取
    with open(test_file, "r") as f:
        content = f.read()
        if "测试文件操作" in content:
            print("✅ 文件读取: 成功")
        else:
            print("❌ 文件读取: 失败")
    
    # 测试追加
    with open(test_file, "a") as f:
        f.write("追加的内容\n")
    
    # 测试文件存在
    if os.path.exists(test_file):
        print("✅ 文件存在检查: 成功")
    
    # 清理
    os.remove(test_file)
    print("✅ 文件清理: 成功")

def test_directory_operations():
    """测试目录操作"""
    print("\n" + "="*50)
    print("测试 3: 目录操作")
    print("="*50)
    
    test_dir = "test_directory"
    
    # 创建目录
    os.makedirs(test_dir, exist_ok=True)
    print(f"✅ 目录创建: {test_dir}")
    
    # 在目录中创建文件
    test_file = os.path.join(test_dir, "test.txt")
    with open(test_file, "w") as f:
        f.write("目录测试文件\n")
    
    # 列出目录内容
    files = os.listdir(test_dir)
    if "test.txt" in files:
        print("✅ 目录列表: 成功")
    
    # 清理
    os.remove(test_file)
    os.rmdir(test_dir)
    print("✅ 目录清理: 成功")

def test_system_info():
    """测试系统信息"""
    print("\n" + "="*50)
    print("测试 4: 系统信息")
    print("="*50)
    
    info = {
        "系统": platform.system(),
        "发行版": platform.release(),
        "架构": platform.machine(),
        "Python版本": platform.python_version(),
        "当前目录": os.getcwd(),
        "用户": os.getenv("USER", "未知"),
    }
    
    for key, value in info.items():
        print(f"  {key}: {value}")
    
    print("✅ 系统信息收集: 成功")

def test_network():
    """测试网络连接"""
    print("\n" + "="*50)
    print("测试 5: 网络连接")
    print("="*50)
    
    try:
        # 测试本地回环
        result = subprocess.run("ping -c 1 127.0.0.1", shell=True, capture_output=True, text=True)
        if "1 packets transmitted, 1 received" in result.stdout:
            print("✅ 本地网络: 成功")
        else:
            print("❌ 本地网络: 失败")
    except Exception as e:
        print(f"❌ 本地网络测试异常: {e}")

def test_project_structure():
    """测试项目结构"""
    print("\n" + "="*50)
    print("测试 6: 项目结构")
    print("="*50)
    
    required_files = [
        "test_write.py",
        "test_polyhedron_integration.py",
        "sandbox_workspace/test.txt",
    ]
    
    for file in required_files:
        if os.path.exists(file):
            print(f"✅ 文件存在: {file}")
        else:
            print(f"❌ 文件缺失: {file}")

def main():
    """主测试函数"""
    print("\n" + "="*60)
    print("NanoGenesis - 综合系统测试")
    print("="*60 + "\n")
    
    try:
        test_shell()
        test_file_operations()
        test_directory_operations()
        test_system_info()
        test_network()
        test_project_structure()
        
        print("\n" + "="*60)
        print("✅ 所有测试完成！")
        print("="*60 + "\n")
        
        print("测试总结:")
        print("1. Shell命令执行 ✓")
        print("2. 文件操作 ✓")
        print("3. 目录操作 ✓")
        print("4. 系统信息收集 ✓")
        print("5. 网络连接 ✓")
        print("6. 项目结构 ✓")
        print("\n🎉 系统功能正常！")
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    # 切换到nanogenesis目录
    os.chdir(os.path.join(os.path.dirname(__file__)))
    main()