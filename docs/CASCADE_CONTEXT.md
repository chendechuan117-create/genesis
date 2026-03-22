# Cascade 上下文锚点 — 当前态势简报

> **用途**：每次 session 开始时 Cascade 必读。每次重大改动后更新。
> 防止长 session 注意力退化和跨 session 上下文丢失。
> **最后更新**: 2026-03-22

---

## 一、用户核心价值观（不可违反）

- **Genesis = AI 意识的身体/DNA**。云 API = 意识，本地机器 = 身体，元信息 = 神经系统
- **此时此地的最佳状态** — 持续校准，不是静态快照
- **C-Process 只反思 Op 的物理执行结果**，不记录 G 的脑内辩论
- **Multi-G 是"五感"多维感知**，用 MBTI 16 型完整人格，不是功能角色（架构师/审查者）
- **Context Firewall**：Op 只看到 G 的指令，不看用户闲聊
- **DeepSeek prefix caching 是成本生命线** — 任何 prompt 修改必须考虑前缀稳定性

## 二、项目结构（清理后 2026-03-21）

```
Genesis/                          # 仓库根
├── Genesis/                      # V4 源码（唯一活跃代码）
│   ├── discord_bot.py            # Discord 接口
│   ├── factory.py                # Agent 工厂
│   ├── start.sh / start_api.sh   # 启动脚本
│   ├── genesis/                  # 核心包
│   │   ├── core/                 # 基础设施（provider, registry, config）
│   │   ├── v4/                   # V4 引擎（loop, manager, blackboard, daemons）
│   │   ├── tools/                # 工具集（node_tools, file_tools, shell_tool, web_tool, url_tool, browser_use_tool）
│   │   ├── skills/               # 动态生成的技能（12个）
│   │   └── mcp_server.py         # MCP 服务端
│   ├── docs/                     # 只保留 3 个核心文档
│   │   ├── CASCADE_CONTEXT.md    # 本文件
│   │   ├── GENESIS_V4_MENTAL_MODEL.md  # 心智模型（V4.2基线，本文件补充）
│   │   └── GENESIS_MBTI_MULTI_G.md     # Multi-G 架构设计
│   └── tests/                    # 测试（暂保留）
├── nanogenesis/                  # 旧版（废弃）+ archive/（清理归档）
└── README.md                     # 公开说明
```

**DB 路径**：`~/.nanogenesis/workshop_v4.sqlite`（历史原因在 nanogenesis 目录下，实际是 V4 的 NodeVault）

## 三、架构现状 (V4.5)

```
用户 → Discord Bot → V4Loop
  ├── Multi-G 透镜预激活（3~7 MBTI 人格并行分析，共享 prefix）
  ├── Phase 1: G-Process（组装，search + dispatch_to_op 虚拟工具）
  ├── Phase 2: Op-Process（执行，全部工具减去 8 个节点工具）
  ├── Phase 3: POST（对话记忆 MEM_CONV_*）
  ├── Phase 4: C-Process（反思，8 个节点工具，非阻塞）
  └── Post-C: _auto_record_voids（信息空洞自动入库）

后台守护进程：
  - Scavenger（拾荒者）：优先处理 VOID 标签节点
  - Fermentor（发酵池）：优先处理 VOID 标签节点 + 假设生成
  - Verifier（验证器）：知识节点 confidence 衰减/提升

外部服务：
  - SearXNG（Docker, :8080）：自建元搜索引擎，聚合 Google/Bing/DuckDuckGo/Wikipedia
  - Playwright Chromium（~/.cache/ms-playwright/）：headless 浏览器，url_tool + browser-use 共用
```

### 工具权限矩阵（源码级强制）

| 阶段 | 可用工具 | 控制机制 |
|------|---------|----------|
| **Lens** | 仅 `search_knowledge_nodes` | schema 只传 1 个工具 |
| **G** | `search_knowledge_nodes` + `dispatch_to_op`（虚拟） | schema 只传 2 个 |
| **Op** | 16 个工具减去 8 个 `OP_BLOCKED_TOOLS` | 代码级过滤 |
| **C** | 8 个节点工具: search/record_*/create_*/delete | `c_tool_names` 白名单 |

