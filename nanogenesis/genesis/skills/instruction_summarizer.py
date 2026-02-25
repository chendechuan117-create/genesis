import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from genesis.core.base import Tool

class InstructionSummarizer(Tool):
    @property
    def name(self) -> str:
        return "instruction_summarizer"
        
    @property
    def description(self) -> str:
        return "专门用于总结用户简短指令的工具，提取核心要求（如‘不求助’、‘自行绕过验证码’、‘找代理’）并重组为简洁陈述。"
        
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "instruction_text": {"type": "string", "description": "需要总结的原始指令文本"}
            },
            "required": ["instruction_text"]
        }
        
    async def execute(self, instruction_text: str) -> str:
        # 核心关键词/短语映射
        key_points = {
            '不提供任何密码或现成资源': '不提供密码或资源',
            '遇到验证码自己想办法找工具绕过': '自行解决验证码',
            '遇到防火墙自己找代理策略': '自行配置代理绕过防火墙',
            '不要问我，去执行吧': '独立执行，不求助',
            '整个过程': '整个任务流程中'
        }
        
        # 提取和重组
        summary_parts = []
        for phrase, meaning in key_points.items():
            if phrase in instruction_text:
                summary_parts.append(meaning)
        
        # 如果未匹配到关键词，则进行简单截断
        if not summary_parts:
            if len(instruction_text) > 100:
                return instruction_text[:97] + "..."
            return instruction_text
        
        # 生成最终摘要
        final_summary = "要求：在" + "，".join(summary_parts) + "。"
        return final_summary