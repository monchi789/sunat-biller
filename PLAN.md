# Plan Maestro — Facturador Electrónico SUNAT como Microservicio

## Contexto

`sunat-biller` es un facturador electrónico multi-empresa para Perú que debe funcionar como **microservicio conectable**: otras aplicaciones (ERP, POS, e-commerce) le piden emitir comprobantes vía REST y reciben el resultado por webhook.

**Estado real hoy** (repo sin commits, rama `main`):

| Área | Estado |
|---|---|
| `app/models/` (14 tablas SQLAlchemy 2.0) | ✅ completo |
| `app/schemas/` (20 archivos Pydantic v2 + enums SUNAT) | ✅ completo |
| `app/core/config.py`, `database.py` | ⚠️ mínimos (4 settings, sesión síncrona psycopg2) |
| `app/main.py` | ⚠️ Hello World, no monta routers |
| `app/api/v1/`, `app/services/`, `app/xml/`, `app/catalogs/`, `tests/` | ❌ **vacíos** |
| Alembic | ❌ declarado pero sin inicializar |
| `podman-compose.yml`, `.env` | ❌ 0 bytes |
| `lxml`, `signxml`, `cryptography`, `zeep`, `redis`, `pytest`, `ruff` | ❌ no instalados |

Es decir: **el modelo de datos y los contratos están 100 % diseñados; la implementación está al 0 %**. `docs/GUIA_PROYECTO.md` es la fuente de verdad funcional y este plan la ejecuta.

**Resultado esperado:** un microservicio desplegable con `podman-compose up` que emite comprobantes válidos ante SUNAT, notifica a sistemas externos por webhook firmado, se reintenta solo cuando SUNAT cae, y tiene la batería de tests que permite tocarlo sin miedo.

### Decisiones del usuario ya tomadas

1. **Alcance:** MVP partido en **Etapa 1 funcional** y **Etapa 2 funcional**. Lo fundamental primero, sin lo que genere fricción.
2. **Procesamiento:** híbrido — `sendBill` síncrono dentro del request; si SUNAT falla o da timeout, se encola reintento con backoff y se avisa por webhook.
3. **Integración:** REST + API Key + **webhooks salientes firmados** hacia las apps que consumen el facturador.
4. **Despliegue:** Podman/Docker Compose + volumen local para XML/CDR/PDF.

### Primer entregable

Copiar este plan aprobado a **`/home/monchi789/Projects/sunat-biller/PLAN.md`** (documento vivo, se marca el progreso ahí) y añadir `CLAUDE.md` con las convenciones del repo.


> **Documento vivo.** Marca cada casilla al cerrar el paso. Fuente funcional: `docs/GUIA_PROYECTO.md`.

## Progreso

### Etapa 1 — Factura electrónica end-to-end
- [x] 1.1 Bootstrap del repositorio
- [~] 1.2 Núcleo de infraestructura (`app/core/`) — config, errors, logging listos; falta dependencies y main
- [x] 1.3 Migraciones Alembic
- [x] 1.4 Catálogos SUNAT (`app/catalogs/`)
- [x] 1.5 Dominio (`app/domain/`)
- [~] 1.6 Servicios base — crypto y storage listos; falta audit
- [~] 1.7 Configuración multi-empresa — series listo; faltan companies, api-keys, certificates
- [~] 1.8 Generación y firma del XML — namespaces, signer, zip, cdr_parser, ubl_invoice listos
- [x] 1.9 Cliente SUNAT
- [ ] 1.10 Emisión de factura
- [ ] 1.11 Webhooks salientes
- [ ] 1.12 Worker
- [~] 1.13 Tests — 236 verdes (dominio, catálogos, firma, UBL, SOAP, migraciones, concurrencia)
- [ ] 1.14 Documentación

### Etapa 2 — Núcleo completo
- [ ] 2.1 Boleta (03)
- [ ] 2.2 Resumen Diario (RC)
- [ ] 2.3 Comunicación de Baja (RA)
- [ ] 2.4 Notas de crédito (07) y débito (08)
- [ ] 2.5 Consulta, descarga y PDF
- [ ] 2.6 Robustez y observabilidad
- [ ] 2.7 Tests de Etapa 2

---

## Arquitectura objetivo

```
                    ┌─────────────────────────────────────────┐
   App cliente ────▶│  API (FastAPI)  :7890                   │
   (ERP/POS)        │  X-API-Key  ·  X-Idempotency-Key        │
        ▲           └───┬──────────────┬──────────────┬───────┘
        │               │              │              │
        │        ┌──────▼─────┐ ┌──────▼──────┐ ┌────▼────────┐
        │        │ PostgreSQL │ │ Storage FS  │ │   Redis     │
        │        │ (verdad)   │ │ /data/...   │ │ (cola arq)  │
        │        └──────┬─────┘ └─────────────┘ └────┬────────┘
        │               │                            │
        │        ┌──────▼────────────────────────────▼───────┐
        └────────┤  Worker (arq)                             │──▶ SUNAT
        webhook  │  · reintento sendBill  · poll de tickets  │    billService
        HMAC     │  · entrega de webhooks · reconciliación   │    (SOAP)
                 └───────────────────────────────────────────┘
```

**Capas** (patrón layered ya insinuado por los directorios vacíos):
`api/v1` (routers, HTTP) → `services` (lógica de negocio) → `models` (persistencia), con `schemas` como DTOs de frontera, `xml` y `catalogs` como soporte del dominio SUNAT, y `core` como infraestructura transversal.

### Desviación deliberada de RNF-03.2 (a documentar en PLAN.md)

