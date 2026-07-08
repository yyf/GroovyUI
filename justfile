# GroovyUI development tasks — see docs/internal/ENGINEERING.md

set shell := ["bash", "-cu"]

default:
    @just --list

install:
    uv sync --all-packages --group dev
    pnpm install

dev:
    @echo "Starting API server (127.0.0.1:8188) and studio (5173)..."
    uv run --package groovy-server groovy-server &
    pnpm dev:studio

test:
    uv run pytest tests/ -q

test-studio:
    pnpm --filter @groovy/studio test

verify:
    uv run pytest tests/golden/ -q

lint:
    uv run ruff check packages/ nodes/ server/ tests/
    uv run ruff format --check packages/ nodes/ server/ tests/
    pnpm lint:studio

format:
    uv run ruff format packages/ nodes/ server/ tests/

server:
    uv run --package groovy-server groovy-server

studio:
    pnpm dev:studio
