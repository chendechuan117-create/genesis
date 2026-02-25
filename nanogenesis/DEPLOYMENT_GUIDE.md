# nanogenesis 部署指南

## 包信息
- **包名称**: nanogenesis_portable_20260225_135733
- **创建时间**: 20260225_135733
- **包大小**: 0.60 MB

## 部署选项

### 1. 本地部署
```bash
# 解压包
tar -xzf nanogenesis_portable_20260225_135733.tar.gz

# 进入目录
cd nanogenesis_portable_20260225_135733

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
