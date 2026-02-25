#!/bin/bash
# 自动部署脚本 - free-container-demo-gh
# 平台: github_actions
# 生成时间: 2026-02-25 13:54:34

echo "=== 部署 free-container-demo-gh 到 github_actions ==="

# 检查必要工具
command -v docker >/dev/null 2>&1 || { echo "错误: Docker 未安装"; exit 1; }
command -v git >/dev/null 2>&1 || { echo "警告: Git 未安装"; }

# 构建Docker镜像 (如果存在Dockerfile)
if [ -f "Dockerfile" ]; then
    echo "构建Docker镜像..."
    docker build -t free-container-demo-gh:latest .
    echo "✅ Docker镜像构建完成"
else
    echo "⚠️ 未找到Dockerfile，跳过构建"
fi

echo ""
echo "=== 部署指令 ==="
