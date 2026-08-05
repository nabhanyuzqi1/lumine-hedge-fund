# Lumine Backend

Python backend for Lumine — an AI-native quantitative hedge fund platform.

## Stack

- Python 3.12+
- FastAPI + Uvicorn
- SQLAlchemy 2.0 (async) + asyncpg
- Alembic
- Redis (hiredis)
- structlog

## Development

```bash
uv sync --all-extras
uv run alembic upgrade head
uv run pytest
```
