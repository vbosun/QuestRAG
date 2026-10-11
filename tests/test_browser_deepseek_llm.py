"""Run in the worker image as unittest; local pytest skips without browser-use."""
import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from pydantic import BaseModel, ValidationError

try:
    from browser_use_worker.deepseek_llm import DeepSeekJSONChat
except ImportError:
    DeepSeekJSONChat = None


class Reply(BaseModel):
    success: bool


@unittest.skipIf(DeepSeekJSONChat is None, "requires worker runtime")
class DeepSeekOptionsTest(unittest.TestCase):
    def invoke(self, disabled, content):
        captured = {}

        async def create(**kwargs):
            captured.update(kwargs)
            return SimpleNamespace(choices=[SimpleNamespace(
                message=SimpleNamespace(content=content), finish_reason="stop")])

        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        with patch.object(DeepSeekJSONChat, "get_client", return_value=client), patch.object(
            DeepSeekJSONChat, "_get_usage", return_value=None
        ):
            llm = DeepSeekJSONChat(model="test", api_key="synthetic", disable_thinking=disabled)
            result = asyncio.run(llm.ainvoke([], Reply))
        return captured, result

    def test_fixed_form_explicitly_disables_provider_thinking(self):
        request, result = self.invoke(True, '{"success":true}')
        self.assertEqual(request["extra_body"], {"thinking": {"type": "disabled"}})
        self.assertEqual(request["response_format"], {"type": "json_object"})
        self.assertTrue(result.completion.success)

    def test_default_preserves_provider_options(self):
        request, _ = self.invoke(False, '{"success":true}')
        self.assertNotIn("extra_body", request)

    def test_fast_mode_still_rejects_invalid_schema(self):
        with self.assertRaises(ValidationError):
            self.invoke(True, '{"wrong":true}')


if __name__ == "__main__":
    unittest.main()
