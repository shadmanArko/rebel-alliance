import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from slmkit import tracing
from slmkit.client import ModelClient, Target

ROOT = Path(__file__).resolve().parents[1]
ANSWER = json.dumps({"decision": "approve"})


class FakeCompletions:
    def create(self, **kwargs):
        message = SimpleNamespace(content=ANSWER, reasoning_content="totals match the PO")
        usage = SimpleNamespace(prompt_tokens=12, completion_tokens=5)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=usage)


def fake_client(source="eval") -> ModelClient:
    target = Target("teacher", "http://localhost:1/v1", "EMPTY", "teacher-model", False)
    client = ModelClient(target, source=source)
    client.client = SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions()))
    return client


@pytest.fixture
def reset_tracing(monkeypatch):
    monkeypatch.setattr(tracing, "_client", None)
    monkeypatch.setattr(tracing, "_initialised", False)


def test_no_keys_is_a_noop(monkeypatch, reset_tracing):
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    for mod in [m for m in sys.modules if m == "langfuse" or m.startswith("langfuse.")]:
        monkeypatch.delitem(sys.modules, mod)

    c = fake_client().complete("INVOICE MESSAGE ...")

    assert c.text == ANSWER and c.reasoning == "totals match the PO"
    assert (c.prompt_tokens, c.completion_tokens) == (12, 5)
    assert not tracing.enabled() and tracing.get_client() is None
    assert "langfuse" not in sys.modules  # nothing imported, so nothing can be sent
    tracing.flush()  # safe with tracing off


def test_one_key_is_not_enough(monkeypatch, reset_tracing):
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-x")
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    assert tracing.get_client() is None


def test_traced_generation_reads_back_through_export(monkeypatch, reset_tracing):
    from langfuse import Langfuse
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    exporter = InMemorySpanExporter()  # spans stay in memory: nothing goes over the network
    lf = Langfuse(public_key="pk-lf-test", secret_key="sk-lf-test",
                  base_url="http://localhost:1", span_exporter=exporter)
    monkeypatch.setattr(tracing, "_client", lf)
    monkeypatch.setattr(tracing, "_initialised", True)

    fake_client(source="eval").complete("INVOICE MESSAGE ...")
    lf.flush()

    (span,) = [s for s in exporter.get_finished_spans() if s.name == "teacher"]
    attrs = span.attributes
    assert "eval" in attrs["langfuse.trace.tags"] and "teacher" in attrs["langfuse.trace.tags"]
    assert json.loads(attrs["langfuse.observation.usage_details"]) == {"input": 12, "output": 5}
    assert json.loads(attrs["langfuse.observation.metadata.reasoning_content"]) == "totals match the PO"

    # Langfuse serves these back as the observation's input/output; the export must accept them.
    spec = importlib.util.spec_from_file_location("lf_export", ROOT / "scripts/langfuse_export.py")
    export = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(export)
    observation = {
        "input": json.loads(attrs["langfuse.observation.input"]),
        "output": json.loads(attrs["langfuse.observation.output"]),
    }
    row = export.convert(observation)
    assert [m["role"] for m in row["messages"]] == ["system", "user", "assistant"]
    assert row["messages"][-1]["content"] == ANSWER


def test_export_reads_a_bare_json_output():
    spec = importlib.util.spec_from_file_location("lf_export", ROOT / "scripts/langfuse_export.py")
    export = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(export)
    row = export.convert({"input": [{"role": "user", "content": "x"}], "output": json.loads(ANSWER)})
    assert row["messages"][-1]["content"] == ANSWER
