#!/usr/bin/env bash
# Run ON the Runpod pod. Serves the student base model as `base` and the trained LoRA adapter
# as `model` from one vLLM server on port 8000 (OpenAI-compatible, /v1).
#
#   MODEL_DIR=/workspace/<slm-id> VLLM_API_KEY=<secret> bash start_vllm.sh
#
# MODEL_DIR is the folder `make deploy` produced: model-adapter/ + config.yaml.
# Schema-valid JSON: clients send response_format=json_schema (slmkit/client.py does), and
# vLLM constrains decoding to the schema, so every answer parses and validates.
set -euo pipefail

MODEL_DIR="${MODEL_DIR:?set MODEL_DIR to the downloaded model folder (model-adapter/ + config.yaml)}"
VLLM_API_KEY="${VLLM_API_KEY:?set VLLM_API_KEY to a secret; clients send it as SERVE_API_KEY}"
PORT="${PORT:-8000}"
MAX_MODEL_LEN="${MAX_MODEL_LEN:-16384}"
GPU_MEM="${GPU_MEMORY_UTILIZATION:-0.85}"

[ -d "$MODEL_DIR/model-adapter" ] || { echo "ERROR: $MODEL_DIR/model-adapter not found" >&2; exit 1; }
[ -f "$MODEL_DIR/config.yaml" ] || { echo "ERROR: $MODEL_DIR/config.yaml not found" >&2; exit 1; }

if ! python3 -c "import vllm" 2>/dev/null; then
  echo "==> Installing vLLM ${VLLM_VERSION:-latest} (use a vLLM/PyTorch CUDA template to skip this)"
  pip install --quiet "vllm${VLLM_VERSION:+==$VLLM_VERSION}" pyyaml
fi
python3 -c "import yaml" 2>/dev/null || pip install --quiet pyyaml

# student name + lora_r from the model's own config, not guessed
read -r STUDENT LORA_R < <(python3 - "$MODEL_DIR/config.yaml" <<'PY'
import sys, yaml
cfg = yaml.safe_load(open(sys.argv[1]))
print(cfg["base"]["student_model_name"], (cfg.get("tuning") or {}).get("lora_r", 64))
PY
)

# HuggingFace repo + parser flags per student family (Distil deployment reference)
case "$STUDENT" in
  Qwen3.5-*|Qwen3.6-*|Qwen3.8-*) HF="Qwen/$STUDENT"; FLAGS=(--enable-auto-tool-choice --tool-call-parser qwen3_xml --reasoning-parser qwen3) ;;
  Qwen3-*)                       HF="Qwen/$STUDENT"; FLAGS=(--enable-auto-tool-choice --tool-call-parser hermes --reasoning-parser qwen3) ;;
  Llama-*)                       HF="meta-llama/$STUDENT"; FLAGS=(--enable-auto-tool-choice --tool-call-parser llama3_json) ;;
  LFM2*)                         HF="LiquidAI/$STUDENT"; FLAGS=(--enable-auto-tool-choice --tool-call-parser lfm2) ;;
  gemma-4-*)                     HF="google/$STUDENT"; FLAGS=(--enable-auto-tool-choice --tool-call-parser gemma4 --reasoning-parser gemma4) ;;
  gemma-3-*|SmolLM2-*)           HF="$( [[ $STUDENT == SmolLM2-* ]] && echo HuggingFaceTB || echo google )/$STUDENT"; FLAGS=() ;;
  *) echo "ERROR: unknown student $STUDENT; add it to start_vllm.sh" >&2; exit 1 ;;
esac

echo "==> Serving $HF (as 'base') + adapter (as 'model'), lora rank $LORA_R, port $PORT"
exec vllm serve "$HF" \
  --served-model-name base \
  --enable-lora \
  --lora-modules "model=$MODEL_DIR/model-adapter" \
  --max-lora-rank "$LORA_R" \
  --max-model-len "$MAX_MODEL_LEN" \
  --gpu-memory-utilization "$GPU_MEM" \
  --host 0.0.0.0 --port "$PORT" \
  --api-key "$VLLM_API_KEY" \
  ${FLAGS[@]+"${FLAGS[@]}"}
