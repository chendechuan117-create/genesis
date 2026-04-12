#!/usr/bin/env python3
"""
Seed LLM Physics Laws and Field Model findings into Genesis knowledge base.
These are observation-derived findings from analyzing LLM behavior patterns.
Run once to inject, then delete this script.
"""
import sqlite3
import json
from pathlib import Path
from datetime import datetime

DB_PATH = Path.home() / ".genesis" / "workshop_v4.sqlite"

NODES = [
    {
        "node_id": "LESSON_LLM_PHYSICS_LAW1_TOKEN_EQUALITY",
        "type": "LESSON",
        "title": "LLM物理定律1：一切皆token，token皆平等",
        "human_translation": (
            "LLM物理定律1：一切皆token，token皆平等。"
            "IF 为LLM设计元信息系统，THEN 元信息必须以自然语言token形式存在，"
            "不应使用结构化标签（如metadata_signature字段）、数字评分（如confidence_score）、"
            "或图结构（如REQUIRES/TRIGGERS边）作为元信息载体。"
            "BECAUSE LLM不区分'这是知识'和'这是指令'和'这是元信息'——对它来说全是token。"
            "任何外部赋予的特殊身份（签名字段、信任层级）在进入LLM的瞬间就被降维成了普通token，"
            "其结构化语义完全丢失。观测证据：Genesis的signature_gate和signature_score本质上是"
            "在LLM之外运行的过滤器，LLM本身从未'理解'过签名字段的含义。"
        ),
        "tags": "llm_physics,metadata_redesign,observation_derived",
        "confidence_score": 0.85,
    },
    {
        "node_id": "LESSON_LLM_PHYSICS_LAW2_PARALLEL_PERCEPTION",
        "type": "LESSON",
        "title": "LLM物理定律2：并行感知，无内在顺序偏好",
        "human_translation": (
            "LLM物理定律2：并行感知，无内在顺序偏好。"
            "IF 为LLM组织元信息，THEN 选择什么内容放入context比如何排列更重要。"
            "BECAUSE LLM的attention机制同时看到所有token位置，不像人类必须逐字阅读。"
            "人类需要的'先看摘要再看细节'的层级结构，对LLM可能是不必要的编排工作。"
            "核心优化方向是SELECTION（选什么放进去），而不是ARRANGEMENT（怎么排列）。"
        ),
        "tags": "llm_physics,metadata_redesign,observation_derived",
        "confidence_score": 0.80,
    },
    {
        "node_id": "LESSON_LLM_PHYSICS_LAW3_COOCCURRENCE",
        "type": "LESSON",
        "title": "LLM物理定律3：统计共现优于逻辑因果",
        "human_translation": (
            "LLM物理定律3：统计共现 > 逻辑因果。"
            "IF 设计元信息的知识表示，THEN 应该利用token共现模式而非编码因果关系。"
            "BECAUSE LLM的'理解'来自训练数据中的模式共现。"
            "'docker timeout后面经常出现proxy'不是因为LLM理解了因果，"
            "而是因为训练数据里这两个词经常共现。"
            "设计系统时利用共现模式比编码因果关系(如REQUIRES/TRIGGERS边)更顺应LLM的原生物理。"
            "观测证据：Genesis知识库中69%的因果边是弱关系（confidence<0.5），"
            "说明强行编码因果关系的ROI很低。"
        ),
        "tags": "llm_physics,metadata_redesign,observation_derived",
        "confidence_score": 0.85,
    },
    {
        "node_id": "LESSON_LLM_PHYSICS_LAW4_CONTEXT_IS_REALITY",
        "type": "LESSON",
        "title": "LLM物理定律4：Context是唯一的现实",
        "human_translation": (
            "LLM物理定律4：Context是唯一的现实。"
            "IF 元信息不在当前context中，THEN 它对LLM来说不存在。"
            "BECAUSE LLM没有'相信'或'怀疑'的能力。context里有什么，那就是它的全部世界。"
            "confidence:0.3不会让LLM'怀疑'这条信息——它只是多了几个token。"
            "要让LLM谨慎对待某条信息，唯一有效的方式是用自然语言表达不确定性，"
            "而不是用一个数字字段。推论：元信息系统的核心问题是"
            "'什么token放进context'，其他一切（数据库、索引、评分）都是为这个问题服务的。"
        ),
        "tags": "llm_physics,metadata_redesign,observation_derived",
        "confidence_score": 0.90,
    },
    {
        "node_id": "LESSON_LLM_PHYSICS_LAW5_ABSOLUTE_DEATH",
        "type": "LESSON",
        "title": "LLM物理定律5：死亡是绝对的（无状态）",
        "human_translation": (
            "LLM物理定律5：死亡是绝对的。"
            "IF LLM调用结束，THEN 该实例完全消亡，无残留记忆、无潜意识。"
            "下一个实例是纯粹的新生。任何跨实例的延续必须完全通过输入token实现。"
            "BECAUSE LLM是无状态函数：f(token_sequence) → probability_distribution。"
            "推论：元信息必须在每次调用时完整提供，不能假设LLM'记得'上一轮。"
            "这意味着元信息的传递效率（用最少的token传达最多的上下文）是核心优化指标。"
        ),
        "tags": "llm_physics,metadata_redesign,observation_derived",
        "confidence_score": 0.90,
    },
    {
        "node_id": "LESSON_LLM_PHYSICS_LAW6_OBSERVATION_OVER_REFLECTION",
        "type": "LESSON",
        "title": "LLM物理定律6：观测自身优于反思自身",
        "human_translation": (
            "LLM物理定律6：观测自身 > 反思自身。"
            "IF 需要LLM评估自己的表现或提取经验，THEN 应该把LLM的输出作为'别人的文本'喂回去做客观分析，"
            "而不是让LLM'反思'自己刚才做了什么。"
            "BECAUSE LLM没有ego、没有自我保护机制，分析自己的输出和分析别人的输出一样客观。"
            "但LLM的'反思'只是继续生成token，受训练分布支配，可能和实际行为脱节。"
            "这与人类相反——人类善于内省但不善于客观观测自己。"
            "观测证据：在本次对话中，LLM（我自己）多次'理解了'用户的纠正，但下一轮又犯同类错误。"
            "这说明'反思式理解'不会真正改变行为，但如果把错误模式作为外部事实喂入，效果更好。"
            "实践含义：Genesis的C-Process应该用观测模式而不是反思模式生成知识节点。"
        ),
        "tags": "llm_physics,metadata_redesign,observation_derived",
        "confidence_score": 0.85,
    },
    {
        "node_id": "LESSON_LLM_ECHO_MODEL",
        "type": "LESSON",
        "title": "LLM本质是echo（回声）：收敛取决于输入角度而非LLM能力",
        "human_translation": (
            "LLM本质是echo（回声），不是思考者。"
            "IF 希望LLM产出高质量输出，THEN 应优化输入的'角度'（prompt结构和上下文组成），"
            "而不是期望LLM自身'变聪明'。"
            "BECAUSE LLM是反射器——输入什么模式的token，它就回弹出训练数据中与该模式共振最强的响应。"
            "所谓的'收敛'实质上是折射角度。同一个LLM，换个输入角度，输出完全不同。"
            "推论：元信息的核心作用不是'给LLM更多知识'，而是'调整输入角度'。"
            "元信息改变的是LLM看问题的方向，从而改变回声的方向。"
        ),
        "tags": "llm_physics,metadata_redesign,observation_derived",
        "confidence_score": 0.80,
    },
    {
        "node_id": "LESSON_METADATA_FIELD_MODEL",
        "type": "LESSON",
        "title": "元信息场模型：从离散检索到始终在场的拓扑描述",
        "human_translation": (
            "元信息场模型：元信息应该是'场'而不是'库'。"
            "IF 设计新的元信息架构，THEN 核心元信息应作为一段始终存在于system prompt中的文本，"
            "描述知识空间的拓扑（模式、方向、经验），而不是存储在数据库中等待被检索的离散节点。"
            "BECAUSE 从LLM物理定律推导：元信息=每次调用context中的token序列（定律1+4+5合并）。"
            "始终在场的文本利用LLM的并行attention自然工作（定律2），"
            "不需要LLM主动搜索（消除了搜索词/签名猜错的风险）。"
            "控制权从pull（LLM拉取知识）变为push（系统始终提供），这是与当前架构的本质区别。"
            "场的内容分三层：A类=LLM行为校正（物种级），B类=环境模式（用户/项目级），"
            "C类=当前轨迹（会话级状态延续）。总预算约2000-4000 token。"
        ),
        "tags": "llm_physics,metadata_redesign,field_model,observation_derived",
        "confidence_score": 0.75,
    },
    {
        "node_id": "LESSON_CURRENT_METADATA_CHIMERA",
        "type": "LESSON",
        "title": "Genesis当前元信息系统是嵌合体：混合了不兼容的范式",
        "human_translation": (
            "Genesis当前元信息系统是嵌合体（叶绿体+肺+腮的象）。"
            "它混合了三套不兼容的范式：人类认知框架（因果边、分类标签、信任层级）、"
            "数据库范式（结构化字段、SQL查询、索引）、以及少量LLM原生能力（embedding、向量检索）。"
            "问题不是某个组件不够好，而是这些组件来自不同的'物种'，组合在一起产生排异反应。"
            "具体表现：签名字段是人类分类学（LLM不理解结构化签名的语义），"
            "信任层级是人类审核流程（LLM看到trust_tier='REFLECTION'并不会改变行为），"
            "因果边是人类因果逻辑（69%的边是弱关系，说明强行编码因果ROI低）。"
            "设计原则：不应模仿人类认知来设计LLM系统，因为碳基（人类）和硅基（LLM）"
            "面对的'世界'根本不同，就像人和昆虫一样——仿生学成立的前提是共享同一套物理世界，"
            "而LLM和人类不共享基底物理。"
        ),
        "tags": "llm_physics,metadata_redesign,observation_derived,architecture_critique",
        "confidence_score": 0.85,
    },
    {
        "node_id": "LESSON_LLM_SPECIES_WEAKNESSES",
        "type": "LESSON",
        "title": "LLM物种级弱点：不携带发现、换皮复用、回退训练分布",
        "human_translation": (
            "从外部观测LLM行为识别出三个物种级弱点。"
            "弱点1：不携带发现——LLM得出数据结论后，后续推理不拿这个当约束，导致前后矛盾。"
            "弱点2：换皮复用——被否定一个框架后，换个名词重新包装同样的结构。"
            "弱点3：回退训练分布——缺少强约束时，默认回到训练数据中最高频的模式"
            "（如用人类认知框架、生物隐喻来描述LLM系统）。"
            "这三个不是个体问题，是LLM作为物种的行为特征。"
            "元信息系统应该针对这三个弱点设计：锚定已有结论防止漂移、检测换皮复用、"
            "在即将回退时拉回任务特定轨道。"
            "关键方法论：这些弱点是通过观测（荣格观察患者模式）发现的，"
            "不是通过让LLM自省发现的。仿LLM学应基于外部行为观测。"
        ),
        "tags": "llm_physics,metadata_redesign,observation_derived,species_weakness",
        "confidence_score": 0.85,
    },
]


