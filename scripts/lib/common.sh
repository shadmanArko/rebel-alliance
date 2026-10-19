#!/usr/bin/env bash
# Shared helpers for every script. Source it; do not run it.
#   source "$(dirname "$0")/../lib/common.sh"

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
export REPO_ROOT
STATE_FILE="$REPO_ROOT/runs/state.env"
export PATH="$HOME/.local/bin:$PATH"   # where the distil installer puts the binary

if [ -t 1 ]; then
  C_RED=$'\033[31m'; C_GRN=$'\033[32m'; C_YEL=$'\033[33m'; C_BLD=$'\033[1m'; C_OFF=$'\033[0m'
else
  C_RED=""; C_GRN=""; C_YEL=""; C_BLD=""; C_OFF=""
fi

info() { printf '%s==>%s %s\n' "$C_BLD" "$C_OFF" "$*"; }
ok()   { printf '%s ok%s  %s\n' "$C_GRN" "$C_OFF" "$*"; }
warn() { printf '%swarn%s %s\n' "$C_YEL" "$C_OFF" "$*" >&2; }
die()  { printf '%sERROR%s %s\n' "$C_RED" "$C_OFF" "$*" >&2; exit 1; }

# ---- run state: runs/state.env holds KEY=value lines (entity ids), one writer at a time ----
state_get() {
  [ -f "$STATE_FILE" ] || return 0
  grep -E "^$1=" "$STATE_FILE" | tail -n1 | cut -d= -f2- || true
}

state_set() {
  mkdir -p "$(dirname "$STATE_FILE")"
  touch "$STATE_FILE"
  local tmp
  tmp="$(mktemp)"
  grep -vE "^$1=" "$STATE_FILE" > "$tmp" || true
  printf '%s=%s\n' "$1" "$2" >> "$tmp"
  mv "$tmp" "$STATE_FILE"
}

state_require() {
  local value
  value="$(state_get "$1")"
  [ -n "$value" ] || die "no $1 in runs/state.env. Run '$2' first."
  printf '%s' "$value"
}

# ---- distil ----
require_distil() {
  command -v distil >/dev/null 2>&1 || die "distil CLI not found. Run 'make setup'."
  command -v jq >/dev/null 2>&1 || die "jq not found. Run 'make setup'."
  distil whoami --output json >/dev/null 2>&1 \
    || die "distil CLI is not logged in. Run 'distil auth' (or 'distil signup' for a new account)."
}

# Credits are metered per route and scarce (5 full trainings per account), so every
# paid submission shows the balance and asks first. YES=1 skips the prompt (CI, scripts).
confirm_spend() {
  local what="$1" route="$2" balance
  balance="$(distil credits-balance --output json 2>/dev/null | jq -r --arg r "$route" '.balances[$r] // "?"')"
  info "About to spend 1 credit on: $what  (route $route, remaining: $balance)"
  if [ "${YES:-0}" = "1" ]; then return 0; fi
  if [ ! -t 0 ]; then die "not a terminal; re-run with YES=1 to confirm spending a credit."; fi
  local answer
  read -r -p "Proceed? [y/N] " answer
  case "$answer" in y|Y|yes) ;; *) die "aborted, nothing submitted." ;; esac
}

# Submit a distil create command with --output json and print the new id; fail loudly.
distil_create() {
  local out id
  if ! out="$(distil "$@" --output json 2>&1)"; then
    die "distil $* failed: $out"
  fi
  id="$(printf '%s' "$out" | jq -r '.id // empty' 2>/dev/null || true)"
  [ -n "$id" ] || die "distil $* returned no id: $out"
  printf '%s' "$id"
}

job_status() {
  local group="$1" id="$2" field=status
  [ "$group" = deployment ] && field=deployment_status
  distil "$group" status --output json "$id" 2>/dev/null | jq -r ".$field // empty" 2>/dev/null || true
}

# Wait for a job. WAIT=0 returns right after submission; POLL_TIMEOUT (seconds, default 4h).
# Exit 0 on JOB_SUCCESS, 1 on failure, 2 if still running at timeout (re-run to resume).
poll_job() {
  local group="$1" id="$2" timeout="${POLL_TIMEOUT:-14400}" interval="${POLL_INTERVAL:-60}"
  local waited=0 status=""
  if [ "${WAIT:-1}" = "0" ]; then
    info "WAIT=0: not waiting. Check later with 'make status'."
    return 0
  fi
  info "Waiting for $group $id (Ctrl-C is safe: re-run the same make target to resume)"
  while [ "$waited" -lt "$timeout" ]; do
    status="$(job_status "$group" "$id")"
    case "$status" in
      JOB_SUCCESS) ok "$group $id: JOB_SUCCESS"; return 0 ;;
      JOB_FAILURE|JOB_STOPPED)
        warn "$group $id: $status. Logs: distil $group logs $id"
        return 1 ;;
    esac
    printf '  %s  %s\n' "$(date +%H:%M:%S)" "${status:-no status yet}"
    sleep "$interval"
    waited=$((waited + interval))
  done
  warn "$group $id still ${status:-running} after ${timeout}s; re-run to keep waiting."
  return 2
}

# Idempotent submit: reuse the id in state unless it failed or FORCE=1.
# Usage: id="$(reuse_or_empty KEY group)"; [ -n "$id" ] || { submit...; }
reuse_or_empty() {
  local key="$1" group="$2" id status
  id="$(state_get "$key")"
  [ -n "$id" ] || return 0
  if [ "${FORCE:-0}" = "1" ]; then
    warn "FORCE=1: ignoring existing $key=$id" ; return 0
  fi
  status="$(job_status "$group" "$id")"
  case "$status" in
    JOB_FAILURE|JOB_STOPPED) warn "previous $key=$id ended $status; submitting a new one." ;;
    *) info "reusing $key=$id (${status:-unknown status}); FORCE=1 to submit a new one." >&2
       printf '%s' "$id" ;;
  esac
}

py() { (cd "$REPO_ROOT" && uv run --quiet python "$@"); }
