# NanoGenesis Docker 部署方案

## 概述
此目录包含用于在陌生远程环境中自动化配置Python环境并拉起Genesis系统的Docker部署方案。

## 生成的文件

### 1. Dockerfile
- 基于Python 3.10-slim镜像
- 安装系统依赖（git, curl）
- 复制整个项目到容器
- 安装Python依赖（litellm, loguru, pydantic）
- 设置环境变量和端口

### 2. docker-compose.yml
- 定义nanogenesis服务
- 端口映射：3000:3000
- 数据卷挂载：./data, ./logs
- 自动重启策略

### 3. build.sh
- Docker镜像构建脚本
- 构建命令：`docker build -t nanogenesis:latest .`

### 4. deploy_remote.sh
- 远程环境自动化部署脚本
- 自动检查并安装Docker和Docker Compose
- 通过SSH传输文件到远程主机
- 在远程主机上构建和启动容器

### 5. test_docker_connection.sh
- Docker连接测试脚本
- 测试hello-world镜像
- 测试Python镜像拉取

## 使用说明

### 本地测试
```bash
# 1. 构建镜像
./build.sh

# 2. 启动容器
docker-compose up -d

# 3. 查看日志
docker logs -f nanogenesis

# 4. 停止容器
docker-compose down
```

### 远程部署
```bash
# 部署到远程主机（需要SSH访问权限）
./deploy_remote.sh user@remote_host

# 示例
./deploy_remote.sh ubuntu@192.168.1.100
```

### 部署脚本功能
1. **检查Docker安装**：如未安装则自动安装
2. **检查Docker Compose安装**：如未安装则自动安装
3. **传输文件**：通过rsync传输项目文件
4. **构建镜像**：在远程主机上构建Docker镜像
5. **启动服务**：使用docker-compose启动容器

## 环境要求

### 本地环境
- Docker 20.10+
- Docker Compose 2.0+
- Bash shell

### 远程环境
- SSH访问权限
- 支持Docker的Linux系统（Ubuntu/CentOS等）
- 至少2GB可用内存
- 至少5GB可用磁盘空间

## 故障排除

### Docker构建失败
1. 检查网络连接：`docker pull python:3.10-slim`
2. 检查Docker服务状态：`sudo systemctl status docker`
3. 检查磁盘空间：`df -h`

### 远程部署失败
1. 检查SSH连接：`ssh user@remote_host`
2. 检查远程用户权限：需要sudo权限安装Docker
3. 检查防火墙设置：确保SSH端口开放

### 容器启动失败
1. 查看容器日志：`docker logs nanogenesis`
2. 检查端口冲突：确保3000端口未被占用
3. 检查环境变量：确保.env文件配置正确

## 自定义配置

### 修改端口
编辑`docker-compose.yml`中的端口映射：
```yaml
ports:
  - "8080:3000"  # 将外部端口改为8080
```

### 添加环境变量
在`docker-compose.yml`中添加：
```yaml
environment:
  - PYTHONPATH=/app
  - PYTHONUNBUFFERED=1
  - API_KEY=your_api_key_here
```

### 修改Python版本
编辑`Dockerfile`第一行：
```dockerfile
FROM python:3.11-slim  # 改为3.11
```

## 安全注意事项

1. **SSH密钥**：建议使用SSH密钥认证而非密码
2. **API密钥**：不要在代码中硬编码敏感信息，使用环境变量
3. **防火墙**：确保只开放必要的端口
4. **用户权限**：使用非root用户运行容器

## 扩展功能

### 添加监控
```yaml
# 在docker-compose.yml中添加
  monitoring:
    image: prom/prometheus:latest
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
```

### 添加日志管理
```yaml
# 在docker-compose.yml中添加
  loki:
    image: grafana/loki:latest
    ports:
      - "3100:3100"
```

## 联系支持
如有问题，请参考项目文档或联系开发团队。