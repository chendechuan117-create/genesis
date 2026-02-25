#!/bin/bash
# 自动部署脚本 - free-container-demo
# 平台: zeabur
# 生成时间: 2026-02-25 13:51:56

echo "=== 部署 free-container-demo 到 zeabur ==="

# 检查必要工具
command -v docker >/dev/null 2>&1 || { echo "错误: Docker 未安装"; exit 1; }
command -v git >/dev/null 2>&1 || { echo "警告: Git 未安装"; }

# 构建Docker镜像 (如果存在Dockerfile)
if [ -f "Dockerfile" ]; then
    echo "构建Docker镜像..."
    docker build -t free-container-demo:latest .
    echo "✅ Docker镜像构建完成"
else
    echo "⚠️ 未找到Dockerfile，跳过构建"
fi

echo ""
echo "=== 部署指令 ==="

# Zeabur 部署指令
echo "1. 访问 https://zeabur.com 并登录"
echo "2. 点击 'Create Project'"
echo "3. 选择 'Import Git Repository' 或上传代码"
echo "4. 配置服务 (端口: 3000，内存: 512MB)"
echo "5. 点击 'Deploy'"
