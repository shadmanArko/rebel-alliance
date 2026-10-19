#!/usr/bin/env bash
# Build the locked test set: the teacher relabels traces into test.jsonl.
# Skipped when the uploaded data already had a test split (TESTSET_FROM_UPLOAD=1).
# SMOKE=1 runs on 128 traces with the smoke credit (a side branch; never continue from it).
source "$(dirname "$0")/../lib/common.sh"
require_distil

parent="$(state_require DATASET_ID 'make dataset')"
if [ -s "$REPO_ROOT/data/test.jsonl" ] && [ "${FORCE:-0}" != "1" ]; then
  state_set TESTSET_DATASET_ID "$parent"
  ok "data/test.jsonl was uploaded; using dataset $parent as the test-set dataset"
  exit 0
fi

key=TESTSET_DATASET_ID; smoke=(); label=""; route=datasets_from_datasets_relabel_traces_post
if [ "${SMOKE:-0}" = "1" ]; then key=TESTSET_SMOKE_ID; smoke=(--smoke); label=" (smoke)"; route=datasets_from_datasets_smoke_post; fi

id="$(reuse_or_empty "$key" dataset)"
if [ -z "$id" ]; then
  confirm_spend "relabel traces -> test split$label" "$route"
  id="$(distil_create dataset relabel-traces-test ${smoke[@]+"${smoke[@]}"} "$parent")"
  state_set "$key" "$id"
fi
poll_job dataset "$id"
distil dataset download --destination "$REPO_ROOT/runs/testset" "$id" >/dev/null 2>&1 \
  && info "test rows: $(wc -l < "$REPO_ROOT/runs/testset/test.jsonl" | tr -d ' ') (runs/testset/test.jsonl)" || true
ok "test-set dataset $id. Review runs/testset/test.jsonl before going further: it is locked from here."
