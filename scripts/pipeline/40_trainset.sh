#!/usr/bin/env bash
# Fill the train split on top of the test-set dataset:
#   1) relabel unused traces into train   (skip with RELABEL=0)
#   2) synthetic data generation          (skip with SYNTH=0)
# SMOKE=1 runs the synthetic step on 128 rows only, as a check of the config and prompt.
source "$(dirname "$0")/../lib/common.sh"
require_distil

parent="$(state_require TESTSET_DATASET_ID 'make testset')"

if [ "${RELABEL:-1}" = "1" ]; then
  id="$(reuse_or_empty TRAIN_RELABEL_ID dataset)"
  if [ -z "$id" ]; then
    confirm_spend "relabel traces -> train split" datasets_from_datasets_relabel_traces_post
    id="$(distil_create dataset relabel-traces-train "$parent")"
    state_set TRAIN_RELABEL_ID "$id"
  fi
  poll_job dataset "$id" || exit $?
  [ "$(job_status dataset "$id")" = JOB_SUCCESS ] || exit 0
  parent="$id"
fi

if [ "${SYNTH:-1}" = "1" ]; then
  key=TRAIN_SYNTH_ID; smoke=(); label=""; route=datasets_from_datasets_generate_synthetic_data_post
  if [ "${SMOKE:-0}" = "1" ]; then key=TRAIN_SYNTH_SMOKE_ID; smoke=(--smoke); label=" (smoke)"; route=datasets_from_datasets_smoke_post; fi
  id="$(reuse_or_empty "$key" dataset)"
  if [ -z "$id" ]; then
    confirm_spend "synthetic data generation -> train split$label" "$route"
    id="$(distil_create dataset generate-synthetic-data-train ${smoke[@]+"${smoke[@]}"} "$parent")"
    state_set "$key" "$id"
  fi
  poll_job dataset "$id" || exit $?
  [ "$(job_status dataset "$id")" = JOB_SUCCESS ] || exit 0
  # A smoke child is never trained on; only the full run becomes the training dataset.
  [ "${SMOKE:-0}" = "1" ] && { ok "smoke done: inspect with 'distil dataset download -d runs/smoke $id'"; exit 0; }
  parent="$id"
fi

state_set TRAIN_DATASET_ID "$parent"
distil dataset download --destination "$REPO_ROOT/runs/trainset" "$parent" >/dev/null 2>&1 \
  && info "train rows: $(wc -l < "$REPO_ROOT/runs/trainset/train.jsonl" | tr -d ' ')" || true
ok "training dataset $parent"
