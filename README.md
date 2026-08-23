# sunat-biller

Facturador electrónico de SUNAT (Perú) como **microservicio**. Otras aplicaciones
—ERP, punto de venta, e-commerce— le piden emitir comprobantes por REST; él genera
el XML UBL 2.1, lo firma con el certificado digital de la empresa, lo envía a
SUNAT y devuelve el resultado.

## Estado

Emite **facturas electrónicas (tipo 01)** de punta a punta, verificado contra el
ambiente BETA real de SUNAT. Boletas, notas de crédito/débito, resúmenes diarios
y comunicaciones de baja están planificados en [`PLAN.md`](PLAN.md).

## Arranque rápido

```bash
make env           # crea .env desde la plantilla
make secret        # → ENCRYPTION_KEY
make admin-token   # → ADMIN_TOKEN
make up            # levanta api + postgres + redis
make migrate
curl -s localhost:7890/health
```

Documentación interactiva en <http://localhost:7890/docs> (oculta en producción).

**Para emitir tu primera factura de prueba con tu propio RUC, sigue
[`docs/PRUEBAS.md`](docs/PRUEBAS.md)** — es un recorrido con `curl`, paso a paso,
hasta recibir el CDR de SUNAT.

## Cómo funciona

```
POST /invoices
  → calcula IGV y totales          app/domain/tax_engine.py
  → reserva correlativo atómico    app/services/series_service.py
  → genera XML UBL 2.1             app/xml/ubl_invoice.py
  → firma XMLDSig                  app/xml/xml_signer.py
  → envía a SUNAT (SOAP)           app/sunat/client.py
  → interpreta el CDR              app/xml/cdr_parser.py
```

El cliente solo envía datos del negocio —cantidad, valor unitario, afectación—;
**los importes tributarios los calcula el servicio**, porque confiar en los del
cliente es justo lo que SUNAT no permite.

## Autenticación

| Cabecera | Para qué |
|---|---|
| `X-API-Key` | Identifica a una empresa. Cada una solo ve sus propios recursos. |
| `X-Admin-Token` | Aprovisionamiento: crear empresas y emitir sus API keys. |
| `X-Idempotency-Key` | Opcional al emitir. Evita duplicados si el cliente reintenta. |

Existen dos porque toda API key pertenece a una empresa, así que la primera
empresa no puede crearse con una.

## Ambientes

Son **dos ejes independientes**, y conviene no confundirlos:

- `APP_ENV` — entorno de despliegue (`development` / `production`). En
  producción no se publican `/docs`, `/redoc` ni el esquema OpenAPI, y el
  servicio no arranca con secretos por defecto.
- `SUNAT_ENVIRONMENT` — a qué servicio de SUNAT se envía (`BETA` / `PRODUCTION`).

Durante la homologación se opera con `APP_ENV=production` apuntando a `BETA`.

## Desarrollo

```bash
make install
make test        # suite completa, sin las pruebas contra SUNAT real
make lint
make typecheck
make test-beta   # pruebas end-to-end contra SUNAT BETA (opt-in)
```

`make help` lista todo.

## Estructura

```
app/
├── api/v1/      routers HTTP
├── services/    lógica de negocio
├── domain/      cálculo fiscal puro (sin BD ni HTTP)
├── xml/         generación y firma UBL 2.1
├── sunat/       cliente SOAP del billService
├── catalogs/    catálogos oficiales de SUNAT
├── models/      persistencia (SQLAlchemy)
└── schemas/     contratos de entrada y salida (Pydantic)
```

## Documentación

| | |
|---|---|
| [`docs/PRUEBAS.md`](docs/PRUEBAS.md) | Emitir tu primera factura con `curl`, paso a paso. |
| [`docs/GUIA_PROYECTO.md`](docs/GUIA_PROYECTO.md) | Requerimientos, reglas de negocio y estructura del XML. |
| [`PLAN.md`](PLAN.md) | Plan de implementación y progreso. |

## Aviso

Los comprobantes enviados al ambiente **BETA no tienen validez tributaria**. Para
emitir en producción hacen falta un certificado digital de una entidad acreditada
registrado en SUNAT, estar dado de alta como emisor electrónico y credenciales SOL
reales.
