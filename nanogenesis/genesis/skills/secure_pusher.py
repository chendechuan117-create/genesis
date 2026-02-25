import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from genesis.core.base import Tool

import os
import json
import base64
import hashlib
import tarfile
import zipfile
import tempfile
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

class SecurePusher(Tool):
    @property
    def name(self) -> str:
        return "secure_pusher"
        
    @property
    def description(self) -> str:
        return "安全推送工具：加密、压缩和传输 nanogenesis 包到远程环境。支持多种传输协议和加密方法。"
        
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "source_path": {"type": "string", "description": "源文件或目录路径"},
                "target_type": {"type": "string", "enum": ["git", "scp", "docker", "free_platform", "local_backup"], "description": "目标类型"},
                "target_config": {"type": "object", "description": "目标配置（JSON格式）"},
                "encryption_key": {"type": "string", "description": "加密密钥（可选，自动生成）"},
                "compress_format": {"type": "string", "enum": ["tar.gz", "zip", "none"], "description": "压缩格式", "default": "tar.gz"},
                "include_state_snapshot": {"type": "boolean", "description": "是否包含状态快照", "default": True}
            },
            "required": ["source_path", "target_type"]
        }
        
    async def execute(self, source_path: str, target_type: str, target_config: Optional[Dict] = None, 
                     encryption_key: Optional[str] = None, compress_format: str = "tar.gz",
                     include_state_snapshot: bool = True) -> str:
        try:
            # 验证源路径
            source = Path(source_path)
            if not source.exists():
                return f"错误：源路径不存在: {source_path}"
            
            # 准备目标配置
            config = target_config or {}
            
            # 创建临时工作目录
            with tempfile.TemporaryDirectory(prefix="secure_pusher_") as temp_dir:
                temp_path = Path(temp_dir)
                
                # 步骤1：准备要传输的内容
                print("准备传输内容...")
                prepared_path = await self._prepare_content(source, temp_path, include_state_snapshot)
                
                # 步骤2：加密（如果提供了密钥）
                if encryption_key:
                    print("加密内容...")
                    encrypted_path = await self._encrypt_content(prepared_path, temp_path, encryption_key)
                    final_path = encrypted_path
                else:
                    final_path = prepared_path
                
                # 步骤3：压缩
                if compress_format != "none":
                    print(f"压缩内容 ({compress_format})...")
                    compressed_path = await self._compress_content(final_path, temp_path, compress_format)
                    transport_path = compressed_path
                else:
                    transport_path = final_path
                
                # 步骤4：传输到目标
                print(f"传输到 {target_type}...")
                result = await self._transfer_to_target(transport_path, target_type, config)
                
                # 步骤5：生成报告
                report = await self._generate_report(source_path, target_type, transport_path, result)
                
                return report
                
        except Exception as e:
            return f"安全推送失败: {str(e)}"
    
    async def _prepare_content(self, source: Path, temp_dir: Path, include_state_snapshot: bool) -> Path:
        """准备要传输的内容"""
        content_dir = temp_dir / "content"
        content_dir.mkdir(exist_ok=True)
        
        # 复制源文件/目录
        if source.is_file():
            shutil.copy2(source, content_dir / source.name)
        else:
            # 复制整个目录，排除不必要的文件
            for item in source.rglob("*"):
                if item.is_file():
                    # 排除一些不必要的文件
                    exclude_patterns = [".git", "__pycache__", ".pytest_cache", "venv", ".venv"]
                    if any(pattern in str(item) for pattern in exclude_patterns):
                        continue
                    
                    rel_path = item.relative_to(source)
                    target_path = content_dir / rel_path
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(item, target_path)
        
        # 如果包含状态快照，尝试捕获当前状态
        if include_state_snapshot:
            snapshot_dir = content_dir / "state_snapshots"
            snapshot_dir.mkdir(exist_ok=True)
            
            try:
                # 尝试使用现有的状态快照工具
                from genesis_state_snapshot_fixed import genesis_state_snapshot_fixed
                snapshot_result = genesis_state_snapshot_fixed(
                    snapshot_name="transfer_snapshot",
                    include_memory_dump=True,
                    compression_level="gzip"
                )
                
                # 查找最新的快照文件
                snapshots_dir = Path("state_snapshots")
                if snapshots_dir.exists():
                    latest_snapshot = max(snapshots_dir.glob("*.json"), key=lambda x: x.stat().st_mtime, default=None)
                    if latest_snapshot:
                        shutil.copy2(latest_snapshot, snapshot_dir / latest_snapshot.name)
            except:
                # 如果无法捕获快照，创建基本信息文件
                info_file = snapshot_dir / "system_info.json"
                info = {
                    "timestamp": datetime.now().isoformat(),
                    "source": str(source),
                    "system": os.uname()._asdict() if hasattr(os, "uname") else {},
                    "python_version": sys.version,
                    "note": "完整状态快照不可用，仅包含系统信息"
                }
                info_file.write_text(json.dumps(info, indent=2))
        
        # 创建清单文件
        manifest = {
            "transfer_timestamp": datetime.now().isoformat(),
            "source_path": str(source),
            "content_type": "directory" if source.is_dir() else "file",
            "include_state_snapshot": include_state_snapshot,
            "files": [str(p.relative_to(content_dir)) for p in content_dir.rglob("*") if p.is_file()],
            "total_files": sum(1 for _ in content_dir.rglob("*") if _.is_file())
        }
        
        manifest_file = content_dir / "transfer_manifest.json"
        manifest_file.write_text(json.dumps(manifest, indent=2))
        
        return content_dir
    
    async def _encrypt_content(self, content_dir: Path, temp_dir: Path, key: str) -> Path:
        """加密内容"""
        import shutil
        from datetime import datetime
        
        encrypted_dir = temp_dir / "encrypted"
        encrypted_dir.mkdir(exist_ok=True)
        
        # 创建加密包
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        encrypted_file = encrypted_dir / f"encrypted_package_{timestamp}.bin"
        
        # 首先创建tar包
        tar_path = temp_dir / "temp.tar"
        with tarfile.open(tar_path, "w") as tar:
            tar.add(content_dir, arcname="content")
        
        # 使用Fernet加密
        if len(key) < 32:
            # 如果密钥太短，使用PBKDF2派生密钥
            salt = b"nanogenesis_salt"
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=salt,
                iterations=100000,
            )
            key_bytes = base64.urlsafe_b64encode(kdf.derive(key.encode()))
        else:
            key_bytes = base64.urlsafe_b64encode(key[:32].encode().ljust(32, b'0'))
        
        fernet = Fernet(key_bytes)
        
        # 读取tar文件并加密
        with open(tar_path, "rb") as f:
            data = f.read()
        
        encrypted_data = fernet.encrypt(data)
        
        # 写入加密文件
        with open(encrypted_file, "wb") as f:
            # 写入加密元数据
            metadata = {
                "encryption_method": "Fernet",
                "timestamp": timestamp,
                "original_size": len(data),
                "encrypted_size": len(encrypted_data),
                "key_hash": hashlib.sha256(key_bytes).hexdigest()[:16]
            }
            metadata_json = json.dumps(metadata).encode()
            f.write(len(metadata_json).to_bytes(4, 'big'))
            f.write(metadata_json)
            f.write(encrypted_data)
        
        # 清理临时文件
        tar_path.unlink(missing_ok=True)
        
        return encrypted_file
    
    async def _compress_content(self, content_path: Path, temp_dir: Path, format: str) -> Path:
        """压缩内容"""
        import shutil
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        if format == "tar.gz":
            output_path = temp_dir / f"package_{timestamp}.tar.gz"
            with tarfile.open(output_path, "w:gz") as tar:
                if content_path.is_file():
                    tar.add(content_path, arcname=content_path.name)
                else:
                    tar.add(content_path, arcname="package")
        
        elif format == "zip":
            output_path = temp_dir / f"package_{timestamp}.zip"
            with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zipf:
                if content_path.is_file():
                    zipf.write(content_path, arcname=content_path.name)
                else:
                    for file_path in content_path.rglob("*"):
                        if file_path.is_file():
                            rel_path = file_path.relative_to(content_path)
                            zipf.write(file_path, arcname=f"package/{rel_path}")
        
        else:
            output_path = content_path
        
        return output_path
    
    async def _transfer_to_target(self, transport_path: Path, target_type: str, config: Dict) -> Dict:
        """传输到目标"""
        import shutil
        from datetime import datetime
        
        result = {
            "target_type": target_type,
            "timestamp": datetime.now().isoformat(),
            "source_path": str(transport_path),
            "source_size": transport_path.stat().st_size,
            "success": False,
            "details": {}
        }
        
        try:
            if target_type == "local_backup":
                # 本地备份
                backup_dir = Path(config.get("backup_dir", "backups"))
                backup_dir.mkdir(parents=True, exist_ok=True)
                
                backup_path = backup_dir / transport_path.name
                shutil.copy2(transport_path, backup_path)
                
                result["success"] = True
                result["details"] = {
                    "backup_path": str(backup_path),
                    "backup_size": backup_path.stat().st_size
                }
            
            elif target_type == "git":
                # Git推送
                repo_path = Path(config.get("repo_path", "."))
                remote_url = config.get("remote_url")
                branch = config.get("branch", "main")
                
                if not remote_url:
                    result["details"]["error"] = "需要提供 remote_url"
                    return result
                
                # 复制文件到仓库
                if repo_path.exists():
                    # 清空仓库（保留.git）
                    for item in repo_path.iterdir():
                        if item.name != ".git":
                            if item.is_file():
                                item.unlink()
                            else:
                                shutil.rmtree(item)
                
                # 解压并复制内容
                if transport_path.suffix in [".gz", ".tar.gz"]:
                    with tarfile.open(transport_path, "r:gz") as tar:
                        tar.extractall(repo_path)
                elif transport_path.suffix == ".zip":
                    with zipfile.ZipFile(transport_path, "r") as zipf:
                        zipf.extractall(repo_path)
                else:
                    shutil.copy2(transport_path, repo_path / transport_path.name)
                
                # 执行git命令
                cmds = [
                    ["git", "add", "."],
                    ["git", "commit", "-m", f"nanogenesis transfer {datetime.now().strftime('%Y%m%d_%H%M%S')}"],
                    ["git", "push", remote_url, branch]
                ]
                
                for cmd in cmds:
                    subprocess.run(cmd, cwd=repo_path, capture_output=True, text=True)
                
                result["success"] = True
                result["details"] = {
                    "repo_path": str(repo_path),
                    "remote_url": remote_url,
                    "branch": branch
                }
            
            elif target_type == "scp":
                # SCP传输
                host = config.get("host")
                username = config.get("username")
                remote_path = config.get("remote_path", ".")
                port = config.get("port", 22)
                
                if not host:
                    result["details"]["error"] = "需要提供 host"
                    return result
                
                # 构建SCP命令
                if username:
                    target = f"{username}@{host}:{remote_path}"
                else:
                    target = f"{host}:{remote_path}"
                
                cmd = ["scp", "-P", str(port), str(transport_path), target]
                
                process = subprocess.run(cmd, capture_output=True, text=True)
                
                result["success"] = process.returncode == 0
                result["details"] = {
                    "command": " ".join(cmd),
                    "returncode": process.returncode,
                    "stdout": process.stdout,
                    "stderr": process.stderr
                }
            
            elif target_type == "free_platform":
                # 免费平台部署
                platform = config.get("platform", "zeabur")
                
                # 这里可以集成现有的部署脚本
                deploy_script = Path("deployment_scripts") / f"deploy_{platform}.sh"
                
                if deploy_script.exists():
                    # 复制包到部署目录
                    deploy_dir = Path("deployments") / platform
                    deploy_dir.mkdir(parents=True, exist_ok=True)
                    
                    deploy_path = deploy_dir / transport_path.name
                    shutil.copy2(transport_path, deploy_path)
                    
                    # 执行部署脚本
                    cmd = ["bash", str(deploy_script)]
                    process = subprocess.run(cmd, capture_output=True, text=True)
                    
                    result["success"] = process.returncode == 0
                    result["details"] = {
                        "platform": platform,
                        "deploy_path": str(deploy_path),
                        "returncode": process.returncode,
                        "stdout": process.stdout[:500],  # 限制输出长度
                        "stderr": process.stderr[:500]
                    }
                else:
                    result["details"]["error"] = f"部署脚本不存在: {deploy_script}"
            
            else:
                result["details"]["error"] = f"不支持的目标类型: {target_type}"
        
        except Exception as e:
            result["details"]["error"] = str(e)
        
        return result
    
    async def _generate_report(self, source_path: str, target_type: str, transport_path: Path, result: Dict) -> str:
        """生成报告"""
        import shutil
        from datetime import datetime
        
        report_lines = [
            "=" * 60,
            "安全推送报告",
            "=" * 60,
            f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"源路径: {source_path}",
            f"目标类型: {target_type}",
            f"传输文件: {transport_path.name}",
            f"文件大小: {transport_path.stat().st_size / 1024 / 1024:.2f} MB",
            "",
            "传输结果:"
        ]
        
        if result.get("success"):
            report_lines.append("✅ 传输成功!")
            report_lines.append("")
            report_lines.append("详细信息:")
            for key, value in result.get("details", {}).items():
                report_lines.append(f"  {key}: {value}")
        else:
            report_lines.append("❌ 传输失败!")
            report_lines.append("")
            report_lines.append("错误信息:")
            report_lines.append(f"  {result.get('details', {}).get('error', '未知错误')}")
        
        report_lines.extend([
            "",
            "=" * 60,
            "下一步建议:",
            "1. 验证目标环境中的文件完整性",
            "2. 测试系统在目标环境中的运行",
            "3. 更新部署文档",
            "=" * 60
        ])
        
        return "\n".join(report_lines)