La guía dice "toda la emisión en **una** transacción de BD". Eso implica mantener una transacción abierta durante los ~2 s de la llamada SOAP a SUNAT — bloquea conexiones y deja la fila de serie tomada. Se parte en tres:

- **TX1** — reservar correlativo (`UPDATE ... RETURNING`, atómico) + snapshots + documento + ítems + cuotas + reserva de idempotencia → `PENDING`. Commit.
- **Fuera de TX** — generar XML, firmar, empaquetar ZIP, guardar en disco.
- **TX2** — `DocumentFile` + `xml_hash` + `filename` → `SIGNED`. Commit.
- **Fuera de TX** — llamar a SUNAT (`sendBill`).
- **TX3** — `SunatSubmission` + estado final + CDR guardado + `audit_log` + **fila en el outbox de webhooks**. Commit.

Si TX1 falla, rollback total y no se consume correlativo utilizable. Si falla después de TX1, el documento queda en un estado recuperable (`PENDING`/`SIGNED`/`SENT`) que el worker retoma. Los correlativos en SUNAT no exigen continuidad estricta, así que un hueco por fallo es aceptable y trazable.

---

## Decisiones técnicas

### Firma digital: `signxml` (no `xmlsec`) — **verificado empíricamente**

SUNAT exige firma **enveloped** dentro de `ext:UBLExtensions/ext:UBLExtension/ext:ExtensionContent`, con `ds:Reference URI=""`, una sola transform `enveloped-signature`, y `KeyInfo` con `X509Certificate`.

`python-xmlsec` exigiría `libxmlsec1-dev` + `libxml2-dev` en el build y tiene acoplamiento ABI con `lxml` (el crash `null argument to internal routine` al mezclar wheel de lxml con xmlsec compilado). **`signxml`** se instala sin compilar y trae soporte documentado para justo lo que hace falta.

**Mecanismo `Id="placeholder"`** — el builder emite `<ds:Signature Id="placeholder"/>` **dentro** de `ext:ExtensionContent`; signxml lo rellena *in situ* y lo excluye del cálculo del digest. No hay que mover el nodo después de firmar, así que no hay riesgo de invalidar la firma.

**Parámetros exactos (probados: firman, verifican, y rechazan XML manipulado):**

| Parámetro | Valor |
|---|---|
| `method` | `methods.enveloped` |
| `signature_algorithm` | `SignatureMethod.RSA_SHA256` |
| `digest_algorithm` | `DigestAlgorithm.SHA256` |
| `c14n_algorithm` | **`CanonicalizationMethod.CANONICAL_XML_1_0`** (inclusiva, `.../REC-xml-c14n-20010315`) |
| `always_add_key_value` | `False` (sin `RSAKeyValue`) |
| `exclude_c14n_transform_element` | `True` (una sola Transform) |
| `reference_uri` | **no pasar** — signxml lo convierte en `#` y falla; el default ya produce `URI=""` |

> **Trampa encontrada y descartada:** la combinación `exc-c14n` + `exclude_c14n_transform_element=True` produce un XML que *parece* correcto pero **no verifica** (`InvalidDigest`): al omitir la transform, el verificador asume c14n inclusiva. Con `CANONICAL_XML_1_0` la omisión es correcta porque inclusiva es el default de XMLDSig — y es además lo que emiten las implementaciones aceptadas por SUNAT.

`ds:Signature/@Id` se fija **después** de firmar (la transform `enveloped-signature` elimina todo el subárbol, así que su `Id` nunca entra en el digest). Debe coincidir con `cac:Signature/cbc:ID`.

**XMLDSig plano, no XAdES-BES.** Los XML reales aceptados por SUNAT no llevan `xades:QualifyingProperties`; añadirlo amplía la superficie de rechazo por XSD sin ganancia.

**PFX peruanos con cifrado legacy:** muchos `.pfx` emitidos en Perú usan RC2-40-CBC / 3DES con MAC SHA-1, que en OpenSSL 3 están en el *legacy provider*: `pkcs12.load_key_and_certificates()` falla con `Invalid password or PKCS12 data` aunque la contraseña sea correcta. `certificate_service` reintenta por la vía legacy y **re-serializa el PFX normalizado con AES-256** en el upload (una sola vez, no en cada emisión).

### Cliente SOAP: envelope artesanal con `httpx` (no `zeep`)

- El WSDL de SUNAT es lento e intermitente; `zeep` lo descarga y parsea en runtime salvo que se cachee a mano, lo que convierte un problema de red de SUNAT en un fallo de arranque.
- Son **4 operaciones** con envelopes triviales y WS-Security `UsernameToken` en texto plano (6 líneas de XML). `zeep` aporta una dependencia pesada para eso.
- `httpx` ya está en el lock (viene con `fastapi[standard]`) y da control directo sobre timeouts, reintentos y trazas.

Implementación: plantillas de envelope por operación, POST con `httpx.Client`, respuesta parseada con `lxml` y traducida a `SunatError` con código clasificado por `app/catalogs/cdr_codes.py`.

**Tres detalles no negociables** (los tres modos de fallo clásicos del envelope artesanal):

1. **Escapar `sol_user` y `sol_password` con `xml.sax.saxutils.escape`.** Las claves SOL contienen `&` y `<` con frecuencia; sin escapar se genera un envelope malformado y SUNAT devuelve un fault genérico ilegible. Es el bug nº1.
2. **Parseo namespace-agnóstico** con `//*[local-name()='applicationResponse']`, `[local-name()='ticket']`, `[local-name()='statusCode']`: los prefijos que devuelve SUNAT varían entre ambientes.
3. **Guarda anti zip-bomb** al abrir el ZIP del CDR: máximo 2 entradas y 10 MB descomprimidos. Y **nunca `verify=False`** en TLS.

