#!/usr/bin/env bash
# Download the trained adapter (free) into models/<slm-id>/ and print how to serve it on Runpod.
# HOSTED=1 instead creates a Distil hosted deployment (2 credits per account; a trial session).
source "$(dirname "$0")/../lib/common.sh"
require_distil

slm="${SLM:-$(state_require SLM_ID 'make train')}"
[ "$(job_status slm "$slm")" = JOB_SUCCESS ] || die "SLM $slm is not finished ($(job_status slm "$slm")). Check 'make status'."

if [ "${HOSTED:-0}" = "1" ]; then
  id="$(reuse_or_empty DEPLOYMENT_ID deployment)"
  if [ -z "$id" ]; then
    confirm_spend "hosted deployment of SLM $slm" deployments_from_slms_post
    id="$(distil_create deployment create-from-slm "$slm")"
    state_set DEPLOYMENT_ID "$id"
  fi
  poll_job deployment "$id" || exit $?
  ok "deployment $id ready. Put an endpoint in front of it:"
  echo "  distil inference-endpoint create-from-deployment --name <prefix> --fallback-model <owner/model> $id"
  exit 0
fi

dest="$REPO_ROOT/models/$slm"
if [ -d "$dest/model-adapter" ] && [ "${FORCE:-0}" != "1" ]; then
  ok "already downloaded: models/$slm (FORCE=1 to re-download)"
else
  mkdir -p "$dest"
  info "Downloading model.tar + config.yaml"
  distil slm download --destination "$dest" "$slm" >/dev/null || die "slm download failed"
  distil slm download-metadata --destination "$dest" "$slm" >/dev/null || warn "no model_client.py yet"
  tar -xf "$dest/model.tar" -C "$dest" || die "could not extract $dest/model.tar"
  ok "models/$slm ready"
fi
state_set MODEL_DIR "models/$slm"

student="$(py -c "import yaml,sys; print(yaml.safe_load(open(sys.argv[1]))['base']['student_model_name'])" "$dest/config.yaml")"
cat <<EOF

Serve it on Runpod (full guide: serve/README.md):
  1. Create a GPU pod (any 16 GB+ GPU is plenty for $student), expose HTTP port 8000.
  2. Copy the adapter to the pod:   scp -P <port> -r models/$slm serve/start_vllm.sh root@<pod-ip>:/workspace/
     (or push models/$slm to a private HF repo / Runpod network volume)
  3. On the pod:                    MODEL_DIR=/workspace/$slm VLLM_API_KEY=<secret> bash /workspace/start_vllm.sh
  4. In .env:                       SERVE_BASE_URL=https://<pod-id>-8000.proxy.runpod.net/v1  SERVE_API_KEY=<secret>
  5. Try it:                        make invoke
EOF
