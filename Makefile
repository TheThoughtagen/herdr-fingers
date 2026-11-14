PYTHON ?= python3

.PHONY: test check lint format
test:
	$(PYTHON) -m unittest -v
check: test lint
	$(PYTHON) -m compileall -q fingers.py ansi.py test_fingers.py test_ansi.py
lint:
	uvx --offline ruff check .
format:
	uvx --offline ruff format .