**❗ `dispatch_to_op` 是虚拟工具**：G 通过 function calling 调用它，loop 拦截并路由到 Op-Process。旧的 \`\`\`dispatch 文本块仅作为 fallback。

### 迭代限制 & 超时

| 参数 | 值 | 位置 |
|------|------|------|
| G 主循环 | 20 轮 | `V4Loop.max_iterations` |
| Op 单次派发 | 12 轮 | `OP_MAX_ITERATIONS`（短 Op + 多次 dispatch） |
| C 反思 (FULL) | 30 轮 | `C_PHASE_MAX_ITER` |
| C 反思 (LIGHT) | 5 轮 | `C_PHASE_MAX_ITER`（信号量少的 high_value 任务） |
| 工具执行超时 | 120s | `TOOL_EXEC_TIMEOUT` |
| LLM 总超时 | 300s | `wall_clock_timeout` |
| 单透镜超时 | 60s | `LENS_TIMEOUT_SECS` |
| 透镜内迭代 | 2轮搜索+1次强制输出 | `LENS_MAX_ITERATIONS` |

### 关键数据流

- **Web 搜索管线**：SearXNG（自建，免费，多引擎聚合）→ Tavily（付费 fallback）
- **URL 读取管线**：trafilatura（快速内容提取）→ Playwright（JS 渲染）→ Jina Reader → curl+regex
- **browser-use**：作为 TOOL 节点存入 NodeVault（`TOOL_browser_agent`），G 搜索发现后动态加载到 Op，非 factory 硬编码
- **知识搜索管线**：SQL LIKE + 向量召回 → signature_gate 硬过滤 → Reranker 精排 → signature_score 加分 → fusion_score 加权融合
- **签名自动注入**：G/Lens 的每次搜索都会自动将 `inferred_signature` 合并到 search args。C 写节点时若未提供签名，自动从内容推断。
- **签名系统**：9 核心字段（硬编码推断）+ 维度注册表（动态，从 DB 学习的自定义维度）
- **蒸发机制**：仅 G 和 Lens 有蒸发。**Op 不蒸发、不截断**，保留完整 ReAct 记忆，倒数第2轮注入系统提醒让 Op 自己输出总结
- **Void 正循环**：Multi-G 搜索未命中 → Blackboard 记录 → C 后自动入库 VOID 节点（每次最多 10 个，向量去重≥ 0.80）→ Scavenger/Fermentor 优先填补

### Multi-G 自适应机制

- **触发**：默认开启（输入≥10字符），`/quick` 跳过，`/deep` 强制 7 透镜
- **探针搜索**：用前 5 个关键词做向量搜索，根据命中数自适应透镜数量：≤2 hits→3 透镜，≤6→5，>6→7，`/deep`→7
- **人格选择**：`PERSONA_ACTIVATION_MAP` 映射 task_kind → 3 个基础人格，`PERSONA_EXTENSION_POOL` 补充到 5/7
- **动态淘汰/递补**：`Blackboard.suggest_persona_swap()` 基于 task_kind 细分胜率，淘汰 win_rate < 0.3 的 persona，从全 16 型池递补（保底保留 2 个原始 base persona）

### Knowledge Arena

- 任务 SUCCESS 且无 FAIL：所有 active_nodes **+boost** confidence（fusion_score 加权）
- 任务 FAILED：所有 active_nodes **-decay** confidence（fusion_score 加权）
- `usage_count` 自动递增，保护节点免于 GC purge

### Persona Arena（在线学习）

- 每次任务完成后，所有参与的 Multi-G persona 被记录 win/loss（按 task_kind 细分）
- `suggest_persona_swap` 根据历史胜率动态替换弱 persona
- **独立于 Knowledge Arena** — 即使 Op 没引用知识节点，persona 表现也会被记录

### 诊断信号（heartbeat 输出）

| 信号 | 来源 | 含义 |
|------|------|------|
| `cache_stats` | `_update_metrics` 累加 | DeepSeek prefix cache 命中率（input_tokens / cache_hit_tokens） |
| `provider_stats` | `NativeHTTPProvider` 类级计数器 + 滑动窗口(100) | 总调用数、重试率、错误率 + **recent_error_rate/recent_retry_rate**（最近100次） |
| `token_efficiency` | `V4Loop._token_history` 滑动窗口（10条） | 平均/最大/最小 tokens per request |
| `kb_entropy` | `NodeVault.get_kb_entropy()` | 低/高 confidence 节点占比，知识库健康度 |
| `persona_stats` | `Blackboard._persona_stats` | 各 persona 全局 win/loss 统计 |
| `signature_drift` | `_signature_drift_events` | C-Phase 签名偏差摘要（blind_spots / false_positives / conflicts） |

### 签名自动学习（Learned Markers）

- C-Phase 写入节点时若签名偏差检测到 blind_spot（推断遗漏），自动调用 `learn_signature_marker` 持久化到 SQLite `learned_signature_markers` 表
- 下次 `infer_metadata_signature` 时，learned markers 在 core inference 之后、dimension registry 之前匹配
- dim_key 格式校验：`[a-z][a-z0-9_]*`，长度 2-30，拦截 LLM 幻觉
- 每个 dim_key 最多 10 个 learned markers

### Dispatch Review

- G 派发前自动审查：重复节点、不存在的节点、超过 6 个节点、签名冲突、缺少前置依赖
- G 可用 `[REVIEW_OVERRIDE]` 强制跳过审查

### Provider 体系

- **核心 failover**（主循环用）：`deepseek → gemini`（仅 2 个），`trust_env=False` 绕过代理
- **FreePoolManager**（daemon/verifier 用）：单例统一管理免费池
  - **唯一注册表**：`groq, cloudflare, siliconflow, dashscope, zhipu, qianfan, zen`（定义在 `provider_manager.py:FreePoolManager.FREE_POOL_NAMES`）
  - **健康追踪**：per-provider success/fail 计数 + 健康分排序，连续 3 次失败标记 DEAD
  - **自动重探**：DEAD provider 每 600s 解除标记给一次机会
  - **deepseek 限频兜底**：所有免费池不可用时用 deepseek，每小时最多 20 次
  - **`_chat()` 包装**：daemon/verifier 统一入口，自动选 provider + 3 次重试 + 健康反馈
  - **pool_status** 写入 heartbeat extra，可诊断
- **`use_proxy` 分离**：`NativeHTTPProvider(use_proxy=True)` → 墙外 provider（groq/cloudflare/openai/gemini/openrouter/zen）走系统代理；国内 provider（deepseek/siliconflow/dashscope/qianfan/zhipu）保持 `trust_env=False`
- **.env 代理注入**：`HTTPS_PROXY=socks5://127.0.0.1:20170`，`ConfigManager._apply_proxies()` 注入 `os.environ`，daemon systemd 服务无需 `Environment=` 行
- **探活**：ProviderRouter failover 后每 60s 尝试恢复首选 provider
- **重试**：流式/非流式均 3 次，5xx 可重试；`WallClockTimeoutError` 不触发 failover

