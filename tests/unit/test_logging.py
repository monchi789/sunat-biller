"""Logging estructurado.

El caso que motiva estos tests: `logger.info(..., extra={"filename": ...})`
lanzaba `KeyError` porque `filename` es un atributo interno de `LogRecord`. Y lo
hacía **solo con el nivel INFO habilitado**, así que pasaba los tests (nivel
WARNING por defecto) y reventaba al desplegar.
"""

from __future__ import annotations

import io
import json
import logging
from collections.abc import Callable, Iterator

import pytest

from app.core.logging import (
    _RESERVED,
    JsonFormatter,
    company_id_var,
    get_logger,
    request_id_var,
)

RESERVED_SAMPLE = ["filename", "module", "name", "process", "args", "levelname", "lineno"]


@pytest.fixture
def emitted(monkeypatch: pytest.MonkeyPatch) -> Iterator[Callable[[], dict]]:
    """Captura la última línea emitida por el logger, ya parseada.

    Se instala el handler en el logger raíz con nivel DEBUG y se fuerza la
    propagación: el fallo original solo aparece con el nivel habilitado, así que
    un test con el nivel por defecto no lo vería.
    """
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    monkeypatch.setattr(root, "handlers", [handler])

    # `setLevel` en vez de asignar `.level`: cada logger cachea el resultado de
    # `isEnabledFor` y solo `setLevel` invalida ese caché. Asignando el atributo
    # a mano, un logger que ya resolvió "INFO deshabilitado" en un test anterior
    # seguiría descartando los mensajes.
    original_level = root.level
    root.setLevel(logging.DEBUG)

    def last() -> dict:
        lines = [line for line in stream.getvalue().splitlines() if line.strip()]
        assert lines, "el logger no emitió nada"
        return json.loads(lines[-1])

    yield last
    root.setLevel(original_level)


class TestClavesReservadas:
    @pytest.mark.parametrize("key", RESERVED_SAMPLE)
    def test_no_revienta_con_una_clave_reservada(self, key: str, emitted: Callable[[], dict]) -> None:
        get_logger("test").info("mensaje", extra={key: "valor"})
        payload = emitted()
        assert payload[key] == "valor", "el nombre original debe conservarse en la salida"

    def test_todas_las_reservadas_a_la_vez(self, emitted: Callable[[], dict]) -> None:
        get_logger("test").warning("mensaje", extra=dict.fromkeys(RESERVED_SAMPLE, "v"))
        payload = emitted()
        for key in RESERVED_SAMPLE:
            assert payload[key] == "v"

    def test_el_caso_que_lo_destapo(self, emitted: Callable[[], dict]) -> None:
        """`filename` con el nombre de archivo SUNAT, en nivel INFO."""
        get_logger("app.sunat.client").info(
            "sendBill respondido",
            extra={"filename": "20000000001-01-F001-00000001.zip", "sunat_code": "0"},
        )
        payload = emitted()
        assert payload["filename"] == "20000000001-01-F001-00000001.zip"
        assert payload["sunat_code"] == "0"


class TestFormato:
    def test_es_json_valido(self, emitted: Callable[[], dict]) -> None:
        get_logger("test").info("hola")
        payload = emitted()
        assert payload["message"] == "hola"
        assert payload["level"] == "INFO"
        assert payload["logger"] == "test"

    def test_incluye_el_contexto_del_request(self, emitted: Callable[[], dict]) -> None:
        token_request = request_id_var.set("req-1")
        token_company = company_id_var.set("comp-1")
        try:
            get_logger("test").info("con contexto")
            payload = emitted()
            assert payload["request_id"] == "req-1"
            assert payload["company_id"] == "comp-1"
        finally:
            request_id_var.reset(token_request)
            company_id_var.reset(token_company)

    def test_registra_la_excepcion(self, emitted: Callable[[], dict]) -> None:
        try:
            raise ValueError("algo salió mal")
        except ValueError:
            get_logger("test").exception("falló")
        payload = emitted()
        assert "ValueError: algo salió mal" in payload["exception"]


def test_la_lista_de_reservadas_cubre_las_de_python() -> None:
    """Si Python añade atributos a `LogRecord`, esto lo detecta."""
    actual = set(logging.LogRecord("", 0, "", 0, "", None, None).__dict__)
    assert actual <= _RESERVED