Timeouts separados y explícitos (`connect=10s`, `read=25s`) para poder decidir cuándo degradar a `SENT` respetando el presupuesto de <3 s. Los tests inyectan `httpx.MockTransport` — no hace falta `respx` ni disponibilidad de SUNAT.

### Worker: `dramatiq` + Redis (no `arq`, no Celery)

`arq` exige que **toda** tarea sea corrutina `async`. Nuestra capa de datos es síncrona (psycopg2 + `Session`), así que cada job tendría que envolver sus accesos en `asyncio.to_thread` o mantener un segundo engine async — coste real sin beneficio, porque el cuello de botella es SUNAT, no el throughput de la cola. Celery aporta demasiada superficie (beat, result backend, pools) para tres jobs.

**`dramatiq`**: los actores son funciones **síncronas** decoradas, broker Redis, `max_retries` + backoff exponencial con jitter integrados, dead-letter queue, y `StubBroker` para tests sin Redis.

**Redis es el disparador, PostgreSQL la fuente de verdad.** El modelo híbrido tiene un agujero: si la request hace commit y el proceso muere antes del `.send()`, el reintento se pierde. Por eso la *intención* se escribe como fila en la misma transacción (patrón outbox) y el encolado en Redis es solo una pista de latencia; el job `sweep_outbox` recupera lo que Redis pierda. Consecuencia útil: **el sistema funciona aunque Redis no esté**, solo con más latencia.

`sunat_submissions` ya es casi la tabla outbox correcta; le faltan `attempts`, `next_attempt_at` (indexada) y `last_error`. Se añaden ahora, antes de la primera migración, con coste cero.

**Reglas de idempotencia de los jobs, no negociables:**
- `retry_send_bill` recarga el documento y **aborta si el estado ya es terminal**.
- **Nunca regenera ni refirma el XML**: reutiliza el firmado que ya está en `document_files`. Refirmar cambiaría el `DigestValue` y por tanto el QR ya entregado.
- El polling de ticket se auto-reprograma mientras `statusCode == "98"`, sin necesidad de cron.

### Precisión numérica

`Decimal` en todo el pipeline, **nunca `float`**. `float` rompe la validación `total == subtotal - discount + igv + isc + icbper + otros` (±0.01) y produce XML que SUNAT rechaza con error 2xxx por descuadre de céntimos.

- Módulo nuevo `app/domain/money.py`: `Q2 = Decimal("0.01")`, `Q6 = Decimal("0.000001")`, helper `round2()` / `round6()` con `ROUND_HALF_UP` (el redondeo comercial que usa SUNAT, no el bancario que trae Python por defecto).
- Montos → 2 decimales. Cantidades, `unit_value`, `unit_price` → 6 decimales (coherente con `Numeric(18,6)` en `app/models/document_item.py`).
- El motor de cálculo recibe `DocumentItemCreate` y devuelve una dataclass `DocumentTotals`; se recalcula **siempre** en backend y solo se compara contra lo que envió el cliente para rechazar con 422 si difiere más de ±0.01 (RF-05.2/RF-05.3).
- La tasa de IGV va en config (`IGV_RATE=0.18`), no hardcodeada — cambia por norma.

**Orden de redondeo — esto es lo que decide si SUNAT acepta:**

1. Por línea, a precisión plena: `bruto = quantity * unit_value` (ninguno redondeado).
2. `valor_neto = round2(bruto - descuento)` → `cbc:LineExtensionAmount`.
3. `igv_linea = round2(valor_neto * IGV_RATE)`.
4. **Los totales de cabecera son la suma de los valores de línea YA redondeados.** No se calculan desde líneas sin redondear: SUNAT recomputa sumando los montos que tú declaraste por línea, así que "redondear al final" deriva céntimos en facturas de 10+ ítems y produce observaciones.
5. `TaxInclusiveAmount = round2(TaxExclusiveAmount + impuestos)`; `PayableAmount = TaxInclusiveAmount - anticipos`.

**Operaciones gratuitas** (afectación `1x`, `21`, `3x`): `LineExtensionAmount = 0.00`, el valor va en `cbc:PriceAmount` con `PriceTypeCode = "02"`. Se excluyen de la suma de `LineExtensionAmount` de cabecera, pero su IGV **sí** se calcula y declara. Fuente clásica del descuadre de dos céntimos.

**Serialización:** siempre `fmt2()`/`fmt6()`, nunca `str(Decimal)` — `str()` puede emitir notación científica (`1E+2`). Y como cualquier cambio en los dígitos serializados cambia el `DigestValue`, formatear desde `float` haría la firma no reproducible y los golden tests intermitentes.

**Prohibiciones verificables en CI:** `sqlalchemy.Float` en cualquier columna, y `Decimal(<float>)` en cualquier parte (`Decimal(0.1)` da `0.1000000000000000055511151231257827`).

### Ergonomía del contrato de entrada (ajuste a `app/schemas/document_item.py`)

Hoy `DocumentItemCreate` exige que el cliente mande `subtotal`, `taxable_amount`, `igv_amount`, `isc_amount`, `icbper_amount`, `other_tax_amount` y `total` ya calculados. Para un microservicio consumido por un POS o un e-commerce eso es fricción pura y contradice RF-05.2 ("no confiar en el cliente"), que obliga a recalcularlo todo igual.

