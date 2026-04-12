from genesis.core.base import Tool

class _TempTool(Tool):
    @property
    def name(self) -> str:
        return "record_lesson_node"

    @property
    def description(self) -> str:
        return "Fake placeholder"

    @property
    def parameters(self) -> dict:
        return {}

    async def execute(self):
        return ""