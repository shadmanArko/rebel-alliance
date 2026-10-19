"""Export LLM generations from Langfuse and convert them to Distil `openai_messages` traces.

    uv run python scripts/langfuse_export.py            # -> data/raw/langfuse_generations.jsonl
                                                        # -> data/traces.jsonl
Uses the Langfuse public REST API (GET /api/public/observations, basic auth pk:sk).
Re-running overwrites both files, so it is safe to repeat.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import httpx

from slmkit.settings import DATA_DIR, env, require_env

PAGE_SIZE = 100
_BAD_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f  ]")


def fetch_generations(limit: int, name: str | None, since: str | None) -> list[dict]:
    keys = require_env("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY")
    host = env("LANGFUSE_HOST", "https://cloud.langfuse.com").rstrip("/")
    params: dict = {"type": "GENERATION", "limit": PAGE_SIZE}
    if name:
        params["name"] = name
    if since:
        params["fromStartTime"] = since if "T" in since else f"{since}T00:00:00Z"
    auth = (keys["LANGFUSE_PUBLIC_KEY"], keys["LANGFUSE_SECRET_KEY"])
    rows: list[dict] = []
    page = 1
    with httpx.Client(base_url=host, auth=auth, timeout=60) as client:
        while len(rows) < limit:
            resp = client.get("/api/public/observations", params={**params, "page": page})
            if resp.status_code == 401:
                sys.exit("ERROR: Langfuse rejected the keys (401). Check LANGFUSE_* in .env.")
            resp.raise_for_status()
            body = resp.json()
            batch = body.get("data", [])
            rows.extend(batch)
            total_pages = body.get("meta", {}).get("totalPages", page)
            print(f"  page {page}/{total_pages}: {len(rows)} generations", file=sys.stderr)
            if not batch or page >= total_pages:
                break
            page += 1
    return rows[:limit]


def _clean(text: str) -> str:
    return _BAD_CHARS.sub(" ", text).strip()


def _messages_from_input(value) -> list[dict] | None:
    """Langfuse stores whatever the SDK integration sent: a list, {"messages": [...]}, or text."""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return [{"role": "user", "content": value}]
    if isinstance(value, dict) and isinstance(value.get("messages"), list):
        value = value["messages"]
    if not isinstance(value, list):
        return None
    messages = []
    for m in value:
        if not isinstance(m, dict) or "role" not in m:
            return None
        content = m.get("content")
        if isinstance(content, list):  # content parts -> text only
            content = "\n".join(p.get("text", "") for p in content if isinstance(p, dict))
        messages.append({"role": m["role"], "content": _clean(str(content or ""))})
    return messages


def _text_from_output(value) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        if "choices" in value:
            value = value["choices"][0].get("message", {})
        return value.get("content")
    return None


def convert(observation: dict) -> dict | None:
    if observation.get("level") == "ERROR":
        return None
    messages = _messages_from_input(observation.get("input"))
    answer = _text_from_output(observation.get("output"))
    if not messages or not answer or not answer.strip():
        return None
    if not any(m["role"] == "user" and m["content"] for m in messages):
        return None
    return {"messages": [*messages, {"role": "assistant", "content": _clean(answer)}]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=int(env("LANGFUSE_LIMIT", "2000")))
    parser.add_argument("--name", default=env("LANGFUSE_GENERATION_NAME"))
    parser.add_argument("--since", default=env("LANGFUSE_FROM"))
    parser.add_argument("--raw", type=Path, default=DATA_DIR / "raw" / "langfuse_generations.jsonl")
    parser.add_argument("--out", type=Path, default=DATA_DIR / "traces.jsonl")
    args = parser.parse_args()

    print("Fetching generations from Langfuse", file=sys.stderr)
    observations = fetch_generations(args.limit, args.name, args.since)
    args.raw.parent.mkdir(parents=True, exist_ok=True)
    with args.raw.open("w") as f:
        for o in observations:
            f.write(json.dumps(o, ensure_ascii=False) + "\n")

    kept, seen = [], set()
    for o in observations:
        row = convert(o)
        if row is None:
            continue
        key = json.dumps(row, sort_keys=True)
        if key in seen:  # exact duplicates add nothing and can collide across splits
            continue
        seen.add(key)
        kept.append(row)
    with args.out.open("w") as f:
        for row in kept:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(f"Raw: {len(observations)} -> {args.raw.relative_to(DATA_DIR.parent)}", file=sys.stderr)
    print(f"Traces kept: {len(kept)} -> {args.out.relative_to(DATA_DIR.parent)}", file=sys.stderr)
    if not kept:
        sys.exit("ERROR: no usable generations (need input messages + non-empty output). "
                 "Check LANGFUSE_GENERATION_NAME / LANGFUSE_FROM.")
    if len(kept) < 300:
        print("WARN: fewer than 300 traces; lower trace_processing.num_*_relabelled in "
              "config/config.yaml (each relabel run needs that many unused traces).", file=sys.stderr)


if __name__ == "__main__":
    main()
