"""Run the task on one input: text in, schema-validated JSON out (+ the reasoning, if any).

    uv run python demo/triage.py data/samples/invoice_hold_price.txt
    cat input.txt | uv run python demo/triage.py -
    uv run python demo/triage.py --target base data/samples/invoice_hold_price.txt   # untrained
    uv run python demo/triage.py --show-reasoning data/samples/invoice_hold_total.txt
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


def triage(text: str, target: str = "tuned") -> tuple[dict | None, str, float, str]:
    # source="demo" tags the Langfuse trace (if enabled); web.py calls this too
    completion = ModelClient(resolve_target(target), source="demo").complete(text)
    return parse_json(completion.text), completion.text, completion.latency_s, completion.reasoning


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("logfile", help="path to an input file, or - for stdin")
    ap.add_argument("--target", default="tuned", choices=["tuned", "base", "teacher"])
    ap.add_argument("--show-reasoning", action="store_true", help="print the thinking block to stderr")
    args = ap.parse_args()

    logs = sys.stdin.read() if args.logfile == "-" else Path(args.logfile).read_text()
    if not logs.strip():
        sys.exit("ERROR: empty input")
    report, raw, latency, reasoning = triage(logs, args.target)
    if args.show_reasoning and reasoning:
        print(f"--- reasoning ---\n{reasoning}\n-----------------", file=sys.stderr)
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
