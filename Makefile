.PHONY: install db-up db-down init fetch import inspect test serve lint
install:
	python -m pip install -e '.[dev]'
db-up:
	docker compose up -d postgres
db-down:
	docker compose down
init:
	testpilot init-db
fetch:
	testpilot fetch
import:
	testpilot ingest --path data/bugswarm
inspect:
	testpilot inspect --path data/bugswarm
test:
	python -m pytest -q
lint:
	ruff check src tests
serve:
	uvicorn testpilot.api:api --host 127.0.0.1 --port 8000 --reload
