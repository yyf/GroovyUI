.PHONY: install test verify lint format server studio dev help

help:
	@echo "GroovyUI dev targets (make install, make test, make server, make studio)"

install:
	bash scripts/install.sh

test:
	uv run pytest tests/ -q

verify:
	uv run pytest tests/golden/ -q
	uv run groovy-verify

lint:
	uv run ruff check packages/ nodes/ server/ tests/
	uv run ruff format --check packages/ nodes/ server/ tests/
	@if command -v pnpm >/dev/null 2>&1; then pnpm lint:studio; fi

format:
	uv run ruff format packages/ nodes/ server/ tests/

server:
	uv run --package groovy-server groovy-server

studio:
	@if command -v pnpm >/dev/null 2>&1; then pnpm dev:studio; else cd apps/studio && npm run dev; fi

dev:
	bash scripts/dev.sh
