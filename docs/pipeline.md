# Pipeline details and Distil CLI notes

Written against **distil CLI 0.35.0** and the
[distil-cli-skill](https://github.com/distil-labs/distil-cli-skill). Check `distil <group> --help`
after `distil update` before you change any script.

## The CLI differs from older guides
| You may have read | Actual command (0.35.0) |
|---|---|
| `distil login` / `distil register` | `distil auth` / `distil signup` |
| `distil model ...` | `distil slm ...` (the trained Small Language Model) |
| "create a model" | `distil dataset create`. A **Dataset** (config, job description, traces, train, test) is the root entity. Models are trained *from* a Dataset |

## Entity chain (ids in `runs/state.env`)
```
data/traces.jsonl ─► DATASET_ID ─relabel-traces-test─► TESTSET_DATASET_ID ─► TEACHER_EVAL_ID
                                                          │
                                   relabel-traces-train ─► TRAIN_RELABEL_ID
                                   generate-synthetic-data-train ─► TRAIN_SYNTH_ID (= TRAIN_DATASET_ID)
                                                          │
                                         slm create-from-dataset ─► SLM_ID ─► models/<SLM_ID>/
```
Every expand creates a new child Dataset. Nothing is mutated in place, so a failed step can be
retried from its parent.

## Commands each script runs
| Script | distil commands |
|---|---|
| `10_dataset.sh` | `dataset create --data runs/bundle` |
| `20_testset.sh` | `dataset relabel-traces-test [--smoke]`, `dataset status`, `dataset download` |
| `30_teacher_eval.sh` | `teacher-evaluation create-from-dataset [--config]`, `metrics`, `download-predictions` |
| `40_trainset.sh` | `dataset relabel-traces-train`, `dataset generate-synthetic-data-train [--smoke]` |
| `50_train.sh` | `slm create-from-dataset [--smoke] [--config]`, `slm status`, `slm metrics` |
| `55_eval_tuned.sh` | `slm metrics`, `slm download-predictions` |
| `70_deploy.sh` | `slm download`, `slm download-metadata`, or `deployment create-from-slm` (HOSTED=1) |

All creates use `--output json` and read `.id`. Status is read from the JSON `status` field
(`deployment_status` for deployments), not from the exit code. Terminal states are
`JOB_SUCCESS`, `JOB_FAILURE` and `JOB_STOPPED`.

## Smoke runs
`SMOKE=1` on `testset`, `trainset` and `train` uses the smoke credit route (20 per account): 128 rows,
or 1 epoch on 128 rows for training. A smoke result is a **side branch**. The full run is always
submitted on the same parent, never on the smoke's child. The scripts store smoke ids under
separate keys (`*_SMOKE_ID`) so they can't leak into the main chain.

## How to read the numbers
- **Distil platform metrics** (`runs/*/metrics.json`) come from an LLM judge (`zai.glm-5.3-low-thinking`, fixed in
  `config/config.yaml`). Because the test set is teacher-labelled, the primary metric is
  `llm-as-a-judge-reference-free`.
- **Our metrics** (`eval/results.json`) are deterministic: JSON and schema validity, exact match,
  per-field F1 (token F1 on free text, exact on enums and booleans) and key-field accuracy (severity,
  category, escalation).
- **Gap closed** = (tuned − base) / (teacher − base). A value of 0.8 or more makes the model a deploy candidate, 0.4–0.8 means retune, and
  below 0.4 means fix the data or the teacher.
- Judge scores are noisy (non-zero temperature). Don't act on differences smaller than the gap between two runs of
  the same evaluation.
- **Cost per 1k requests.** For the teacher it's token usage × the `.env` prices. For the student it's GPU $/hour ×
  mean latency ÷ concurrency (`--workers`). That's an upper bound: a busier pod batches more requests and costs less per request.

## Troubleshooting
| Symptom | Fix |
|---|---|
| `distil: command not found` | `export PATH="$HOME/.local/bin:$PATH"` or open a new terminal |
| `Not logged in or session expired` | `distil auth` |
| relabel job refuses: not enough traces | lower `trace_processing.num_*_relabelled` or export more traces |
| `Invalid config: ...` on create | read the message; the bundle is in `runs/bundle/` |
| A job failed | `distil <group> logs <id>`, fix it, then re-run the target (failed ids are replaced automatically) |
| Tuned model much worse live than in Distil metrics | the system prompt or thinking setting differs; test with `model_client.py` (serve/README.md) |
