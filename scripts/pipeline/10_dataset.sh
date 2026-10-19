#!/usr/bin/env bash
# Create the Distil Dataset ("the model's data") from config/ + data/traces.jsonl
# (+ data/train.jsonl / data/test.jsonl if present). Validates the bundle on upload.
source "$(dirname "$0")/../lib/common.sh"
require_distil

id="$(reuse_or_empty DATASET_ID dataset)"
if [ -n "$id" ]; then ok "dataset $id"; exit 0; fi

bundle="$REPO_ROOT/runs/bundle"
rm -rf "$bundle" && mkdir -p "$bundle"
cp "$REPO_ROOT/config/config.yaml" "$REPO_ROOT/config/job_description.json" "$bundle/"
found=0
for f in traces train test; do
  if [ -s "$REPO_ROOT/data/$f.jsonl" ]; then
    cp "$REPO_ROOT/data/$f.jsonl" "$bundle/"
    info "  $f.jsonl: $(wc -l < "$REPO_ROOT/data/$f.jsonl" | tr -d ' ') rows"
    found=1
  fi
done
[ "$found" = 1 ] || die "no data/traces.jsonl, data/train.jsonl or data/test.jsonl. Run 'make traces' first."

confirm_spend "dataset upload" datasets_post
id="$(distil_create dataset create --data "$bundle")"
state_set DATASET_ID "$id"
ok "dataset $id (saved to runs/state.env)"