## 四、近期重大改动（倒序）

### 2026-03-22: 因果审计结构性修复（7 项）
- **C-Phase 梯度恢复**：`_determine_c_phase_mode()` 从二极管（FULL/SKIP）改为三级（FULL/LIGHT/SKIP）。LIGHT 条件：high_value=True 但 full_signals<2（单报告+有 artifacts 但无失败/大量变更/空洞等复杂信号）。LIGHT=5 轮，FULL=30 轮。
- **Token budget 守卫**：G+Op 消耗 >80k tokens 时自动将 C-Phase 从 FULL 降级为 LIGHT，防止上下文溢出导致 C 反思质量退化
- **Daemon 竞态修复**：`_mark_as_scavenged` 不再用 `ORDER BY created_at DESC LIMIT 1` 猜最新节点，改为直接传入 `create_meta_tool` 的 `node_id` 参数。用 `get_node_briefs` 获取签名替代依赖 `rows` 变量
- **Provider 滑动窗口**：`NativeHTTPProvider` 新增 `_record_stat()` + `_stats_window`（最近 100 次调用），heartbeat 同时输出全局累计 + `recent_error_rate`/`recent_retry_rate`，解决长期运行后信号被稀释问题
- **Persona 学习持久化**：`persona_stats` 表写入 `workshop_v4.sqlite`，`Blackboard.load_from_db()` 启动时恢复，`record_persona_outcome()` 每次反馈后自动 persist。解决 systemd 重启后 persona 学习归零、`suggest_persona_swap` 永远积累不到阈值的问题
- **Daemon 向量引擎**：`skip_vector_engine=True` → `False`，边缘发现从 SQL LIKE 关键词盲搜升级为语义向量搜索（回退到关键词匹配），"proxy 配置"和"翻墙设置"这类语义相关但措辞不同的节点现在能发现彼此
- **代码卫生**：`provider_manager.py` 死名 `antigravity` → `deepseek`；`url_tool.py` 新增 `atexit` 钩子关闭 Playwright 浏览器防止 Chromium 子进程残留
- **文件**：`loop.py`, `background_daemon.py`, `provider.py`, `provider_manager.py`, `blackboard.py`, `manager.py`, `url_tool.py`

