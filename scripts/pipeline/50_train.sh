#!/usr/bin/env bash
# Fine-tune the student (base.student_model_name) on the training dataset.
# SMOKE=1: 1 epoch on 128 rows with the smoke credit (20 per account vs 5 full runs).
# CONFIG=path/to/config.yaml: train with an override (e.g. a sweep), same dataset.
source "$(dirname "$0")/../lib/common.sh"
require_distil

dataset="$(state_get TRAIN_DATASET_ID)"
[ -n "$dataset" ] || dataset="$(state_require DATASET_ID 'make dataset')"

key=SLM_ID; args=(); label=""; route=slms_from_datasets_post
if [ "${SMOKE:-0}" = "1" ]; then key=SLM_SMOKE_ID; args=(--smoke); label=" (smoke)"; route=slms_from_datasets_smoke_post; fi
if [ -n "${CONFIG:-}" ]; then [ -f "$CONFIG" ] || die "CONFIG=$CONFIG not found"; args+=(--config "$CONFIG"); fi

id="$(reuse_or_empty "$key" slm)"
if [ -z "$id" ]; then
  confirm_spend "train student on dataset $dataset$label" "$route"
  id="$(distil_create slm create-from-dataset ${args[@]+"${args[@]}"} "$dataset")"
  state_set "$key" "$id"
fi
poll_job slm "$id" || exit $?
[ "$(job_status slm "$id")" = JOB_SUCCESS ] || exit 0

out="$REPO_ROOT/runs/slm-$id"
mkdir -p "$out"
distil slm metrics --output json "$id" > "$out/metrics.json" || die "could not read slm metrics"
info "base : $(jq -c '.base_model_performance' "$out/metrics.json")"
info "tuned: $(jq -c '.tuned_model_performance' "$out/metrics.json")"
ok "SLM $id trained. Next: make eval-tuned, make deploy"