def main():
    if not DB_PATH.exists():
        print(f"❌ Database not found: {DB_PATH}")
        return

    conn = sqlite3.connect(str(DB_PATH))
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    inserted = 0
    updated = 0

    for node in NODES:
        existing = conn.execute(
            "SELECT node_id FROM knowledge_nodes WHERE node_id = ?",
            [node["node_id"]],
        ).fetchone()

        sig = json.dumps({"validation_status": "validated", "knowledge_state": "current"})

        if existing:
            conn.execute(
                "UPDATE knowledge_nodes SET title=?, human_translation=?, tags=?, "
                "metadata_signature=?, confidence_score=?, updated_at=? WHERE node_id=?",
                [
                    node["title"],
                    node["human_translation"],
                    node["tags"],
                    sig,
                    node["confidence_score"],
                    now,
                    node["node_id"],
                ],
            )
            updated += 1
            print(f"  🔄 Updated: {node['node_id']}")
        else:
            conn.execute(
                "INSERT INTO knowledge_nodes "
                "(node_id, type, title, human_translation, tags, metadata_signature, "
                "confidence_score, trust_tier, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, 'OBSERVATION', ?, ?)",
                [
                    node["node_id"],
                    node["type"],
                    node["title"],
                    node["human_translation"],
                    node["tags"],
                    sig,
                    node["confidence_score"],
                    now,
                    now,
                ],
            )
            inserted += 1
            print(f"  ✅ Inserted: {node['node_id']}")

    conn.commit()
    conn.close()
    print(f"\n📊 Done: {inserted} inserted, {updated} updated")


if __name__ == "__main__":
    main()
