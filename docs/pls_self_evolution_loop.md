# PLS 自进化循环设计

> 基于 Point-Line-Surface 知识架构的安全自修改循环。
> 从隔离沙箱变更 → 受控晋升流程 → 生产环境确定性应用。

---

## 1. 动机

当前 SelfEvolution 机制存在三个根本缺陷：

1. **证据分类缺失**：`test-diff` 返回 "No test files found" 时 exit 0（算通过），SelfEvolution 把"无证据"当成"正面证据"，自动应用未经任何测试的补丁。
2. **晋升无审查**：沙箱变更冷却后直接 `auto-apply`，没有独立审查环节。Yogg 既是提议者又是执行者——自己写、自己测、自己应用。
3. **范围语义错误**：`--only` 用逗号分隔路径传给 `git diff`，git 把它当单个 glob 模式，scope gate 实际上匹配不到任何文件。

PLS 架构的价值信号（入线数、CONTRADICTS 边、饱和标记）天然适合做自进化的安全锚：**拓扑密度高的区域可以直接执行，VOID 洞需要先调查，CONTRADICTS 标记的区域需要审查**。自进化循环应该继承这个判断逻辑。

---

## 2. 现有自进化原语映射

### 2.1 Doctor 沙箱命令

| 命令 | 当前用途 | PLS 对应 |
|------|---------|---------|
| `doctor.sh start` | 启动沙箱容器 | — (基础设施) |
| `doctor.sh reset` | 重置到生产基线 | Surface 重建（清空临时变更） |
| `doctor.sh diff` | 查看所有修改 | PatchPoint 候选集 |
| `doctor.sh test-diff` | 差分范围测试 | EvidenceLine（证据线） |
| `doctor.sh auto-apply` | 非交互式应用 | PromotionGate（晋升门） |
| `doctor.sh rollback` | 回滚到指定 commit | 降级/撤销 |
| `doctor.sh list-changed` | 列出修改文件 | scope gate 输入 |
| `doctor.sh file-status` | 逐文件 hash | 冷却追踪基础 |

### 2.2 SelfEvolution 类（auto_mode.py）

| 机制 | 当前行为 | 问题 |
|------|---------|------|
| 文件级冷却 | 每文件独立 stable_count，达到阈值触发 apply | 无审查，冷却=自动晋升 |
| scope gate | CRITICAL_SELF_EVOLUTION_FILES 集合阻止关键文件自动应用 | `--only` 语义错误导致实际不生效 |
| test-diff | exit 0=通过，其他=失败 | "无测试"也算通过 |
| 死循环守卫 | 连续 3 次同原因 test_failed → 跳过 5 轮 | 只覆盖 test_failed，不覆盖 collection_failed |
| 崩溃回滚 | yogg_auto.py 的 _pre_import_crash_guard | 事后补救，不是事前预防 |

---

## 3. PLS 补丁晋升模型

### 3.1 核心实体

```
PatchPoint        — 沙箱中的一个文件变更集合（diff）
  ├── EvidenceLine   — 测试结果作为证据线（pass/fail/unverified/collection_failed）
  ├── ReviewLine     — 独立审查者的判断线（approve/reject/needs_changes）
  ├── PromotionLine  — 晋升决策线（canary → production）
  └── CanaryLine     — 金丝雀部署观察线（运行 N 轮无崩溃 → 晋升）
```

### 3.2 晋升状态机

```
                    ┌──────────────────────────────────┐
                    │                                  │
                    ▼                                  │
  [SANDBOX] ──test-diff──▶ [EVIDENCE] ──review──▶ [REVIEWED]
      │                      │                         │
      │  NO_TESTS_FOUND      │  test_failed            │  approve
      │  (unverified)        │  collection_failed      │
      ▼                      ▼                         ▼
  [UNVERIFIED]          [REJECTED]              [APPROVED]
      │                                              │
      │  (proceed with caution)                      │  canary deploy
      ▼                                              ▼
  [APPLIED_UNVERIFIED]                          [CANARY]
      │                                              │
      │  crash_guard                                 │  N rounds stable
      ▼                                              ▼
  [PRODUCTION] ◀──────────────────────────── [PROMOTED]
```

### 3.3 证据分类（已实施）

| exit code | 标记 | 含义 | SelfEvolution 行为 |
|-----------|------|------|-------------------|
| 0 | — | 测试通过 | 正常 apply |
| 3 | NO_TESTS_FOUND | 无测试覆盖 | 允许 apply，标记 test_unverified |
| 4 | COLLECTION_FAILED | 测试基础设施损坏 | 阻止 apply，selective reset |
| 1/2/其他 | — | 实际测试失败 | 阻止 apply，selective reset |

