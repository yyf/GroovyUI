# GroovyUI development tasks — see CONTRIBUTING.md

set shell := ["bash", "-cu"]

default:
    @just --list

install:
    # Prefer 3.11 so DeepFilterNet (podcast-denoise) can use deepfilterlib wheels.
    @[ -d .venv ] || uv venv --python 3.11
    uv sync --all-packages --group dev
    pnpm install

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
