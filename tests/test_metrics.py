import importlib.util
import json
from pathlib import Path

from slmkit.metrics import aggregate, parse_json, score_one

ROOT = Path(__file__).resolve().parents[1]
REF = json.dumps({
    "severity": "SEV2", "category": "database", "affected_service": "orders-api",
    "summary": "orders-api returns 500s.", "probable_root_cause": "pool exhausted",
    "suggested_actions": ["kill slow query"], "requires_escalation": True,
})


def test_identical_prediction_scores_perfect():
    s = score_one(REF, REF)
    assert s["json_valid"] and s["schema_valid"] and s["exact_match"]
    assert s["field_f1"] == 1.0 and s["key_field_acc"] == 1.0


def test_code_fences_still_parse():
    assert parse_json(f"```json\n{REF}\n```")["severity"] == "SEV2"


def test_wrong_severity_hits_key_field_accuracy():
    pred = json.loads(REF) | {"severity": "SEV4"}
    s = score_one(json.dumps(pred), REF)
    assert not s["exact_match"]
    assert s["fields"]["severity"] == 0.0
    assert s["key_field_acc"] < 1.0


def test_invalid_json_scores_zero():
    s = score_one("not json at all", REF)
    assert not s["json_valid"] and s["field_f1"] == 0.0
    assert aggregate([s])["json_valid"] == 0.0


def test_sample_test_rows_match_schema():
    for line in (ROOT / "data/samples/test_sample.jsonl").read_text().splitlines():
        answer = json.loads(line)["messages"][-1]["content"]
        assert score_one(answer, answer)["schema_valid"]


def _langfuse_module():
    spec = importlib.util.spec_from_file_location("lf", ROOT / "scripts/langfuse_export.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_langfuse_conversion_shapes():
    convert = _langfuse_module().convert
    chat_input = [{"role": "system", "content": "sys"}, {"role": "user", "content": "logs"}]
    out = convert({"input": chat_input, "output": {"role": "assistant", "content": "{}"}})
    assert [m["role"] for m in out["messages"]] == ["system", "user", "assistant"]
    assert convert({"input": {"messages": chat_input}, "output": "{}"}) is not None
    assert convert({"input": "plain logs", "output": "{}"})["messages"][0]["role"] == "user"
    assert convert({"input": chat_input, "output": ""}) is None
    assert convert({"input": chat_input, "output": "{}", "level": "ERROR"}) is None