**Cambio:** esos siete campos pasan a `| None = None`. El integrador manda solo lo esencial — `quantity`, `unit_code`, `unit_value` (o `unit_price`), `discount`, `tax_affectation`, `price_type`, `description` — y el backend calcula el resto. Si el cliente **sí** los envía, se validan contra lo calculado con tolerancia ±0.01 y se rechaza con 422 si difieren (conserva la validación cruzada existente para quien quiera doble verificación).

Otros dos huecos del contrato actual, a corregir en la misma pasada:

- **`DocumentCreateBase` no tiene campo `series`** (`app/schemas/document.py`). Una empresa puede tener `F001` y `F002`; el cliente necesita poder elegir. Se añade `series: str | None = Field(default=None, pattern=r"^[A-Z]\d{3}$")`; si viene `None` se usa la única serie activa de ese tipo de documento y se responde 409 si hay más de una.
- **`xml_hash`** — la columna es `VARCHAR(64)` y el schema valida base64 (`^[A-Za-z0-9+/=]{20,}$`). **No se cambia ninguno de los dos:** se define que `xml_hash` es el **`ds:DigestValue` de la firma en base64** — 44 caracteres, cabe en `VARCHAR(64)`, satisface el patrón, y es exactamente el valor que exige el QR de la representación impresa. Confirmado en la prueba de firma: el `DigestValue` sale de 44 chars. `document_files.sha256` sigue siendo el hash hexadecimal del archivo, que es otra cosa. Se documenta en el docstring del modelo.

### Seguridad de secretos

La receta de la guía (`SECRET_KEY[:32].ljust(32)`) **no es un KDF** y es frágil. Se sustituye por una setting dedicada `ENCRYPTION_KEY` (clave Fernet válida generada con `Fernet.generate_key()`), separada de `SECRET_KEY`, con derivación HKDF si se quiere multi-propósito. Sin esa variable la app **no arranca** en producción (validador en `Settings`).

---

## ETAPA 1 — Factura electrónica funcional end-to-end

**Objetivo verificable:** emitir una factura tipo 01 contra el ambiente **BETA de SUNAT** y recibir un CDR aceptado, con la notificación llegando por webhook al sistema cliente. Todo el andamiaje transversal queda listo para que la Etapa 2 sea "más de lo mismo".

### 1.1 Bootstrap del repositorio

| Archivo | Acción |
|---|---|
| `.gitignore` | añadir `__pycache__/`, `*.pyc`, `.pytest_cache/`, `.ruff_cache/`, `.mypy_cache/`, `*.pfx`, `*.p12`, `storage/`, `data/`, `.coverage`, `htmlcov/` |
| `pyproject.toml` | añadir deps de runtime y grupo `dev`; configurar `[tool.ruff]`, `[tool.pytest.ini_options]`, `[tool.coverage]` |
| `.env.example` | plantilla completa de variables (el `.env` real sigue ignorado) |
| `Containerfile` | imagen multi-stage (builder Poetry → runtime slim), usuario no-root |
| `podman-compose.yml` | servicios `api`, `worker`, `db` (postgres:17), `redis` (redis:7) + volúmenes `pgdata`, `storage` |
| `Makefile` | `up`, `down`, `logs`, `migrate`, `revision`, `test`, `lint`, `fmt`, `typecheck`, `shell` |
| `pyrightconfig.json` | añadir `tests` a `include` |
| — | **primer commit** (el repo no tiene ninguno) |

Dependencias de runtime a añadir: `lxml`, `signxml`, `cryptography`, `httpx`, `python-multipart`, `redis`, `arq`.
Dependencias de dev: `pytest`, `pytest-cov`, `pytest-asyncio`, `respx`, `ruff`, `freezegun`, `factory-boy` (o fixtures a mano).

### 1.2 Núcleo de infraestructura (`app/core/`)

- **`config.py`** — ampliar `Settings` con: `SUNAT_ENVIRONMENT`, `SUNAT_BETA_URL` (`https://e-beta.sunat.gob.pe/ol-ti-itcpfegem-beta/billService`), `SUNAT_PRODUCTION_URL` (`https://e-factura.sunat.gob.pe/ol-ti-itcpfegem/billService`), `SUNAT_TIMEOUT_SECONDS`, `STORAGE_ROOT`, `CERTIFICATE_ROOT`, `REDIS_URL`, `ENCRYPTION_KEY`, `IGV_RATE`, `ICBPER_RATE`, `RECEIPT_CUSTOMER_THRESHOLD` (S/ 700, configurable), `IDEMPOTENCY_TTL_HOURS=24`, `WEBHOOK_TIMEOUT_SECONDS`, `WEBHOOK_MAX_ATTEMPTS`, `MAX_CERTIFICATE_SIZE_MB=5`, `API_PORT`.
- **`dependencies.py`** (nuevo) — `get_current_company` según §12 de la guía, más `get_idempotency_key`, `get_request_context` (IP + user-agent para auditoría), `get_pagination`.
- **`errors.py`** (nuevo) — jerarquía de excepciones de dominio (`DomainError`, `NotFoundError`, `ForbiddenError`, `ConflictError`, `ValidationError`, `SunatError`, `SigningError`) + `exception_handlers` que las traducen al `ErrorResponse` ya definido en `app/schemas/common.py`. Los servicios lanzan excepciones de dominio, **no `HTTPException`** (convención §10 de la guía).
- **`logging.py`** (nuevo) — logging estructurado JSON con `request_id`, `company_id`, `document_id`; nunca loguear contraseñas SOL ni contenido de PFX.
- **`main.py`** — reescribir: `lifespan`, montaje de routers bajo `settings.API_V1_PREFIX`, CORS, middleware de `request_id`, exception handlers, `GET /health` sin auth, metadatos OpenAPI (título, versión, descripción, tags).
- **`database.py`** — se mantiene síncrono (psycopg2). **Consecuencia obligatoria:** los endpoints que tocan BD se escriben `def`, no `async def`, para que FastAPI los mande al threadpool y no bloqueen el event loop. Es un fallo fácil de cometer con el `async def` del ejemplo de `dependencies.py` en la guía.

