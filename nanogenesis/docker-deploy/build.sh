#!/bin/bash
# NanoGenesis Docker构建脚本

set -e

echo "🔧 构建NanoGenesis Docker镜像..."
docker build -t nanogenesis:latest .

echo "✅ 镜像构建完成！"
echo "运行以下命令启动容器："
echo "  docker run -p 3000:3000 -v $(pwd)/data:/app/data -v $(pwd)/logs:/app/logs nanogenesis:latest"
echo "或使用docker-compose："
echo "  docker-compose up -d"
