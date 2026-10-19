"""Print teacher vs base vs tuned from eval/results.json and the Distil platform metrics.

    uv run python eval/compare.py            # or: make compare
"""

from __future__ import annotations

import json

from rich.console import Console
from rich.table import Table

from slmkit.settings import EVAL_DIR, RUNS_DIR

TARGETS = [("teacher", "Teacher"), ("base", "Base 0.8B"), ("tuned", "Tuned 0.8B")]
JUDGE_KEY = "llm-as-a-judge-reference-free"  # Distil's default primary metric for teacher-written refs


def read_state() -> dict[str, str]:
    path = RUNS_DIR / "state.env"
    if not path.exists():
        return {}
    pairs = (line.split("=", 1) for line in path.read_text().splitlines() if "=" in line)
    return {k: v for k, v in pairs}


def platform_scores() -> dict[str, dict]:
    """Judge scores the Distil platform computed on the same test set."""
    out: dict[str, dict] = {}
    teacher = RUNS_DIR / "teacher-eval" / "metrics.json"
    if teacher.exists():
        out["teacher"] = json.loads(teacher.read_text()).get("teacher_performance") or {}
    slm_id = read_state().get("SLM_ID")
    slm = RUNS_DIR / f"slm-{slm_id}" / "metrics.json" if slm_id else None
    if slm and slm.exists():
        data = json.loads(slm.read_text())
        out["base"] = data.get("base_model_performance") or {}
        out["tuned"] = data.get("tuned_model_performance") or {}
    return out


def fmt(value, kind: str = "pct") -> str:
    if value is None:
        return "-"
    if kind == "pct":
        return f"{100 * value:.1f}%"
    if kind == "s":
        return f"{value:.2f}s"
    if kind == "usd":
        return f"${value:.3f}"
    return str(value)


def pick(entry: dict, key: str):
    """Prefer the live endpoint run, fall back to the Distil predictions file."""
    for source in ("endpoint", "distil_predictions"):
        if key in entry.get(source, {}):
            return entry[source][key]
    return None


def main() -> None:
    results_path = EVAL_DIR / "results.json"
    results = json.loads(results_path.read_text()) if results_path.exists() else {}
    platform = platform_scores()

    table = Table(title="Teacher vs base vs tuned (same locked test set)")
    # Short headers so the table fits an 80-column terminal; see README for definitions.
    for col in ["Model", "n", "JSON", "Schema", "Exact", "F1", "KeyAcc", "Judge", "p50", "p95", "$/1k"]:
        table.add_column(col, justify="left" if col == "Model" else "right", no_wrap=True)
    for key, label in TARGETS:
        e = results.get(key, {})
        table.add_row(
            label,
            fmt(pick(e, "n"), "raw"),
            fmt(pick(e, "json_valid")),
            fmt(pick(e, "schema_valid")),
            fmt(pick(e, "exact_match")),
            fmt(pick(e, "field_f1")),
            fmt(pick(e, "key_field_acc")),
            fmt(platform.get(key, {}).get(JUDGE_KEY)),
            fmt(e.get("endpoint", {}).get("latency_p50_s"), "s"),
            fmt(e.get("endpoint", {}).get("latency_p95_s"), "s"),
            fmt(e.get("endpoint", {}).get("cost_per_1k_usd"), "usd"),
        )
    console = Console()
    if not console.is_terminal:  # piped / CI: don't squeeze into 80 columns
        console = Console(width=130)
    console.print(table)

    base = platform.get("base", {}).get(JUDGE_KEY)
    tuned = platform.get("tuned", {}).get(JUDGE_KEY)
    teacher = platform.get("teacher", {}).get(JUDGE_KEY)
    if None not in (base, tuned, teacher) and teacher != base:
        closed = (tuned - base) / (teacher - base)
        verdict = "deploy candidate" if closed >= 0.8 else "retune" if closed >= 0.4 else "iterate"
        console.print(f"Gap closed (tuned-base)/(teacher-base) on {JUDGE_KEY}: "
                      f"[bold]{closed:.2f}[/bold] -> {verdict}")
    console.print("[dim]JSON/Schema = valid rate, Exact = whole-object match, F1 = per-field F1, "
                  "KeyAcc = enum/bool fields, Judge = Distil llm-as-a-judge-reference-free.[/dim]")
    console.print("[dim]Judge scores are samples (non-zero temperature): ignore differences "
                  "smaller than the run-to-run noise. Missing cells: run the matching make "
                  "target (see README).[/dim]")


if __name__ == "__main__":
    main()