### 1.3 Migraciones

`alembic init -t async? no → plantilla síncrona`; `alembic/env.py` importa `Base` desde `app.models` y toma la URL de `settings.DATABASE_URL`. Primera revisión autogenerada con las 14 tablas + las nuevas de webhooks. Verificar a mano que Alembic detecte el **índice parcial único** de `digital_certificates` (`WHERE active = true`) — autogenerate suele perderlo.

### 1.4 Catálogos (`app/catalogs/`)

Diccionarios puros `{código: descripción}` según §11: `cat01_document_types`, `cat03_unit_codes`, `cat06_identity_docs`, `cat07_tax_affectation`, `cat09_credit_note_reasons`, `cat10_debit_note_reasons`, `cat16_price_types`, `cat51_operation_types`.

Añadidos que la guía no contempla y hacen falta:
- **`tax_schemes.py`** — mapa afectación → `(TaxCategory ID, TaxScheme ID, Name, TaxTypeCode)`: `10..17 → ("S","1000","IGV","VAT")`, `20/21 → ("Z","9997","EXO","VAT")`, `30..36 → ("O","9998","INA","FRE")`, `40 → ("G","9995","EXP","FRE")`. Es la tabla que más rechazos 2xxx causa si se equivoca.
- **`cdr_codes.py`** — clasificación de códigos de respuesta SUNAT: `0` aceptado, `100–999` excepción (**reintentable**), `1000–1999` error del contribuyente, `2000–3999` **rechazo definitivo** (no reintentar), `4000+` observación (aceptado con observación). Esta tabla gobierna la política de reintentos del worker y es un hueco explícito de la documentación actual.

### 1.5 Dominio (`app/domain/`, nuevo)

- **`money.py`** — cuantización `Decimal`, `ROUND_HALF_UP`.
- **`number_to_words.py`** — `Decimal → "SON CIEN CON 00/100 SOLES"` para `cbc:Note`. Soporta PEN/USD/EUR. Componente que la guía menciona pero no ubica.
- **`tax_engine.py`** — `calculate_item(...)` y `calculate_totals(items) -> DocumentTotals`: reparte por afectación en `taxable_total` / `exempt_total` / `unaffected_total` / `export_total` / `free_total`, calcula IGV/ISC/ICBPER, aplica descuentos de línea, y devuelve también los `TaxSubtotal` agregados que el XML necesita. **Es el corazón del sistema y donde debe caer la mayor densidad de tests unitarios.**
- **`naming.py`** — nombres de archivo SUNAT: `{RUC}-{TIPO}-{SERIE}-{NUMERO:08d}`, `{RUC}-RC-{YYYYMMDD}-{NNN}`, `{RUC}-RA-{YYYYMMDD}-{NNN}`.

### 1.6 Servicios base (`app/services/`)

`crypto_service` (Fernet con `ENCRYPTION_KEY`), `file_storage_service` (layout `storage/{company_id}/{YYYY}/{MM}/{filename}.{ext}`, calcula SHA-256 y tamaño, escritura atómica vía archivo temporal + `rename`), `audit_service` (nunca propaga excepciones, sesión propia para no arrastrar el rollback del caller).

### 1.7 Configuración multi-empresa (routers CRUD)

`company_service` + `api_key_service` + `certificate_service` + `series_service`, cada uno con su router en `app/api/v1/`. Endpoints exactamente los de §8 de la guía. Puntos que exigen cuidado:

- `api_key_service.create_api_key` → `secrets.token_hex(32)`, se persiste solo SHA-256, se devuelve en claro **una sola vez**.
- `certificate_service.upload_certificate` → valida extensión/tamaño, carga el PFX con `cryptography.hazmat.primitives.serialization.pkcs12`, extrae `serial_number`/`valid_from`/`valid_until`, **rechaza certificados ya vencidos**, cifra la contraseña, desactiva el anterior en la misma transacción, guarda fuera del árbol de storage público.
- `series_service.get_next_number` → `UPDATE document_series SET current_number = current_number + 1 WHERE id = :id AND active RETURNING current_number` en su propia transacción (única excepción a la regla "los servicios no hacen commit").
- Aislamiento por `company_id` en **todas** las queries + filtro `deleted_at IS NULL` (los modelos usan `SoftDeleteMixin` pero no hay filtro global; se centraliza en helpers de query para no olvidarlo).

### 1.8 Generación y firma del XML

