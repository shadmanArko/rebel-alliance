# Invoice approval: runbook

Source: [distil-labs/reasoning-blogpost-benchmark](https://github.com/distil-labs/reasoning-blogpost-benchmark)
(`invoice/`, pinned at `71aac74`, Apache 2.0, fully synthetic).

**Task.** The input is three documents: an invoice email, a PO from the ERP and a goods receipt from the ERP. The
output is `{"decision": "approve|hold_no_po|hold_quantity|hold_price|hold_total"}`. Four policy checks are
run in order, and the first one that fails decides the label. Score = exact match of the decision (our
`Exact` / `KeyAcc` columns).

## What to beat (their numbers: Qwen3.5-**4B**, the same 100 test rows)
| Model | Accuracy |
|---|---|
| Base, thinking off | 53 |
| Base, thinking on | 37 (63 rows cut off at 2,048 tokens) |
| Tuned, thinking off | 84 |
| Tuned, thinking on | **98** (median reasoning ≈ 270 tokens) |

Our question: **how much of that does a 0.8B student keep, at what latency and cost?** Expect it to land
below the 4B. The gap between thinking and no thinking is the interesting part of the story.

## How it maps onto our pipeline
| Benchmark README (old CLI) | Here (CLI 0.35.0) |
|---|---|
| `distil seed-dataset create --data invoice/seed` | `make import-invoice` then `make dataset` (`distil dataset create --data`) |
| `distil teacher-evaluation create-from-seed-dataset` | `make eval-teacher` |
| `distil training-dataset create-from-seed-dataset` | `make trainset` (synthetic generation, 4,000 rows, thinking on) |
| `distil slm create-from-training-dataset [--config no-thinking]` | `make train`, plus `CONFIG=config/config-no-thinking.yaml FORCE=1 make train` |

`make testset` isn't needed. The 100 test rows are uploaded with the dataset and locked from the start.
`config/config.yaml` is their config ported to the current schema. Only the student changed
(4B → 0.8B), and `max_completion_length` was raised to 3,072 for headroom.

## Run order (pipeline owner)
```bash
make import-invoice              # free: data/train.jsonl (40 seed rows w/ reasoning) + data/test.jsonl (100)
make dataset                     # 1 upload credit: the platform validates config + rows
make eval-teacher                # 1 teacher-eval credit: GLM 5.3 high-thinking on the 100 rows = ceiling
SMOKE=1 make trainset            # 1 smoke credit: 128 generated rows; read some reasoning_content
make trainset                    # 1 synthgen credit: ~4,000 rows with reasoning (slowest step)
SMOKE=1 make train               # optional, 1 smoke credit: catches config problems in 1 epoch
make train                       # 1 training credit: 0.8B, thinking ON
CONFIG=config/config-no-thinking.yaml FORCE=1 make train   # 1 training credit: thinking OFF, same data
make eval-tuned && make deploy   # free
```
`FORCE=1` on the second training run makes it a new job, and `runs/state.env` then points `SLM_ID` at the newer
run. **Write down both SLM ids.** `make status` lists them.

Total: 1 upload, 1 teacher eval, 1–2 smoke, 1 synthgen and 2 training credits. That leaves 3
trainings for iterations.

**Fast path** (when time is short): `FAST=1 make import-invoice` takes their finished 4,156-row training set
instead of the 40 seed rows. Then run `make dataset`, then `SYNTH=0 make trainset`, then `make train`. That skips generation
(one credit and the slowest wait), but we no longer generate the data ourselves. Say so in the pitch.

## Serving a reasoning student
- `serve/start_vllm.sh` already passes `--reasoning-parser qwen3` for Qwen3.5. The thinking arrives
  in `reasoning_content` and `content` holds only the JSON.
- Our client reads `base.enable_thinking` from `config/config.yaml`. When the pod serves the no-thinking adapter,
  set `STUDENT_THINKING=0` in `.env`. Sampling in thinking mode is the Qwen3.5 vendor setting (T=1.0, top_p 0.95, top_k 20).
- `make invoke FILE=data/samples/invoice_hold_total.txt` shows the decision. Add reasoning with
  `uv run python demo/triage.py --show-reasoning <file>`.
- Latency matters here: thinking adds about 270 output tokens per request. `make compare` shows the cost of
  that accuracy.

## Where Langfuse fits
This task has no production traffic, so Langfuse doesn't supply the data. Use it to trace every model call
(teacher, base, tuned) from the eval and the demo. That gives us latency and cost dashboards, and a record of
the calls to feed into a next iteration (`make traces`).
