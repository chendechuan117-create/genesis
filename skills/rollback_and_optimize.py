import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from core.base import Tool

from typing import Dict, Any, Optional
import os
import subprocess
import shutil
from datetime import datetime

class RollbackAndOptimize:
    """回滚和优化工具，支持多种回滚方式和系统优化"""
    
    def __init__(self):
        self.name = "rollback_and_optimize"
        self.description = "执行系统回滚和优化操作"
        self.parameters = {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string", 
                    "enum": ["rollback", "optimize", "both"],
                    "description": "执行的操作：回滚、优化或两者都执行"
                },
                "target_path": {
                    "type": "string",
                    "description": "目标路径（对于回滚操作）"
                },
                "rollback_type": {
                    "type": "string",
                    "enum": ["git", "backup", "snapshot"],
                    "description": "回滚类型：git提交、备份文件、系统快照"
                },
                "rollback_target": {
                    "type": "string", 
                    "description": "回滚目标（git commit hash、备份文件名等）"
                },
                "optimization_level": {
                    "type": "string",
                    "enum": ["light", "medium", "aggressive"],
                    "description": "优化级别"
                }
            },
            "required": ["action"]
        }
    
    def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        action = params.get("action", "both")
        target_path = params.get("target_path", ".")
        rollback_type = params.get("rollback_type")
        rollback_target = params.get("rollback_target")
        optimization_level = params.get("optimization_level", "medium")
        
        results = []
        
        # 执行回滚
        if action in ["rollback", "both"]:
            rollback_result = self._perform_rollback(target_path, rollback_type, rollback_target)
            results.append(rollback_result)
        
        # 执行优化
        if action in ["optimize", "both"]:
            optimize_result = self._perform_optimization(optimization_level)
            results.append(optimize_result)
        
        return {
            "success": True,
            "results": results,
            "timestamp": datetime.now().isoformat()
        }
    
    def _perform_rollback(self, target_path: str, rollback_type: Optional[str], rollback_target: Optional[str]) -> Dict[str, Any]:
        """执行回滚操作"""
        
        # 如果未指定回滚类型，尝试自动检测
        if not rollback_type:
            rollback_type = self._detect_rollback_type(target_path)
        
        result = {
            "type": rollback_type,
            "target": rollback_target,
            "path": target_path,
            "success": False,
            "message": ""
        }
        
        try:
            os.chdir(target_path)
            
            if rollback_type == "git":
                # Git回滚
                if not rollback_target:
                    # 获取最近的提交
                    cmd = "git log --oneline -5"
                    output = subprocess.check_output(cmd, shell=True, text=True)
                    result["message"] = f"最近的提交：\n{output}"
                    result["success"] = True
                else:
                    # 回滚到指定提交
                    cmd = f"git reset --hard {rollback_target}"
                    subprocess.run(cmd, shell=True, check=True)
                    result["message"] = f"已回滚到提交：{rollback_target}"
                    result["success"] = True
            
            elif rollback_type == "backup":
                # 备份文件恢复
                if not rollback_target:
                    # 列出备份文件
                    backup_files = []
                    for root, dirs, files in os.walk("."):
                        for file in files:
                            if any(ext in file for ext in [".bak", ".backup", ".old", "~"]):
                                backup_files.append(os.path.join(root, file))
                    
                    if backup_files:
                        result["message"] = f"找到备份文件：\n" + "\n".join(backup_files[:10])
                        result["success"] = True
                    else:
                        result["message"] = "未找到备份文件"
                        result["success"] = False
                else:
                    # 恢复备份文件
                    if os.path.exists(rollback_target):
                        original_file = rollback_target.rstrip(".bak").rstrip(".backup").rstrip(".old").rstrip("~")
                        shutil.copy2(rollback_target, original_file)
                        result["message"] = f"已从备份恢复：{rollback_target} -> {original_file}"
                        result["success"] = True
                    else:
                        result["message"] = f"备份文件不存在：{rollback_target}"
                        result["success"] = False
            
            elif rollback_type == "snapshot":
                # 系统快照回滚（需要btrfs或zfs）
                result["message"] = "系统快照回滚需要特定的文件系统支持（如btrfs/zfs）"
                result["success"] = False
            
            else:
                result["message"] = f"不支持的回滚类型：{rollback_type}"
                result["success"] = False
                
        except Exception as e:
            result["message"] = f"回滚失败：{str(e)}"
            result["success"] = False
        
        return result
    
    def _detect_rollback_type(self, path: str) -> str:
        """检测可用的回滚类型"""
        try:
            os.chdir(path)
            
            # 检查是否是Git仓库
            if os.path.exists(".git"):
                return "git"
            
            # 检查是否有备份文件
            for root, dirs, files in os.walk("."):
                for file in files:
                    if any(ext in file for ext in [".bak", ".backup", ".old", "~"]):
                        return "backup"
            
            return "snapshot"
        except:
            return "snapshot"
    
    def _perform_optimization(self, level: str) -> Dict[str, Any]:
        """执行系统优化"""
        
        result = {
            "level": level,
            "success": True,
            "operations": [],
            "message": ""
        }
        
        try:
            operations = []
            
            if level == "light":
                # 轻度优化
                operations.append(self._clean_package_cache())
                operations.append(self._clean_temp_files())
                
            elif level == "medium":
                # 中度优化
                operations.append(self._clean_package_cache())
                operations.append(self._clean_temp_files())
                operations.append(self._clean_log_files())
                operations.append(self._optimize_memory())
                
            elif level == "aggressive":
                # 激进优化
                operations.append(self._clean_package_cache())
                operations.append(self._clean_temp_files())
                operations.append(self._clean_log_files())
                operations.append(self._optimize_memory())
                operations.append(self._optimize_swap())
                operations.append(self._clean_docker())
            
            result["operations"] = operations
            result["message"] = f"完成{level}级别优化，执行了{len(operations)}个操作"
            
        except Exception as e:
            result["success"] = False
            result["message"] = f"优化失败：{str(e)}"
        
        return result
    
    def _clean_package_cache(self) -> Dict[str, Any]:
        """清理包管理器缓存"""
        try:
            # Arch Linux (pacman)
            cmd = "sudo pacman -Sc --noconfirm 2>/dev/null || echo '需要sudo权限'"
            output = subprocess.check_output(cmd, shell=True, text=True)
            return {"operation": "clean_package_cache", "success": True, "output": output}
        except:
            return {"operation": "clean_package_cache", "success": False}
    
    def _clean_temp_files(self) -> Dict[str, Any]:
        """清理临时文件"""
        try:
            cmd = "find /tmp -type f -atime +1 -delete 2>/dev/null || true"
            subprocess.run(cmd, shell=True)
            return {"operation": "clean_temp_files", "success": True}
        except:
            return {"operation": "clean_temp_files", "success": False}
    
    def _clean_log_files(self) -> Dict[str, Any]:
        """清理日志文件"""
        try:
            cmd = "sudo journalctl --vacuum-time=3d 2>/dev/null || echo '需要sudo权限'"
            output = subprocess.check_output(cmd, shell=True, text=True)
            return {"operation": "clean_log_files", "success": True, "output": output}
        except:
            return {"operation": "clean_log_files", "success": False}
    
    def _optimize_memory(self) -> Dict[str, Any]:
        """优化内存使用"""
        try:
            # 清理页面缓存、目录项和inode
            cmd = "sudo sync && echo 3 | sudo tee /proc/sys/vm/drop_caches 2>/dev/null || echo '需要sudo权限'"
            output = subprocess.check_output(cmd, shell=True, text=True)
            return {"operation": "optimize_memory", "success": True, "output": output}
        except:
            return {"operation": "optimize_memory", "success": False}
    
    def _optimize_swap(self) -> Dict[str, Any]:
        """优化swap"""
        try:
            cmd = "sudo swapoff -a && sudo swapon -a 2>/dev/null || echo '需要sudo权限'"
            output = subprocess.check_output(cmd, shell=True, text=True)
            return {"operation": "optimize_swap", "success": True, "output": output}
        except:
            return {"operation": "optimize_swap", "success": False}
    
    def _clean_docker(self) -> Dict[str, Any]:
        """清理Docker（如果存在）"""
        try:
            cmd = "docker system prune -f 2>/dev/null || echo 'Docker未安装'"
            output = subprocess.check_output(cmd, shell=True, text=True)
            return {"operation": "clean_docker", "success": True, "output": output}
        except:
            return {"operation": "clean_docker", "success": False}