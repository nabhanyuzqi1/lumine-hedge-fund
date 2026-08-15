# ── Stage 1: Build dependencies ───────────────────────────────────────────────
FROM python:3.12.5-slim-bookworm AS builder

WORKDIR /app

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock README.md ./
RUN pip install --no-cache-dir uv && uv sync --frozen --no-dev --no-install-project
COPY src/ src/
RUN uv sync --frozen --no-dev

# ── Stage 2: Runtime ──────────────────────────────────────────────────────────
FROM python:3.12.5-slim-bookworm AS runtime

# Patch OS packages for known CVEs in base image (libexpat, libgnutls, openssl, libsqlite3).
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get upgrade -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --system lumine && useradd --system --gid lumine --no-create-home lumine

# Superadmin system-info: Docker socket akses butuh group docker.
# Host docker.sock biasanya gid 999 atau dynamically assigned — match host GID.
# WORKAROUND: buat group docker dengan GID yang match socket host (default 999),
# lalu tambahkan lumine ke group itu. Jika host GID berbeda, override di compose:
#   args: DOCKER_GID=<stat -c %g /var/run/docker.sock>
ARG DOCKER_GID=988
RUN groupadd -g ${DOCKER_GID} docker 2>/dev/null || true \
    && usermod -aG docker lumine

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY src/ src/
COPY alembic/ alembic/
COPY alembic.ini ./
COPY scripts/ scripts/

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

USER lumine

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

CMD ["uvicorn", "lumine.api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]