"""从版本化 JSON 文件读取办事定义。

新增常规表单时，新增 ``form_definitions/*.json`` 即可；通用表单、草稿校验和
浏览器同步代码无需修改。新字段类型或新的站点交互模式才需要扩展代码。
"""

import json
from copy import deepcopy
from pathlib import Path


_DEFINITION_DIR = Path(__file__).with_name("form_definitions")


def _load_definitions() -> dict[str, dict]:
    definitions: dict[str, dict] = {}
    for path in sorted(_DEFINITION_DIR.glob("*.json")):
        with path.open(encoding="utf-8") as source:
            definition = json.load(source)
        required = {"business_code", "version", "name", "steps", "form", "adapter", "adapter_id"}
        missing = required - set(definition)
        if missing:
            raise RuntimeError(f"办事定义 {path.name} 缺少字段: {', '.join(sorted(missing))}")
        if definition["business_code"] in definitions:
            raise RuntimeError(f"重复的办事定义: {definition['business_code']}")
        definitions[definition["business_code"]] = definition
    return definitions


def get_definition(business_code: str) -> dict | None:
    definition = _load_definitions().get(business_code)
    return deepcopy(definition) if definition else None


def list_definitions() -> list[dict]:
    return [
        {
            "business_code": item["business_code"], "version": item["version"],
            "name": item["name"], "region": item.get("region", "未指定地区"),
            "official_service_name": item.get("official_service_name", "未指定官方服务"),
            "eligibility_summary": item.get("eligibility", {}).get("summary", "请查看办理条件"),
        }
        for item in _load_definitions().values()
    ]
