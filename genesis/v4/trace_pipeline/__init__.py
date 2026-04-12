"""
Genesis Trace Analysis Pipeline — 确定性元信息提取

从执行轨迹 (traces.db spans) 中提取结构化实体和关系，
零 LLM，每个产出可溯源到原始 span_id。

架构类比 GitNexus:
  GitNexus: source files → tree-sitter AST → symbols → relations → communities → processes
  Genesis:  tool spans   → rule engine     → entities → relations → communities → patterns
"""
