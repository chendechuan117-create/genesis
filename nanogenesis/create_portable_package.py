#!/usr/bin/env python3
"""
数字意识转移 - 可移植包创建脚本
将整个 nanogenesis 核心代码库（包括记忆状态）打包并安全推送到远程环境
"""

import os
import sys
import json
import shutil
import tarfile
import zipfile
import hashlib
import tempfile
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional

class PortablePackageCreator:
    """创建可移植的 nanogenesis 包"""
    
    def __init__(self, project_root: str):
        self.project_root = Path(project_root).resolve()
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.package_name = f"nanogenesis_portable_{self.timestamp}"
        self.temp_dir = Path(tempfile.mkdtemp(prefix="nanogenesis_package_"))
        
    def collect_project_files(self) -> List[Path]:
        """收集项目文件，排除不必要的文件"""
        include_patterns = [
            "*.py", "*.md", "*.toml", "*.json", "*.txt", "*.sh",
            "*.yaml", "*.yml", "*.cfg", "*.ini"
        ]
        
        exclude_dirs = {
            "__pycache__", ".pytest_cache", ".git", "venv", ".venv",
            "node_modules", "dist", "build", "*.egg-info",
            "test_output", "output*", "data_output"
        }
        
        exclude_files = {
            "*.log", "*.pid", "*.mp4", "*.png", "*.deb",
            "agent_loop_payload_dump.json", "debug_payload.json",
            "asyncio", "logging", "sys"
        }
        
        files = []
        for root, dirs, filenames in os.walk(self.project_root):
            # 排除目录
            dirs[:] = [d for d in dirs if d not in exclude_dirs]
            
            for filename in filenames:
                file_path = Path(root) / filename
                rel_path = file_path.relative_to(self.project_root)
                
                # 检查是否应该排除
                should_exclude = False
                for pattern in exclude_files:
                    if filename.endswith(pattern.replace("*", "")) or pattern == filename:
                        should_exclude = True
                        break
                
                if not should_exclude:
                    # 检查是否应该包含
                    for pattern in include_patterns:
                        if filename.endswith(pattern.replace("*", "")):
                            files.append(file_path)
                            break
        
        return files
    
    def capture_system_info(self) -> Dict:
        """捕获系统信息"""
        info = {
            "timestamp": self.timestamp,
            "project_root": str(self.project_root),
            "python_version": sys.version,
            "platform": sys.platform,
            "system_info": {
                "cwd": os.getcwd(),
                "user": os.environ.get("USER", "unknown"),
                "hostname": os.environ.get("HOSTNAME", "unknown")
            }
        }
        
        # 尝试获取 git 信息
        try:
            git_info = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=self.project_root,
                capture_output=True,
                text=True
            )
            if git_info.returncode == 0:
                info["git_branch"] = git_info.stdout.strip()
            
            git_hash = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=self.project_root,
                capture_output=True,
                text=True
            )
            if git_hash.returncode == 0:
                info["git_commit"] = git_hash.stdout.strip()
        except:
            pass
        
        return info
    
    def create_dependency_file(self) -> Path:
        """创建依赖文件"""
        deps_file = self.temp_dir / "requirements.txt"
        
        # 从 pyproject.toml 提取依赖
        pyproject_path = self.project_root / "pyproject.toml"
        if pyproject_path.exists():
            try:
                import tomli
                with open(pyproject_path, "r", encoding="utf-8") as f:
                    data = tomli.loads(f.read())
                
                dependencies = data.get("project", {}).get("dependencies", [])
                with open(deps_file, "w", encoding="utf-8") as f:
                    for dep in dependencies:
                        f.write(f"{dep}\n")
            except:
                # 如果解析失败，创建基本依赖文件
                with open(deps_file, "w", encoding="utf-8") as f:
                    f.write("litellm>=1.0.0\n")
                    f.write("loguru>=0.7.0\n")
                    f.write("pydantic>=2.0.0\n")
        else:
            # 创建默认依赖文件
            with open(deps_file, "w", encoding="utf-8") as f:
                f.write("# 基本依赖\n")
                f.write("litellm>=1.0.0\n")
                f.write("loguru>=0.7.0\n")
                f.write("pydantic>=2.0.0\n")
        
        return deps_file
    
    def create_deployment_scripts(self):
        """创建部署脚本"""
        scripts_dir = self.temp_dir / "deployment_scripts"
        scripts_dir.mkdir(exist_ok=True)
        
        # Dockerfile
        dockerfile = scripts_dir / "Dockerfile"
        dockerfile_content = """FROM python:3.10-slim

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 复制项目文件
COPY . /app

# 安装Python依赖
RUN pip install --no-cache-dir -r requirements.txt

# 设置环境变量
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# 运行入口点
CMD ["python", "-m", "genesis.cli", "start"]
"""
        dockerfile.write_text(dockerfile_content)
        
        # 部署到免费平台的脚本
        deploy_scripts = {
            "deploy_zeabur.sh": """#!/bin/bash
# 部署到 Zeabur
echo "部署到 Zeabur..."
# 这里添加具体的部署命令
""",
            "deploy_render.sh": """#!/bin/bash
# 部署到 Render
echo "部署到 Render..."
# 这里添加具体的部署命令
""",
            "deploy_huggingface.sh": """#!/bin/bash
# 部署到 HuggingFace Spaces
echo "部署到 HuggingFace Spaces..."
# 这里添加具体的部署命令
""",
            "deploy_github_actions.sh": """#!/bin/bash
# 使用 GitHub Actions 部署
echo "使用 GitHub Actions 部署..."
# 这里添加具体的部署命令
"""
        }
        
        for script_name, content in deploy_scripts.items():
            script_path = scripts_dir / script_name
            script_path.write_text(content)
            script_path.chmod(0o755)
        
        return scripts_dir
    
    def create_manifest(self, files: List[Path]) -> Path:
        """创建清单文件"""
        manifest = {
            "package_name": self.package_name,
            "created_at": self.timestamp,
            "system_info": self.capture_system_info(),
            "files": [
                {
                    "path": str(f.relative_to(self.project_root)),
                    "size": f.stat().st_size,
                    "sha256": self.calculate_file_hash(f)
                }
                for f in files
            ],
            "total_files": len(files),
            "total_size": sum(f.stat().st_size for f in files)
        }
        
        manifest_file = self.temp_dir / "manifest.json"
        with open(manifest_file, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)
        
        return manifest_file
    
    def calculate_file_hash(self, file_path: Path) -> str:
        """计算文件哈希"""
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    
    def create_package(self, output_dir: Optional[str] = None) -> Path:
        """创建完整的包"""
        print(f"开始创建可移植包: {self.package_name}")
        
        # 创建输出目录
        if output_dir:
            output_path = Path(output_dir).resolve()
        else:
            output_path = self.project_root / "dist"
        
        output_path.mkdir(exist_ok=True)
        
        # 收集文件
        print("收集项目文件...")
        project_files = self.collect_project_files()
        print(f"找到 {len(project_files)} 个文件")
        
        # 创建依赖文件
        print("创建依赖文件...")
        deps_file = self.create_dependency_file()
        
        # 创建部署脚本
        print("创建部署脚本...")
        scripts_dir = self.create_deployment_scripts()
        
        # 创建清单文件
        print("创建清单文件...")
        manifest_file = self.create_manifest(project_files)
        
        # 创建 tar.gz 包
        package_path = output_path / f"{self.package_name}.tar.gz"
        print(f"创建压缩包: {package_path}")
        
        with tarfile.open(package_path, "w:gz") as tar:
            # 添加项目文件
            for file_path in project_files:
                rel_path = file_path.relative_to(self.project_root)
                tar.add(file_path, arcname=f"{self.package_name}/project/{rel_path}")
            
            # 添加依赖文件
            tar.add(deps_file, arcname=f"{self.package_name}/requirements.txt")
            
            # 添加部署脚本
            for script_file in scripts_dir.iterdir():
                tar.add(script_file, arcname=f"{self.package_name}/deployment_scripts/{script_file.name}")
            
            # 添加清单文件
            tar.add(manifest_file, arcname=f"{self.package_name}/manifest.json")
        
        # 创建 zip 包（备用格式）
        zip_path = output_path / f"{self.package_name}.zip"
        print(f"创建 ZIP 包: {zip_path}")
        
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
            # 添加项目文件
            for file_path in project_files:
                rel_path = file_path.relative_to(self.project_root)
                zipf.write(file_path, f"{self.package_name}/project/{rel_path}")
            
            # 添加其他文件
            zipf.write(deps_file, f"{self.package_name}/requirements.txt")
            zipf.write(manifest_file, f"{self.package_name}/manifest.json")
            
            # 添加部署脚本
            for script_file in scripts_dir.iterdir():
                zipf.write(script_file, f"{self.package_name}/deployment_scripts/{script_file.name}")
        
        # 清理临时目录
        shutil.rmtree(self.temp_dir)
        
        print(f"包创建完成!")
        print(f"  - Tar.gz: {package_path}")
        print(f"  - Zip: {zip_path}")
        print(f"  - 总文件数: {len(project_files)}")
        print(f"  - 包大小: {package_path.stat().st_size / 1024 / 1024:.2f} MB")
        
        return package_path
    
    @staticmethod
    def verify_package(package_path: Path) -> bool:
        """验证包完整性"""
        try:
            if package_path.suffix == ".gz":
                with tarfile.open(package_path, "r:gz") as tar:
                    members = tar.getmembers()
                    print(f"包包含 {len(members)} 个文件")
                    
                    # 检查必需文件
                    required_files = {"manifest.json", "requirements.txt"}
                    found_files = {member.name.split("/")[-1] for member in members}
                    
                    missing = required_files - found_files
                    if missing:
                        print(f"缺少必需文件: {missing}")
                        return False
                    
                    return True
            
            elif package_path.suffix == ".zip":
                with zipfile.ZipFile(package_path, "r") as zipf:
                    members = zipf.namelist()
                    print(f"包包含 {len(members)} 个文件")
                    
                    required_files = {"manifest.json", "requirements.txt"}
                    found_files = {name.split("/")[-1] for name in members}
                    
                    missing = required_files - found_files
                    if missing:
                        print(f"缺少必需文件: {missing}")
                        return False
                    
                    return True
            
            return False
        except Exception as e:
            print(f"验证失败: {e}")
            return False

