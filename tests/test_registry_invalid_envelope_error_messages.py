import unittest

from genesis.core.base import Tool
from genesis.core.registry import ToolRegistry


class _DummyTool(Tool):
    @property
    def name(self) -> str:
        return "dummy_invalid_envelope"

    @property
    def description(self) -> str:
        return "dummy"

    @property
    def parameters(self) -> dict:
        return {"type": "object", "properties": {}}

    async def execute(self, **kwargs) -> str:
        return "ok"


class RegistryInvalidEnvelopeErrorMessageTest(unittest.IsolatedAsyncioTestCase):
    async def test_invalid_arguments_envelope_reports_nested_key_semantics(self):
        reg = ToolRegistry()
        reg.register(_DummyTool())

        result = await reg.execute("dummy_invalid_envelope", {"arguments": "oops"})

        self.assertIn("arguments envelope", result)
        self.assertIn("object/dict", result)
        self.assertIn("str", result)
        self.assertNotIn("收到 dict", result)

    async def test_invalid_input_envelope_reports_nested_key_semantics(self):
        reg = ToolRegistry()
        reg.register(_DummyTool())

        result = await reg.execute("dummy_invalid_envelope", {"input": ["oops"]})

        self.assertIn("input envelope", result)
        self.assertIn("object/dict", result)
        self.assertIn("list", result)
        self.assertNotIn("收到 dict", result)

    async def test_invalid_arguments_envelope_log_includes_nested_value_shape_summary(self):
        reg = ToolRegistry()
        reg.register(_DummyTool())

        with self.assertLogs("genesis.core.registry", level="ERROR") as cm:
            result = await reg.execute("dummy_invalid_envelope", {"arguments": "oops"})

        self.assertIn("arguments envelope", result)
        joined = "\n".join(cm.output)
        self.assertIn("nested_value_shape=", joined)
        self.assertIn("str(len=4, sample='oops')", joined)

    async def test_invalid_input_envelope_log_includes_truncated_nested_value_shape_summary(self):
        reg = ToolRegistry()
        reg.register(_DummyTool())
        payload = {"input": [{"deep": list(range(20))}] * 5}

        with self.assertLogs("genesis.core.registry", level="ERROR") as cm:
            result = await reg.execute("dummy_invalid_envelope", payload)

        self.assertIn("input envelope", result)
        joined = "\n".join(cm.output)
        self.assertIn("nested_value_shape=", joined)
        self.assertIn("list(len=5, sample=[dict(deep:list(len=20", joined)
        self.assertIn("...", joined)

    async def test_kwargs_envelope_log_includes_stable_shape_summary_and_marker(self):
        reg = ToolRegistry()
        reg.register(_DummyTool())
        payload = {"kwargs": {"z": [1, 2, 3, 4], "alpha": {"nested": "v" * 40}}}

        with self.assertLogs("genesis.core.registry", level="ERROR") as cm:
            result = await reg.execute("dummy_invalid_envelope", payload)

        self.assertIn("不支持 kwargs envelope", result)
        joined = "\n".join(cm.output)
        self.assertIn("kwargs_envelope_shape=", joined)
        self.assertIn("kwargs_envelope", joined)
        self.assertIn("dict(alpha:dict(nested:str(len=40", joined)
        self.assertIn("z:list(len=4, sample=[int, int, int, ...])", joined)


    async def test_sentinel_kwargs_envelope_shape_collection_probe(self):
        reg = ToolRegistry()
        reg.register(_DummyTool())

        with self.assertLogs("genesis.core.registry", level="ERROR") as cm:
            result = await reg.execute("dummy_invalid_envelope", {"kwargs": "sentinel_kwargs_envelope_shape"})

        self.assertIn("sentinel_kwargs_envelope_shape", "sentinel_kwargs_envelope_shape")
        self.assertIn("kwargs envelope", result)
        self.assertTrue(any("kwargs_envelope" in line for line in cm.output))


if __name__ == "__main__":
    unittest.main()

