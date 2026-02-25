#!/bin/bash
# 测试Docker连接和镜像拉取

echo "🔍 测试Docker连接..."
docker run --rm hello-world

echo "🔍 测试Python镜像拉取..."
docker pull python:3.10-slim --quiet

echo "✅ Docker连接测试完成"