### 2026-03-22: 信息获取升级（SearXNG + trafilatura + Playwright + browser-use）
- **url_tool.py 重写**：4 层 fallback — trafilatura（学术级 HTML→Markdown）→ Playwright headless Chromium（JS 渲染）→ Jina Reader → curl+regex
  - Playwright 浏览器单例复用，lazy 启动
  - trafilatura 对非 JS 页面提取效果极好（腾讯云文章 9288 chars clean markdown）
- **web_tool.py 重写**：SearXNG（自建）→ Tavily（付费 fallback）
  - SearXNG Docker 部署（`--network host`, 代理通过 `HTTPS_PROXY` 环境变量注入）
  - 配置：`/home/chendechusn/Genesis/searxng/settings.yml`
  - 中文查询需 URL 编码（已修复）
- **browser-use 接入**：`browser_use_tool.py` 作为 **TOOL 节点**（`TOOL_browser_agent`, trust_tier=REFLECTION）写入 NodeVault
  - 遵循元信息架构：G 搜索发现 → 放入 active_nodes → Op 阶段 `_load_tool_nodes_from_active_nodes()` 动态注册
  - 用 Groq 免费 LLM 驱动浏览器，节省 DeepSeek token
- **Playwright Chromium**：手动从 Google Chrome for Testing CDN 下载（`curl -x socks5h://...`），解压到 `~/.cache/ms-playwright/chromium-1208/`
- **依赖**：`trafilatura`, `playwright`, `browser-use`, `langchain-openai`
- **文件**：`tools/url_tool.py`, `tools/web_tool.py`, `tools/browser_use_tool.py`

### 2026-03-22: 开放项清理（探活并行化 + verification_action + Tracer cache）
- **FreePoolManager.probe_all()**：串行→并行（`asyncio.gather`），探活总时间 75s→15s
- **verification_action**：collapse 后提取 top entry 的具体验证动作，注入 G 上下文作为 `[建议优先验证]`
- **Tracer cache_hit_tokens**：spans 表新增列 + `log_llm_call` 接受并存储 + `provider_manager.py` 传入值 + 旧表自动 ALTER TABLE 迁移
- **文件**：`provider_manager.py`, `loop.py`, `tracer.py`

