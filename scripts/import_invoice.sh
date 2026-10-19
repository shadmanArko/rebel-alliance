#!/usr/bin/env bash
# Fetch the invoice-approval data from distil-labs/reasoning-blogpost-benchmark (Apache 2.0,
# fully synthetic) at a pinned commit into data/. Safe to re-run: files are overwritten.
#
#   make import-invoice            seed: 40 train rows with reasoning + 100 test rows
#   FAST=1 make import-invoice     their finished training set (4,156 rows) instead of the
#                                  40 seed rows: skips synthetic generation (saves ~1 credit
#                                  and the generation time), but the data is theirs, not ours
source "$(dirname "$0")/lib/common.sh"

REPO_SHA="71aac7419f90b82ec40ff3058003cb027af670c7"
BASE="https://raw.githubusercontent.com/distil-labs/reasoning-blogpost-benchmark/$REPO_SHA/invoice"
train_src="seed/train.jsonl"
[ "${FAST:-0}" = "1" ] && train_src="training-data/train.jsonl"

mkdir -p "$REPO_ROOT/data"
fetch() {
  local src="$1" dest="$2" tmp
  tmp="$(mktemp)"
  curl -fsSL "$BASE/$src" -o "$tmp" || { rm -f "$tmp"; die "download failed: $BASE/$src"; }
  py -c "import json,sys; [json.loads(l) for l in open(sys.argv[1])]" "$tmp" \
    || { rm -f "$tmp"; die "$src is not valid JSONL"; }
  mv "$tmp" "$dest"
  ok "data/$(basename "$dest"): $(grep -c '' "$dest") rows  <- invoice/$src"
}
fetch "$train_src" "$REPO_ROOT/data/train.jsonl"
fetch "seed/test.jsonl" "$REPO_ROOT/data/test.jsonl"

if [ -s "$REPO_ROOT/data/traces.jsonl" ]; then
  warn "data/traces.jsonl exists and would be uploaded too; delete it unless you mean to."
fi
info "Next: make dataset   (uploads config/ + data/train.jsonl + data/test.jsonl)"
