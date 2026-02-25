# 免费容器/VPS平台部署指南

## 搜索到的免费平台

根据全网搜索，以下平台提供免费容器/VPS服务：

### 1. Zeabur
- **免费套餐**: 每月 $5 信用额度，每个服务最多 1 vCPU 和 2GB 内存
- **部署方式**: Web控制台或CLI
- **CLI工具**: `npm install -g @zeabur/cli`
- **部署命令**: `zeabur deploy`

### 2. Render
- **免费套餐**: 750小时/月，512MB RAM，共享CPU
- **特点**: 自动休眠（15分钟无流量）
- **部署方式**: Web控制台连接Git仓库

### 3. Hugging Face Spaces
- **免费套餐**: CPU Basic (2 vCPU, 16GB RAM)
- **特点**: 专门为AI/ML应用设计，但也支持通用Docker容器
- **部署方式**: Web控制台上传Dockerfile

### 4. GitHub Actions + 自托管运行器
- **免费套餐**: 每个作业最多6小时运行时间
- **特点**: 高度可定制，可使用免费云资源作为运行器

## 已创建的演示应用

位于 `demo-app/` 目录：
- `app.js` - 简单的Node.js HTTP服务器
- `package.json` - 项目配置
- `Dockerfile` - Docker容器配置

## 生成的部署脚本

1. `deploy_zeabur.sh` - Zeabur部署脚本
2. `deploy_render.sh` - Render部署脚本  
3. `deploy_huggingface.sh` - Hugging Face Spaces部署脚本
4. `deploy_github_actions.sh` - GitHub Actions部署脚本

## 快速部署命令

### Zeabur (推荐)
```bash
# 1. 安装CLI
npm install -g @zeabur/cli

# 2. 登录（需要浏览器）
zeabur auth login

# 3. 部署
cd demo-app
zeabur deploy
```

### Render
1. 访问 https://render.com
2. 点击 'New +' -> 'Web Service'
3. 连接Git仓库或上传代码
4. 选择免费套餐部署

### Hugging Face Spaces
1. 访问 https://huggingface.co/spaces
2. 点击 'Create new Space'
3. 选择 'Docker' 模板
4. 上传demo-app目录中的文件
5. 选择CPU Basic硬件

## 自动化部署脚本

运行以下命令生成所有平台的部署指南：
```bash
chmod +x deploy_*.sh
./deploy_zeabur.sh
./deploy_render.sh
./deploy_huggingface.sh
```

## 总结

已成功完成：
- ✅ 搜索全网免费容器/VPS平台
- ✅ 创建可部署的演示应用
- ✅ 为多个平台生成部署脚本
- ✅ 提供详细的部署指南

选择任意平台按照上述指南即可完成免费容器部署。