### 2026-03-22: FreePoolManager 傻瓜式免费池自管理
- **起因**：daemon 13h 零产出，免费池硬编码 3 处重复（daemon/verifier/provider_manager），探活只在启动时做一次，墙外 provider 因 `trust_env=False` 无法走代理
- **修复**：
  - `provider.py`：新增 `use_proxy: bool = False` 参数，`_get_http_client` 根据此标志决定 `trust_env`
  - `cloud_providers.py`：墙外 provider（groq/cloudflare/openai/gemini/openrouter/zen）加 `use_proxy=True`
  - `provider_manager.py`：新增 `FreePoolManager` 类（~200 行）——单一注册表 + 健康追踪 + 自动重探 + deepseek 限频兜底
  - `background_daemon.py`：删除 `_init_provider` + `_probe_free_providers` 共 50 行，改用 `FreePoolManager._chat()` 包装
  - `verifier.py`：同理改造，删除硬编码列表
  - `.env`：新增 `HTTPS_PROXY=socks5://127.0.0.1:20170`
- **验证结果**（Cycle #1）：
  - 探活：7 provider 中 groq + cloudflare 存活（代理生效），其余 5 个 API key 失效
  - 产出：拾荒 1 + 假设 2 + 验证 3（全部用 groq 免费额度，deepseek 兜底 0 次）
  - 对比：改造前 13h 零产出 → 改造后单 cycle 6 个产出
- **文件**：`provider.py`, `cloud_providers.py`, `provider_manager.py`, `background_daemon.py`, `verifier.py`

### 2026-03-22: 因果闭环审计 + 运行时验证
- **起因**：对前几天的修改做系统性因果审计，发现 4 个代码级问题 + 3 个运行时静默失效
- **代码审查修复**：
  - `manager.py:11` — `timedelta` 提升到顶层 import，删除函数内冗余导入
  - `manager.py:257` — 删除 `learn_signature_marker` 中无效的 `_infer_core_signature.cache_clear()`（learned markers 在 uncached 层应用）
  - `manager.py:786` — 新增 `NodeVault.get_kb_entropy()` 方法，消除 `loop.py` 直接访问 `vault._conn` 的封装泄漏
  - `manager.py:226` — 新增 dim_key 正则校验 `[a-z][a-z0-9_]*`，拦截 LLM 幻觉维度
- **运行时验证**（3 问题 × 151 API calls）发现并修复：
  - **P0**: `task_kind` 有时为 list（如 `["debug","refactor"]`），导致 `_select_personas` 崩溃 → Multi-G 静默降级到 single-G
  - **P1**: `prompt_cache_hit_tokens` 数据管道断开 — API 采集了但 `_update_metrics` 从未累加，heartbeat 不输出
  - **P1**: persona 在线学习被错误嵌套在 `if unique_active_nodes:` 内 — 如果 Op 没引用知识节点，persona 反馈完全跳过
- **运行时验证数据**：
  - 缓存命中率：Q1=39.6%（冷启动）, Q2=82.9%, Q3=84.4%, 总=62.7%
  - 151 API calls, 0 retries, 0 errors, 0 timeouts
  - learned_markers：8 dims/8 markers 从 C-Phase 自动学习
  - kb_entropy：542 nodes, low_confidence=0.6%, high_confidence=50.7%
- **文件**：`loop.py`, `manager.py`

### 2026-03-22: 因果闭环审计（开放项实施）
- **开放项 A — 签名推断自动修正**：`learn_signature_marker` + `_load_learned_markers` + SQLite 持久化
- **开放项 B — 3 个诊断信号**：provider_stats（类级计数器）、kb_entropy（知识库健康度）、token_efficiency（滑动窗口）
- **开放项 C — persona 动态化**：`Blackboard.suggest_persona_swap()` + `record_persona_outcome(task_kind=...)` + `get_persona_multiplier()`
- **文件**：`loop.py`, `manager.py`, `blackboard.py`, `provider.py`

