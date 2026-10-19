"""Triage an incident from logs: logs in, schema-validated JSON report out.

    uv run python demo/triage.py data/samples/incident_db_pool.log
    cat some.log | uv run python demo/triage.py -
    uv run python demo/triage.py --target base data/samples/incident_db_pool.log   # untrained model
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator

from slmkit.client import ModelClient, resolve_target
from slmkit.metrics import parse_json
from slmkit.settings import output_schema


def triage(logs: str, target: str = "tuned") -> tuple[dict | None, str, float]:
    completion = ModelClient(resolve_target(target)).complete(logs)
    return parse_json(completion.text), completion.text, completion.latency_s


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("logfile", help="path to a log file, or - for stdin")
    ap.add_argument("--target", default="tuned", choices=["tuned", "base", "teacher"])
    args = ap.parse_args()

    logs = sys.stdin.read() if args.logfile == "-" else Path(args.logfile).read_text()
    if not logs.strip():
        sys.exit("ERROR: empty input")
    report, raw, latency = triage(logs, args.target)
    if report is None:
        print(raw)
        sys.exit("ERROR: model output is not valid JSON")
    errors = [e.message for e in Draft202012Validator(output_schema()).iter_errors(report)]
    print(json.dumps(report, indent=2))
    print(f"\n[{args.target}] {latency:.2f}s, schema {'valid' if not errors else 'INVALID: ' + '; '.join(errors)}",
          file=sys.stderr)
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
