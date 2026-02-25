# NanoGenesis Docker镜像
FROM python:3.10-slim

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 复制项目文件
COPY . /app

# 安装Python依赖
RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir litellm>=1.0.0 loguru>=0.7.0 pydantic>=2.0.0

# 设置环境变量
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# 暴露端口
EXPOSE 3000

# 启动命令
CMD ["python", "-m", "genesis.daemon"]