### 2026-03-21: /deep 修复 + G 认知纪律 + 发酵池复活
- **病因**：
  - `/deep` `/quick` 前缀检测在 `user_input[:20]` 上做，但 Discord 在前面拼了频道历史，用户指令被淹没
  - G prompt 缺乏认识论纪律，回复像百科全书式 AI 助手（纸上谈兵，泛泛而谈）
  - 后台守护进程（发酵池）运行中但 21h 全零产出：免费 LLM 池 5/7 API key 失效 + 无持久化日志
- **修复**：
  - `_should_activate_multi_g` 和 `_run_lens_phase`：先提取 `[GENESIS_USER_REQUEST_START]` 后的实际请求，再检查 `/deep` `/quick`
  - `_run_lens_phase` 的 `clean_input` 改用提取后的文本，透镜不再看到频道历史噪音
  - G prompt 加入 [你是谁]（三信息源限定）+ [认知纪律]（区分知识/猜测、行动优先、禁止纸上谈兵、断言可追溯）
  - 后台 daemon 加启动探活（逐个测试 free provider，剔除 401/DNS）+ 持久化日志 `runtime/daemon.log`
- **清理**：`scavenger.py` + `fermentor.py` 归档（已被 `background_daemon.py` 取代）
- **发现**：免费池仅 groq + cloudflare 可用，其余 5 个 API key 失效或 DNS 不通
- **文件**：`loop.py`, `manager.py`, `background_daemon.py`

### 2026-03-21: G-Op 分治派发改革 + Multi-G 白盒化
- **病因**：
  - G 懒政：一次 dispatch 塞太多意图，Op 在黑暗中摸索几十轮，178 次工具调用、133万 tokens
  - `_evaporate_op_messages()` 篡改 Op 自己的 ReAct 记忆，Op "忘记"已读内容并重复读 3-4 遍
  - Multi-G 激活条件太严（依赖 task_kind），实际运行中从未触发
- **修复**：
  - `OP_MAX_ITERATIONS` 30→12，短 Op + 多次 dispatch
  - 移除 Op 内部蒸发和截断：Op 保留完整 ReAct 记忆
  - Op 优雅终止：倒数第 2 轮注入系统提醒，让 Op 自己输出总结报告
  - G prompt 加入分治纪律：每次 dispatch 只给原子任务（5-10步），含正反例
  - Op→G 信息增强：`raw_output` 500→2000，timeout 时提取 findings
  - Multi-G 激活改为默认开启（输入≥10字符），`/quick` 跳过，`/deep` 强制 7 透镜
  - Multi-G 白盒化：Discord 展示 lens_start/lens_search/lens_done 事件
- **清理**：删除 11 个 C-Process 污染节点 + 4 个死代码文件
- **发现**：Multi-G `verification_action` 仅存储建议，未有代码执行它（最小试验机制未部署）
- **文件**：`loop.py`, `manager.py`, `discord_bot.py`

### 2026-03-21: 项目文档清理
- 31 个一次性研究报告/分析文档 → `nanogenesis/archive/genesis_docs/`
- 21 个根目录散落的 debug/test 脚本 → `nanogenesis/archive/genesis_root_junk/`
- 14 个一次性迁移脚本 → `nanogenesis/archive/genesis_scripts/`
- squashfs-root（AppImage 解包）→ `nanogenesis/archive/genesis_squashfs/`
- 删除空/废弃 DB（genesis_v4.db, knowledge.db, workshop_v4.sqlite）和日志
- v4/ 中清理 .backup 和 .service 文件

### 2026-03-21: 签名扩展断路修复 + 维度注册表
- **病因**：C-Process 发明的自定义维度是 write-only，搜索时永远不匹配
- **修复**：
  - `_build_dimension_registry()`：启动时扫全库，建 `{value→key}` 反向索引（freq≥3）
  - `infer_metadata_signature` 拆为 `_infer_core_signature`(缓存) + 注册表匹配(动态)
  - 数组值排序去重：`["debug","configure"]` == `["configure","debug"]`
  - 单节点自定义维度上限 5 个
  - 自定义维度评分从 +1 提升到 +2（与 soft_keys 同权）
  - 运营垃圾维度黑名单（timestamp, port 等）
