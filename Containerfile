# ── build ───────────────────────────────────────────────────────────────────
FROM python:3.13-slim AS builder

ENV POETRY_VERSION=2.4.1 \
    POETRY_VIRTUALENVS_CREATE=false \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

RUN pip install "poetry==${POETRY_VERSION}" poetry-plugin-export

WORKDIR /build
COPY pyproject.toml poetry.lock ./
# Se exporta a requirements para que la imagen final no cargue con Poetry.
RUN poetry export --without dev --without-hashes -o requirements.txt \
    && pip wheel --wheel-dir /wheels -r requirements.txt

# ── runtime ─────────────────────────────────────────────────────────────────
FROM python:3.13-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 libxml2 libxslt1.1 curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /wheels /wheels
COPY --from=builder /build/requirements.txt .
RUN pip install --no-index --find-links=/wheels -r requirements.txt && rm -rf /wheels requirements.txt

# Usuario sin privilegios: el contenedor maneja certificados digitales.
RUN useradd --create-home --uid 10001 biller
WORKDIR /app

COPY --chown=biller:biller alembic.ini ./
COPY --chown=biller:biller alembic ./alembic
COPY --chown=biller:biller app ./app

# Volúmenes de datos. `data/certificates` queda fuera del árbol servible.
RUN mkdir -p /app/data/storage /app/data/certificates && chown -R biller:biller /app/data

USER biller
EXPOSE 7890

# El healthcheck se declara en podman-compose.yml, no aquí: Podman ignora la
# instrucción HEALTHCHECK cuando construye en formato OCI (su default).

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7890"]
