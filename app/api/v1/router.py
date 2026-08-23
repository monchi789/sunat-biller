"""Agrega todos los routers de la versión 1."""

from fastapi import APIRouter

from app.api.v1 import api_keys, certificates, companies, documents, invoices, series

api_router = APIRouter()

# El orden define cómo aparecen las secciones en /docs: primero la
# configuración de la empresa, luego la emisión y la consulta.
api_router.include_router(companies.router)
api_router.include_router(api_keys.router)
api_router.include_router(certificates.router)
api_router.include_router(series.router)
api_router.include_router(invoices.router)
api_router.include_router(documents.router)

__all__ = ["api_router"]