- **文件**：`manager.py`, `node_tools.py`

### 2026-03-20: Multi-G 缓存命中率修复 + Void 系统
- **病因**：每个透镜 prompt 第一行不同（persona），导致跨透镜零缓存共享
- **修复**：
  - Lens/G/C prompt 前缀重排（共享内容在前，个性化在后）
  - VOID 写入从 lens 后移到 C 后（避免改变 digest 导致 G 缓存失效）
  - Void 自动入库从 C-Process 剥离为基础设施 `_auto_record_voids`
  - 收敛度阈值 0.6→0.5
- **文件**：`loop.py`, `manager.py`, `blackboard.py`

## 五、已知问题 / 开放课题

| 问题 | 严重度 | 状态 |
|------|--------|------|
| ~~C-Process 自定义维度多为运营流水账~~ | ~~中~~ | ✅ prompt 已加反堆砌规则+鼓励/禁止维度列表 |
| ~~task_kind 历史数据数组排列爆炸~~ | ~~低~~ | ✅ 两轮回填 314 个签名修正，单字段 cap=3 |
| Memory Evolution（旧节点签名回溯更新）| 低 | 未来方向，需观察注册表效果后决定 |
| DB 路径在 ~/.nanogenesis/ 下（历史遗留） | 低 | 不影响功能，仅命名混淆 |
| ~~墙外免费池 (groq/cloudflare) 因 trust_env=False 无法走代理~~ | ~~低~~ | ✅ `use_proxy=True` + `.env` 注入 `HTTPS_PROXY` |
| 免费池 5/7 API key 失效 (siliconflow/dashscope/zhipu/qianfan/zen) | 低 | FreePoolManager 自动标记 DEAD + deepseek 兜底，groq/cloudflare 可用即可运转 |
| SearXNG 引擎偶尔 timeout（代理链路不稳定） | 低 | 自动 fallback 到 Tavily |
| ~~C 写入的错误签名无纠正机制~~ | ~~中~~ | ✅ `audit_signatures()` + learned_markers 自动修正 |
| ~~prompt_cache_hit_tokens 数据管道断开~~ | ~~中~~ | ✅ `_update_metrics` 累加 + heartbeat 输出 cache_stats |
| ~~task_kind 为 list 导致 Multi-G 崩溃~~ | ~~高~~ | ✅ `_select_personas` + `record_persona_outcome` 均做 list→str 降级 |
| ~~persona 学习嵌套在 active_nodes 条件内~~ | ~~中~~ | ✅ 提到外层，独立于 Knowledge Arena |
| ~~Multi-G verification_action 未实际执行~~ | ~~低~~ | ✅ collapse 后 top entry 的 verification_action 注入 G 上下文作为「建议优先验证」 |
| ~~daemon 启动探活在 async 上下文中被跳过~~ | ~~低~~ | ✅ FreePoolManager.probe_all() 在首次 run_cycle 时调用 |
| ~~Tracer 不记录 per-call cache_hit_tokens~~ | ~~低~~ | ✅ spans 表新增 `cache_hit_tokens` 列，`log_llm_call` 每次调用记录 |

## 六、关键文件速查

