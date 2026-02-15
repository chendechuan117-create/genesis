
import subprocess
import logging
import time
from pathlib import Path
from typing import Tuple, Optional

logger = logging.getLogger(__name__)

class SandboxManager:
    """
    Docker 沙箱管理器
    负责管理 NanoGenesis 的隔离执行环境
    """
    
    def __init__(self, workspace_path: str):
        self.image_name = "nanogenesis-sandbox"
        self.container_name = "nanogenesis-runner"
        self.workspace_path = Path(workspace_path).resolve()
        self.dockerfile_path = Path(__file__).parent.parent / "sandbox"
    
    def _run_docker_cmd(self, args: list) -> Tuple[int, str, str]:
        """执行 Docker 命令"""
        try:
            result = subprocess.run(
                ["docker"] + args,
                capture_output=True,
                text=True,
                check=False
            )
            return result.returncode, result.stdout, result.stderr
        except Exception as e:
            return -1, "", str(e)

    def is_docker_available(self) -> bool:
        """检查 Docker 是否可用"""
        code, _, _ = self._run_docker_cmd(["--version"])
        return code == 0

    def ensure_image(self) -> bool:
        """确保沙箱镜像存在，不存在则构建"""
        # 检查镜像是否存在
        code, stdout, _ = self._run_docker_cmd(["image", "inspect", self.image_name])
        if code == 0:
            return True
            
        logger.info(f"正在构建沙箱镜像 {self.image_name}...")
        if not self.dockerfile_path.exists():
            logger.error(f"Dockerfile 目录不存在: {self.dockerfile_path}")
            return False
            
        code, stdout, stderr = self._run_docker_cmd([
            "build", 
            "-t", self.image_name, 
            str(self.dockerfile_path)
        ])
        
        if code != 0:
            logger.error(f"构建镜像失败: {stderr}")
            return False
            
        logger.info("沙箱镜像构建成功")
        return True

    def start_container(self) -> bool:
        """启动沙箱容器"""
        # 检查容器是否已经在运行
        code, stdout, _ = self._run_docker_cmd([
            "inspect", 
            "--format", "{{.State.Running}}", 
            self.container_name
        ])
        
        if code == 0 and stdout.strip() == "true":
            return True
            
        # 如果容器存在但未运行，或者状态异常，先删除
        self._run_docker_cmd(["rm", "-f", self.container_name])
        
        logger.info(f"启动沙箱容器 {self.container_name}...")
        
        # 挂载工作目录
        # 注意: 需要确保宿主机路径存在
        self.workspace_path.mkdir(parents=True, exist_ok=True)
        
        code, stdout, stderr = self._run_docker_cmd([
            "run", 
            "-d", 
            "--name", self.container_name,
            "-v", f"{self.workspace_path}:/workspace",
            "--workdir", "/workspace",
            self.image_name
        ])
        
        if code != 0:
            logger.error(f"启动容器失败: {stderr}")
            return False
            
        return True

    def exec_command(self, cmd: str, timeout: int = 60) -> Tuple[int, str, str]:
        """在沙箱中执行命令"""
        if not self.start_container():
            return -1, "", "Failed to start sandbox container"
            
        logger.debug(f"沙箱执行: {cmd}")
        
        # 使用 exec 执行
        # 注意: 复杂的 shell 命令可能需要用 bash -c 包裹
        try:
            result = subprocess.run(
                ["docker", "exec", self.container_name, "bash", "-c", cmd],
                capture_output=True,
                text=True,
                timeout=timeout
            )
            return result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            return -1, "", "Command timed out"
        except Exception as e:
            return -1, "", str(e)

    def stop_container(self):
        """停止并清理容器"""
        self._run_docker_cmd(["rm", "-f", self.container_name])

    def get_status(self) -> dict:
        """获取沙箱状态"""
        return {
            "image": self.ensure_image(),
            "container_running": self.start_container()
        }
