from __future__ import annotations

import asyncio
from typing import Any

from openai import AsyncOpenAI

from quest_rag.core.config import OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_MODEL


async def _score_metric(name: str, scorer: Any, payload: dict[str, Any]) -> tuple[str, Any]:
    try:
        result = await scorer.ascore(**payload)
        return name, _to_jsonable(result)
    except Exception as exc:
        return name, {"error": str(exc)}


async def _score_with_collections(
    *,
    question: str,
    answer: str,
    contexts: list[str],
    reference: str,
    metrics: list[str],
    model: str | None,
) -> dict[str, Any]:
    from ragas.llms import llm_factory
    from ragas.metrics.collections import (
        ContextPrecision,
        ContextRecall,
        FactualCorrectness,
        Faithfulness,
        ResponseRelevancy,
    )

    client = AsyncOpenAI(
        api_key=OPENAI_API_KEY,
        base_url=OPENAI_BASE_URL,
    )
    llm = llm_factory(model or OPENAI_MODEL, client=client)
    metric_map = {
        "faithfulness": Faithfulness(llm=llm),
        "factual_correctness": FactualCorrectness(llm=llm),
        "response_relevancy": ResponseRelevancy(llm=llm),
        "context_precision": ContextPrecision(llm=llm),
        "context_recall": ContextRecall(llm=llm),
    }
    payload = {
        "user_input": question,
        "response": answer,
        "retrieved_contexts": contexts,
        "reference": reference,
    }
    selected = [metric for metric in metrics if metric in metric_map]
    pairs = await asyncio.gather(*[_score_metric(metric, metric_map[metric], payload) for metric in selected])
    return {name: value for name, value in pairs}


def score_ragas_sample(
    *,
    question: str,
    answer: str,
    contexts: list[str],
    reference: str | None,
    options: dict[str, Any],
    generation_options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not options.get("enabled", True):
        return {"enabled": False}
    if not answer.strip():
        return {"enabled": True, "error": "empty answer"}
    if not contexts:
        return {"enabled": True, "error": "empty contexts"}
    metrics = options.get("metrics") or [
        "faithfulness",
        "factual_correctness",
        "response_relevancy",
        "context_precision",
        "context_recall",
    ]
    try:
        scores = asyncio.run(
            _score_with_collections(
                question=question,
                answer=answer,
                contexts=contexts,
                reference=reference or "",
                metrics=metrics,
                model=(generation_options or {}).get("model"),
            )
        )
        return {"enabled": True, **scores}
    except ImportError as exc:
        return {"enabled": True, "error": f"ragas is not installed or incompatible: {exc}"}
    except Exception as exc:
        return {"enabled": True, "error": str(exc)}


def _to_jsonable(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, dict):
        return {str(k): _to_jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_to_jsonable(item) for item in value]
    if hasattr(value, "model_dump"):
        return _to_jsonable(value.model_dump())
    if hasattr(value, "dict"):
        return _to_jsonable(value.dict())
    if hasattr(value, "score"):
        return _to_jsonable(value.score)
    return str(value)
