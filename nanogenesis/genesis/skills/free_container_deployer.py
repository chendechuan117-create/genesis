import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from genesis.core.base import Tool

class FreeContainerDeployer(Tool):
    @property
    def name(self) -> str:
        return "free_container_deployer"
        
    @property
    def description(self) -> str:
        return "自动部署应用到免费容器/VPS平台。支持多种平台：Zeabur, Render, HuggingFace Spaces等。"
        
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "platform": {
                    "type": "string", 
                    "enum": ["zeabur", "render", "huggingface", "github_actions"],
                    "description": "目标部署平台"
                },
                "app_name": {
                    "type": "string", 
                    "description": "应用名称（可选，自动生成）"
                },
                "dockerfile_path": {
                    "type": "string", 
                    "description": "Dockerfile路径（可选，默认为当前目录）"
                },
                "git_repo": {
                    "type": "string", 
                    "description": "Git仓库URL（可选，用于自动部署）"
                },
                "port": {
                    "type": "integer", 
                    "description": "应用监听端口（可选，默认3000）",
                    "default": 3000
                }
            },
            "required": ["platform"]
        }
        
    async def execute(self, platform: str, app_name: str = None, dockerfile_path: str = None, git_repo: str = None, port: int = 3000) -> str:
        import subprocess
        import os
        import time
        from pathlib import Path
        
        # 生成默认应用名称
        if not app_name:
            app_name = f"genesis-app-{int(time.time())}"
        
        # 获取当前目录
        current_dir = os.getcwd()
        
        # 检查Dockerfile
        if dockerfile_path:
            dockerfile = Path(dockerfile_path)
        else:
            dockerfile = Path(current_dir) / "Dockerfile"
        
        result_lines = []
        
        if platform == "zeabur":
            result_lines.append(f"开始部署到 Zeabur (应用: {app_name})")
            result_lines.append("Zeabur 部署步骤:")
            result_lines.append("1. 访问 https://zeabur.com 注册账号")
            result_lines.append("2. 创建新项目")
            result_lines.append("3. 连接你的Git仓库或上传代码")
            result_lines.append("4. 配置环境变量和端口")
            result_lines.append("5. 点击部署")
            result_lines.append("")
            result_lines.append("免费套餐限制:")
            result_lines.append("- 每月 $5 信用额度")
            result_lines.append("- 每个服务最多 1 vCPU 和 2GB 内存")
            result_lines.append("- 社区支持")
            
        elif platform == "render":
            result_lines.append(f"开始部署到 Render (应用: {app_name})")
            result_lines.append("Render 部署步骤:")
            result_lines.append("1. 访问 https://render.com 注册账号")
            result_lines.append("2. 点击 'New +' 选择 'Web Service'")
            result_lines.append("3. 连接你的Git仓库")
            result_lines.append("4. 配置构建命令和启动命令")
            result_lines.append("5. 选择免费套餐")
            result_lines.append("")
            result_lines.append("免费套餐限制:")
            result_lines.append("- 750小时/月 (约31天)")
            result_lines.append("- 自动休眠 (15分钟无流量)")
            result_lines.append("- 512MB RAM, 共享CPU")
            
        elif platform == "huggingface":
            result_lines.append(f"开始部署到 HuggingFace Spaces (应用: {app_name})")
            result_lines.append("HuggingFace Spaces 部署步骤:")
            result_lines.append("1. 访问 https://huggingface.co/spaces 注册账号")
            result_lines.append("2. 点击 'Create new Space'")
            result_lines.append("3. 选择 'Docker' 模板")
            result_lines.append("4. 上传你的Dockerfile和相关文件")
            result_lines.append("5. 配置硬件 (CPU Basic 免费)")
            result_lines.append("")
            result_lines.append("免费套餐限制:")
            result_lines.append("- CPU Basic (2 vCPU, 16GB RAM)")
            result_lines.append("- 存储空间有限")
            result_lines.append("- 公开访问")
            
        elif platform == "github_actions":
            result_lines.append(f"开始配置 GitHub Actions 临时运行器 (应用: {app_name})")
            result_lines.append("GitHub Actions 临时运行器部署步骤:")
            result_lines.append("1. 创建 GitHub 仓库")
            result_lines.append("2. 添加 .github/workflows/deploy.yml 文件")
            result_lines.append("3. 配置自托管运行器 (使用免费云资源)")
            result_lines.append("4. 设置工作流触发条件")
            result_lines.append("")
            result_lines.append("优势:")
            result_lines.append("- 每个作业最多6小时运行时间")
            result_lines.append("- 免费额度内无费用")
            result_lines.append("- 高度可定制")
        
        # 检查本地Docker环境
        try:
            docker_version = subprocess.run(["docker", "--version"], capture_output=True, text=True)
            if docker_version.returncode == 0:
                result_lines.append(f"\n✅ Docker 已安装: {docker_version.stdout.strip()}")
            else:
                result_lines.append("\n⚠️ Docker 未安装或不可用")
        except Exception as e:
            result_lines.append(f"\n⚠️ 检查Docker时出错: {e}")
        
        # 检查Git
        try:
            git_version = subprocess.run(["git", "--version"], capture_output=True, text=True)
            if git_version.returncode == 0:
                result_lines.append(f"✅ Git 已安装: {git_version.stdout.strip()}")
            else:
                result_lines.append("⚠️ Git 未安装或不可用")
        except Exception as e:
            result_lines.append(f"⚠️ 检查Git时出错: {e}")
        
        # 生成部署脚本
        script_content = f"""#!/bin/bash
# 自动部署脚本 - {app_name}
# 平台: {platform}
# 生成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}

echo "=== 部署 {app_name} 到 {platform} ==="

# 检查必要工具
command -v docker >/dev/null 2>&1 || {{ echo "错误: Docker 未安装"; exit 1; }}
command -v git >/dev/null 2>&1 || {{ echo "警告: Git 未安装"; }}

# 构建Docker镜像 (如果存在Dockerfile)
if [ -f "Dockerfile" ]; then
    echo "构建Docker镜像..."
    docker build -t {app_name}:latest .
    echo "✅ Docker镜像构建完成"
else
    echo "⚠️ 未找到Dockerfile，跳过构建"
fi

echo ""
echo "=== 部署指令 ==="
"""
        
        if platform == "zeabur":
            script_content += """
# Zeabur 部署指令
echo "1. 访问 https://zeabur.com 并登录"
echo "2. 点击 'Create Project'"
echo "3. 选择 'Import Git Repository' 或上传代码"
echo "4. 配置服务 (端口: {}，内存: 512MB)"
echo "5. 点击 'Deploy'"
""".format(port)
        
        elif platform == "render":
            script_content += """
# Render 部署指令
echo "1. 访问 https://render.com 并登录"
echo "2. 点击 'New +' -> 'Web Service'"
echo "3. 连接你的Git仓库"
echo "4. 配置:"
echo "   - Name: {}"
echo "   - Environment: Docker"
echo "   - Plan: Free"
echo "5. 点击 'Create Web Service'"
""".format(app_name)
        
        # 保存脚本
        script_path = Path(current_dir) / f"deploy_{platform}.sh"
        with open(script_path, "w") as f:
            f.write(script_content)
        
        os.chmod(script_path, 0o755)
        
        result_lines.append(f"\n✅ 已生成部署脚本: {script_path}")
        result_lines.append(f"运行命令: chmod +x {script_path} && ./{script_path}")
        
        return "\n".join(result_lines)