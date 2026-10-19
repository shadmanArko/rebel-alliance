# Distil a ~0.8B model for one narrow task. `make help` lists everything.
# Invoice task:   setup -> check -> import-invoice -> dataset -> eval-teacher -> trainset (SMOKE=1, then full)
#                 -> train -> eval-tuned -> deploy -> (start pod) -> eval-base -> invoke -> compare
# With traces:    setup -> check -> traces -> dataset -> testset -> eval-teacher -> trainset
#                 -> train -> eval-tuned -> deploy -> (start pod) -> eval-base -> invoke -> compare
#
# Common knobs (env vars): YES=1 skip credit prompts | SMOKE=1 small cheap run | FORCE=1 resubmit
#                          WAIT=0 submit and return | LIMIT=N eval on first N test rows

SHELL := /bin/bash
export PATH := $(HOME)/.local/bin:$(PATH)
PIPE := scripts/pipeline
PY := uv run --quiet python

.DEFAULT_GOAL := help
.PHONY: help setup check import-invoice traces dataset testset eval-teacher trainset train status \
        eval-base eval-tuned deploy invoke demo compare lint test clean-state

help: ## List targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[1m%-14s\033[0m %s\n",$$1,$$2}'

setup: ## One-time setup: brew, git, uv, Python, venv, Distil CLI, .env
	@bash scripts/setup.sh

check: ## PASS/FAIL per tool, .env key and Distil login
	@bash scripts/check.sh

import-invoice: ## Fetch the invoice seed data (40 train + 100 test) into data/  (FAST=1: their 4k train set)
	@bash scripts/import_invoice.sh

traces: ## Export generations from Langfuse -> data/traces.jsonl
	@$(PY) scripts/langfuse_export.py

dataset: ## Create the Distil Dataset from config/ + data/*.jsonl  (1 credit)
	@bash $(PIPE)/10_dataset.sh

testset: ## Teacher relabels traces into the locked test set  (1 credit)
	@bash $(PIPE)/20_testset.sh

eval-teacher: ## Distil teacher evaluation + our metric; + endpoint latency/cost if TEACHER_* set
	@bash $(PIPE)/30_teacher_eval.sh
	@if grep -qE '^TEACHER_BASE_URL=.+' .env 2>/dev/null; then \
	  $(PY) eval/run_eval.py --target teacher --endpoint $(if $(LIMIT),--limit $(LIMIT)); \
	else echo "  (TEACHER_BASE_URL not set: skipped teacher latency/cost)"; fi

trainset: ## Relabel traces into train + synthetic data generation  (1-2 credits)
	@bash $(PIPE)/40_trainset.sh

train: ## Fine-tune the 0.8B student  (1 training credit; SMOKE=1 uses a smoke credit)
	@bash $(PIPE)/50_train.sh

status: ## Status of every submitted job + remaining credits
	@bash $(PIPE)/60_status.sh

eval-base: ## Untrained 0.8B on the test set via the vLLM pod (needs SERVE_BASE_URL)
	@$(PY) eval/run_eval.py --target base --endpoint $(if $(LIMIT),--limit $(LIMIT))

eval-tuned: ## Tuned 0.8B: Distil predictions + live pod latency/cost
	@bash $(PIPE)/55_eval_tuned.sh

deploy: ## Download the trained adapter to models/ + Runpod instructions (HOSTED=1: Distil hosting)
	@bash $(PIPE)/70_deploy.sh

invoke: ## Send a sample invoice to the served model (FILE=path TARGET=base|tuned|teacher)
	@$(PY) demo/triage.py --target $(or $(TARGET),tuned) $(or $(FILE),data/samples/invoice_hold_price.txt)

demo: ## Web demo: base vs tuned side by side on http://127.0.0.1:7860
	@$(PY) demo/web.py

compare: ## Table: teacher vs base vs tuned (accuracy, latency, cost per 1k)
	@$(PY) eval/compare.py

lint: ## shellcheck + ruff
	@shellcheck -x scripts/*.sh scripts/lib/*.sh scripts/pipeline/*.sh serve/*.sh
	@uv run --quiet ruff check .

test: ## Unit tests (metrics, trace conversion)
	@uv run --quiet pytest -q

clean-state: ## Forget submitted job ids (does NOT delete anything on Distil)
	@rm -f runs/state.env && echo "runs/state.env removed"