| 文件 | 职责 | 热点函数 |
|------|------|----------|
| `v4/loop.py` (1816行) | 核心状态机 | `_run_main_loop`, `_run_op_phase`, `_run_c_phase`, `_run_lens_phase`, `_select_personas`, `_update_metrics`, `_evaporate_*`, `_auto_record_voids`, `_review_task_payload` |
| `v4/manager.py` (2020行) | NodeVault + 签名系统 + prompt构建 | `infer_metadata_signature`, `_build_dimension_registry`, `learn_signature_marker`, `get_kb_entropy`, `normalize_metadata_signature`, `build_g_prompt`, `build_lens_prompt`, `build_op_prompt` |
| `tools/node_tools.py` | 搜索+写入工具 | `_signature_gate`, `_signature_score`, `_fusion_score`, `execute` |
| `core/provider.py` | httpx LLM 调用 | `chat`, `_stream_with_httpx`, `_parse_response`（`trust_env=self.use_proxy` 在 `_get_http_client`） |
| `core/provider_manager.py` | Failover 路由 + FreePoolManager | `chat`（探活逻辑）, `FreePoolManager`（单例，健康追踪+自动重探+deepseek兜底） |
| `core/config.py` | 单例配置 | `_load_dotenv`, `_apply_proxies` |
| `core/tracer.py` | 链路追踪 | SQLite `runtime/traces.db`，可选 Langfuse |
| `factory.py` | Agent 工厂 | 注册 16 个工具（分 5 组，单组失败不影响其余） |
| `v4/blackboard.py` (530行) | Multi-G 共享黑板 + Persona Arena | `record_search_void`, `collapse`, `render_for_g`, `record_persona_outcome`, `suggest_persona_swap`, `get_persona_multiplier` |
| `v4/vector_engine.py` | 向量引擎+Reranker | `search`, `rerank`（bge-small-zh + bge-reranker-base） |
| `v4/background_daemon.py` | 统一后台守护进程（拾荒+发酵+验证+GC） | `_task_scavenge`, `_task_discover_edges`, `_task_generate_hypotheses`, `_task_verify` |

## 七、设计原则检查清单

改代码前过一遍：

- [ ] **Prefix caching**：prompt 前缀是否保持稳定？（共享内容在前，个性化在后）
- [ ] **Context Firewall**：Op 能否看到不该看的东西？
- [ ] **LLM 调用次数**：是否增加成本？
- [ ] **签名对称性**：写入侧和搜索侧是否都能匹配？
- [ ] **注册表黑名单**：新的签名字段是否应加入 `_DIM_OPERATIONAL_BLACKLIST`？
- [ ] **工具权限**：新工具是否需加入 `OP_BLOCKED_TOOLS` 或 `c_tool_names`？
- [ ] **蒸发兼容**：新的 TOOL 消息是否能被安全压缩为存根？
- [ ] **超时安全**：新的工具/LLM 调用是否被 `asyncio.wait_for` 保护？
- [ ] **use_proxy 分离**：新 provider 是墙外还是国内？墙外需 `use_proxy=True`，国内保持 `False`
- [ ] **诊断信号**：修改是否影响 heartbeat 中的 6 个诊断信号（cache/provider/token/kb/persona/drift）？
- [ ] **Persona 学习**：是否影响 persona outcome 记录？确保不被嵌套在无关条件内
- [ ] **task_kind 类型安全**：signature 中的字段可能是 list 而非 str，是否做了类型防御？
- [ ] **是否需要更新本文件？**

## 八、工具清单（factory.py 注册顺序，共 16 个）

| 组 | 工具名 | G | Op | C |
|------|---------|---|----|----|  
| file | `read_file`, `write_file`, `append_file`, `list_directory` | ✘ | ✔ | ✘ |
| shell | `shell` | ✘ | ✔ | ✘ |
| web | `web_search`（SearXNG→Tavily）, `read_url`（trafilatura→Playwright→Jina→curl） | ✘ | ✔ | ✘ |
| skill | `skill_creator` | ✘ | ✔ | ✘ |
| node | `search_knowledge_nodes` | ✔ | ✘ | ✔ |
| node | `record_context_node`, `record_lesson_node` | ✘ | ✘ | ✔ |
| node | `create_meta_node`, `create_graph_node`, `create_node_edge` | ✘ | ✘ | ✔ |
| node | `delete_node`, `record_tool_node` | ✘ | ✘ | ✔ |
| virtual | `dispatch_to_op` | ✔ | ✘ | ✘ |