`app/xml/`:
- **`namespaces.py`** — todos los namespaces de §6.1 (incluido `sac`; verificar si el `pe-cac` que menciona RNF-05.1 aplica realmente al perfil UBL 2.1 vigente — en 2.1 no se usa, se documenta la conclusión).
- **`ubl_invoice.py`** — construye el `Invoice` (sirve para tipo 01 y 03) con `lxml.etree`, siguiendo el árbol de §6.2 al detalle: `UBLVersionID=2.1`, `CustomizationID=2.0`, `InvoiceTypeCode` con `@listID` del catálogo 51, `Note` en letras, emisor/receptor, `PaymentMeans`/`PaymentTerms` por cuotas, `TaxTotal` con un `TaxSubtotal` por esquema, `LegalMonetaryTotal`, `InvoiceLine` con `PricingReference`.
- **`xml_signer.py`** — firma XAdES/XMLDSig enveloped insertada en `ext:UBLExtensions/ext:UBLExtension/ext:ExtensionContent`, `ds:Reference URI=""`, transform `enveloped-signature`, canonicalización C14N, `KeyInfo` con `X509Certificate`, `Signature Id` coherente con `cac:Signature/cbc:ID`. Implementa el patrón "firmar → reubicar en `ExtensionContent`" descrito en Decisiones técnicas, con `signxml`.
- **`zip_helper.py`** — ZIP con el XML en la raíz, nombre exacto `{filename}.xml` dentro de `{filename}.zip`.
- **`cdr_parser.py`** — abre el ZIP de respuesta, localiza `R-{filename}.xml`, extrae `cbc:ResponseCode`, `cbc:Description` y las notas de observación; clasifica con `cat cdr_codes`.

### 1.9 Cliente SUNAT (`app/services/sunat_client_service.py`)

`send_bill(ruc, sol_user, sol_password, filename, zip_bytes) -> CdrResult`, más `get_status_cdr(...)`. WS-Security `UsernameToken` con `Username = {RUC}{sol_user}`. Timeout configurable, reintento inmediato acotado para errores de red, y traducción de SOAP Fault → `SunatError` con código clasificado. Envelope artesanal con `httpx`, según Decisiones técnicas.

Todas las llamadas quedan registradas como filas en `sunat_submissions` (el modelo ya soporta 1:N para historial de reintentos).

### 1.10 Emisión de factura

`document_service` (totales, snapshots, consultas, cambios de estado) + `invoice_service.emit_invoice` orquestando el flujo de tres transacciones descrito arriba + router `POST /invoices` y `GET /invoices/{id}`.

Idempotencia: `X-Idempotency-Key` se **reserva** en TX1 (insert con `UNIQUE(company_id, key)`); si ya existe y está completa se devuelve la respuesta guardada; si existe y está en curso se responde 409. TTL 24 h con limpieza periódica.

Semántica HTTP según §13: rechazo de SUNAT → **200 con `status=REJECTED`**; SUNAT caído → **200 con `status=SENT`** y job de reintento encolado. Solo los errores propios del servicio son 4xx/5xx.

### 1.11 Webhooks salientes

Modelos nuevos (`app/models/webhook.py`) + migración:

- **`WebhookEndpoint`** — `company_id`, `url`, `secret_encrypted`, `events` (array de tipos suscritos), `active`, `description`, timestamps.
- **`WebhookDelivery`** — `endpoint_id`, `event_type`, `event_id` (UUID, idempotencia del lado del receptor), `payload` (JSONB), `status` (`PENDING|DELIVERING|DELIVERED|FAILED`), `attempts`, `next_attempt_at`, `last_status_code`, `last_error`, `delivered_at`.

`WebhookDelivery` funciona como **outbox transaccional**: la fila se inserta en la misma transacción que el cambio de estado del documento, así que ningún evento se pierde aunque Redis se caiga. El worker las toma por `next_attempt_at`.

Eventos de Etapa 1: `document.accepted`, `document.accepted_with_observation`, `document.rejected`, `document.error`, `document.sent` (pendiente en SUNAT).

Firma HMAC-SHA256 sobre `{timestamp}.{body}`, cabeceras `X-Sunat-Biller-Signature: t=<unix>,v1=<hex>`, `X-Sunat-Biller-Event`, `X-Sunat-Biller-Delivery`. El receptor debe rechazar timestamps de más de 5 min (anti-replay). Reintentos con backoff exponencial (`1m, 5m, 30m, 2h, 6h, 24h`), máximo configurable. Router `/webhooks` para CRUD de endpoints + `POST /webhooks/{id}/test` que dispara un evento `ping`.

### 1.12 Worker (`app/worker/`)

Proceso `arq` separado en compose, compartiendo la imagen. Jobs de Etapa 1:
- `deliver_webhook(delivery_id)` — entrega con backoff.
- `retry_send_bill(document_id)` — reintenta documentos en `SENT` sin CDR, con backoff y tope; consulta `getStatusCdr` antes de reenviar para no duplicar.
- `sweep_pending` (cron, cada minuto) — barre `webhook_deliveries` y documentos atascados que Redis pudiera haber perdido. **PostgreSQL es la fuente de verdad; Redis es solo el disparador.**
- `purge_idempotency_keys` (cron diario).

### 1.13 Tests de Etapa 1

```
tests/
├── conftest.py              # engine de test, sesión con rollback por test, TestClient, factories
├── fixtures/
│   ├── certs/               # PFX autofirmado generado en tiempo de test (nunca uno real)
│   ├── xsd/                 # XSD oficiales UBL 2.1 + SUNAT para validación estructural
│   └── golden/              # XML de referencia por caso
├── unit/
│   ├── test_money.py
│   ├── test_tax_engine.py           # ← la batería más densa
│   ├── test_number_to_words.py
│   ├── test_naming.py
│   ├── test_catalogs.py
│   ├── test_crypto_service.py
│   └── test_cdr_parser.py
├── xml/
│   ├── test_ubl_invoice_golden.py   # comparación contra golden files
│   ├── test_ubl_invoice_xsd.py      # validación contra XSD oficial
│   └── test_xml_signer.py           # firma verificable + ubicación correcta en ExtensionContent
├── api/
│   ├── test_auth.py                 # API key inválida/expirada/revocada, aislamiento entre empresas
│   ├── test_companies.py
│   ├── test_certificates.py
│   ├── test_series.py               # incluye concurrencia del correlativo
│   ├── test_invoices.py             # SUNAT mockeado: aceptado / observado / rechazado / timeout
│   ├── test_idempotency.py
│   └── test_webhooks.py             # firma HMAC, reintentos, outbox
└── e2e/
    └── test_sunat_beta.py           # marcado @pytest.mark.beta, opt-in, contra BETA real
```

