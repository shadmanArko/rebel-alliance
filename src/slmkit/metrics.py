"""Task metrics for JSON outputs: validity, exact match, per-field F1, key-field accuracy.

Field scoring is derived from config/schema.json, so changing the task only means changing
the schema:
  - enum / boolean / number fields   -> exact match (these are the "key fields")
  - free-text string fields          -> token-level F1
  - arrays                           -> token-level F1 over the joined items
"""

from __future__ import annotations

import json
import re
import statistics
from collections import Counter

from jsonschema import Draft202012Validator

from slmkit.settings import output_schema

_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)
_TOKEN = re.compile(r"[a-z0-9_]+")


def parse_json(text: str) -> dict | None:
    """Parse a model answer; tolerate code fences so they cost F1 elsewhere, not everything."""
    if not text:
        return None
    candidate = _FENCE.sub("", text.strip()).strip()
    try:
        value = json.loads(candidate)
    except json.JSONDecodeError:
        start, end = candidate.find("{"), candidate.rfind("}")
        if start == -1 or end <= start:
            return None
        try:
            value = json.loads(candidate[start : end + 1])
        except json.JSONDecodeError:
            return None
    return value if isinstance(value, dict) else None


def _tokens(value) -> list[str]:
    if isinstance(value, list):
        value = " ".join(str(v) for v in value)
    return _TOKEN.findall(str(value).lower())


def token_f1(pred, ref) -> float:
    p, r = _tokens(pred), _tokens(ref)
    if not p and not r:
        return 1.0
    common = sum((Counter(p) & Counter(r)).values())
    if common == 0:
        return 0.0
    precision, recall = common / len(p), common / len(r)
    return 2 * precision * recall / (precision + recall)


def _norm(value):
    return value.strip().lower() if isinstance(value, str) else value


def field_kinds(schema: dict | None = None) -> dict[str, str]:
    schema = schema or output_schema()
    kinds = {}
    for key, spec in schema.get("properties", {}).items():
        if "enum" in spec or spec.get("type") in ("boolean", "integer", "number"):
            kinds[key] = "exact"
        else:
            kinds[key] = "f1"
    return kinds


def score_one(pred_text: str, ref_text: str) -> dict:
    schema = output_schema()
    kinds = field_kinds(schema)
    ref = parse_json(ref_text)
    pred = parse_json(pred_text)
    result = {"json_valid": pred is not None, "schema_valid": False, "exact_match": False,
              "field_f1": 0.0, "key_field_acc": 0.0, "fields": {}}
    if pred is None or ref is None:
        return result
    result["schema_valid"] = not any(Draft202012Validator(schema).iter_errors(pred))
    per_field = {}
    for key, kind in kinds.items():
        if key not in ref:
            continue
        if kind == "exact":
            per_field[key] = float(_norm(pred.get(key)) == _norm(ref[key]))
        else:
            per_field[key] = token_f1(pred.get(key, ""), ref[key])
    result["fields"] = per_field
    if per_field:
        result["field_f1"] = statistics.fmean(per_field.values())
    exact_keys = [k for k, kind in kinds.items() if kind == "exact" and k in per_field]
    if exact_keys:
        result["key_field_acc"] = statistics.fmean(per_field[k] for k in exact_keys)
    result["exact_match"] = json.dumps(pred, sort_keys=True) == json.dumps(ref, sort_keys=True)
    return result


def aggregate(scores: list[dict]) -> dict:
    if not scores:
        return {"n": 0}
    out = {"n": len(scores)}
    for key in ("json_valid", "schema_valid", "exact_match"):
        out[key] = statistics.fmean(float(s[key]) for s in scores)
    for key in ("field_f1", "key_field_acc"):
        out[key] = statistics.fmean(s[key] for s in scores)
    fields: dict[str, list[float]] = {}
    for s in scores:
        for k, v in s["fields"].items():
            fields.setdefault(k, []).append(v)
    out["per_field"] = {k: statistics.fmean(v) for k, v in fields.items()}
    return out


def percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(pct / 100 * (len(ordered) - 1))))
    return ordered[index]
