import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from genesis.core.base import Tool

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

class ProjectPhoenixProtocol:
    name = "project_phoenix_protocol"
    description = "执行 Project Phoenix 协议（轻量级模式）：验证结构、创建日志、克隆系统、验证备份"
    parameters = {
        "backup_path": {
            "type": "string",
            "description": "备份目录路径",
            "default": "/home/chendechusn/Genesis_Phoenix_Backup"
        },
        "genesis_root": {
            "type": "string", 
            "description": "Genesis 系统根目录",
            "default": "/home/chendechusn/Genesis"
        }
    }
    
    def execute(self, backup_path, genesis_root):
        results = {
            "steps": {},
            "success": True,
            "errors": []
        }
        
        # 步骤 1: 验证 nanogenesis/genesis/core 结构
        print("步骤 1: 验证 nanogenesis/genesis/core 目录结构...")
        core_path = os.path.join(genesis_root, "nanogenesis", "genesis", "core")
        
        if os.path.exists(core_path):
            try:
                items = os.listdir(core_path)
                results["steps"]["structure_verification"] = {
                    "status": "success",
                    "path": core_path,
                    "items_count": len(items),
                    "items": items[:10]  # 只显示前10个
                }
                print(f"✓ 目录结构验证成功: {core_path}")
                print(f"  包含 {len(items)} 个项目")
                for item in items[:5]:
                    print(f"    - {item}")
                if len(items) > 5:
                    print(f"    ... 还有 {len(items)-5} 个项目")
            except Exception as e:
                results["steps"]["structure_verification"] = {
                    "status": "failed",
                    "error": str(e)
                }
                results["errors"].append(f"结构验证失败: {e}")
                results["success"] = False
                print(f"✗ 结构验证失败: {e}")
        else:
            results["steps"]["structure_verification"] = {
                "status": "failed",
                "error": f"路径不存在: {core_path}"
            }
            results["errors"].append(f"核心目录不存在: {core_path}")
            results["success"] = False
            print(f"✗ 核心目录不存在: {core_path}")
        
        # 步骤 2: 创建 stress_test_log.txt 带时间戳
        print("\n步骤 2: 创建 stress_test_log.txt...")
        log_path = os.path.join(genesis_root, "stress_test_log.txt")
        try:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with open(log_path, 'w') as f:
                f.write(f"Project Phoenix 压力测试日志\n")
                f.write(f"生成时间: {timestamp}\n")
                f.write(f"系统: {sys.platform}\n")
                f.write(f"Python版本: {sys.version}\n")
            
            results["steps"]["log_creation"] = {
                "status": "success",
                "path": log_path,
                "timestamp": timestamp,
                "size": os.path.getsize(log_path)
            }
            print(f"✓ 日志文件创建成功: {log_path}")
            print(f"  时间戳: {timestamp}")
        except Exception as e:
            results["steps"]["log_creation"] = {
                "status": "failed",
                "error": str(e)
            }
            results["errors"].append(f"日志创建失败: {e}")
            results["success"] = False
            print(f"✗ 日志创建失败: {e}")
        
        # 步骤 3: 执行复制/克隆操作
        print("\n步骤 3: 克隆 Genesis 系统...")
        try:
            # 首先检查 replication_tool 是否存在
            replication_tool_path = os.path.join(genesis_root, "replication_tool")
            script_tool_path = os.path.join(genesis_root, "scripts", "replication_tool.py")
            
            if os.path.exists(replication_tool_path) or os.path.exists(script_tool_path):
                # 如果 replication_tool 存在，使用它
                print("检测到 replication_tool，尝试使用...")
                if os.path.exists(replication_tool_path):
                    cmd = [replication_tool_path, genesis_root, backup_path]
                else:
                    cmd = ["python", script_tool_path, genesis_root, backup_path]
                
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
                
                results["steps"]["replication"] = {
                    "status": "success" if result.returncode == 0 else "failed",
                    "tool_used": "replication_tool",
                    "returncode": result.returncode,
                    "stdout": result.stdout[:500] if result.stdout else "",
                    "stderr": result.stderr[:500] if result.stderr else ""
                }
                
                if result.returncode == 0:
                    print(f"✓ replication_tool 执行成功")
                else:
                    print(f"✗ replication_tool 执行失败 (返回码: {result.returncode})")
                    print(f"  错误: {result.stderr[:200]}")
                    results["errors"].append(f"replication_tool 失败: {result.stderr[:200]}")
                    results["success"] = False
            else:
                # 如果没有 replication_tool，使用 rsync 或 cp 创建备份
                print("未找到 replication_tool，使用 rsync 创建备份...")
                
                # 确保备份目录存在
                os.makedirs(backup_path, exist_ok=True)
                
                # 使用 rsync（如果可用）
                rsync_result = subprocess.run(
                    ["which", "rsync"], 
                    capture_output=True, 
                    text=True
                )
                
                if rsync_result.returncode == 0:
                    # 使用 rsync
                    cmd = [
                        "rsync", "-av", "--progress",
                        f"{genesis_root}/",
                        f"{backup_path}/"
                    ]
                    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
                else:
                    # 使用 cp
                    cmd = ["cp", "-r", genesis_root, backup_path]
                    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
                
                results["steps"]["replication"] = {
                    "status": "success" if result.returncode == 0 else "failed",
                    "tool_used": "rsync" if rsync_result.returncode == 0 else "cp",
                    "returncode": result.returncode,
                    "method": "fallback_copy"
                }
                
                if result.returncode == 0:
                    print(f"✓ 系统克隆成功: {genesis_root} -> {backup_path}")
                else:
                    print(f"✗ 系统克隆失败: {result.stderr[:200]}")
                    results["errors"].append(f"克隆失败: {result.stderr[:200]}")
                    results["success"] = False
                    
        except subprocess.TimeoutExpired:
            results["steps"]["replication"] = {
                "status": "timeout",
                "error": "克隆操作超时"
            }
            results["errors"].append("克隆操作超时")
            results["success"] = False
            print("✗ 克隆操作超时")
        except Exception as e:
            results["steps"]["replication"] = {
                "status": "failed",
                "error": str(e)
            }
            results["errors"].append(f"克隆异常: {e}")
            results["success"] = False
            print(f"✗ 克隆异常: {e}")
        
        # 步骤 4: 验证备份
        print("\n步骤 4: 验证备份...")
        try:
            if os.path.exists(backup_path):
                backup_items = os.listdir(backup_path)
                results["steps"]["backup_verification"] = {
                    "status": "success",
                    "path": backup_path,
                    "exists": True,
                    "items_count": len(backup_items),
                    "items": backup_items[:10]
                }
                print(f"✓ 备份验证成功: {backup_path}")
                print(f"  包含 {len(backup_items)} 个项目")
                
                # 检查关键文件是否存在
                critical_files = ["nanogenesis", "scripts", "README.md", "ARCHITECTURE.md"]
                for file in critical_files:
                    check_path = os.path.join(backup_path, file)
                    if os.path.exists(check_path):
                        print(f"  ✓ {file}")
                    else:
                        print(f"  ✗ {file} (缺失)")
            else:
                results["steps"]["backup_verification"] = {
                    "status": "failed",
                    "exists": False
                }
                results["errors"].append("备份目录不存在")
                results["success"] = False
                print("✗ 备份目录不存在")
        except Exception as e:
            results["steps"]["backup_verification"] = {
                "status": "failed",
                "error": str(e)
            }
            results["errors"].append(f"备份验证失败: {e}")
            results["success"] = False
            print(f"✗ 备份验证失败: {e}")
        
        # 生成最终报告
        print("\n" + "="*50)
        print("Project Phoenix 协议执行报告")
        print("="*50)
        
        success_count = sum(1 for step in results["steps"].values() if step.get("status") == "success")
        total_steps = len(results["steps"])
        
        print(f"完成步骤: {success_count}/{total_steps}")
        print(f"总体状态: {'成功' if results['success'] else '失败'}")
        
        if results["errors"]:
            print("\n错误列表:")
            for i, error in enumerate(results["errors"], 1):
                print(f"  {i}. {error}")
        
        return results