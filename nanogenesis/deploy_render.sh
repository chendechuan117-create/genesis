#!/bin/bash
# 自动部署脚本 - free-container-demo-render
# 平台: render
# 生成时间: 2026-02-25 13:54:22

echo "=== 部署 free-container-demo-render 到 render ==="

# 检查必要工具
command -v docker >/dev/null 2>&1 || { echo "错误: Docker 未安装"; exit 1; }
command -v git >/dev/null 2>&1 || { echo "警告: Git 未安装"; }

# 构建Docker镜像 (如果存在Dockerfile)
if [ -f "Dockerfile" ]; then
    echo "构建Docker镜像..."
    docker build -t free-container-demo-render:latest .
    echo "✅ Docker镜像构建完成"
else
    echo "⚠️ 未找到Dockerfile，跳过构建"
fi

echo ""
echo "=== 部署指令 ==="

# Render 部署指令
echo "1. 访问 https://render.com 并登录"
echo "2. 点击 'New +' -> 'Web Service'"
echo "3. 连接你的Git仓库"
echo "4. 配置:"
echo "   - Name: free-container-demo-render"
echo "   - Environment: Docker"
echo "   - Plan: Free"
echo "5. 点击 'Create Web Service'"
