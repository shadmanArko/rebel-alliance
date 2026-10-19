#!/usr/bin/env bash
# Teacher evaluation on the locked test set, then score its predictions with our metric.
# TEACHER=<catalog name> evaluates a different teacher via a config override.
source "$(dirname "$0")/../lib/common.sh"
require_distil

dataset="$(state_require TESTSET_DATASET_ID 'make testset')"
out="$REPO_ROOT/runs/teacher-eval"
mkdir -p "$out"

args=()
if [ -n "${TEACHER:-}" ]; then
  distil dataset download-metadata --destination "$out/override" "$dataset" >/dev/null \
    || die "could not download the dataset config for the override"
  py - "$out/override/config.yaml" "$TEACHER" <<'PY'
import sys, yaml
path, teacher = sys.argv[1], sys.argv[2]
cfg = yaml.safe_load(open(path))
cfg["base"]["teacher_model_name"] = teacher   # the judge stays as it was: scores stay comparable
yaml.safe_dump(cfg, open(path, "w"), sort_keys=False)
PY
  args=(--config "$out/override/config.yaml")
fi

id="$(reuse_or_empty TEACHER_EVAL_ID teacher-evaluation)"
if [ -z "$id" ]; then
  confirm_spend "teacher evaluation${TEACHER:+ ($TEACHER)}" teacher_evaluations_post
  id="$(distil_create teacher-evaluation create-from-dataset ${args[@]+"${args[@]}"} "$dataset")"
  state_set TEACHER_EVAL_ID "$id"
fi
poll_job teacher-evaluation "$id" || exit $?
[ "$(job_status teacher-evaluation "$id")" = JOB_SUCCESS ] || exit 0

distil teacher-evaluation metrics --output json "$id" > "$out/metrics.json" || die "could not read metrics"
distil teacher-evaluation download-predictions --file-name "$out/predictions.jsonl" "$id" >/dev/null \
  || die "could not download predictions"
info "platform metrics: $(jq -c '.teacher_performance' "$out/metrics.json")"
py eval/run_eval.py --target teacher --predictions "$out/predictions.jsonl"