Estrategia: unitarios con `Decimal` exacto; XML contra **golden files + XSD oficiales**; API con `TestClient` y el WS SUNAT mockeado con `respx`; concurrencia del correlativo con hilos reales contra PostgreSQL; E2E contra BETA excluido de CI por defecto.

**Base de datos de test:** el propio PostgreSQL del compose sobre una BD separada `sunat_biller_test`, migrada con Alembic (no `create_all`, para que las migraciones se validen en cada corrida). Se descarta `testcontainers` para no exigir Docker-in-Docker en un entorno Podman. Cada test corre dentro de una transacción con rollback al final; los pocos que necesitan commits reales (concurrencia del correlativo) usan una fixture con limpieza explícita.

**Fixtures clave:** `company_factory`, `api_key_factory` (devuelve el key en claro), `certificate_factory` (genera un PFX autofirmado con `cryptography` en tiempo de test — **nunca** se versiona un certificado real), `series_factory`, `invoice_payload_factory`, y `sunat_mock` (respx con escenarios: aceptado `0`, observado `4xxx`, rechazado `2xxx`, excepción `1xxx`, timeout, SOAP Fault).

### 1.14 Documentación de Etapa 1

- **`README.md`** — qué es, arranque en 5 minutos, variables de entorno, comandos del Makefile.
- **`docs/DESPLIEGUE.md`** — compose paso a paso, volúmenes y backup, reverse proxy con TLS, checklist de producción (rotación de `ENCRYPTION_KEY`, backups de `storage/`, monitoreo).
- **`docs/INTEGRACION.md`** — guía para el equipo que consume el servicio: obtener API key, emitir una factura, manejo de idempotencia, recibir y **verificar** webhooks (con snippet de verificación HMAC), tabla de códigos de error.
- **`CLAUDE.md`** — convenciones del repo (capas, servicios sin commit, `def` no `async def` para endpoints con BD, `Decimal` siempre).
- OpenAPI enriquecido con ejemplos por endpoint.
- Actualizar `docs/GUIA_PROYECTO.md` con las desviaciones acordadas (transacciones, KDF, códigos CDR).

**Criterio de cierre de Etapa 1:** `podman-compose up` levanta todo; se crea empresa, se sube certificado, se crea serie `F001`, se emite una factura, SUNAT BETA devuelve CDR `0` aceptado, el XML firmado y el CDR quedan en disco, y el webhook `document.accepted` llega firmado al endpoint del cliente. Suite verde.

---

## ETAPA 2 — Núcleo completo de comprobantes

Todo lo que sigue reutiliza el andamiaje de la Etapa 1 sin inventar arquitectura nueva.

### 2.1 Boleta de venta (tipo 03)
`receipt_service.emit_receipt` — mismo flujo hasta firmar, **sin llamada a SUNAT**, termina en `SIGNED`. Reutiliza `ubl_invoice.py` cambiando `InvoiceTypeCode`, `schemeID` del receptor (DNI `1`) y el caso "público en general". Regla del umbral (`RECEIPT_CUSTOMER_THRESHOLD`, S/ 700): sobre el umbral el cliente pasa a ser obligatorio. Router `POST /receipts`.

### 2.2 Resumen Diario (RC) — flujo asíncrono con ticket
`ubl_summary.py` (`SummaryDocuments` con `sac:SummaryDocumentsLine`), `sunat_client_service.send_summary` → ticket, `get_status(ticket)` → CDR. `daily_summary_service` con generación del identificador `RC-YYYYMMDD-NNN` correlativo por empresa/fecha. Router `POST /daily-summaries`, `GET /daily-summaries/{id}`, `POST /daily-summaries/{id}/poll`.

**Mejora sobre la guía:** además del `/poll` manual, un job `poll_ticket(summary_id)` en el worker que consulta con backoff hasta resolver el ticket y emite webhook `daily_summary.accepted` / `.rejected`, marcando las boletas como `ACCEPTED`. El integrador no debería tener que hacer polling.

### 2.3 Comunicación de Baja (RA)
`ubl_voided.py` (`VoidedDocuments`), `voided_document_service`, mismo `sendSummary` + ticket + job de polling. Identificador `RA-YYYYMMDD-NNN`. Valida que los documentos estén en `ACCEPTED`/`ACCEPTED_WITH_OBSERVATION` y respeta el plazo SUNAT (máx. 7 días para facturas). Al confirmarse → `VOIDED` + webhook.

### 2.4 Notas de crédito (07) y débito (08)
`ubl_credit_note.py` / `ubl_debit_note.py` con `cac:DiscrepancyResponse` + `cac:BillingReference`. `credit_note_service` / `debit_note_service` vía `sendBill` (mismo flujo que la factura). Validación de referencia solo a `01`/`03` y `reason_code` del catálogo correcto (09 / 10). **Nota:** implementar `CreditNoteReferenceCreate` y `DebitNoteReferenceCreate` separados en vez de la unión de enums actual, como recomienda `docs/facturador_schemas_uml.md`.

