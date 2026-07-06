.PHONY: install test verify lint format server studio dev help

help:
	@echo "GroovyUI dev targets (make install, make test, make server, make studio)"

install:
	uv sync --all-packages --group dev
	@if command -v pnpm >/dev/null 2>&1; then pnpm install; \
	elif [ -f apps/studio/package.json ]; then cd apps/studio && npm install; \
	else echo "Install Node 20+ for the studio UI"; fi

test:
	uv run pytest tests/ -q

verify:
	uv run pytest tests/golden/ -q

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
	@echo "Start API (8188) and studio (5173) in separate terminals:"
	@echo "  make server"
	@echo "  make studio"
