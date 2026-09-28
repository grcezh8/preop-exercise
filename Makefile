INPUT ?= data/patients_sample_50.jsonl
OUTPUT ?= data/baseline_outputs.jsonl
REPORT ?= data/eval_report.json
DETERMINISM_REPORT ?= data/determinism_report.json
MODEL ?= gpt-4.1-mini

.PHONY: baseline evals determinism score report test all clean scenarios evals-full

baseline:
	uv run run_baseline.py \
		--input $(INPUT) \
		--output $(OUTPUT) \
		--model $(MODEL)

evals:
	uv run run_evals.py \
		--input $(INPUT) \
		--outputs $(OUTPUT) \
		--report $(REPORT)

determinism:
	uv run run_evals.py \
		--determinism \
		--input $(INPUT) \
		--model $(MODEL) \
		--report $(DETERMINISM_REPORT)

score:
	@python3 -c 'import json; r=json.load(open("$(REPORT)")); s=(r.get("primary_score",{}) or {}).get("value_pct"); print(s if s is not None else r.get("local_metrics_summary",{}).get("aggregate_local_score_pct", 0.0))'

report:
	uv run view_report.py --report $(REPORT)

test:
	uv run \
		--with 'openai>=2.0.0' \
		--with 'pydantic>=2.8.0' \
		--with 'pytest>=8.0.0' \
		--with 'hypothesis>=6.100' \
		python -m pytest tests

# builds the hand-labeled scenarios, then scores seed + scenarios + each text check
# MODE=pattern_only lets python wording checks approve on their own (offline, no llm)
MODE ?= default

scenarios:
	uv run --with 'pydantic>=2.8.0' python -m evals.build_cases

# LLM=openai (real api) or a scripted misbehaving llm: outage | garbage | cautious | yes_man
LLM ?= openai

evals-full:
	uv run --with 'pydantic>=2.8.0' --with 'openai>=2.0.0' python -m evals.run_evals_full --mode $(MODE) --llm $(LLM) --model $(MODEL)

all: baseline evals determinism score

clean:
	rm -f data/baseline_outputs.jsonl \
		data/eval_report.json \
		data/determinism_report.json
	rm -rf data/audit evals/data data/eval_full_report.json
