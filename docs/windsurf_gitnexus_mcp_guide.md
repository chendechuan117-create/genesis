# Windsurf通过MCP接入GitNexus配置指南

## 概述

Windsurf AI IDE通过Model Context Protocol (MCP)可以连接GitNexus代码图谱服务器，实现深度代码分析和智能编程辅助。

## GitNexus MCP服务器配置

### 1. 安装GitNexus MCP服务器

```bash
# 通过npm安装
npm install -g @gitnexus/mcp-server

# 或通过npx直接运行
npx @gitnexus/mcp-server
```

### 2. Windsurf MCP配置

在Windsurf中配置GitNexus MCP服务器：

#### 方法一：通过Windsurf UI配置

1. 打开Windsurf IDE
2. 点击侧边栏的 **Plugins** 图标
3. 选择 **Manage plugins** → **View raw config**
4. 编辑 `mcp_config.json` 文件

#### 方法二：直接编辑配置文件

配置文件位置：`~/.codeium/windsurf/mcp_config.json`

```json
{
  "mcpServers": {
    "gitnexus": {
      "command": "npx",
      "args": ["-y", "@gitnexus/mcp-server"],
      "env": {
        "GITNEXUS_API_KEY": "your_gitnexus_api_key",
        "GITNEXUS_SERVER_URL": "http://localhost:8080",
        "GITNEXUS_REPO_PATH": "/path/to/your/codebase"
      }
    }
  }
}
```

### 3. 配置参数说明

| 参数 | 说明 | 必需 |
|------|------|------|
| `command` | 启动命令 | 是 |
| `args` | 命令参数 | 是 |
| `GITNEXUS_API_KEY` | GitNexus API密钥 | 可选 |
| `GITNEXUS_SERVER_URL` | GitNexus服务器地址 | 可选 |
| `GITNEXUS_REPO_PATH` | 代码仓库路径 | 是 |

### 4. 高级配置选项

```json
{
  "mcpServers": {
    "gitnexus": {
      "command": "npx",
      "args": [
        "-y", "@gitnexus/mcp-server",
        "--port", "8080",
        "--log-level", "info",
        "--max-depth", "5"
      ],
      "env": {
        "GITNEXUS_API_KEY": "your_api_key",
        "GITNEXUS_SERVER_URL": "http://localhost:8080",
        "GITNEXUS_REPO_PATH": "/home/user/project",
        "GITNEXUS_INDEX_TIMEOUT": "300",
        "GITNEXUS_CACHE_SIZE": "1000"
      }
    }
  }
}
```

## 使用方法

### 1. 代码库索引

在Windsurf聊天中输入：

```
@gitnexus 请为当前代码库建立索引
```

### 2. 代码搜索

```
@gitnexus 搜索包含"authentication"的函数
```

### 3. 依赖分析

```
@gitnexus 分析UserService的依赖关系
```

### 4. 执行流追踪

```
@gitnexus 追踪login函数的执行流程
```

### 5. 代码聚类分析

```
@gitnexus 分析用户管理相关的代码聚类
```

## GitNexus MCP工具功能

### 核心工具

1. **gitnexus_search** - 智能代码搜索
2. **gitnexus_analyze** - 深度代码分析  
3. **gitnexus_trace** - 执行流追踪
4. **gitnexus_cluster** - 功能聚类分析
5. **gitnexus_dependencies** - 依赖关系分析
6. **gitnexus_index** - 代码库索引管理

### 工具参数

#### gitnexus_search
- `query`: 搜索关键词
- `scope`: 搜索范围 (file/function/class/module)
- `include_context`: 是否包含上下文

#### gitnexus_analyze  
- `target`: 分析目标
- `analysis_type`: 分析类型 (complexity/dependencies/security)
- `depth`: 分析深度

#### gitnexus_trace
- `entry_point`: 入口函数
- `max_depth`: 最大追踪深度
- `include_conditions`: 是否包含条件分支

## 故障排除

### 常见问题

1. **连接失败**
   ```
   错误：无法连接到GitNexus MCP服务器
   ```
   解决方案：
   - 检查GitNexus服务器是否运行
   - 验证端口配置是否正确
   - 确认防火墙设置

2. **索引失败**
   ```
   错误：代码库索引建立失败
   ```
   解决方案：
   - 检查代码库路径是否正确
   - 确认代码库是Git仓库
   - 检查磁盘空间是否充足

3. **权限问题**
   ```
   错误：无权限访问代码文件
   ```
   解决方案：
   - 检查文件权限设置
   - 确认用户有读取权限
   - 验证.gitignore配置

### 调试方法

1. **查看MCP日志**
   ```bash
   # Windsurf日志位置
   ~/.codeium/windsurf/logs/
   ```

2. **测试GitNexus连接**
   ```bash
   curl http://localhost:8080/health
   ```

3. **验证配置**
   ```bash
   npx @gitnexus/mcp-server --help
   ```

## 最佳实践

### 1. 性能优化

- 限制索引深度：`--max-depth 3`
- 启用缓存：`GITNEXUS_CACHE_SIZE=1000`
- 定期清理索引：`@gitnexus clean-index`

### 2. 安全考虑

- 使用只读API密钥
- 限制访问路径范围
- 定期更新API密钥

### 3. 团队协作

- 共享标准配置文件
- 统一代码库结构
- 建立索引更新策略

## 示例配置

### 开发环境
```json
{
  "mcpServers": {
    "gitnexus-dev": {
      "command": "npx",
      "args": ["-y", "@gitnexus/mcp-server", "--dev"],
      "env": {
        "GITNEXUS_REPO_PATH": "./src",
        "GITNEXUS_LOG_LEVEL": "debug"
      }
    }
  }
}
```

### 生产环境
```json
{
  "mcpServers": {
    "gitnexus-prod": {
      "command": "docker",
      "args": [
        "run", "-i", "--rm",
        "-e", "GITNEXUS_API_KEY",
        "-v", "/project:/workspace",
        "gitnexus/mcp-server:latest"
      ],
      "env": {
        "GITNEXUS_API_KEY": "${GITNEXUS_API_KEY}",
        "GITNEXUS_SERVER_URL": "https://gitnexus.company.com"
      }
    }
  }
}
```

## 支持的语言

GitNexus MCP服务器支持多种编程语言：

- **Python** - 完整支持
- **JavaScript/TypeScript** - 完整支持  
- **Java** - 完整支持
- **Go** - 完整支持
- **Rust** - 完整支持
- **C/C++** - 部分支持
- **C#** - 部分支持

## 更新和维护

### 更新GitNexus MCP服务器
```bash
npm update -g @gitnexus/mcp-server
```

### 清理缓存
```bash
@gitnexus clean-cache
```

### 重建索引
```bash
@gitnexus rebuild-index --force
```

---

通过以上配置，你可以在Windsurf中充分利用GitNexus的代码图谱能力，实现更智能的代码分析和编程辅助。