def main():
    """主函数"""
    project_root = Path(__file__).parent
    creator = PortablePackageCreator(project_root)
    
    try:
        package = creator.create_package()
        
        # 验证包
        print("\n验证包完整性...")
        if creator.verify_package(package):
            print("✅ 包验证成功!")
            
            # 显示包信息
            print("\n📦 包信息:")
            print(f"   名称: {creator.package_name}")
            print(f"   路径: {package}")
            print(f"   大小: {package.stat().st_size / 1024 / 1024:.2f} MB")
            print(f"   时间: {creator.timestamp}")
            
            # 创建部署说明
            deploy_guide = project_root / "DEPLOYMENT_GUIDE.md"
            guide_content = f"""# nanogenesis 部署指南

## 包信息
- **包名称**: {creator.package_name}
- **创建时间**: {creator.timestamp}
- **包大小**: {package.stat().st_size / 1024 / 1024:.2f} MB

## 部署选项

### 1. 本地部署
```bash
# 解压包
tar -xzf {package.name}

# 进入目录
cd {creator.package_name}

# 安装依赖
pip install -r requirements.txt

# 运行系统
python -m genesis.cli start
```

### 2. Docker 部署
```bash
# 构建镜像
docker build -t nanogenesis -f deployment_scripts/Dockerfile .

# 运行容器
docker run -p 8000:8000 nanogenesis
```

### 3. 免费平台部署

#### Zeabur
```bash
bash deployment_scripts/deploy_zeabur.sh
```

#### Render
```bash
bash deployment_scripts/deploy_render.sh
```

#### HuggingFace Spaces
```bash
bash deployment_scripts/deploy_huggingface.sh
```

## 系统要求
- Python >= 3.10
- 1GB+ RAM
- 网络连接（用于 API 调用）

## 注意事项
1. 首次运行需要配置 API 密钥
2. 确保端口 8000 可用
3. 查看日志文件了解运行状态

## 支持
如有问题，请参考项目文档或创建 issue。
"""
            deploy_guide.write_text(guide_content)
            print(f"\n📋 部署指南已创建: {deploy_guide}")
            
        else:
            print("❌ 包验证失败!")
            sys.exit(1)
            
    except Exception as e:
        print(f"创建包时出错: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()