PYTHON ?= .venv/bin/python
PROFILE ?= smoke
MODE ?= fixed
STAMP := $(shell date +%Y%m%d-%H%M%S)
OUT ?= results/$@-$(MODE)-$(STAMP)

.PHONY: install lint test smoke load stress spike soak compare report app
install:
	$(PYTHON) -m pip install -r requirements.lock
	$(PYTHON) -m pip install --no-deps -e .
lint:
	.venv/bin/ruff check .
	.venv/bin/ruff format --check .
test:
	$(PYTHON) -m pytest -q
smoke:
	$(PYTHON) -m tools.run --profile smoke --mode fixed --out $(OUT) --gate
stress spike soak load:
	$(PYTHON) -m tools.run --profile $@ --mode $(MODE) --out $(OUT)
compare:
	$(PYTHON) -m tools.compare --out results/comparison-$(STAMP)
report:
	$(PYTHON) -m tools.report --input measurements/comparison.json --evidence measurements --out site
app:
	APP_MODE=$(MODE) $(PYTHON) -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8120
