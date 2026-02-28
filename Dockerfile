# ImpactOS — Multi-stage Docker build
# Stage 1: Build dependencies (cached unless pyproject.toml changes)
# Stage 2: Slim runtime with non-root user

# ---------------------------------------------------------------------------
# Stage 1: Builder — install Python dependencies
# ---------------------------------------------------------------------------
FROM python:3.11-slim AS builder

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency manifest + files referenced by pyproject.toml FIRST.
# This layer is cached until pyproject.toml or README.md changes.
COPY pyproject.toml README.md ./

# Minimal src/ stub so setuptools can resolve the package for dep install.
RUN mkdir -p src/models && touch src/__init__.py src/models/__init__.py

RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir --upgrade pip \
    && /opt/venv/bin/pip install --no-cache-dir . 2>/dev/null || true

# Now copy the real source and do a final install.
COPY src/ src/
RUN /opt/venv/bin/pip install --no-cache-dir .

# ---------------------------------------------------------------------------
# Stage 2: Runtime — slim image, non-root user
# ---------------------------------------------------------------------------
FROM python:3.11-slim AS runtime

RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home impactos

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app

# Application code
COPY src/ src/
COPY alembic/ alembic/
COPY alembic.ini .
COPY scripts/ scripts/

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH="." \
    PYTHONUNBUFFERED=1

USER impactos

EXPOSE 8000

CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
