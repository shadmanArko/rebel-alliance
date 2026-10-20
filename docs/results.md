# Results: invoice approval, 0.8B student

**Task:** an invoice email, a purchase order and a goods receipt go in. The model runs four policy checks in order and answers
`{"decision": "approve | hold_no_po | hold_quantity | hold_price | hold_total"}`.
**Score:** exact match of the decision on the same 100 held-out test invoices, scored by Distil Labs.

| Model | Size | Correct decisions (judge vs reference) | Exact JSON match | Valid JSON | Source |
|---|---|---|---|---|---|
| Teacher: GLM 5.3 high-thinking | very large | **97 / 100** | 97% | 100% | teacher evaluation `4d15b316` |
| Base Qwen3.5-0.8B, untrained | 0.8B | **41 / 100** | 2% | (n/a) | `slm metrics` base, SLM `9c0ca97f` |
| **Tuned Qwen3.5-0.8B, thinking on** | 0.8B | **90 / 100** | 90% | 100% | `slm metrics` + predictions, SLM `9c0ca97f` |

**The tuned 0.8B keeps 93% of the teacher's accuracy (90 / 97)** and closes 87% of the base-to-teacher gap
(`(90 − 41) / (97 − 41)`), so it counts as a deploy candidate. The untrained model's 2% exact match is mostly format
failure: its answers are not the bare JSON object. The judge column scores the decision itself.

Training: 4 epochs over 4,156 rows, final training loss ≈ 0.023 (from 0.47). It took about 2 hours on Distil Labs.

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
