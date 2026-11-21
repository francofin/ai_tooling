import json
import re
import sys

import pytest

from pipelines import earnings_prompt as ep


@pytest.fixture(autouse=True)
def _no_anthropic_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


def job(symbol="RY.TO", previous=None):
    return ep.NoteJob(
        symbol=symbol, company_name="Royal Bank", region="ca", fiscal_year=2026,
        fiscal_quarter=3, report_date="2026-08-28", call_date="2026-08-28",
        transcript="TRANSCRIPT-BODY revenue was $3.2 billion",
        estimates={"eps_estimate": 2.1, "eps_actual": 2.3,
                   "revenue_estimate": None, "revenue_actual": 3.2e9},
        previous_note=previous)


def test_quarter():
    assert job().quarter == "2026-Q3"


def test_request_shape():
    req = ep.build_request(job(), 7)
    assert re.match(r"^[a-zA-Z0-9_-]{1,64}$", req["custom_id"])
    p = req["params"]
    assert p["model"] == "claude-opus-5-5"
    assert p["max_tokens"] == 16000
    assert p["output_config"]["effort"] == "low"
    assert p["output_config"]["format"] == {"type": "json_schema", "schema": ep.NOTE_SCHEMA}
    assert "thinking" not in p and "tool_choice" not in p and "stream" not in p
    assert p["system"] == ep.SYSTEM_PROMPT
    assert len(p["messages"]) == 1 and p["messages"][0]["role"] == "user"
    text = p["messages"][0]["content"]
    assert "TRANSCRIPT-BODY" in text
    assert json.dumps(job().estimates, sort_keys=True) in text
    assert "Royal Bank" in text and "2026-Q3" in text
    assert "none" in text


def test_request_includes_previous_note():
    prev = {"headline": "PREV-HEADLINE"}
    text = ep.build_request(job(previous=prev), 0)["params"]["messages"][0]["content"]
    assert "PREV-HEADLINE" in text


def test_custom_id_never_contains_symbol():
    assert ep.custom_id_for(0) == "note-0000"
    assert ep.build_request(job("BRK-B"), 0)["custom_id"] == "note-0000"


def _objects(node):
    if isinstance(node, dict):
        if node.get("type") == "object":
            yield node
        for v in node.values():
            yield from _objects(v)
    elif isinstance(node, list):
        for v in node:
            yield from _objects(v)


def test_schema_is_closed():
    objs = list(_objects(ep.NOTE_SCHEMA))
    assert len(objs) == 2
    for o in objs:
        assert o["additionalProperties"] is False
        assert set(o["required"]) == set(o["properties"])
    assert "minItems" not in json.dumps(ep.NOTE_SCHEMA)
    assert "maxItems" not in json.dumps(ep.NOTE_SCHEMA)
    sections = ep.NOTE_SCHEMA["properties"]["sections"]["properties"]
    assert sections["what_changed"]["type"] == ["string", "null"]
    assert ep.NOTE_SCHEMA["properties"]["lean"]["enum"] == ["bullish", "neutral", "bearish"]
    assert set(ep.NOTE_SCHEMA["properties"]) == {"lean", "headline", "key_points", "sections"}


def test_system_prompt_rules():
    s = ep.SYSTEM_PROMPT.lower()
    assert "1,500" in s and "2,500" in s
    assert "price target" in s
    assert "only figures" in s
    assert "what_changed" in s and "null" in s


def test_stored_note_fields():
    out = {"lean": "neutral", "headline": "h", "key_points": ["a", "b", "c"],
           "sections": {k: "x" for k in ep.NOTE_SCHEMA["properties"]["sections"]["properties"]}}
    note = ep.to_stored_note(job(), out, "2026-11-21T00:00:00Z")
    assert set(note) == {
        "symbol", "company_name", "fiscal_year", "fiscal_quarter", "report_date",
        "call_date", "lean", "headline", "key_points", "sections", "model",
        "generated_at", "source"}
    assert note["source"] == "FMP earnings call transcript"
    assert note["model"] == "claude-opus-5-5"
    assert note["generated_at"] == "2026-11-21T00:00:00Z"
    assert note["symbol"] == "RY.TO"


def test_unset_key_refuses_without_import(monkeypatch):
    from pipelines import earnings_claude as ec
    monkeypatch.setitem(sys.modules, "anthropic", None)
    assert ec.has_key("unset") is False
    assert ec.has_key(" unset ") is False
    assert ec.has_key("") is False and ec.has_key(None) is False
    assert ec.has_key("sk-ant-x") is True
    with pytest.raises(ValueError):
        ec.AnthropicBatchClient("unset")
    with pytest.raises(ValueError):
        ec.AnthropicBatchClient("")


def test_cost_usd():
    from pipelines import earnings_claude as ec
    assert ec.cost_usd({"input_tokens": 14000, "output_tokens": 8000}) == pytest.approx(0.108)


def _item(cid, rtype, stop="end_turn", text=None, error_type=None):
    from types import SimpleNamespace as NS
    if rtype == "succeeded":
        msg = NS(stop_reason=stop, content=[NS(type="text", text=text)],
                 usage=NS(input_tokens=10, output_tokens=5))
        return NS(custom_id=cid, result=NS(type="succeeded", message=msg))
    if rtype == "errored":
        return NS(custom_id=cid, result=NS(type="errored", error=NS(type="error", error=NS(type=error_type, message="busy"))))
    return NS(custom_id=cid, result=NS(type=rtype))


def test_result_conversion():
    from pipelines.earnings_claude import AnthropicBatchClient as C
    ok = C._convert(_item("a", "succeeded", text='{"lean": "neutral"}'))
    assert (ok.kind, ok.output, ok.usage) == (
        "succeeded", {"lean": "neutral"}, {"input_tokens": 10, "output_tokens": 5})
    assert C._convert(_item("a", "succeeded", stop="refusal", text="")).kind == "refused"
    assert C._convert(_item("a", "succeeded", stop="max_tokens", text="{")).kind == "errored"
    assert C._convert(_item("a", "succeeded", text="not json")).kind == "errored"
    err = C._convert(_item("a", "errored", error_type="overloaded_error"))
    assert err.kind == "errored" and "overloaded_error" in err.error and "busy" in err.error
    assert C._convert(_item("a", "expired")).kind == "expired"
    assert C._convert(_item("a", "canceled")).kind == "canceled"
