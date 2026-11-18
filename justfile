# GroovyUI development tasks — see CONTRIBUTING.md

set shell := ["bash", "-cu"]

default:
    @just --list

install:
    bash scripts/install.sh

dev:
    bash scripts/dev.sh

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
