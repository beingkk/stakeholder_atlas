# Stakeholder Atlas

Minimal full-stack scaffold for stakeholder research tooling.

## Stack

- **Backend**: FastAPI (Python 3.12, managed with [uv](https://github.com/astral-sh/uv))
- **Frontend**: React + TypeScript (Vite)

## Getting started

### Prerequisites

- Node.js 18+
- [uv](https://github.com/astral-sh/uv)

### Backend

```bash
cd backend
cp .env.example .env
uv sync --dev
uv run python main.py
```

API: http://localhost:8000 — docs at http://localhost:8000/docs

### Frontend

```bash
cd frontend
cp .env.example .env.local
npm install
npm run dev
```

App: http://localhost:3000

### Pre-commit hooks

```bash
cd backend
uv sync --dev
cd ..
uv run --directory backend pre-commit install
uv run --directory backend pre-commit run --all-files
```

## Development

```bash
# Backend tests
cd backend && uv run pytest test/

# Backend linting
cd backend && uv run ruff check . && uv run ruff format .

# Frontend linting
cd frontend && npm run lint
```
