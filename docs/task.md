# The task, and how to change it

**Current task:** incident triage. The input is raw server logs and the output is one JSON incident report.

Three files define a task. No code changes are needed to swap it:

| File | What to change |
|---|---|
| `config/job_description.json` | `task_description` (becomes the model's system prompt, so state the output format and give one short example), `llm_as_a_judge_instructions` (pass/fail criteria), `synthetic_data_generation_instructions` (what the inputs look like) |
| `config/schema.json` | JSON schema of the output. Used for guided decoding in vLLM and for scoring: enum, boolean and number fields are scored by exact match, strings and arrays by token F1 |
| `config/config.yaml` | `base.task` (`question-answering` for text in and JSON out), student, teacher, generation targets |

For a non-JSON task (free text or a single label), set `synthgen.output_is_json: false`, adapt
`src/slmkit/metrics.py`, and drop `response_format` in `src/slmkit/client.py`.

Also update `data/samples/` (the tiny test fixtures) and the README headline.

**Lock the task before `make testset`.** Changing `task_description` after the first teacher
evaluation invalidates every score.
