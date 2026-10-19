# Results: invoice approval, 0.8B student

**Task:** an invoice email, a purchase order and a goods receipt go in. The model runs four policy checks in order and answers
`{"decision": "approve | hold_no_po | hold_quantity | hold_price | hold_total"}`.
**Score:** exact match of the decision on the same 100 held-out test invoices, scored by Distil Labs.

| Model | Size | Accuracy (exact match) | Judge (Distil) | Source |
|---|---|---|---|---|
| Teacher: GLM 5.3 high-thinking | very large | **97 / 100** | 96% | our Distil teacher evaluation `4d15b316` |
| Base Qwen3.5-0.8B, untrained | 0.8B | _pending_ | _pending_ | Distil `slm metrics` (base) for SLM `9c0ca97f` |
| **Tuned Qwen3.5-0.8B, thinking on** | 0.8B | _pending_ | _pending_ | Distil `slm metrics` / predictions for SLM `9c0ca97f` |

Reference from Distil's published benchmark (Qwen3.5-**4B**, same test set): untrained 53, tuned without
thinking 84, **tuned with thinking 98**.

## What we built
- **One-command repo**: `make setup` → `make check`. The pipeline is `make import-invoice → dataset → eval-teacher →
  train → eval-tuned → compare`, and every paid step confirms the credit spend first.
- **Data**: 4,156 synthetic training invoices with step-by-step reasoning. Distil's teacher generated them from 40 seed
  examples, and we reused the published set to fit the time limit. The 100 test invoices are never trained on.
- **Training**: Distil Labs LoRA fine-tune of Qwen3.5-0.8B with `enable_thinking: true`, so the model writes its checks
  before it answers.
- **Observability**: every teacher, base and tuned call can be traced in Langfuse when keys are set.
- **Serving (ready, not run)**: `serve/start_vllm.sh` serves base and tuned side by side on vLLM, with
  schema-constrained JSON. We didn't run it today because the Runpod account had no credit.

## Not measured today
Latency and cost per 1k requests need a live GPU. We skipped Runpod, so those columns are empty.
The case for cost rests on size: a 0.8B model runs on a single small GPU, while the teacher needs a large multi-GPU
deployment.
