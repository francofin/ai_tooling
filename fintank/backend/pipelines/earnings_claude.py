"""Claude Message Batches client for earnings notes. `anthropic` is imported
only inside AnthropicBatchClient.__init__, after the key check, so an unset key
can never reach the API and tests never need the package."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Iterator, Protocol

NO_KEY = {"", "unset"}
INPUT_USD_PER_MTOK = 2.0   # batch price, Opus 5.5
OUTPUT_USD_PER_MTOK = 10.0


def has_key(value: str | None) -> bool:
    return value is not None and value.strip() not in NO_KEY


@dataclass
class BatchResult:
    custom_id: str
    kind: str  # succeeded | errored | refused | canceled | expired
    output: dict | None = None
    usage: dict | None = None
    error: str | None = None


class BatchClient(Protocol):
    def submit(self, requests: list[dict]) -> str: ...
    def status(self, batch_id: str) -> str: ...
    def results(self, batch_id: str) -> Iterator[BatchResult]: ...


def cost_usd(usage_totals: dict) -> float:
    return (usage_totals.get("input_tokens", 0) * INPUT_USD_PER_MTOK / 1e6
            + usage_totals.get("output_tokens", 0) * OUTPUT_USD_PER_MTOK / 1e6)


class AnthropicBatchClient:
    def __init__(self, api_key: str):
        if not has_key(api_key):
            raise ValueError("ANTHROPIC_API_KEY is not set")
        import anthropic  # lazy: only reached with a key
        self._client = anthropic.Anthropic(api_key=api_key.strip())

    def submit(self, requests: list[dict]) -> str:
        return self._client.messages.batches.create(requests=requests).id

    def status(self, batch_id: str) -> str:
        return self._client.messages.batches.retrieve(batch_id).processing_status

    def results(self, batch_id: str) -> Iterator[BatchResult]:
        for item in self._client.messages.batches.results(batch_id):
            yield self._convert(item)

    @staticmethod
    def _convert(item) -> BatchResult:
        cid, res = item.custom_id, item.result
        if res.type == "succeeded":
            return _from_message(cid, res.message)
        if res.type == "errored":
            err = getattr(res, "error", None)
            inner = getattr(err, "error", None)  # ErrorResponse(type="error").error is the cause
            src = inner if inner is not None else err
            etype = getattr(src, "type", None) or "unknown"
            msg = getattr(src, "message", None)
            return BatchResult(cid, "errored", error=f"{etype}: {msg}" if msg else str(etype))
        return BatchResult(cid, res.type)  # canceled | expired


def _from_message(cid: str, msg) -> BatchResult:
    usage = {"input_tokens": msg.usage.input_tokens,
             "output_tokens": msg.usage.output_tokens}
    if msg.stop_reason == "refusal":
        return BatchResult(cid, "refused", usage=usage, error="refusal")
    if msg.stop_reason == "max_tokens":
        return BatchResult(cid, "errored", usage=usage, error="max_tokens")
    text = next((b.text for b in msg.content if b.type == "text"), None)
    if text is None:
        return BatchResult(cid, "errored", usage=usage, error="no text block")
    try:
        output = json.loads(text)
    except ValueError:
        return BatchResult(cid, "errored", usage=usage, error="invalid JSON")
    if not isinstance(output, dict):
        return BatchResult(cid, "errored", usage=usage, error="invalid JSON")
    return BatchResult(cid, "succeeded", output=output, usage=usage)
