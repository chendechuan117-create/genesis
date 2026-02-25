import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from genesis.core.base import Tool

class DockerEnvBuilderTool(Tool):
    @property
    def name(self) -> str:
        return "docker_env_builder"
        
    @property
    def description(self) -> str:
        return "根据当前nanogenesis代码库状态，动态生成Dockerfile、docker-compose.yml和部署脚本，用于在远程环境中自动化配置Python环境并拉起Genesis系统。"
        
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "output_dir": {"type": "string", "description": "输出目录路径，默认为当前目录", "default": "."},
                "python_version": {"type": "string", "description": "Python版本，默认为3.10", "default": "3.10"},
                "port": {"type": "integer", "description": "应用监听端口，默认为3000", "default": 3000},
                "include_dev_deps": {"type": "boolean", "description": "是否包含开发依赖，默认为False", "default": False},
                "generate_deploy_script": {"type": "boolean", "description": "是否生成远程部署脚本，默认为True", "default": True}
            },
            "required": []
        }
        
    async def execute(self, output_dir: str = ".", python_version: str = "3.10", port: int = 3000, 
                     include_dev_deps: bool = False, generate_deploy_script: bool = True) -> str:
        import os
        import json
        from pathlib import Path
        
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        # 读取pyproject.toml获取依赖
        pyproject_path = Path("/home/chendechusn/Genesis/nanogenesis/pyproject.toml")
        dependencies = ["litellm>=1.0.0", "loguru>=0.7.0", "pydantic>=2.0.0"]
        dev_dependencies = ["pytest>=7.0.0", "pytest-asyncio>=0.21.0", "black>=23.0.0", "ruff>=0.1.0"]
        
        if pyproject_path.exists():
            try:
                import tomllib
                with open(pyproject_path, 'rb') as f:
                    data = tomllib.load(f)
                    dependencies = data.get('project', {}).get('dependencies', dependencies)
                    dev_dependencies = data.get('project', {}).get('optional-dependencies', {}).get('dev', dev_dependencies)
            except Exception as e:
                print(f"Warning: Failed to parse pyproject.toml: {e}")
        
        # 生成Dockerfile
        dockerfile_content = f"""# NanoGenesis Docker镜像
FROM python:{python_version}-slim

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \\
    git \\
    curl \\
    && rm -rf /var/lib/apt/lists/*

# 复制项目文件
COPY . /app

# 安装Python依赖
RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir {' '.join(dependencies)}
"""

        if include_dev_deps:
            dockerfile_content += f"""RUN pip install --no-cache-dir {' '.join(dev_dependencies)}
"""

        dockerfile_content += f"""
# 设置环境变量
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# 暴露端口
EXPOSE {port}

# 启动命令
CMD ["python", "-m", "genesis.daemon"]
"""
        
        # 生成docker-compose.yml
        compose_content = f"""version: '3.8'

services:
  nanogenesis:
    build: .
    container_name: nanogenesis
    ports:
      - "{port}:{port}"
    environment:
      - PYTHONPATH=/app
      - PYTHONUNBUFFERED=1
    volumes:
      - ./data:/app/data
      - ./logs:/app/logs
    restart: unless-stopped
    networks:
      - nanogenesis-net

networks:
  nanogenesis-net:
    driver: bridge
"""
        
        # 生成构建脚本
        build_script = """#!/bin/bash
# NanoGenesis Docker构建脚本

set -e

echo "🔧 构建NanoGenesis Docker镜像..."
docker build -t nanogenesis:latest .

echo "✅ 镜像构建完成！"
echo "运行以下命令启动容器："
echo "  docker run -p 3000:3000 -v $(pwd)/data:/app/data -v $(pwd)/logs:/app/logs nanogenesis:latest"
echo "或使用docker-compose："
echo "  docker-compose up -d"
"""
        
        # 生成远程部署脚本
        deploy_script = """#!/bin/bash
# NanoGenesis远程环境部署脚本
# 使用方法：./deploy_remote.sh user@remote_host

set -e

if [ $# -ne 1 ]; then
    echo "使用方法: $0 user@remote_host"
    exit 1
fi

REMOTE_HOST="$1"
LOCAL_DIR="."
REMOTE_DIR="~/nanogenesis-deploy"

echo "🚀 开始部署到远程主机: $REMOTE_HOST"

# 1. 检查远程Docker是否安装
echo "🔍 检查远程Docker安装..."
ssh "$REMOTE_HOST" "command -v docker >/dev/null 2>&1 || { echo 'Docker未安装，正在安装...'; curl -fsSL https://get.docker.com | sh; sudo usermod -aG docker \$USER; }"

# 2. 检查远程Docker Compose是否安装
echo "🔍 检查远程Docker Compose安装..."
ssh "$REMOTE_HOST" "command -v docker-compose >/dev/null 2>&1 || { echo 'Docker Compose未安装，正在安装...'; sudo curl -L \"https://github.com/docker/compose/releases/latest/download/docker-compose-\$(uname -s)-\$(uname -m)\" -o /usr/local/bin/docker-compose; sudo chmod +x /usr/local/bin/docker-compose; }"

# 3. 创建远程目录
echo "📁 创建远程目录..."
ssh "$REMOTE_HOST" "mkdir -p $REMOTE_DIR"

# 4. 传输文件
echo "📤 传输文件到远程主机..."
rsync -avz --exclude='__pycache__' --exclude='.git' --exclude='venv' --exclude='*.pyc' \
    "$LOCAL_DIR/" "$REMOTE_HOST:$REMOTE_DIR/"

# 5. 在远程主机上构建和启动
echo "🔨 在远程主机上构建Docker镜像..."
ssh "$REMOTE_HOST" "cd $REMOTE_DIR && docker build -t nanogenesis:latest ."

echo "🚀 启动NanoGenesis容器..."
ssh "$REMOTE_HOST" "cd $REMOTE_DIR && docker-compose up -d"

echo "✅ 部署完成！"
echo "📊 检查容器状态："
ssh "$REMOTE_HOST" "docker ps | grep nanogenesis"
echo ""
echo "📝 查看日志："
echo "  ssh $REMOTE_HOST 'docker logs -f nanogenesis'"
echo ""
echo "🔧 停止容器："
echo "  ssh $REMOTE_HOST 'cd $REMOTE_DIR && docker-compose down'"
"""
        
        # 写入文件
        dockerfile_path = output_path / "Dockerfile"
        compose_path = output_path / "docker-compose.yml"
        build_script_path = output_path / "build.sh"
        deploy_script_path = output_path / "deploy_remote.sh"
        
        dockerfile_path.write_text(dockerfile_content, encoding="utf-8")
        compose_path.write_text(compose_content, encoding="utf-8")
        build_script_path.write_text(build_script, encoding="utf-8")
        
        if generate_deploy_script:
            deploy_script_path.write_text(deploy_script, encoding="utf-8")
            # 设置执行权限
            os.chmod(str(deploy_script_path), 0o755)
        
        # 设置构建脚本执行权限
        os.chmod(str(build_script_path), 0o755)
        
        # 生成配置文件列表
        config_files = {
            "Dockerfile": str(dockerfile_path),
            "docker-compose.yml": str(compose_path),
            "build.sh": str(build_script_path)
        }
        
        if generate_deploy_script:
            config_files["deploy_remote.sh"] = str(deploy_script_path)
        
        result = f"""✅ Docker环境配置生成完成！

📁 生成的文件：
{json.dumps(config_files, indent=2, ensure_ascii=False)}

📋 使用说明：
1. 构建镜像：./build.sh
2. 本地测试：docker-compose up -d
3. 远程部署：./deploy_remote.sh user@remote_host

🔧 配置详情：
- Python版本: {python_version}
- 端口: {port}
- 包含开发依赖: {include_dev_deps}
- 主依赖: {len(dependencies)}个
- 开发依赖: {len(dev_dependencies)}个
"""
        
        return result