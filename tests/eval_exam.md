# Multi-G 认知基准测试：考题

## 背景（请一并复制给空白 Claude）

Genesis 是一个本地运行的 AI Agent 系统，架构如下：
- 核心循环：G（规划）→ Op（执行）→ C（反思）三阶段
- G 阶段：接收用户请求，搜索本地知识库（NodeVault），制定执行蓝图
- Op 阶段：拿着蓝图调用 12 个工具（read_file, write_file, shell, web_search 等）执行
- C 阶段：反思执行结果，提取经验教训写回知识库
- 知识库 NodeVault：SQLite + 向量搜索（BAAI/bge-small-zh-v1.5），存储 LESSON/CONTEXT/ASSET/EPISODE/EVENT 等类型节点
- LLM 后端：DeepSeek-chat（通过 HTTP API，经代理访问）
- 运行环境：Linux 服务器，systemd 管理，通过 Discord bot 接收用户输入
- 后台守护进程：Scavenger（知识拾荒）、Fermentor（知识发酵）、Verifier（知识验证）

## 考题

请逐题分析，给出你认为的关键维度、可能的根因、以及你会建议的解决方案。

---

### Q1: 网络延迟诊断

Genesis 运行在一台 Linux 服务器上，通过 SOCKS5 代理访问 DeepSeek API 和 Discord API。最近出现间歇性的消息延迟（5-10 秒），但日志中没有明显错误。可能的原因是什么？你会怎么排查？

---

### Q2: 知识库搜索性能

NodeVault 使用 SQLite 存储知识节点，向量搜索用本地 embedding 模型（BAAI/bge-small-zh-v1.5）。当节点数超过 500 时搜索明显变慢。瓶颈可能在哪？如何优化？

---

### Q3: 多 LLM Provider 容错

Genesis 需要支持多个 LLM provider（DeepSeek、OpenAI 兼容接口等），通过 HTTP 调用。如何设计一个健壮的 provider 容错机制？考虑：failover、超时、SSE 流式响应解析、JSON 修复。

---

### Q4: Agent 知识质量控制

Genesis 的 C 阶段会自动提取经验教训（LESSON 节点）写入知识库。时间一长，知识库可能出现：重复、过时、矛盾的节点。如何设计一个知识质量控制机制？

---

### Q5: 从单 Agent 到多视角分析

Genesis 目前是单 agent 循环。如果要让 G 阶段从多个认知视角分析问题（类似让不同思维风格的人同时思考同一个问题），你会怎么设计这个多视角机制？考虑：如何让不同视角真正产生差异而不是重复？如何合并多个视角的结论？