---

## 4. Twin-Review 机制

### 4.1 设计原理

当前 Yogg 既是提议者（在沙箱中修改代码）又是执行者（auto-apply 到生产）。这违反了 PLS 的核心原则：**价值判断需要独立视角**。

Twin-Review 引入"审查者 Yogg"角色：
- **Proposer Yogg**：在沙箱中探索和修改代码（当前行为不变）
- **Reviewer Yogg**：独立审视 Proposer 的变更，决定是否允许晋升

### 4.2 实现方案

审查者不需要是独立的进程。利用 C-Phase 的 Gardener 模式：

```
Proposer (GP) 修改沙箱 → 冷却完成 → C-Phase 审查沙箱 diff → 输出审查判断
```

具体流程：
1. GP 在沙箱中修改文件（现有行为）
2. 冷却完成后，不直接 auto-apply
3. 触发 C-Phase 审查：将 `doctor.sh diff` 输出注入 C prompt
4. C 输出审查判断：`APPROVE` / `REJECT: <reason>` / `NEEDS_CHANGES: <suggestion>`
5. 只有 `APPROVE` 才进入 auto-apply 流程

### 4.3 C-Phase 审查 Prompt 片段

```python
REVIEW_PROMPT = """
你正在审查 Yogg 自进化的沙箱变更。以下是变更的 diff：

{diff_output}

审查标准：
1. 变更是否只修改了它声称要修改的问题？（范围审查）
2. 变更是否引入了新的副作用？（副作用审查）
3. 变更是否与已有知识矛盾？（CONTRADICTS 审查）

输出格式（只输出一行）：
APPROVE — 如果变更安全且聚焦
REJECT: <原因> — 如果变更有明显风险
NEEDS_CHANGES: <建议> — 如果变更方向对但需要调整
"""
```

### 4.4 渐进部署

Twin-Review 不需要一步到位：

| 阶段 | 行为 | 安全增益 |
|------|------|---------|
| Phase 0（当前） | 冷却后直接 auto-apply | 基线 |
| Phase 1（已实施） | test-diff 证据分类 | 阻止无证据晋升 |
| Phase 2 | C-Phase 审查（非阻塞） | C 输出审查意见，但不强制 |
| Phase 3 | C-Phase 审查（阻塞） | C 必须 APPROVE 才能 apply |
| Phase 4 | Canary 部署 | apply 后观察 N 轮才算成功 |

---

## 5. Canary 部署

### 5.1 设计

当前 auto-apply 后立即重启 Yogg，如果崩溃则由 crash_guard 回滚。这是"全量部署+事后补救"。

Canary 部署改为：
1. auto-apply 后**不立即重启**
2. 标记当前 round 为 "canary round"
3. 继续运行 N 轮（默认 3），观察：
   - 无 ERROR 日志
   - 无 crash_guard 触发
   - 工具调用成功率 ≥ 80%
4. N 轮通过 → 写入 `CANARY_PASSED` 标记，晋升为正式生产
5. 任一条件失败 → 自动 rollback

### 5.2 实现

```python
class SelfEvolution:
    CANARY_ROUNDS = 3  # 观察轮数

    async def _try_apply(self, round_num, channel):
        # ... existing test-diff + scope gate logic ...

        # auto-apply
        apply_ok, apply_output = await _run_doctor_sync_command(*apply_cmd)

        if apply_ok:
            # Instead of immediate restart, enter canary mode
            self._canary_state = {
                "applied_commit": applied_commit,
                "rollback_commit": rollback_commit,
                "start_round": round_num,
                "rounds_observed": 0,
                "errors_seen": 0,
            }
            self._save()
            await channel.send(f"🧬 ✅ Canary 部署开始，观察 {self.CANARY_ROUNDS} 轮")
            # Don't restart yet — let current process continue with new code
            # (Python import cache means new code takes effect on next round's imports)

    async def check_canary(self, round_num, channel):
        """Called each round after GP execution. Observes canary health."""
        if not self._canary_state:
            return

        self._canary_state["rounds_observed"] += 1

        # Check error count in recent logs
        # ... (parse genesis.log for ERROR lines since canary start)

        if self._canary_state["rounds_observed"] >= self.CANARY_ROUNDS:
            if self._canary_state["errors_seen"] == 0:
                await channel.send("🧬 ✅ Canary 通过，晋升为正式生产")
                self._write_restart_marker(...)
                # Now restart to fully load new code
            else:
                await channel.send("🧬 ❌ Canary 失败，回滚")
                # rollback
            self._canary_state = None
            self._save()
```

### 5.3 Canary 与 Python import 缓存

