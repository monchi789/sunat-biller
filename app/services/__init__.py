"""Lógica de negocio.

Convenciones (docs/GUIA_PROYECTO.md §10):

* Todos los servicios reciben ``db: Session`` como primer argumento.
* **Ningún servicio hace commit**: la transacción la controla quien llama.
  Única excepción documentada: ``series_service.next_number``, que necesita su
  propia transacción para que el correlativo sea atómico.
* Los servicios lanzan excepciones de dominio (``app.core.errors``), nunca
  ``HTTPException``.
"""
