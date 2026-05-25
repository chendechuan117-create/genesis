import asyncio
from pathlib import Path

from genesis.core.registry import ToolRegistry
from genesis.tools.skill_creator_tool import SkillInventoryTool


class _RegisteredProbeTool:
    @property
    def name(self):
        return "registered_probe"

    @property
    def description(self):
        return "registered probe"

    @property
    def parameters(self):
        return {"type": "object", "properties": {}, "required": []}

    async def execute(self):
        return "ok"


def test_skill_inventory_reports_registered_orphan_rejected_and_non_tool_files(tmp_path):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    (skills_dir / "registered_probe.py").write_text(
        "from genesis.core.base import Tool\n"
        "class RegisteredProbe(Tool):\n"
        "    @property\n"
        "    def name(self):\n"
        "        return 'registered_probe'\n"
        "    @property\n"
        "    def description(self):\n"
        "        return 'registered probe'\n"
        "    @property\n"
        "    def parameters(self):\n"
        "        return {'type': 'object', 'properties': {}, 'required': []}\n"
        "    async def execute(self):\n"
        "        return 'ok'\n",
        encoding="utf-8",
    )
    (skills_dir / "orphan_probe.py").write_text(
        "from genesis.core.base import Tool\n"
        "class OrphanProbe(Tool):\n"
        "    @property\n"
        "    def name(self):\n"
        "        return 'orphan_probe'\n"
        "    @property\n"
        "    def description(self):\n"
        "        return 'orphan probe'\n"
        "    @property\n"
        "    def parameters(self):\n"
        "        return {'type': 'object', 'properties': {}, 'required': []}\n"
        "    async def execute(self):\n"
        "        return 'ok'\n",
        encoding="utf-8",
    )
    (skills_dir / "unsafe_probe.py").write_text(
        "import os\n"
        "from genesis.core.base import Tool\n"
        "class UnsafeProbe(Tool):\n"
        "    @property\n"
        "    def name(self):\n"
        "        return 'unsafe_probe'\n"
        "    @property\n"
        "    def description(self):\n"
        "        return 'unsafe probe'\n"
        "    @property\n"
        "    def parameters(self):\n"
        "        return {'type': 'object', 'properties': {}, 'required': []}\n"
        "    async def execute(self):\n"
        "        return 'ok'\n",
        encoding="utf-8",
    )
    (skills_dir / "plain_module.py").write_text("VALUE = 1\n", encoding="utf-8")

    registry = ToolRegistry()
    registry.register(_RegisteredProbeTool())
    tool = SkillInventoryTool(registry=registry, skills_dir=skills_dir)

    report = tool.build_inventory(include_non_tools=True)
    by_file = {item["file"]: item for item in report["items"]}

    assert by_file["registered_probe.py"]["status"] == "registered"
    assert by_file["registered_probe.py"]["registered"] is True
    assert by_file["orphan_probe.py"]["status"] == "orphan_candidate"
    assert by_file["unsafe_probe.py"]["status"] == "safety_rejected"
    assert by_file["plain_module.py"]["status"] == "missing_tool_subclass"
    assert report["status_counts"]["registered"] == 1
    assert report["status_counts"]["orphan_candidate"] == 1
    assert report["status_counts"]["safety_rejected"] == 1
    assert report["status_counts"]["missing_tool_subclass"] == 1


def test_skill_inventory_does_not_import_skill_files(tmp_path):
    skills_dir = tmp_path / "skills"
    marker = tmp_path / "import_side_effect"
    skills_dir.mkdir()
    (skills_dir / "side_effect_probe.py").write_text(
        "from pathlib import Path\n"
        f"Path({str(marker)!r}).write_text('imported', encoding='utf-8')\n"
        "from genesis.core.base import Tool\n"
        "class SideEffectProbe(Tool):\n"
        "    @property\n"
        "    def name(self):\n"
        "        return 'side_effect_probe'\n"
        "    @property\n"
        "    def description(self):\n"
        "        return 'side effect probe'\n"
        "    @property\n"
        "    def parameters(self):\n"
        "        return {'type': 'object', 'properties': {}, 'required': []}\n"
        "    async def execute(self):\n"
        "        return 'ok'\n",
        encoding="utf-8",
    )

    tool = SkillInventoryTool(registry=ToolRegistry(), skills_dir=skills_dir)
    output = asyncio.run(tool.execute(include_non_tools=True))

    assert "side_effect_probe.py" in output
    assert not marker.exists()


def test_factory_registers_skill_inventory_without_importing_factory():
    factory_source = Path(__file__).resolve().parents[1].joinpath("factory.py").read_text(encoding="utf-8")

    assert "SkillCreatorTool, SkillInventoryTool" in factory_source
    assert "tools.register(SkillInventoryTool(tools))" in factory_source
