# data/

Everything here is gitignored except this file, `samples/` and `raw/.gitkeep`.

| Path | Produced by | Notes |
|---|---|---|
| `raw/langfuse_generations.jsonl` | `make traces` | raw Langfuse observations, kept for debugging the conversion |
| `traces.jsonl` | `make traces` | `{"messages": [...]}` per line (`openai_messages`), the input to relabelling |
| `train.jsonl`, `test.jsonl` | optional, by hand | only if you have **gold** labels. They are uploaded with `make dataset`. A `test.jsonl` here skips `make testset` |
| `samples/` | committed | tiny hand-made fixtures for tests and `make invoke`. **No production data** |

The test set built on the platform is downloaded to `runs/testset/test.jsonl`, and the eval scripts use it.
