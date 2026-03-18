PYTHON  := python3.11
VENV    := .venv
BIN     := $(VENV)/bin

.PHONY: setup test run run-sse clean

setup:
	$(PYTHON) -m venv $(VENV)
	$(BIN)/pip install --upgrade pip
	$(BIN)/pip install -e ".[dev]"
	@cp -n .env.example .env 2>/dev/null || true
	@echo ""
	@echo "Done! Next steps:"
	@echo "  1. Edit .env to set MONGO_URI"
	@echo "  2. Run: make run"

test:
	$(BIN)/pytest -v

run:
	$(BIN)/python -m tron_event_mcp

run-sse:
	MCP_TRANSPORT=sse $(BIN)/python -m tron_event_mcp

clean:
	rm -rf $(VENV) src/*.egg-info
