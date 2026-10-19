# Contributing

## Rules
- **Never push to `main`.** Every change goes through a PR, and one teammate approves it.
- **Small PRs**: one change each, reviewable in 5 minutes. Draft PRs are welcome early.
- **Never commit secrets or big files.** `.env`, `data/*.jsonl`, `runs/`, `models/` and `*.tar`
  are gitignored. Don't force-add them. Run `git status` before you commit.
- Run `make lint test` before you open a PR.

## Branch names
`<type>/<short-name>`, where type is one of:

| Type | For |
|---|---|
| `feat/` | new script, target, feature (`feat/web-demo-latency`) |
| `fix/` | bug fix (`fix/langfuse-pagination`) |
| `data/` | data pipeline or sample changes (`data/filter-error-traces`) |
| `exp/` | an experiment: a config or prompt change plus its results (`exp/teacher-kimi-k3`) |
| `docs/` | docs only |

## Adding data
- Real traces come from Langfuse via `make traces`. Don't commit them. They stay in `data/`, which is gitignored.
- `data/samples/` holds only **tiny, hand-made, non-sensitive** examples for tests and demos.
  Never put production logs there.
- Don't write training rows by hand to pad the dataset. New rows come from relabelling traces and from
  synthetic generation (`make trainset`). To steer that, edit
  `synthetic_data_generation_instructions` in `config/job_description.json`.
- The test set is locked after `make testset`. Changing it makes every earlier score stale, so
  discuss it in the team channel first.

## Running an experiment
1. Branch `exp/<name>`.
2. Change one thing: `config/config.yaml` (student, epochs, lora_r), the job description, or
   the teacher (`TEACHER=... make eval-teacher`).
3. Ask the pipeline owner to run it, because credits are shared. Use `SMOKE=1` first whenever possible.
4. Add `docs/experiments/<name>.md` with what changed, the job ids, the `make compare` output and
   one line saying what you learned.
5. Open the PR. Commit `eval/results.json` only if this run becomes the new reference.

## Python / shell style
- Python: `uv add <pkg>` to add a dependency (it updates `pyproject.toml` and `uv.lock`), and `ruff` for linting.
- Shell: `scripts/lib/common.sh` helpers, and `shellcheck` must pass. Scripts must stay safe to re-run.
