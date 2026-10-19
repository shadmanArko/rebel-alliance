#!/usr/bin/env bash
# Score the tuned student: Distil's predictions on the test set (free), plus the live
# Runpod endpoint (latency + cost) when SERVE_BASE_URL is set.
source "$(dirname "$0")/../lib/common.sh"
require_distil

slm="${SLM:-$(state_require SLM_ID 'make train')}"
[ "$(job_status slm "$slm")" = JOB_SUCCESS ] || die "SLM $slm is not finished yet ('make status')."
out="$REPO_ROOT/runs/slm-$slm"
mkdir -p "$out"
[ -s "$out/metrics.json" ] || distil slm metrics --output json "$slm" > "$out/metrics.json"
distil slm download-predictions --file-name "$out/predictions.jsonl" "$slm" >/dev/null \
  || die "could not download predictions for $slm"
py eval/run_eval.py --target tuned --predictions "$out/predictions.jsonl"

if grep -qE '^SERVE_BASE_URL=.+' "$REPO_ROOT/.env" 2>/dev/null; then
  py eval/run_eval.py --target tuned --endpoint ${LIMIT:+--limit "$LIMIT"}
else
  warn "SERVE_BASE_URL not set: skipped the live endpoint run (no latency/cost for tuned)."
fi
