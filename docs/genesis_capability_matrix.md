# Genesis 系统能力接入矩阵

> 日期: 2026-05-21  
> 目的: 区分 production / experiment / dead / deprecated，防止死代码被误读为已接入能力。

## 模块状态总表

| 模块 | 状态 | 导入次数 | 入口调用 | 进入 prompt | 写 NodeVault | 说明 |
|------|------|---------|---------|------------|-------------|------|
| `v4/loop.py` | **production** | 2 | discord_bot, yogg_auto | ✅ | ✅ | 主循环 |
| `v4/c_phase.py` | **production** | 1 | loop.py (Mixin) | ✅ | ✅ (edges) | Gardener |
| `v4/lens_phase.py` | **production** | 1 | loop.py (Mixin) | ✅ | ❌ | 知识透镜 |
| `v4/surface.py` | **production** | 2 | search_tool, loop | ✅ | ❌ | 面组装 |
| `v4/diagnostics.py` | **production** | 3 | loop, search_tool, c_phase | ✅ (summary) | ❌ | 诊断信号 (P0 补齐后) |
| `v4/manager.py` | **production** | 17 | 全系统 | ❌ | ✅ | NodeVault 核心 |
| `v4/knowledge_query.py` | **production** | 多 | manager | ✅ | ❌ | 知识查询/渲染 |
| `v4/background_daemon.py` | **production** | 0 | systemd | ❌ | ✅ (GC) | 守护进程 |
| `v4/trace_pipeline/runner.py` | **production** | 3 | c_phase, daemon | ❌ | ❌ | Trace 管线 |
| `v4/trace_pipeline/entity_extractor.py` | **production** | 0 | runner | ❌ | ❌ | 实体提取 |
| `v4/trace_pipeline/entity_store.py` | **production** | 0 | runner | ❌ | ✅ | 实体存储 |
| `v4/trace_pipeline/relationship_builder.py` | **production** | 1 | runner | ❌ | ✅ | 关系构建 (P0 激活后) |
| `v4/trace_pipeline/community_detector.py` | **production** | 1 | runner | ❌ | ❌ | 社区检测 (P0 激活后) |
| `v4/trace_pipeline/evidence_assessor.py` | **production** | 0 | runner | ❌ | ✅ | 证据评估 (P0 激活后) |
| `tools/search_tool.py` | **production** | 0 | factory → loop | ✅ | ❌ | 搜索工具 |
| `tools/node_tools.py` | **production** | 多 | factory → loop | ❌ | ✅ | 节点创建工具 |
| `tools/pls_query_tool.py` | **production** | 1 | factory → loop | ✅ | ❌ | PLS 查询 |
| `auto_mode.py` | **production** | 0 | yogg_auto | ✅ | ❌ | Auto 模式 |
| `factory.py` | **production** | 多 | 入口脚本 | ❌ | ❌ | Agent 工厂 |
| `discord_bot.py` | **production** | 0 | systemd | ❌ | ❌ | Discord 入口 |
| `yogg_auto.py` | **production** | 0 | systemd | ❌ | ❌ | Yogg 入口 |
| `v4/network_health.py` | **dead** | 0 | ❌ | ❌ | ❌ | 441行零导入孤岛 |
| `v4/challenger.py` | **deleted** | — | — | — | — | 源码已删除，仅 .pyc 残留 |
| `v6/__init__.py` | **experiment** | 0 | ❌ | ❌ | ❌ | V6 shadow 占位 |
| `experiments/pls_chapter_state_recovery/` | **experiment** | 0 | ❌ | ❌ | ❌ | ChapterState 实验 |
| `experiments/pls_value_validation/` | **experiment** | 0 | ❌ | ❌ | ❌ | PLS 验证实验 |
| `skills/*.py` | **runtime** | 0 | factory autoload | ❌ | ❌ | 物理技能 (运行时注册，知识图谱不可见) |

## 状态定义

- **production**: 在生产环境中被 systemd 服务调用或通过 import chain 进入主执行路径。
- **experiment**: 存在代码但未接入生产路径，仅用于本地实验或设计草案。
- **runtime**: 运行时通过 autoload 注册，但不在知识图谱中持久化。
- **dead**: 有完整实现但零导入、零入口调用，从未进入主路径。
- **deprecated**: 已被官方废弃但代码/文档残留。
- **deleted**: 源码已删除，仅剩编译缓存或文档引用。

## 关键发现

1. **`network_health.py` (441行)**: 代码库中唯一零导入的非入口模块，完全孤立。
2. **ChallengerMixin**: 源码已删除，但 `__pycache__/challenger.cpython-314.pyc` 和文档引用仍残留。
3. **物理技能 42:2**: 42 个技能文件通过 autoload 注册为 PHYS_* 运行时节点，但仅 2 个在 knowledge_nodes 表中有 TOOL 节点。
4. **Evidence Assessor / 社区检测**: 在 P0 修复前为死代码（`rebuild_relationships=False`），现已激活。
5. **V6**: 当前为 shadow_only 占位，不参与任何生产路径。
