# Meta-Skills 改造蓝图：让技能成为可执行的知识节点

## 核心痛点
当前 Genesis 通过 `SkillCreatorTool` 生成 `.py` 脚本文件存入 `skills/` 目录。
这导致了：
1. **垃圾堆积**：脚本文件只增不减（目前已达 41 个，大量重复和废弃代码）。
2. **脱离进化体系**：知识节点（Nodes）在 SQLite 中有自动沉底和淘汰机制，但脚本文件没有。
3. **加载开销**：每次都要扫描文件系统和用 importlib 动态加载。

## 目标形态 (The "Tool Node" Paradigm)
把 Skill 的 Python 源码直接作为文本存入 SQLite 的 `NodeVault`，类型标记为 `TOOL_NODE`。

### 1. 结构设计
在 Node 表中，`TOOL_NODE` 的字段映射如下：
- `node_id`: tool_name (e.g., `n8n_browser_tool`)
- `type`: `TOOL`
- `title`: 工具的功能一句话描述
- `content`: **Python 源码文本**（只需包含 `class XxxTool(Tool): ...` 的定义）
- `metadata_signature`: 工具的触发条件（例如包含 `framework: n8n` 或 `task: browser_automation`）

### 2. 生命周期
1. **生成 (C-Process)**:
   - 当 G 认为需要一个新技能时，派发任务给 Op。
   - Op 编写/调试好 Python 源码后，C-Process 调用 `record_tool_node`（新增的内置节点工具）。
   - 代码被存入数据库。
2. **检索 (G-Process)**:
   - G 根据当前任务的 metadata signature（比如发现用户在问 n8n），去 NodeVault 搜索。
   - 搜出了 `TOOL_NODE: n8n_browser_tool`。
   - G 将其包含在派发书的 `active_nodes` 中。
3. **加载 (Op-Process)**:
   - Op 启动前，检查 `active_nodes`。
   - 发现类型为 `TOOL` 的节点，取出其 `content`（Python代码）。
   - 在安全的受限环境中通过 `exec()` 或动态编译将其转化为 Python 类，并临时注册到 `ToolRegistry`。
   - Op 执行完毕后，临时工具随内存销毁。
4. **淘汰 (NodeVault)**:
   - 长时间没被匹配到的 Tool Node 会在搜索权重中降低，最终被系统“遗忘”。不再有磁盘垃圾。

## 实施步骤 (建议分两步走)

### Phase 1: 运行时注入支持 (当前推荐)
1. 在 `genesis/core/registry.py` 的 `ToolRegistry` 中添加一个 `register_from_source(name: str, source_code: str)` 方法。
2. 在 `genesis/tools/node_tools.py` 中新增 `RecordToolNodeTool`。
3. 让 `V4Loop` 在准备 `Op-Process` 环境时，读取 payload 里的 TOOL_NODE 并动态注入。

### Phase 2: 平滑迁移旧 Skills
- 写一个一次性脚本，遍历当前的 41 个 `skills/*.py` 文件。
- 把每一个文件读出来，作为一个 `TOOL` 类型的节点塞进 SQLite。
- 删掉 `skills/` 目录。

> 此架构将彻底消除 "代码生成的工具无法自我管理" 的核心痛点。
