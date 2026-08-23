"""Logging estructurado en JSON con contexto de request.

Regla dura: **nunca** se registran contraseñas SOL, contraseñas de certificados
ni el contenido de un PFX. Los servicios que manejan esos datos loguean solo
identificadores.
"""

from __future__ import annotations

import json
import logging
import sys
from collections.abc import MutableMapping
from contextvars import ContextVar
from typing import Any

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
company_id_var: ContextVar[str | None] = ContextVar("company_id", default=None)
document_id_var: ContextVar[str | None] = ContextVar("document_id", default=None)

_RESERVED = frozenset(logging.LogRecord("", 0, "", 0, "", None, None).__dict__) | {
    "message",
    "asctime",
    "taskName",
}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        for key, var in (
            ("request_id", request_id_var),
            ("company_id", company_id_var),
            ("document_id", document_id_var),
        ):
            value = var.get()
            if value:
                payload[key] = value

        # `extra={...}` del llamador. `SafeExtraAdapter` prefija las claves que
        # chocan con `LogRecord`; aquí se devuelve el nombre original.
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                payload[key.removeprefix("ctx_")] = value

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(*, debug: bool = False) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.DEBUG if debug else logging.INFO)

    # uvicorn trae sus propios handlers; los silenciamos para no duplicar líneas.
    for name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = True


class SafeExtraAdapter(logging.LoggerAdapter):
    """Evita el choque entre `extra=` y los atributos internos de `LogRecord`.

    `logging.makeRecord` lanza ``KeyError: Attempt to overwrite 'filename'`` si
    `extra` trae una clave reservada —`filename`, `module`, `name`, `process`…—.
    Y lo hace **solo cuando el nivel está habilitado**, así que un `logger.info`
    con una clave reservada funciona en los tests (nivel WARNING) y revienta en
    producción. Renombrar aquí mata esa clase de fallo de una vez.
    """

    def process(
        self, msg: Any, kwargs: MutableMapping[str, Any]
    ) -> tuple[Any, MutableMapping[str, Any]]:
        extra = kwargs.get("extra")
        if extra:
            kwargs["extra"] = {
                (f"ctx_{key}" if key in _RESERVED else key): value
                for key, value in extra.items()
            }
        return msg, kwargs


def get_logger(name: str) -> SafeExtraAdapter:
    return SafeExtraAdapter(logging.getLogger(name), {})
