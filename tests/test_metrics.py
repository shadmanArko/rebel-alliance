import importlib.util
import json
from pathlib import Path

from slmkit.metrics import aggregate, parse_json, score_one

ROOT = Path(__file__).resolve().parents[1]
REF = json.dumps({"decision": "hold_price"})


def test_identical_prediction_scores_perfect():
    s = score_one(REF, REF)
    assert s["json_valid"] and s["schema_valid"] and s["exact_match"]
    assert s["key_field_acc"] == 1.0


def test_code_fences_and_spacing_still_parse():
    assert parse_json('```json\n{"decision":  "hold_price"}\n```')["decision"] == "hold_price"
    assert score_one('{"decision":"hold_price"}', REF)["exact_match"]


def test_wrong_label_is_wrong():
    s = score_one(json.dumps({"decision": "approve"}), REF)
    assert not s["exact_match"] and s["key_field_acc"] == 0.0


def test_label_outside_enum_fails_schema():
    s = score_one(json.dumps({"decision": "hold"}), REF)
    assert s["json_valid"] and not s["schema_valid"]


def test_invalid_json_scores_zero():
    s = score_one("I think we should approve it", REF)
    assert not s["json_valid"]
    assert aggregate([s])["exact_match"] == 0.0


def test_sample_rows_match_schema():
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
    chat_input = [{"role": "system", "content": "sys"}, {"role": "user", "content": "inv"}]
    out = convert({"input": chat_input, "output": {"role": "assistant", "content": "{}"}})
    assert [m["role"] for m in out["messages"]] == ["system", "user", "assistant"]
    assert convert({"input": {"messages": chat_input}, "output": "{}"}) is not None
    assert convert({"input": "plain text", "output": "{}"})["messages"][0]["role"] == "user"
    assert convert({"input": chat_input, "output": ""}) is None
    assert convert({"input": chat_input, "output": "{}", "level": "ERROR"}) is None
