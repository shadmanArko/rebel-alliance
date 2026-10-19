# Serving on Runpod with vLLM

One vLLM server serves both students:
- `base`: the untrained Qwen3.5-0.8B (for `make eval-base`)
- `model`: base plus the trained LoRA adapter (for `make eval-tuned`, `make invoke`, `make demo`)

The adapter is small (tens of MB). vLLM pulls the base model from HuggingFace at startup.

## 1. Get the adapter
```bash
make deploy                 # -> models/<slm-id>/{model-adapter/, config.yaml, model_client.py}
```

## 2. Create the pod (Runpod console)
- **GPU:** a 0.8B model fits on any 16 GB+ card. Pick the cheapest one available (e.g. an L4, an A4000/A5000
  class card or an RTX 4090). Put its hourly price in `.env` as `RUNPOD_GPU_USD_PER_HOUR`.
- **Template:** a recent PyTorch/CUDA template, or a vLLM template if one is listed. `start_vllm.sh`
  pip-installs vLLM when it's missing. Qwen3.5 needs a recent vLLM. Pin a version with `VLLM_VERSION=...` if
  the latest gives you trouble.
- **Expose HTTP port 8000.** The proxy URL is then `https://<pod-id>-8000.proxy.runpod.net`.
- Container disk: 30 GB or more (vLLM wheel + base model).

## 3. Copy the files and start
Use the SSH details from the pod's **Connect** dialog:
```bash
scp -P <port> -r models/<slm-id> serve/start_vllm.sh root@<pod-ip>:/workspace/
ssh -p <port> root@<pod-ip>
MODEL_DIR=/workspace/<slm-id> VLLM_API_KEY=$(openssl rand -hex 16) bash /workspace/start_vllm.sh
```
Note the key you used. Run it in `tmux` so the server survives when you disconnect.

## 4. Point the repo at it
In `.env`:
```
SERVE_BASE_URL=https://<pod-id>-8000.proxy.runpod.net/v1
SERVE_API_KEY=<the VLLM_API_KEY you used>
```
```bash
make invoke                      # tuned model on a sample incident
make invoke TARGET=base          # untrained model, same input
make eval-base eval-tuned compare
```

## Schema-valid JSON
`src/slmkit/client.py` sends `response_format={"type": "json_schema", ...}` with `config/schema.json`.
vLLM then constrains decoding to the schema, so every answer parses and validates. The eval reports
`schema_valid` either way. `--no-guided-json` on `eval/run_eval.py` measures the raw model.

The client also sends the training-time system prompt (`task_description`) and
`chat_template_kwargs: {enable_thinking: false}`. A small model degrades sharply outside its training setup.
Distil's generated `models/<slm-id>/model_client.py` is the reference client. If our numbers
disagree with Distil's, smoke-test with it:
```bash
uv run python models/<slm-id>/model_client.py --base-url "$SERVE_BASE_URL" --api-key "$SERVE_API_KEY" --model model
```

## Stop paying
Stop or terminate the pod in the Runpod console when you're done. A stopped pod still bills for its volume storage.

## Alternative: Distil hosted deployment
`make deploy HOSTED=1` creates a Distil-hosted deployment (2 per account, a trial session). Then
`distil inference-endpoint create-from-deployment ...`. See docs/pipeline.md.