关键约束：Python 的 `importlib` 缓存意味着 `auto-apply` 后新代码不会立即生效——只有下次 `import` 时才会加载。这实际上天然提供了"软 canary"：

- 已加载的模块继续用旧代码运行
- 新 round 中 GP 的 `shell` 工具调用新代码（新进程）
- 只有显式 restart 才会让所有模块重载

因此 Canary Phase 0（当前行为）已经是部分 canary——只是没有显式观察窗口。

---

## 6. PromotionGate 确定性保证

### 6.1 当前问题

`auto-apply` 的 git 安全网依赖：
1. `git add -A && git commit` 作为 rollback point
2. `git apply --binary` 应用补丁
3. 失败时 `git reset --hard HEAD`

问题：如果 `git apply` 部分成功（某些 hunk 应用、某些失败），git 状态会不一致。当前代码在 `APPLY_FAILED` 时做 `git reset --hard HEAD + git clean -fd`，但这可能丢失之前的 rollback point。

### 6.2 修复

```bash
cmd_auto_apply() {
    # 1. Create named rollback tag (not just commit — tag is harder to lose)
    git tag "rollback/$(date +%Y%m%d_%H%M%S)" HEAD

    # 2. Apply with --check first (dry run)
    if ! git apply --check --binary "$patch_file" 2>&1; then
        echo "APPLY_CHECK_FAILED: patch would not apply cleanly"
        rm -f "$patch_file"
        return 1
    fi

    # 3. Real apply
    git apply --binary "$patch_file"
    # ...
}
```

### 6.3 原子性保证

PromotionGate 应该是原子的：
- **要么全部应用**：所有 hunk 都成功
- **要么全部不应用**：任何 hunk 失败 → 回滚到 rollback tag

`git apply --check` 提供了 dry-run 验证，确保实际 apply 不会部分成功。

---

## 7. 已实施修复清单

### 7.1 test-diff 证据分类（2026-05-03）

**文件**：`scripts/doctor.sh` `cmd_test_diff()`

- `NO_TESTS_FOUND` → exit 3（以前 exit 0）
- `COLLECTION_FAILED` → exit 4（以前直接返回 pytest 的 exit code）
- SelfEvolution 新增 `test_unverified` 状态：无测试覆盖但允许继续
- Death loop guard 扩展到覆盖 `test_collection_failed`

### 7.2 --only 多路径语义（2026-05-03）

**文件**：`scripts/doctor.sh` `_doctor_workspace_patch()`

- 逗号分隔路径 → 空格分隔传给 `git diff`
- untracked grep 用 `^path1$|^path2$` 交替模式
- 修复前：`git diff HEAD -- file1,file2` 匹配不到任何文件
- 修复后：`git diff HEAD -- file1 file2` 正确匹配

---

## 8. 待实施路线图

| 优先级 | 项目 | 依赖 | 预估工作量 |
|--------|------|------|-----------|
| P0 | ~~test-diff 证据分类~~ | 无 | ✅ 已完成 |
| P0 | ~~--only 多路径语义~~ | 无 | ✅ 已完成 |
| P1 | auto-apply --check dry-run | 无 | 20 行 bash |
| P1 | rollback tag（替代匿名 commit） | 无 | 10 行 bash |
| P2 | C-Phase 非阻塞审查 | C-Phase Gardener | 50 行 Python |
| P2 | Canary 部署观察窗口 | auto-apply 修复 | 80 行 Python |
| P3 | C-Phase 阻塞审查 | Phase 2 验证 | 20 行 Python |
| P3 | 完整 PromotionGate 状态机 | 全部上述 | 150 行 Python |

---

## 9. 与 PLS 架构的对应关系

| PLS 概念 | 自进化对应 | 作用 |
|----------|-----------|------|
| Point（点） | PatchPoint（补丁点） | 沙箱变更作为认知片段 |
| Line（线） | EvidenceLine / ReviewLine | 证据和审查作为推理链 |
| Surface（面） | PatchSurface | 当前轮次所有候选补丁的拓扑 |
| 入线数 | 审查通过次数 | 补丁被多少独立视角确认 |
| CONTRADICTS | 测试失败 / C-Phase 拒绝 | 负面信号阻止晋升 |
| 饱和标记 | 冷却完成 | 稳定=可晋升，不稳定=继续观察 |
| VOID | 无测试覆盖 | UNVERIFIED 状态，需要补充证据 |
| 消融 | rollback | 确认有害的变更被移除 |

核心原则不变：**价值判断来自拓扑结构（多条独立证据线），不是单一数字评分（冷却计数）**。冷却只是时间维度的最低门槛，真正的安全来自证据线的拓扑密度。
