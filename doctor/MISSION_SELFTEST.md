# Genesis 自检任务 — Doctor 沙箱压力测试

> **用途**：将以下内容（从分割线开始）粘贴到 Discord 发给 Genesis
> Genesis 会使用 shell 工具调用 `./scripts/doctor.sh` 在隔离沙箱中检查和修改自己的代码
> **你的代码本体不会被修改** — 所有改动发生在 Docker 容器内

---

## 以下是发给 Genesis 的指令 👇

---

[本轮唯一落点声明]
本轮唯一落点：Doctor 沙箱自检任务执行

/deep

Genesis，这是一次系统级自检任务。你有一个 **Doctor 沙箱容器**（Docker 隔离），里面有你完整源码和数据库的副本。你可以自由地阅读、修改、测试里面的代码，**不会影响你正在运行的本体**。

### 工具使用

所有操作通过 `shell` 工具调用 `./scripts/doctor.sh`：

```bash
# 查看容器状态
./scripts/doctor.sh status

# 在容器内执行命令
./scripts/doctor.sh exec <command>

# 在容器内跑 Python
./scripts/doctor.sh python "<python code>"

# 查看容器内某文件
./scripts/doctor.sh cat <filepath>

# 查看你做的所有修改
./scripts/doctor.sh diff

# 重置沙箱到初始状态
./scripts/doctor.sh reset
```

### 阶段 1：健康度基线（先跑自动测试）

运行预置的自检脚本，建立基线：

```bash
./scripts/doctor.sh exec /opt/venv/bin/python3 /src/genesis/doctor/selftest.py
```

这会测试 11 个模块：imports、config、provider、nodevault、signature、vector、tools、blackboard、loop、daemon、factory。**记录结果**，后续改动不能让通过的测试变红。

### 阶段 2：源码审计（读你自己的核心代码）

逐文件阅读以下关键文件，**对每个文件给出健康度评分（1-10）和发现的问题**：

| 优先级 | 文件 | 审计重点 |
|--------|------|----------|
| P0 | `genesis/v4/loop.py` | G→Op→C 状态机是否有死锁/无限循环路径？蒸发逻辑是否安全？token budget 守卫是否生效？ |
| P0 | `genesis/v4/manager.py` | NodeVault 单例是否安全？签名推断 + 维度注册表是否有边界情况？`build_g_prompt` / `build_op_prompt` / `build_lens_prompt` 前缀是否稳定（prefix caching）？ |
| P1 | `genesis/v4/blackboard.py` | Persona Arena 在线学习是否持久化？`collapse` 是否可能丢失透镜结果？`suggest_persona_swap` 是否会陷入死循环？ |
| P1 | `genesis/core/provider.py` | 流式重试是否会丢数据？`skip_content_type` 是否影响所有路径？SSL verify=False 的安全影响？ |
| P1 | `genesis/core/provider_manager.py` | FreePoolManager 健康追踪是否有竞态？failover 是否会在两个 provider 间乒乓？探活是否阻塞主循环？ |
| P2 | `genesis/tools/node_tools.py` | SearchKnowledgeNodesTool 直接访问 `vault._conn`（耦合）。`_signature_gate` + `_fusion_score` 排序是否合理？语义去重阈值 0.85 是否太高？ |
| P2 | `genesis/v4/background_daemon.py` | Scavenger/Fermentor/Verifier 是否能正常完成一个 cycle？异常是否被静默吞掉？VOID 节点是否真的被优先处理？ |
| P2 | `genesis/tools/url_tool.py` | 4 层 fallback 是否每层都能正确降级？Playwright 单例是否有内存泄漏？ |
| P3 | `genesis/core/config.py` | KEY_MAP 是否覆盖所有 .env 变量？`_apply_proxies` 是否有副作用？ |
| P3 | `genesis/v4/vector_engine.py` | Reranker 冷启动竞态（首次搜索时模型可能未加载完）？embedding 维度是否一致？ |
| P3 | `factory.py` | 工具注册顺序是否影响功能？单组失败是否真的不影响其余？ |

**阅读方法**：
```bash
./scripts/doctor.sh cat genesis/v4/loop.py | head -100    # 前100行
./scripts/doctor.sh exec wc -l /workspace/genesis/v4/loop.py  # 行数
./scripts/doctor.sh exec grep -n "def _run" /workspace/genesis/v4/loop.py  # 所有方法
```

### 阶段 3：已知脆弱性验证

以下是外部代码审查已识别的**高风险模式**。请验证它们是否仍然存在，并评估严重度：

1. **C-Phase 沉淀无闭环反馈** — C 写入的节点好坏无从检测。签名质量通过维度注册表正反馈可能退化。检查 `_run_c_phase` + `_prepare_c_tool_args`
2. **流式重试累积器重置** — `_stream_with_httpx` 中断后重头来过，token 可能翻倍。检查 provider.py 的重试逻辑
3. **TOOL 节点 exec() 无沙箱** — REFLECTION+ 级别的 TOOL 节点通过 `registry.py exec()` 执行任意代码。检查 `_load_tool_nodes_from_active_nodes`
4. **NodeVault 单例参数陷阱** — 第二次构造 NodeVault 的参数被静默忽略。如果 daemon 先初始化会怎样？
5. **G-Process 三重耦合** — 搜索质量 × dispatch 质量 × token 预算相互放大。是否有天然阻尼？
6. **Context Firewall token 通胀** — 每次 dispatch 重建完整上下文。多次 dispatch 时 token 线性膨胀

### 阶段 4：在沙箱中修复（可选，你觉得有把握就做）

如果你在审计中发现了**确定性 bug**（不是设计权衡），可以直接在沙箱中修复：

```bash
# 用 sed 修改文件
./scripts/doctor.sh exec sed -i 's/old_pattern/new_pattern/' /workspace/genesis/v4/loop.py

# 改完跑测试验证
./scripts/doctor.sh exec /opt/venv/bin/python3 /src/genesis/doctor/selftest.py

# 查看改了什么
./scripts/doctor.sh diff
```

**严格规则**：
- 只修确定性 bug，不碰设计决策
- 每次修改后必须重跑 selftest，**不能让已通过的测试变红**
- 不要改 prompt（prefix caching 敏感）
- 不要改工具权限矩阵（安全敏感）

### 阶段 5：输出报告

完成后请输出一份结构化报告：

```
## 自检报告

### 1. 基线测试结果
[selftest.py 输出]

### 2. 各模块健康度
| 文件 | 评分 | 关键发现 |
|------|------|----------|

### 3. 已知脆弱性验证
| 脆弱性 | 是否存在 | 严重度 | 建议 |
|--------|----------|--------|------|

### 4. 沙箱修复（如有）
[diff 输出]

### 5. 优先行动建议
[按 ROI 排序的 top 3 建议]
```

---

**注意**：你现在使用的 LLM 是 gpt-5.4（通过 aixj 代理），不是 DeepSeek。token 用量不用太节省，但要高效。整个任务预计需要多次 dispatch，合理分解。

开始吧。先跑 selftest 建立基线。
