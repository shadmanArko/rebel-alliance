"""Score one target (teacher / base / tuned) and merge the result into eval/results.json.

Two sources, combinable:
  --predictions FILE   score a Distil predictions JSONL (teacher eval or `slm download-predictions`):
                       accuracy only, no latency (free, no endpoint needed)
  --endpoint           call the live OpenAI-compatible endpoint on the test set:
                       accuracy + latency + cost per 1k requests

    uv run python eval/run_eval.py --target tuned --predictions runs/slm-<id>/predictions.jsonl
    uv run python eval/run_eval.py --target base --endpoint --limit 50
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

from slmkit.client import ModelClient, resolve_target
from slmkit.metrics import aggregate, percentile, score_one
from slmkit.settings import DATA_DIR, EVAL_DIR, ROOT, RUNS_DIR, env_float

RESULTS = EVAL_DIR / "results.json"


def _content(message) -> str:
    if isinstance(message, dict):
        return message.get("content") or ""
    return str(message or "")


def load_test_rows(path: Path | None) -> list[tuple[str, str]]:
    """(user input, reference answer) pairs from a chat-format test.jsonl."""
    candidates = [path] if path else [RUNS_DIR / "testset" / "test.jsonl", DATA_DIR / "test.jsonl"]
    for p in candidates:
        if p and p.exists() and p.stat().st_size:
            rows = []
            for line in p.read_text().splitlines():
                msgs = json.loads(line)["messages"]
                user = next(m["content"] for m in msgs if m["role"] == "user")
                ref = next(m["content"] for m in reversed(msgs) if m["role"] == "assistant")
                rows.append((user, ref))
            print(f"test set: {p.relative_to(ROOT)} ({len(rows)} rows)", file=sys.stderr)
            return rows
    sys.exit("ERROR: no test set. Run 'make testset' (writes runs/testset/test.jsonl) "
             "or put rows in data/test.jsonl.")


def score_predictions(path: Path) -> dict:
    if not path.exists():
        sys.exit(f"ERROR: {path} not found")
    scores = []
    for line in path.read_text().splitlines():
        row = json.loads(line)
        scores.append(score_one(_content(row.get("prediction")), _content(row.get("completion"))))
    return aggregate(scores)


def score_endpoint(target_name: str, rows, workers: int, guided: bool) -> dict:
    client = ModelClient(resolve_target(target_name), guided_json=guided)

    def run(row):
        user, ref = row
        try:
            c = client.complete(user)
        except Exception as exc:  # one bad request should not sink the whole run
            print(f"  request failed: {exc}", file=sys.stderr)
            return None
        return score_one(c.text, ref), c

    results = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for i, res in enumerate(pool.map(run, rows), 1):
            if res:
                results.append(res)
            if i % 10 == 0:
                print(f"  {i}/{len(rows)}", file=sys.stderr)
    if not results:
        sys.exit("ERROR: every request failed; check the endpoint URL and key in .env")

    summary = aggregate([s for s, _ in results])
    latencies = [c.latency_s for _, c in results]
    p_tok = statistics.fmean(c.prompt_tokens for _, c in results)
    c_tok = statistics.fmean(c.completion_tokens for _, c in results)
    summary.update({
        "failed_requests": len(rows) - len(results),
        "latency_p50_s": percentile(latencies, 50),
        "latency_p95_s": percentile(latencies, 95),
        "avg_prompt_tokens": p_tok,
        "avg_completion_tokens": c_tok,
        "cost_per_1k_usd": cost_per_1k(target_name, latencies, p_tok, c_tok, workers),
        "guided_json": guided and target_name != "teacher",
    })
    return summary


def cost_per_1k(target: str, latencies, p_tok: float, c_tok: float, workers: int) -> float | None:
    if target == "teacher":
        price_in = env_float("TEACHER_USD_PER_M_INPUT")
        price_out = env_float("TEACHER_USD_PER_M_OUTPUT")
        if price_in is None or price_out is None:
            return None
        return 1000 * (p_tok * price_in + c_tok * price_out) / 1e6
    # Self-hosted: GPU time per request at the concurrency we measured with. A pod that is
    # kept busy with more parallel requests is cheaper per request than this estimate.
    usd_per_hour = env_float("RUNPOD_GPU_USD_PER_HOUR")
    if usd_per_hour is None:
        return None
    seconds_per_request = statistics.fmean(latencies) / max(workers, 1)
    return 1000 * seconds_per_request * usd_per_hour / 3600


def merge(target: str, source: str, summary: dict) -> None:
    results = json.loads(RESULTS.read_text()) if RESULTS.exists() and RESULTS.stat().st_size else {}
    entry = results.setdefault(target, {})
    entry[source] = {**summary, "updated_at": datetime.now(UTC).isoformat(timespec="seconds")}
    RESULTS.write_text(json.dumps(results, indent=2, sort_keys=True) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--target", required=True, choices=["teacher", "base", "tuned"])
    ap.add_argument("--predictions", type=Path)
    ap.add_argument("--endpoint", action="store_true")
    ap.add_argument("--test-file", type=Path)
    ap.add_argument("--limit", type=int, default=0, help="first N test rows only (0 = all)")
    ap.add_argument("--workers", type=int, default=4, help="parallel requests to the endpoint")
    ap.add_argument("--no-guided-json", action="store_true", help="disable vLLM schema-constrained decoding")
    args = ap.parse_args()
    if not args.predictions and not args.endpoint:
        ap.error("pass --predictions FILE and/or --endpoint")

    if args.predictions:
        summary = score_predictions(args.predictions)
        merge(args.target, "distil_predictions", summary)
        print(f"{args.target} (Distil predictions): {json.dumps(summary)}")
    if args.endpoint:
        rows = load_test_rows(args.test_file)
        if args.limit:
            rows = rows[: args.limit]
        summary = score_endpoint(args.target, rows, args.workers, not args.no_guided_json)
        merge(args.target, "endpoint", summary)
        print(f"{args.target} (endpoint): {json.dumps(summary)}")
    print(f"-> {RESULTS.relative_to(ROOT)}", file=sys.stderr)


if __name__ == "__main__":
    main()
