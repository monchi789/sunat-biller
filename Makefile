# Atajos de desarrollo. `make help` lista todo.
.DEFAULT_GOAL := help
COMPOSE ?= podman-compose
PY := .venv/bin/python

.PHONY: help
help:  ## Muestra esta ayuda
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

# ── entorno ─────────────────────────────────────────────────────────────────
.PHONY: install
install:  ## Instala dependencias con Poetry
	poetry install

.PHONY: env
env:  ## Crea .env desde la plantilla si no existe
	@test -f .env || (cp .env.example .env && echo "creado .env — revisa ENCRYPTION_KEY")

.PHONY: secret
secret:  ## Genera una clave Fernet para ENCRYPTION_KEY
	@$(PY) -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# ── contenedores ────────────────────────────────────────────────────────────
.PHONY: up
up: env  ## Levanta todo el stack
	$(COMPOSE) up -d --build

.PHONY: down
down:  ## Detiene el stack
	$(COMPOSE) down

.PHONY: clean
clean:  ## Detiene el stack y BORRA los volúmenes (datos incluidos)
	$(COMPOSE) down -v

.PHONY: logs
logs:  ## Sigue los logs de la API
	$(COMPOSE) logs -f api

.PHONY: shell
shell:  ## Abre una shell en el contenedor de la API
	$(COMPOSE) exec api bash

# ── base de datos ───────────────────────────────────────────────────────────
.PHONY: migrate
migrate:  ## Aplica las migraciones pendientes
	$(PY) -m alembic upgrade head

.PHONY: revision
revision:  ## Genera una migración (uso: make revision m="mensaje")
	$(PY) -m alembic revision --autogenerate -m "$(m)"

.PHONY: downgrade
downgrade:  ## Revierte la última migración
	$(PY) -m alembic downgrade -1

# ── calidad ─────────────────────────────────────────────────────────────────
.PHONY: test
test:  ## Corre la suite (excluye las pruebas contra SUNAT BETA)
	$(PY) -m pytest -m "not beta"

.PHONY: test-cov
test-cov:  ## Corre la suite con reporte de cobertura
	$(PY) -m pytest -m "not beta" --cov=app --cov-report=term-missing

.PHONY: test-beta
test-beta:  ## Corre las pruebas end-to-end contra el ambiente BETA real de SUNAT
	$(PY) -m pytest -m beta -v

.PHONY: lint
lint:  ## Revisa estilo con Ruff
	$(PY) -m ruff check app tests

.PHONY: fmt
fmt:  ## Corrige estilo automáticamente
	$(PY) -m ruff check app tests --fix
	$(PY) -m ruff format app tests

.PHONY: typecheck
typecheck:  ## Revisa tipos con Pyright
	npx --yes pyright

.PHONY: check
check: lint test  ## Lint + tests, lo mínimo antes de commitear
