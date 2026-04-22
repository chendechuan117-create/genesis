"""
节点工具公共基类和共享常量。

从 node_tools.py 提取，供 node_tools.py 和 search_tool.py 共同引用，
避免循环导入。
"""

from genesis.core.base import Tool
from genesis.v4.manager import NodeVault, METADATA_SIGNATURE_FIELDS

# 5 个写入类 Tool 共享的可选信任字段 Schema
TRUST_SCHEMA_PROPERTIES = {
    "metadata_signature": {
        "type": "object",
        "description": "环境/任务签名。核心字段: os_family, language, framework, runtime, error_kind, task_kind, target_kind, environment_scope, validation_status。也接受 observed_environment_scope / applies_to_environment_scope 这类环境元信息，以及任意自定义维度（如 polarity, maturity, user_preference 等），系统会自动保存和检索。",
        "properties": {
            **{field: {"type": "string", "description": f"{field} 签名"} for field in METADATA_SIGNATURE_FIELDS if field != "metadata_schema_version"},
            "metadata_schema_version": {"type": "string", "description": "内部 contract 版本；通常由系统自动补全"},
            "observed_environment_scope": {"type": "string", "description": "这条知识是在哪个环境面被观察到的"},
            "observed_environment_epoch": {"type": "string", "description": "观察发生时的环境 epoch"},
            "applies_to_environment_scope": {"type": "string", "description": "这条知识默认适用于哪个环境面"},
            "applies_to_environment_epoch": {"type": "string", "description": "这条知识默认适用的环境 epoch"},
        },
        "additionalProperties": {"type": "string"}
    },
    "last_verified_at": {"type": "string", "description": "可选。最近验证时间，建议 ISO 或 'YYYY-MM-DD HH:MM:SS'。"},
    "verification_source": {"type": "string", "description": "可选。验证依据来源，如 command_output, manual_check, reflection。"}
}


class BaseNodeTool(Tool):
    """所有节点管理工具的公共基类，统一 vault 初始化。"""

    # V2 点线面工具的跨实例共享状态（同一轮 GP 内）
    _round_state: dict = {}  # {'last_point_id': str, 'insight_markers': [str]}

    def __init__(self):
        self.vault = NodeVault()
