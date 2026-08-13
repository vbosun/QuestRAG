from __future__ import annotations

import asyncio
import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI

from quest_rag.core.config import (
    EMBEDDING_BASE_URL,
    OPENAI_API_KEY,
    OPENAI_BASE_URL,
    OPENAI_EMBEDDING_MODEL,
    OPENAI_MODEL,
)

RAGAS_JUDGE_MAX_TOKENS = int(os.environ.get("RAGAS_JUDGE_MAX_TOKENS", "8192"))
RAGAS_LOG_DIR = Path(os.environ.get("RAGAS_LOG_DIR", "logs"))
RAGAS_DEBUG_INCLUDE_TEXT = os.environ.get("RAGAS_DEBUG_INCLUDE_TEXT", "").lower() in {"1", "true", "yes", "y"}
RAGAS_DEBUG_TEXT_LIMIT = int(os.environ.get("RAGAS_DEBUG_TEXT_LIMIT", "1200"))


async def _score_metric(name: str, scorer: Any, payload: dict[str, Any], log_base: dict[str, Any]) -> tuple[str, Any]:
    started = time.perf_counter()
    try:
        result = await scorer.ascore(**payload)
        value = _to_jsonable(result)
        _write_ragas_log(
            {
                **log_base,
                "event": "metric_completed",
                "metric": name,
                "elapsed_ms": int((time.perf_counter() - started) * 1000),
                "result_type": type(result).__name__,
                "result": value,
            }
        )
        return name, value
    except Exception as exc:
        _write_ragas_log(
            {
                **log_base,
                "event": "metric_failed",
                "metric": name,
                "elapsed_ms": int((time.perf_counter() - started) * 1000),
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
        )
        return name, {"error": str(exc)}


async def _score_with_collections(
    *,
    question: str,
    answer: str,
    contexts: list[str],
    reference: str,
    metrics: list[str],
    model: str | None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from ragas.embeddings.base import embedding_factory
    from ragas.llms import llm_factory
    from ragas.metrics.collections import (
        AnswerRelevancy,
        ContextPrecision,
        ContextRecall,
        FactualCorrectness,
        Faithfulness,
    )

    client = AsyncOpenAI(
        api_key=OPENAI_API_KEY,
        base_url=OPENAI_BASE_URL,
    )
    embedding_client = AsyncOpenAI(
        api_key=OPENAI_API_KEY,
        base_url=EMBEDDING_BASE_URL,
    )
    llm = llm_factory(
        model or OPENAI_MODEL,
        client=client,
        temperature=0,
        max_tokens=RAGAS_JUDGE_MAX_TOKENS,
    )
    embeddings = embedding_factory("openai", model=OPENAI_EMBEDDING_MODEL, client=embedding_client)
    metric_map = {
        "faithfulness": (
            Faithfulness(llm=llm),
            {
                "user_input": question,
                "response": answer,
                "retrieved_contexts": contexts,
            },
        ),
        "factual_correctness": (
            FactualCorrectness(llm=llm),
            {
                "response": answer,
                "reference": reference,
            },
        ),
        "response_relevancy": (
            AnswerRelevancy(llm=llm, embeddings=embeddings),
            {
                "user_input": question,
                "response": answer,
            },
        ),
        "context_precision": (
            ContextPrecision(llm=llm),
            {
                "user_input": question,
                "reference": reference,
                "retrieved_contexts": contexts,
            },
        ),
        "context_recall": (
            ContextRecall(llm=llm),
            {
                "user_input": question,
                "retrieved_contexts": contexts,
                "reference": reference,
            },
        ),
    }
    selected = [metric for metric in metrics if metric in metric_map]
    log_base = _build_log_base(
        question=question,
        answer=answer,
        contexts=contexts,
        reference=reference,
        selected_metrics=selected,
        model=model or OPENAI_MODEL,
        metadata=metadata or {},
    )
    _write_ragas_log({**log_base, "event": "sample_started"})
    pairs = await asyncio.gather(
        *[_score_metric(metric, metric_map[metric][0], metric_map[metric][1], log_base) for metric in selected]
    )
    scores = {name: value for name, value in pairs}
    _write_ragas_log({**log_base, "event": "sample_completed", "metrics": scores})
    return scores


def score_ragas_sample(
    *,
    question: str,
    answer: str,
    contexts: list[str],
    reference: str | None,
    options: dict[str, Any],
    generation_options: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not options.get("enabled", True):
        _write_ragas_log({"event": "sample_skipped", "reason": "disabled", **(metadata or {})})
        return {"enabled": False}
    if not answer.strip():
        _write_ragas_log({"event": "sample_skipped", "reason": "empty_answer", **(metadata or {})})
        return {"enabled": True, "error": "empty answer"}
    if not contexts:
        _write_ragas_log({"event": "sample_skipped", "reason": "empty_contexts", **(metadata or {})})
        return {"enabled": True, "error": "empty contexts"}
    metrics = options.get("metrics") or [
        "faithfulness",
        "factual_correctness",
    ]
    sample_log_base = _build_log_base(
        question=question,
        answer=answer,
        contexts=contexts,
        reference=reference or "",
        selected_metrics=[metric for metric in metrics if isinstance(metric, str)],
        model=(generation_options or {}).get("model") or OPENAI_MODEL,
        metadata=metadata or {},
    )
    try:
        scores = asyncio.run(
            _score_with_collections(
                question=question,
                answer=answer,
                contexts=contexts,
                reference=reference or "",
                metrics=metrics,
                model=(generation_options or {}).get("model"),
                metadata=metadata,
            )
        )
        return {"enabled": True, **scores}
    except ImportError as exc:
        _write_ragas_log({**sample_log_base, "event": "sample_failed", "error_type": type(exc).__name__, "error": str(exc)})
        return {"enabled": True, "error": f"ragas is not installed or incompatible: {exc}"}
    except Exception as exc:
        _write_ragas_log({**sample_log_base, "event": "sample_failed", "error_type": type(exc).__name__, "error": str(exc)})
        return {"enabled": True, "error": str(exc)}


def _to_jsonable(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if hasattr(value, "value"):
        return _to_jsonable(value.value)
    if isinstance(value, dict):
        return {str(k): _to_jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_to_jsonable(item) for item in value]
    if hasattr(value, "model_dump"):
        return _to_jsonable(value.model_dump())
    if hasattr(value, "dict"):
        return _to_jsonable(value.dict())
    return str(value)


def _build_log_base(
    *,
    question: str,
    answer: str,
    contexts: list[str],
    reference: str,
    selected_metrics: list[str],
    model: str,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    payload = {
        "model": model,
        "max_tokens": RAGAS_JUDGE_MAX_TOKENS,
        "temperature": 0,
        "selected_metrics": selected_metrics,
        "question_chars": len(question),
        "answer_chars": len(answer),
        "reference_chars": len(reference),
        "contexts_count": len(contexts),
        "contexts_chars": [len(context) for context in contexts],
        "contexts_total_chars": sum(len(context) for context in contexts),
        **metadata,
    }
    if RAGAS_DEBUG_INCLUDE_TEXT:
        payload.update(
            {
                "question_preview": _truncate_debug_text(question),
                "answer_preview": _truncate_debug_text(answer),
                "reference_preview": _truncate_debug_text(reference),
                "contexts_preview": [_truncate_debug_text(context) for context in contexts],
            }
        )
    return payload


def _truncate_debug_text(value: str) -> str:
    if len(value) <= RAGAS_DEBUG_TEXT_LIMIT:
        return value
    return value[:RAGAS_DEBUG_TEXT_LIMIT] + "...[truncated]"


def _write_ragas_log(payload: dict[str, Any]) -> None:
    try:
        RAGAS_LOG_DIR.mkdir(parents=True, exist_ok=True)
        path = RAGAS_LOG_DIR / f"ragas-eval-{datetime.now().strftime('%Y%m%d')}.log"
        event = {
            "ts": datetime.now().isoformat(timespec="milliseconds"),
            **_to_jsonable(payload),
        }
        with path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(event, ensure_ascii=False) + "\n")
    except Exception:
        pass