### 2.5 Consulta, descarga y PDF
- Router `/documents` completo: listado con filtros (`document_type`, `status`, rango de `issue_date`, `series`) y paginación; detalle con ítems/cuotas/referencias/envíos; `GET /documents/{id}/xml|/cdr|/pdf`; `POST /documents/{id}/status` (refresco vía `getStatusCdr`).
- Router `/audit-logs`.
- **Representación impresa PDF** — `app/pdf/`: plantilla Jinja2 (ya disponible vía `fastapi[standard]`) + WeasyPrint, con **código QR obligatorio** (`RUC|TIPO|SERIE|NUMERO|IGV|TOTAL|FECHA|TIPO_DOC_RECEPTOR|NRO_DOC_RECEPTOR`) y hash de la firma. Generación perezosa y cacheada como `DocumentFile`.

### 2.6 Robustez y observabilidad
- Job de **reconciliación** diario: documentos en `SENT` sin CDR → `getStatusCdr` → cierre de estado (cubre el "futuro job" que RNF-03.1 dejaba pendiente).
- `GET /health` (liveness) y `GET /ready` (BD + Redis + storage).
- Métricas Prometheus: latencia de emisión, tasa de rechazo por código, profundidad de cola, fallos de webhook.
- Rate limiting por API key.
- Alerta de **certificados próximos a vencer** (job diario + webhook `certificate.expiring`).

### 2.7 Tests de Etapa 2
Extender la pirámide: golden files y XSD para `CreditNote`, `DebitNote`, `SummaryDocuments`, `VoidedDocuments`; tests del flujo de ticket (mock que devuelve "en proceso" y luego CDR); snapshot del PDF; test del job de reconciliación; validación del contenido del QR.

---

## ETAPA 3 — Roadmap (fuera del MVP, solo documentado)

Guía de Remisión Electrónica (09/31 — API REST v2 de SUNAT con OAuth2, subsistema aparte), Retenciones (20) y Percepciones (40), flujo OSE (los campos ya existen en `Company` pero no hay especificación), anticipos y detracciones completas, storage S3/MinIO, multi-moneda con tipo de cambio SUNAT, panel web de administración.

---

## Archivos críticos

**Se modifican:** `pyproject.toml`, `.gitignore`, `podman-compose.yml`, `app/main.py`, `app/core/config.py`, `app/core/database.py`, `app/schemas/document_reference.py` (separar NC/ND).

**Se crean** (patrón repetido, rutas representativas): `app/core/{dependencies,errors,logging}.py`; `app/domain/{money,tax_engine,number_to_words,naming}.py`; `app/catalogs/cat*.py` + `{tax_schemes,cdr_codes}.py`; `app/xml/{namespaces,ubl_invoice,xml_signer,zip_helper,cdr_parser}.py` (+ `ubl_credit_note`, `ubl_debit_note`, `ubl_summary`, `ubl_voided` en Etapa 2); `app/services/*_service.py` (16 de la guía + `webhook_service`); `app/api/v1/*.py` (un router por dominio); `app/models/webhook.py`; `app/worker/{main,jobs}.py`; `alembic/`; `tests/**`; `Containerfile`, `Makefile`, `README.md`, `CLAUDE.md`, `PLAN.md`, `docs/{DESPLIEGUE,INTEGRACION}.md`.

**Se reutilizan tal cual** (ya completos, no tocar salvo bug): los 15 archivos de `app/models/` y los 20 de `app/schemas/` — incluidos el validador de RUC módulo-11 en `app/schemas/company.py`, todos los enums de catálogos SUNAT en `app/schemas/common.py`, `ErrorResponse`, `PaginatedResponse[T]`, y los mixins de `app/models/base.py`.

---

## Verificación

**Por capa**
1. `make lint && make typecheck` — Ruff + Pyright limpios.
2. `make test` — suite completa con cobertura; umbral ≥ 85 % en `app/domain/` y `app/xml/`.
3. Validación XSD: cada XML generado pasa contra los XSD oficiales de SUNAT (falla el test si no).
4. Verificación de firma: el XML firmado se verifica criptográficamente en el propio test y la firma está dentro de `ext:ExtensionContent`.

**End-to-end en BETA** (guion manual documentado en `docs/DESPLIEGUE.md`)
```
podman-compose up -d && make migrate
POST /api/v1/companies                      # RUC de pruebas 20000000001
POST /api/v1/companies/{id}/certificates    # PFX de prueba
PATCH /api/v1/companies/{id}/sunat-credentials   # MODDATOS / moddatos
POST /api/v1/companies/{id}/series          # F001
POST /api/v1/companies/{id}/api-keys
POST /api/v1/webhooks                       # endpoint receptor de prueba
POST /api/v1/invoices                       # → status ACCEPTED, sunat_code 0
GET  /api/v1/documents/{id}/xml   y   /cdr  # descargan correctamente
# el receptor de prueba registra el webhook document.accepted con firma válida
```

**Resiliencia** (simulable con el mock)
- SUNAT con timeout → 200 `status=SENT`, job encolado, webhook `document.sent`, y al recuperarse SUNAT el reintento cierra el documento.
- Redis caído → el sweeper de PostgreSQL entrega los webhooks igual.
- Doble `POST /invoices` con la misma `X-Idempotency-Key` → una sola factura, misma respuesta.
- 20 emisiones concurrentes sobre la misma serie → 20 correlativos distintos, sin huecos ni duplicados.
