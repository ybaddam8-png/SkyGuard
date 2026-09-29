PY=.venv/bin/python

.PHONY: bench all test venv sync-dashboard

venv:
	uv venv .venv --python 3.11
	uv pip install -p .venv -r requirements.txt

bench:
	$(PY) src/run_step2.py

test:
	$(PY) -m pytest tests/ -q

all:
	@test -f data/clean/observations_clean.parquet || $(PY) src/prepare_data.py
	$(MAKE) bench
	$(MAKE) test

sync-dashboard:
	cp outputs/metrics.json outputs/replay_stream.json stations.csv client/src/data/
	cp outputs/figures/*.png client/src/data/figures/
