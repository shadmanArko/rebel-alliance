#!/usr/bin/env bash
# Status of every entity recorded in runs/state.env, plus remaining credits.
source "$(dirname "$0")/../lib/common.sh"
require_distil

[ -s "$STATE_FILE" ] || { info "nothing submitted yet (runs/state.env is empty)"; exit 0; }

group_for() {
  case "$1" in
    TEACHER_EVAL_ID) echo teacher-evaluation ;;
    SLM_ID|SLM_SMOKE_ID) echo slm ;;
    DEPLOYMENT_ID) echo deployment ;;
    *_ID) echo dataset ;;
    *) echo "" ;;
  esac
}

printf '%-22s %-38s %s\n' KEY ID STATUS
while IFS='=' read -r key value; do
  [ -n "$key" ] || continue
  group="$(group_for "$key")"
  status="-"
  [ -n "$group" ] && status="$(job_status "$group" "$value")"
  printf '%-22s %-38s %s\n' "$key" "$value" "${status:-unknown}"
done < "$STATE_FILE"

echo
distil credits-balance 2>/dev/null || true
