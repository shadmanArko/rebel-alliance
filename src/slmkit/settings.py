"""Repo paths, .env loading and the task definition (system prompt + output schema)."""

from __future__ import annotations

import json
import os
import sys
from functools import cache
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
RUNS_DIR = ROOT / "runs"
EVAL_DIR = ROOT / "eval"

load_dotenv(ROOT / ".env")


def env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name, "").strip()
    return value or default


def require_env(*names: str) -> dict[str, str]:
    missing = [n for n in names if not env(n)]
    if missing:
        die(f"missing in .env: {', '.join(missing)}  (see .env.example)")
    return {n: env(n) for n in names}  # type: ignore[misc]


def env_float(name: str) -> float | None:
    value = env(name)
    try:
        return float(value) if value else None
    except ValueError:
        die(f"{name} must be a number, got {value!r}")


def die(message: str, code: int = 1):
    print(f"ERROR: {message}", file=sys.stderr)
    sys.exit(code)


@cache
def job_description() -> dict:
    return json.loads((CONFIG_DIR / "job_description.json").read_text())


@cache
def system_prompt() -> str:
    # The student is trained and served with task_description as its system prompt.
    return job_description()["task_description"]


@cache
def output_schema() -> dict:
    return json.loads((CONFIG_DIR / "schema.json").read_text())
