#!/usr/bin/env bash
# Prints PASS / FAIL / WARN per item. Exits 1 if any required item fails.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT" || exit 1
export PATH="$HOME/.local/bin:$PATH"

if [ -t 1 ]; then G=$'\033[32m'; R=$'\033[31m'; Y=$'\033[33m'; O=$'\033[0m'; else G=""; R=""; Y=""; O=""; fi
fails=0
pass() { printf '  %sPASS%s  %s\n' "$G" "$O" "$1"; }
fail() { printf '  %sFAIL%s  %s  -> %s\n' "$R" "$O" "$1" "$2"; fails=$((fails + 1)); }
note() { printf '  %sWARN%s  %s  -> %s\n' "$Y" "$O" "$1" "$2"; }

# Read KEY from .env without sourcing it (values may contain anything).
env_value() {
  [ -f .env ] || return 0
  grep -E "^$1=" .env | tail -n1 | cut -d= -f2- | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' -e 's/^"\(.*\)"$/\1/'
}

echo "Tools"
for tool in brew git uv jq; do
  if command -v "$tool" >/dev/null 2>&1; then pass "$tool"; else fail "$tool" "make setup"; fi
done
if command -v distil >/dev/null 2>&1; then pass "distil $(distil --version 2>/dev/null)"; else fail "distil CLI" "make setup"; fi
if [ -x .venv/bin/python ] && .venv/bin/python -c "import slmkit, openai, jsonschema, yaml" 2>/dev/null; then
  pass "python venv + deps ($(.venv/bin/python --version 2>&1))"
else
  fail "python venv + deps" "make setup"
fi
if command -v shellcheck >/dev/null 2>&1; then pass "shellcheck"; else note "shellcheck" "brew install shellcheck (only for 'make lint')"; fi

echo "Distil Labs"
if command -v distil >/dev/null 2>&1 && who="$(distil whoami --output json 2>/dev/null)"; then
  pass "logged in as $(printf '%s' "$who" | jq -r '.email // .username // "?"')"
  balance="$(distil credits-balance --output json 2>/dev/null | jq -r '.balances.slms_from_datasets_post // empty')"
  [ -n "$balance" ] && pass "training credits left: $balance"
else
  fail "distil login" "distil auth   (or: distil signup)"
fi

echo ".env"
if [ -f .env ]; then pass ".env exists"; else fail ".env" "make setup (copies .env.example)"; fi
for key in LANGFUSE_PUBLIC_KEY LANGFUSE_SECRET_KEY LANGFUSE_HOST; do
  if [ -n "$(env_value "$key")" ]; then pass "$key"; else note "$key" "only needed for 'make traces' (the invoice task starts from files)"; fi
done
# Serving and teacher keys are only needed later in the pipeline.
for key in SERVE_BASE_URL SERVE_API_KEY RUNPOD_GPU_USD_PER_HOUR; do
  if [ -n "$(env_value "$key")" ]; then pass "$key"; else note "$key" "needed for eval-base / eval-tuned / invoke (serve/README.md)"; fi
done
for key in TEACHER_BASE_URL TEACHER_MODEL; do
  if [ -n "$(env_value "$key")" ]; then pass "$key"; else note "$key" "optional: teacher latency/cost in 'make compare'"; fi
done

echo "Git hygiene"
if git rev-parse --git-dir >/dev/null 2>&1; then
  if git ls-files --error-unmatch .env >/dev/null 2>&1; then fail ".env is tracked by git" "git rm --cached .env"; else pass ".env not tracked"; fi
else
  note "git" "not a git repository"
fi

echo
if [ "$fails" -eq 0 ]; then
  printf '%sAll required checks passed.%s\n' "$G" "$O"
else
  printf '%s%d required check(s) failed.%s\n' "$R" "$fails" "$O"
  exit 1
fi
