"""Browser Use adapter for DeepSeek's documented JSON object output.

JSON object mode avoids unsupported JSON Schema requests and free-text/DSML
output. Pydantic still validates the complete Browser Use action schema.
"""
import json

from browser_use.llm.openai.chat import ChatOpenAI
from browser_use.llm.openai.serializer import OpenAIMessageSerializer
from browser_use.llm.views import ChatInvokeCompletion


class DeepSeekJSONChat(ChatOpenAI):
    async def ainvoke(self, messages, output_format=None, **kwargs):
        if output_format is None:
            return await super().ainvoke(messages, output_format, **kwargs)
        serialized = OpenAIMessageSerializer.serialize_messages(messages)
        schema = json.dumps(output_format.model_json_schema(), ensure_ascii=False)
        serialized.insert(0, {"role": "system", "content": "Return one JSON object only. Match this JSON schema exactly; do not use XML, DSML, tool-call tags or Markdown fences.\n" + schema})
        response = await self.get_client().chat.completions.create(
            model=self.model,
            messages=serialized,
            temperature=self.temperature,
            max_completion_tokens=self.max_completion_tokens,
            response_format={"type": "json_object"},
        )
        if not response.choices:
            raise ValueError("Model returned no completion choices")
        choice = response.choices[0]
        result = output_format.model_validate_json(choice.message.content or "")
        return ChatInvokeCompletion(completion=result, usage=self._get_usage(response), stop_reason=choice.finish_reason)
