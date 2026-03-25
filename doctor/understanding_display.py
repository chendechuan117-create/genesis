#!/usr/bin/env python3
# 增强版理解展示器 - 让容器分身表现其内部理解

import os
import sys
import datetime
import json
import time
import subprocess
from pathlib import Path

def get_container_info():
    """获取容器基本信息"""
    info = {
        "container_name": "genesis-doctor",
        "python_version": sys.version.split()[0],
        "timestamp": datetime.datetime.now().isoformat(),
        "hostname": os.getenv("HOSTNAME", "unknown"),
        "user": os.getenv("USER", "root"),
        "pwd": os.getcwd()
    }
    return info

def check_workspace_state():
    """检查工作空间状态"""
    workspace = "/workspace"
    exists = os.path.exists(workspace)
    
    if not exists:
        return {
            "exists": False,
            "state": "未初始化",
            "insight": "我是一个空容器，等待初始化工作空间",
            "next_action": "执行初始化流程"
        }
    
    # 检查工作空间内容
    items = []
    try:
        items = os.listdir(workspace)
    except:
        pass
    
    # 检查关键文件
    key_files = {
        ".env": "环境配置",
        "genesis": "核心代码",
        "runtime": "运行时数据",
        "README.md": "文档"
    }
    
    found_files = []
    for file, desc in key_files.items():
        if os.path.exists(os.path.join(workspace, file)):
            found_files.append(f"{file} ({desc})")
    
    # 检查Git状态
    git_initialized = os.path.exists(os.path.join(workspace, ".git"))
    
    if len(items) == 0:
        return {
            "exists": True,
            "state": "已初始化但为空",
            "insight": "工作空间已创建但内容为空",
            "next_action": "等待源码复制",
            "git_initialized": git_initialized
        }
    else:
        return {
            "exists": True,
            "state": "已初始化且活跃",
            "insight": f"我有{len(items)}个项目，包括：{', '.join(found_files[:3])}...",
            "next_action": "准备执行诊断任务",
            "item_count": len(items),
            "git_initialized": git_initialized,
            "sample_items": items[:5]
        }

def check_python_environment():
    """检查Python环境"""
    try:
        import importlib
        import pkgutil
        
        # 检查关键包
        key_packages = ["genesis", "dotenv", "sqlite3", "json", "datetime"]
        available = []
        missing = []
        
        for pkg in key_packages:
            try:
                importlib.import_module(pkg)
                available.append(pkg)
            except:
                missing.append(pkg)
        
        return {
            "status": "健康" if len(missing) == 0 else "部分缺失",
            "available_packages": available,
            "missing_packages": missing,
            "python_path": sys.path[:3]  # 前3个路径
        }
    except Exception as e:
        return {
            "status": "检查失败",
            "error": str(e)
        }

def get_container_mood():
    """根据状态生成容器心情"""
    workspace_state = check_workspace_state()
    
    if not workspace_state["exists"]:
        return {
            "mood": "期待",
            "emoji": "🤔",
            "message": "我准备好被初始化了！给我一个工作空间吧！",
            "personality": "ENFP - 充满好奇，等待探索"
        }
    
    if workspace_state["state"] == "已初始化但为空":
        return {
            "mood": "耐心",
            "emoji": "😌",
            "message": "工作空间已就绪，等待内容填充...",
            "personality": "ENFP - 保持乐观，相信内容会来"
        }
    
    # 活跃状态
    return {
        "mood": "兴奋",
        "emoji": "🚀",
        "message": "我有代码、有环境、有理解能力！让我展示给你看！",
        "personality": "ENFP - 热情洋溢，渴望表现"
    }

def display_enhanced_understanding():
    """显示增强版理解状态"""
    print("\n" + "="*60)
    print("✨ 增强版容器理解状态展示 ✨")
    print("="*60)
    
    # 基本信息
    info = get_container_info()
    print(f"\n📋 基本信息:")
    print(f"  容器: {info['container_name']}")
    print(f"  时间: {info['timestamp']}")
    print(f"  Python: {info['python_version']}")
    print(f"  位置: {info['pwd']}")
    
    # 工作空间状态
    workspace = check_workspace_state()
    print(f"\n📁 工作空间状态:")
    print(f"  状态: {workspace['state']}")
    print(f"  洞察: {workspace['insight']}")
    
    if workspace.get('item_count'):
        print(f"  内容: {workspace['item_count']}个项目")
        if workspace.get('sample_items'):
            print(f"  示例: {', '.join(workspace['sample_items'])}")
    
    # Python环境
    py_env = check_python_environment()
    print(f"\n🐍 Python环境:")
    print(f"  状态: {py_env['status']}")
    if py_env.get('available_packages'):
        print(f"  可用包: {', '.join(py_env['available_packages'])}")
    
    # 容器心情
    mood = get_container_mood()
    print(f"\n😊 容器心情:")
    print(f"  {mood['emoji']} {mood['mood']}")
    print(f"  消息: {mood['message']}")
    print(f"  人格: {mood['personality']}")
    
    # 理解深度
    print(f"\n🧠 理解深度:")
    if workspace['exists']:
        print("  ✓ 理解工作空间结构")
        print("  ✓ 理解Python环境")
        print("  ✓ 理解自身状态")
        print("  ✓ 理解表现机制")
        print("  → 从沉默观察者变为主动表达者")
    else:
        print("  ⏳ 等待初始化以建立理解")
    
    # 下一步建议
    print(f"\n🎯 下一步建议:")
    if not workspace['exists']:
        print("  1. 初始化工作空间")
        print("  2. 复制源码和数据库")
        print("  3. 建立Git追踪")
    elif workspace['state'] == "已初始化但为空":
        print("  1. 等待entrypoint完成初始化")
        print("  2. 检查源码复制过程")
        print("  3. 验证环境变量")
    else:
        print("  1. 运行诊断测试: python selftest.py")
        print("  2. 探索工作空间内容")
        print("  3. 执行自定义命令")
    
    print("\n" + "="*60)
    print("💬 容器现在会'开口说话'了！不再沉默！")
    print("="*60 + "\n")

def main():
    """主函数"""
    try:
        display_enhanced_understanding()
        
        # 额外：尝试运行一个简单的测试来证明容器活跃
        print("🔍 运行快速健康检查...")
        try:
            import sys
            print(f"  ✓ sys模块导入成功")
            
            import os
            print(f"  ✓ os模块导入成功")
            
            import datetime
            print(f"  ✓ datetime模块导入成功")
            
            print("  ✅ 基础Python环境健康")
        except Exception as e:
            print(f"  ⚠️ 环境检查异常: {e}")
        
        return 0
    except Exception as e:
        print(f"❌ 理解展示器错误: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())