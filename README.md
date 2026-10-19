# rebel-alliance: distil a 0.8B model for invoice approval

```bash
git clone https://github.com/shadmanArko/rebel-alliance.git && cd rebel-alliance
make setup            # brew, git, uv, Python, venv, Distil CLI, .env
distil auth           # or: distil signup
make check            # PASS on every required item
make import-invoice   # fetch the task data (free); then see docs/invoice.md
```

**Task (GTC Berlin Builders Night):** invoice approval, taken from
[distil-labs/reasoning-blogpost-benchmark](https://github.com/distil-labs/reasoning-blogpost-benchmark).
The input is an invoice email, a purchase order and a goods receipt. The output is
`{"decision": "approve|hold_no_po|hold_quantity|hold_price|hold_total"}`. The teacher (GLM 5.3,
high thinking) writes the reasoning data, and Distil Labs fine-tunes **Qwen3.5-0.8B** with thinking on.
Their 4B student reached 98% this way. We find out what a 0.8B keeps, and at what latency and cost.
**Runbook: [docs/invoice.md](docs/invoice.md).** Everything specific to the task is in `config/`
([docs/task.md](docs/task.md)).

## Architecture

```
 Langfuse ──make traces──► data/traces.jsonl ──make dataset──► Distil Dataset
                                                                    │
                     make testset   (teacher relabels traces → locked test set)
                     make eval-teacher (teacher scored on the test set = the ceiling)
                     make trainset  (relabel + synthetic data → train set)
                     make train     (LoRA fine-tune of Qwen3.5-0.8B)
                                                                    │
                     make deploy    (download adapter) ──► Runpod pod: vLLM serves
                                                            `base` (untrained) + `model` (tuned)
                                                                    │
           make eval-base / eval-tuned / invoke / demo ◄────────────┘
           make compare  →  teacher vs base vs tuned: accuracy, latency, $/1k requests
```

| Piece | Where | Notes |
|---|---|---|
| Trace export | `scripts/langfuse_export.py` | Langfuse public API → Distil `openai_messages` format |
| Pipeline | `scripts/pipeline/*.sh` | Thin wrappers around the `distil` CLI. They are idempotent, and job ids go in `runs/state.env` |
| Task definition | `config/job_description.json`, `config/schema.json`, `config/config.yaml` | System prompt, judge rules, JSON schema, models |
| Metrics | `src/slmkit/metrics.py`, `eval/` | JSON validity, schema validity, exact match, per-field F1, key-field accuracy |
| Serving | `serve/` | vLLM on Runpod, schema-constrained JSON (`response_format: json_schema`) |
| Demo | `demo/` | CLI (`make invoke`) and a web page with base and tuned side by side (`make demo`) |

## Workflow

| Step | Command | Costs | Output |
|---|---|---|---|
| 1 | `make traces` | free | `data/traces.jsonl` (aim for 300+) |
| 2 | `make dataset` | 1 upload credit | `DATASET_ID` |
| 3 | `make testset` | 1 relabel credit | locked test set in `runs/testset/` (review it) |
| 4 | `make eval-teacher` | 1 teacher-eval credit | teacher score = the ceiling |
| 5 | `make trainset` | 1 relabel + 1 synthgen credit (`SMOKE=1` first) | `TRAIN_DATASET_ID` |
| 6 | `make train` | 1 training credit (`SMOKE=1` first) | `SLM_ID`, base and tuned platform metrics |
| 7 | `make eval-tuned` | free | tuned accuracy (plus latency once the pod is up) |
| 8 | `make deploy` | free | `models/<slm-id>/`, then start the pod ([serve/README.md](serve/README.md)) |
| 9 | `make eval-base`, `make invoke`, `make demo` | Runpod time | base numbers, live demo |
| 10 | `make compare` | free | the final table |

**Credits are scarce.** A new Distil account gets 5 full trainings, 5 relabels, 5 synthgen runs,
5 teacher evals and 2 hosted deployments, plus 20 smoke runs per route. Every paid step shows the
balance and asks before it submits (`YES=1` skips the prompt). Re-running a target reuses the
job that already exists, and `FORCE=1` submits a new one. **Only the pipeline owner runs steps
2–6, from one Distil account.** Job ids are tied to that account.

Knobs: `SMOKE=1` (small, cheap run), `WAIT=0` (submit and return), `LIMIT=50` (evaluate on the
first 50 rows), `TEACHER=<catalog name>` (try another teacher), `CONFIG=path.yaml` (training override).
Run `make help` for all targets. Full details are in [docs/pipeline.md](docs/pipeline.md).

## Team roles (4–6 people)

| Role | Owns | Main targets / files |
|---|---|---|
| Pipeline owner | The single Distil account, credits, `runs/state.env` | `make dataset testset eval-teacher trainset train` |
| Data | Langfuse export, trace quality, test-set review | `make traces`, `scripts/langfuse_export.py`, `runs/testset/` |
| Task & prompt | Job description, judge rules, schema, synthgen instructions | `config/` |
| Eval | Metrics, the compare table, error analysis | `eval/`, `src/slmkit/metrics.py` |
| Serving | Runpod pod, vLLM, guided JSON, cost numbers | `serve/`, `make deploy eval-base` |
| Demo & pitch | Demo UI, slides, the story | `demo/`, `make demo compare` |

See [CONTRIBUTING.md](CONTRIBUTING.md) before your first PR.
