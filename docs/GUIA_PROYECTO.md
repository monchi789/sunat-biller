# Guía de Proyecto — Facturador Electrónico SUNAT

> Documento de referencia técnica y funcional. Define todos los requerimientos, casos de uso, servicios, lógica de negocio, estructura XML y orden de implementación del proyecto.

---

## Tabla de Contenidos

1. [Visión General](#1-visión-general)
2. [Stack Tecnológico](#2-stack-tecnológico)
3. [Requerimientos Funcionales](#3-requerimientos-funcionales)
4. [Requerimientos No Funcionales](#4-requerimientos-no-funcionales)
5. [Ciclo de Vida de un Comprobante](#5-ciclo-de-vida-de-un-comprobante)
6. [Estructura del XML UBL 2.1 (SUNAT)](#6-estructura-del-xml-ubl-21-sunat)
7. [Servicios del Sistema](#7-servicios-del-sistema)
8. [API REST — Endpoints](#8-api-rest--endpoints)
9. [Módulo XML (`app/xml/`)](#9-módulo-xml-appxml)
10. [Módulo Services (`app/services/`)](#10-módulo-services-appservices)
11. [Módulo Catalogs (`app/catalogs/`)](#11-módulo-catalogs-appcatalogs)
12. [Seguridad y Autenticación](#12-seguridad-y-autenticación)
13. [Manejo de Errores](#13-manejo-de-errores)
14. [Orden de Implementación](#14-orden-de-implementación)

---

## 1. Visión General

El sistema es un **facturador electrónico multi-empresa** que permite emitir comprobantes de pago electrónicos válidos ante SUNAT (Perú). Cada empresa que usa el sistema gestiona sus propias series, certificados digitales y credenciales SOL. El sistema genera el XML en formato UBL 2.1, lo firma digitalmente con el certificado PFX de la empresa, lo envía a SUNAT vía Web Service y almacena el resultado.

### Tipos de Comprobantes Soportados

| Código | Tipo | Clase | Envío SUNAT |
|--------|------|-------|-------------|
| 01 | Factura electrónica | `InvoiceCreate` | `sendBill` (síncrono) |
| 03 | Boleta de venta electrónica | `ReceiptCreate` | Resumen diario (`sendSummary`) |
| 07 | Nota de crédito electrónica | `CreditNoteCreate` | `sendBill` (síncrono) |
| 08 | Nota de débito electrónica | `DebitNoteCreate` | `sendBill` (síncrono) |

### Documentos de Resumen

| Tipo | Clase | Descripción |
|------|-------|-------------|
| Resumen Diario (RC) | `DailySummaryCreate` | Agrupa boletas emitidas en un día |
| Comunicación de Baja (RA) | `VoidedDocumentCreate` | Da de baja facturas/boletas aceptadas |

---

## 2. Stack Tecnológico

```
FastAPI 0.141        — framework HTTP async
SQLAlchemy 2.0       — ORM + Mapped types
PostgreSQL           — base de datos principal
Alembic              — migraciones de esquema
Pydantic v2          — validación de datos / schemas
pydantic-settings    — configuración por entorno (.env)
psycopg2-binary      — driver PostgreSQL síncrono
uvicorn              — servidor ASGI
lxml                 — generación y parsing de XML UBL 2.1
signxml              — firma digital XML (XMLDSig / XAdES-BES)
cryptography         — lectura de certificados PFX (.p12)
httpx                — cliente HTTP async para llamadas al WS SUNAT
```


## 3. Requerimientos Funcionales

### RF-01 Gestión de Empresas

| ID | Descripción |
|----|-------------|
| RF-01.1 | Registrar empresa con RUC, razón social, dirección, ubigeo, país. Validar dígito verificador del RUC (módulo 11 SUNAT). |
| RF-01.2 | Actualizar datos de empresa (todos opcionales en el update). |
| RF-01.3 | Soft-delete de empresa (marca `deleted_at`, no borra). |
| RF-01.4 | Actualizar credenciales SOL (`sol_user`, `sol_password`) de forma separada. La contraseña se almacena cifrada, nunca en texto plano. |
| RF-01.5 | Configurar modo de envío: `SUNAT_DIRECT` (conexión directa) u `OSE` (Operador de Servicios Electrónicos). |
| RF-01.6 | Listar empresas con paginación. |

### RF-02 Gestión de Certificados Digitales

| ID | Descripción |
|----|-------------|
| RF-02.1 | Subir certificado digital en formato PFX/P12 con contraseña. Validar que sea un archivo válido y extraer `serial_number`, `valid_from`, `valid_until`. |
| RF-02.2 | Solo puede haber **un certificado activo** por empresa (índice parcial único en `digital_certificates` donde `active = true`). Al activar uno nuevo, el anterior se desactiva automáticamente. |
| RF-02.3 | Soft-delete de certificado. |
| RF-02.4 | El archivo del certificado se almacena en filesystem local (path en `certificate_path`). La contraseña se almacena cifrada. |

### RF-03 Gestión de Series

| ID | Descripción |
|----|-------------|
| RF-03.1 | Crear serie para un tipo de documento (ej: `F001` para facturas, `B001` para boletas). Patrón `^[A-Z]\d{3}$`. |
| RF-03.2 | Una empresa no puede tener dos series con el mismo `document_type + series`. |
| RF-03.3 | Activar / desactivar serie. |
| RF-03.4 | El campo `current_number` se incrementa **atómicamente** al emitir un comprobante (con `SELECT FOR UPDATE` o `UPDATE ... RETURNING`). |

### RF-04 Gestión de API Keys

| ID | Descripción |
|----|-------------|
| RF-04.1 | Crear API Key con nombre y fecha de expiración opcional. El sistema genera el key aleatorio (32 bytes hex), lo retorna **una sola vez** al cliente, y almacena solo el hash (SHA-256). |
| RF-04.2 | Listar API Keys (nunca expone el key en texto plano). |
| RF-04.3 | Revocar (soft-delete) API Key. |
| RF-04.4 | El middleware de autenticación verifica que el hash del key recibido en cabecera coincida con `key_hash` en BD, que `active = true` y que no haya expirado. |
| RF-04.5 | Actualizar `last_used_at` al autenticar. |

### RF-05 Emisión de Factura (Tipo 01)

| ID | Descripción |
|----|-------------|
| RF-05.1 | Recibir `InvoiceCreate` con validaciones: cliente obligatorio con `document_type = RUC`, mínimo 1 ítem, fecha no futura. |
| RF-05.2 | Calcular totales en backend (no confiar en el cliente): `subtotal`, `discount_total`, `taxable_total`, `exempt_total`, `unaffected_total`, `igv_total`, `isc_total`, `icbper_total`, `total`. |
| RF-05.3 | Validar consistencia: `total == subtotal - discount_total + igv_total + isc_total + icbper_total + other_tax_total` (tolerancia ±0.01). |
| RF-05.4 | Asignar número correlativo de la serie (atómico). |
| RF-05.5 | Crear snapshot de empresa y cliente en ese momento. |
| RF-05.6 | Generar XML UBL 2.1 (`Invoice`). |
| RF-05.7 | Firmar XML con certificado PFX de la empresa (XMLDSig). |
| RF-05.8 | Enviar a SUNAT mediante `sendBill` → recibir CDR. |
| RF-05.9 | Parsear CDR y actualizar `status`, `sunat_code`, `sunat_description`, `accepted_at`. |
| RF-05.10 | Almacenar archivos: XML firmado, CDR, PDF. |
| RF-05.11 | Soporte de idempotencia: misma `X-Idempotency-Key` retorna la respuesta almacenada sin reprocesar. |

### RF-06 Emisión de Boleta (Tipo 03)

| ID | Descripción |
|----|-------------|
| RF-06.1 | Recibir `ReceiptCreate`. Cliente opcional salvo que el total supere el umbral SUNAT vigente (S/ 700 según norma actual; verificar). |
| RF-06.2 | Las mismas validaciones de cálculo de RF-05.2 a RF-05.5. |
| RF-06.3 | Generar XML UBL 2.1 (`Invoice` con tipo `03`). |
| RF-06.4 | Firmar XML. |
| RF-06.5 | La boleta **no** se envía individualmente. Se almacena con `status = SIGNED` esperando ser incluida en un Resumen Diario. |
| RF-06.6 | Retornar la boleta con `status = SIGNED`. |

### RF-07 Resumen Diario de Boletas (RC)

| ID | Descripción |
|----|-------------|
| RF-07.1 | Recibir `DailySummaryCreate` con `reference_date` y lista de `document_ids` (UUIDs de boletas). |
| RF-07.2 | Validar: todos los `document_ids` son boletas (`document_type = 03`), emitidas en `reference_date`, pertenecientes a la empresa autenticada, en estado `SIGNED`, sin duplicados. |
| RF-07.3 | Generar identifier del resumen: `RC-YYYYMMDD-NNN` (correlativo por empresa y fecha). |
| RF-07.4 | Generar XML UBL 2.1 (`SummaryDocuments`). |
| RF-07.5 | Firmar XML. |
| RF-07.6 | Enviar a SUNAT mediante `sendSummary` → recibir `ticket`. |
| RF-07.7 | Almacenar `ticket` y marcar boletas como `status = SENT`. |
| RF-07.8 | Permitir consultar el estado del ticket (`getStatus`) y actualizar cuando SUNAT responde con CDR. |
| RF-07.9 | Al confirmarse, marcar boletas como `ACCEPTED`. |

### RF-08 Comunicación de Baja (RA)

| ID | Descripción |
|----|-------------|
| RF-08.1 | Recibir `VoidedDocumentCreate` con `reference_date` y lista de items (cada uno con `document_id` y `reason`). |
| RF-08.2 | Validar: documentos en estado `ACCEPTED` o `ACCEPTED_WITH_OBSERVATION`, sin duplicados, pertenecientes a la empresa. |
| RF-08.3 | Generar identifier: `RA-YYYYMMDD-NNN`. |
| RF-08.4 | Generar XML UBL 2.1 (`VoidedDocuments`). |
| RF-08.5 | Firmar XML. |
| RF-08.6 | Enviar a SUNAT mediante `sendSummary` (mismo WS) → recibir `ticket`. |
| RF-08.7 | Consultar ticket y actualizar al confirmarse → marcar documentos como `VOIDED`. |

### RF-09 Nota de Crédito (Tipo 07)

| ID | Descripción |
|----|-------------|
| RF-09.1 | Recibir `CreditNoteCreate` con `reference` (documento que se corrige) y cliente obligatorio. |
| RF-09.2 | Validar que `reference.reference_document_type` sea `01` (Factura) o `03` (Boleta). No puede referenciar otra nota. |
| RF-09.3 | `reason_code` debe pertenecer al Catálogo 09 SUNAT (`CreditNoteReasonType`). |
| RF-09.4 | Generar XML `CreditNote` UBL 2.1. Firmar y enviar como `sendBill`. |
| RF-09.5 | Mismo flujo de CDR que la factura. |

### RF-10 Nota de Débito (Tipo 08)

| ID | Descripción |
|----|-------------|
| RF-10.1 | Recibir `DebitNoteCreate` con `reference` y cliente obligatorio. |
| RF-10.2 | Validar `reference_document_type` = `01` o `03`. |
| RF-10.3 | `reason_code` debe pertenecer al Catálogo 10 SUNAT (`DebitNoteReasonType`). |
| RF-10.4 | Generar XML `DebitNote` UBL 2.1. Firmar y enviar como `sendBill`. |

### RF-11 Consulta y Descarga de Documentos

| ID | Descripción |
|----|-------------|
| RF-11.1 | Listar comprobantes de la empresa con filtros: `document_type`, `status`, `issue_date` (rango), `series`, paginación. |
| RF-11.2 | Obtener comprobante por ID con todos sus ítems, cuotas, referencias, estado SUNAT. |
| RF-11.3 | Descargar XML firmado del comprobante. |
| RF-11.4 | Descargar CDR del comprobante. |
| RF-11.5 | Descargar PDF del comprobante. |
| RF-11.6 | Consultar estado actual de un comprobante ante SUNAT (`getStatusCdr`). |

### RF-12 Auditoría

| ID | Descripción |
|----|-------------|
| RF-12.1 | Registrar en `audit_logs` cada operación relevante: emisión, envío, respuesta SUNAT, errores, cambios de configuración. |
| RF-12.2 | Capturar `ip_address` y `user_agent` del cliente en cada request. |
| RF-12.3 | Listar audit logs de la empresa con filtros por `action`, `status`, rango de fechas. |

---

## 4. Requerimientos No Funcionales

### RNF-01 Seguridad

| ID | Descripción |
|----|-------------|
| RNF-01.1 | Autenticación por API Key en cabecera `X-API-Key`. Sin JWT en esta versión. |
| RNF-01.2 | Cada empresa solo accede a sus propios recursos (aislamiento por `company_id` en todas las queries). |
| RNF-01.3 | Credenciales SOL (`sol_password`) y contraseñas de certificados cifradas en reposo con AES-256 (usando `cryptography.fernet`). La `SECRET_KEY` de la aplicación es la llave maestra. |
| RNF-01.4 | El contenido del PFX nunca se expone por API. Solo `serial_number`, `valid_from`, `valid_until`. |
| RNF-01.5 | HTTPS obligatorio en producción (manejo en reverse proxy, no en la app). |
| RNF-01.6 | `X-Idempotency-Key` limita reenvíos accidentales. Expiración en 24 h. |

### RNF-02 Rendimiento

| ID | Descripción |
|----|-------------|
| RNF-02.1 | Tiempo de respuesta < 3 s para emisión de factura con una sola llamada al WS SUNAT. |
| RNF-02.2 | El incremento del correlativo de serie es atómico y con bloqueo a nivel de fila (`SELECT FOR UPDATE`) para evitar duplicados bajo concurrencia. |
| RNF-02.3 | Queries con índices en `(company_id, status)`, `(company_id, issue_date)`, `sunat_status`. Ya definidos en el modelo. |

### RNF-03 Confiabilidad

| ID | Descripción |
|----|-------------|
| RNF-03.1 | Si SUNAT no responde, el comprobante queda en `status = SENT` para reintento manual o futuro job de reconciliación. |
| RNF-03.2 | Toda la operación de emisión (crear documento + snapshot + ítems + serie increment) ocurre en **una transacción de BD**. Si algo falla, se hace rollback completo. |
| RNF-03.3 | Los archivos XML, CDR y PDF se almacenan en filesystem local. En producción se puede externalizar a S3/GCS. |
| RNF-03.4 | El soft-delete en `Company`, `APIKey`, `DigitalCertificate`, `ElectronicDocument` garantiza trazabilidad. |

### RNF-04 Mantenibilidad

| ID | Descripción |
|----|-------------|
| RNF-04.1 | Un modelo por archivo en `app/models/`. Un schema por archivo en `app/schemas/`. Un servicio por dominio en `app/services/`. |
| RNF-04.2 | Un generador de XML por tipo de comprobante en `app/xml/`. |
| RNF-04.3 | Catálogos SUNAT centralizados en `app/catalogs/` (constantes puras, sin lógica). |
| RNF-04.4 | Migraciones de BD con Alembic. No usar `Base.metadata.create_all()` en producción. |

### RNF-05 Compatibilidad SUNAT

| ID | Descripción |
|----|-------------|
| RNF-05.1 | XML en formato UBL 2.1 con namespaces SUNAT (`pe-cac`, `sac`). |
| RNF-05.2 | Firma digital XMLDSig con el certificado X.509 embebido en el PFX. |
| RNF-05.3 | Comunicación vía SOAP/WSDL al WS SUNAT (URL beta y producción configurables). |
| RNF-05.4 | Catálogos fieles a los publicados por SUNAT: Catálogo 01 (tipos de doc), 03 (unidades), 06 (doc identidad), 07 (afectación IGV), 09 (motivos NC), 10 (motivos ND), 16 (tipo precio), 51 (tipo operación). |
| RNF-05.5 | Nombre de archivo según norma SUNAT: `{RUC}-{TIPO}-{SERIE}-{NUMERO}.xml`. |

---

## 5. Ciclo de Vida de un Comprobante

```
                         Cliente
                            │
                    POST /invoices
                            │
                     ┌──────▼──────┐
                     │  DRAFT      │  (antes de procesar)
                     └──────┬──────┘
                            │ validate + calcular totales
                     ┌──────▼──────┐
                     │  PENDING    │  (en cola)
                     └──────┬──────┘
                            │ generar XML
                     ┌──────▼──────┐
                     │ PROCESSING  │
                     └──────┬──────┘
                            │ firmar XML
                     ┌──────▼──────┐
                     │   SIGNED    │ ← Boletas se quedan aquí
                     └──────┬──────┘
                            │ sendBill / sendSummary
                     ┌──────▼──────┐
                     │    SENT     │
                     └──────┬──────┘
                    ┌───────┴──────────┐
             ┌──────▼──────┐   ┌──────▼──────────────┐
             │  ACCEPTED   │   │ ACCEPTED_WITH_OBS   │
             └──────┬──────┘   └──────┬──────────────┘
                    │                  │
          ┌─────────▼──────────────────▼────────┐
          │           VOIDED (baja aceptada)     │
          └──────────────────────────────────────┘

     Error en cualquier paso → ERROR
     Cancelado antes de enviar → CANCELLED
     Rechazado por SUNAT → REJECTED
```

---

## 6. Estructura del XML UBL 2.1 (SUNAT)

### 6.1 Namespaces obligatorios

```xml
xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"
xmlns:ds="http://www.w3.org/2000/09/xmldsig#"
xmlns:ext="urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2"
xmlns:sac="urn:sunat:names:specification:ubl:peru:schema:xsd:SunatAggregateComponents-1"
```

### 6.2 Estructura Factura (`Invoice` tipo 01)

```
Invoice
├── ext:UBLExtensions
│   └── ext:UBLExtension
│       └── ext:ExtensionContent          ← aquí va la firma XMLDSig
├── cbc:UBLVersionID                      "2.1"
├── cbc:CustomizationID                   "2.0"
├── cbc:ID                                "F001-00000001"
├── cbc:IssueDate                         "2024-01-15"
├── cbc:IssueTime                         "12:00:00"  (opcional)
├── cbc:InvoiceTypeCode
│   └── @listID = "0101"                  (OperationType: Catálogo 51)
│   └── valor = "01"                      (DocumentType: Catálogo 01)
├── cbc:Note                              "SON CIEN CON 00/100 SOLES" (literal en letras)
├── cbc:DocumentCurrencyCode              "PEN"
├── cbc:LineCountNumeric                  número de ítems
│
├── cac:OrderReference (si hay anticipo)
│
├── cac:DespatchDocumentReference (referencias adicionales)
│
├── cac:Signature                         referencia a la firma
│   ├── cbc:ID                            "signatureKG"
│   └── cac:SignatoryParty
│       └── cac:PartyIdentification
│           └── cbc:ID                   RUC del emisor
│
├── cac:AccountingSupplierParty           EMISOR
│   └── cac:Party
│       ├── cac:PartyIdentification
│       │   └── cbc:ID schemeID="6"      RUC emisor
│       ├── cac:PartyName
│       │   └── cbc:Name                 Nombre comercial
│       └── cac:PostalAddress
│           ├── cbc:ID                   Ubigeo
│           ├── cbc:StreetName           Dirección
│           ├── cbc:CitySubdivisionName  Urbanización
│           ├── cbc:CityName             Provincia
│           ├── cbc:CountrySubentity     Departamento
│           └── cac:Country
│               └── cbc:IdentificationCode  "PE"
│
├── cac:AccountingCustomerParty           RECEPTOR
│   └── cac:Party
│       ├── cac:PartyIdentification
│       │   └── cbc:ID schemeID="6"      RUC o DNI receptor
│       └── cac:PartyLegalEntity
│           └── cbc:RegistrationName     Razón social receptor
│
├── cac:PaymentMeans                      Forma de pago
│   ├── cbc:PaymentMeansCode              "Contado" o "Credito"
│   └── cbc:PaymentDueDate               si es crédito
│
├── cac:PaymentTerms (N cuotas si crédito)
│   ├── cbc:ID                           "FormaPago"
│   ├── cbc:PaymentMeansID               "Cuota001"
│   ├── cbc:Amount currencyID="PEN"
│   └── cbc:PaymentDueDate
│
├── cac:TaxTotal                          TOTALES TRIBUTARIOS
│   ├── cbc:TaxAmount currencyID="PEN"   total IGV + ISC + ICBPER
│   └── cac:TaxSubtotal (por cada impuesto)
│       ├── cbc:TaxableAmount            base imponible
│       ├── cbc:TaxAmount                monto del impuesto
│       └── cac:TaxCategory
│           ├── cbc:ID                   "S" IGV, "Z" exonerado, "O" inafecto
│           ├── cbc:Percent              18.00 (IGV)
│           └── cac:TaxScheme
│               ├── cbc:ID               "1000" IGV, "2000" ISC, "7152" ICBPER
│               ├── cbc:Name             "IGV", "ISC", "ICBPER"
│               └── cbc:TaxTypeCode      "VAT", "EXC", "OTH"
│
├── cac:LegalMonetaryTotal                TOTALES MONETARIOS
│   ├── cbc:LineExtensionAmount          suma de valores netos de ítems
│   ├── cbc:TaxExclusiveAmount           base imponible total
│   ├── cbc:TaxInclusiveAmount           total con impuestos
│   ├── cbc:AllowanceTotalAmount         total descuentos
│   ├── cbc:ChargeTotalAmount            total cargos
│   ├── cbc:PrepaidAmount                anticipos
│   └── cbc:PayableAmount                total a pagar
│
└── cac:InvoiceLine (N ítems)             ÍTEMS
    ├── cbc:ID                           número de línea
    ├── cbc:InvoicedQuantity unitCode="NIU"  cantidad + unidad
    ├── cbc:LineExtensionAmount          subtotal línea (sin IGV)
    │
    ├── cac:PricingReference             precio referencia (si aplica)
    │   └── cac:AlternativeConditionPrice
    │       ├── cbc:PriceAmount          precio unitario con IGV
    │       └── cbc:PriceTypeCode        "01" o "02" (Catálogo 16)
    │
    ├── cac:TaxTotal                     impuestos del ítem
    │   └── cac:TaxSubtotal (por impuesto)
    │       ├── cbc:TaxableAmount
    │       ├── cbc:TaxAmount
    │       └── cac:TaxCategory
    │           ├── cbc:ID               código afectación
    │           ├── cbc:Percent
    │           └── cac:TaxScheme
    │
    ├── cac:Item
    │   ├── cbc:Description              descripción del producto
    │   └── cac:SellersItemIdentification
    │       └── cbc:ID                   código interno del producto
    │
    └── cac:Price
        └── cbc:PriceAmount              precio unitario sin IGV (valor unitario)
```

### 6.3 Boleta (`Invoice` tipo 03)

Estructura idéntica a la Factura. Diferencias:
- `cbc:InvoiceTypeCode` = `"03"`
- El receptor puede tener `schemeID="1"` (DNI) en lugar de `"6"` (RUC)
- Si no hay receptor (público en general), el bloque `cac:AccountingCustomerParty` usa un valor genérico

### 6.4 Nota de Crédito (`CreditNote`)

```
CreditNote
├── ... (cabecera igual que Invoice, sin InvoiceTypeCode)
├── cbc:CreditNoteTypeCode               "07"
├── cac:DiscrepancyResponse              REFERENCIA Y MOTIVO
│   ├── cbc:ReferenceID                  "F001-00000001" (comprobante afectado)
│   ├── cbc:ResponseCode                 "01" (Catálogo 09)
│   └── cbc:Description                  descripción del motivo
├── cac:BillingReference
│   └── cac:InvoiceDocumentReference
│       ├── cbc:ID                       "F001-00000001"
│       └── cbc:DocumentTypeCode         "01"
└── cac:CreditNoteLine (igual que InvoiceLine)
```

### 6.5 Nota de Débito (`DebitNote`)

```
DebitNote
├── ... (cabecera)
├── cbc:DebitNoteTypeCode                "08"
├── cac:DiscrepancyResponse
│   ├── cbc:ReferenceID
│   ├── cbc:ResponseCode                 código Catálogo 10
│   └── cbc:Description
├── cac:BillingReference
└── cac:DebitNoteLine
```

### 6.6 Resumen Diario (`SummaryDocuments`)

```
SummaryDocuments
├── cbc:ID                               "RC-20240115-001"
├── cbc:ReferenceDate                    "2024-01-15"
├── cbc:IssueDate                        fecha de envío
├── cac:AccountingSupplierParty          emisor
└── sac:SummaryDocumentsLine (por cada boleta)
    ├── cbc:LineID                       número de línea
    ├── cbc:DocumentTypeCode             "03"
    ├── cbc:ID                           "B001-00000001"
    ├── cac:AccountingCustomerParty      receptor (si aplica)
    ├── cac:Status
    │   └── cbc:ConditionCode            "1" ADD, "2" MODIFY, "3" VOID
    ├── cac:TotalAmount                  total de la boleta
    ├── sac:BillingPayment               pago
    └── cac:TaxTotal                     totales tributarios
```

### 6.7 Comunicación de Baja (`VoidedDocuments`)

```
VoidedDocuments
├── cbc:ID                               "RA-20240115-001"
├── cbc:ReferenceDate                    "2024-01-15"
├── cbc:IssueDate                        fecha de envío
├── cac:AccountingSupplierParty
└── sac:VoidedDocumentsLine (por cada doc)
    ├── cbc:LineID
    ├── cbc:DocumentTypeCode             "01", "03", etc.
    ├── cbc:ID                           "F001-00000001"
    └── cbc:VoidReasonDescription        motivo de la baja
```

### 6.8 Nombre de Archivos (norma SUNAT)

| Tipo | Patrón | Ejemplo |
|------|--------|---------|
| Factura/Boleta/NC/ND | `{RUC}-{TIPO}-{SERIE}-{NUMERO}` | `20123456789-01-F001-00000001` |
| Resumen Diario | `{RUC}-RC-{YYYYMMDD}-{NNN}` | `20123456789-RC-20240115-001` |
| Comunicación de Baja | `{RUC}-RA-{YYYYMMDD}-{NNN}` | `20123456789-RA-20240115-001` |
| ZIP enviado a SUNAT | `{filename}.zip` | `20123456789-01-F001-00000001.zip` |

---

## 7. Servicios del Sistema

### 7.1 Mapa de Servicios

```
app/services/
├── company_service.py          # CRUD empresa + credenciales SOL
├── api_key_service.py          # generación, verificación, revocación de API Keys
├── certificate_service.py      # upload, parsing PFX, activación de cert
├── series_service.py           # CRUD series + obtener siguiente número (atómico)
├── document_service.py         # lógica base: calcular totales, crear snapshots, guardar
├── invoice_service.py          # orquesta emisión de facturas
├── receipt_service.py          # orquesta emisión de boletas
├── credit_note_service.py      # orquesta emisión de notas de crédito
├── debit_note_service.py       # orquesta emisión de notas de débito
├── daily_summary_service.py    # genera y envía Resumen Diario RC
├── voided_document_service.py  # genera y envía Comunicación de Baja RA
├── xml_sign_service.py         # lee PFX, firma XML con XMLDSig
├── sunat_client_service.py     # cliente SOAP para WS SUNAT (sendBill, sendSummary, getStatus)
├── file_storage_service.py     # almacena/recupera XML, CDR, PDF en filesystem
├── crypto_service.py           # cifrado/descifrado de secretos con Fernet
└── audit_service.py            # registra eventos en audit_logs
```

### 7.2 Descripción de cada Servicio

#### `company_service.py`
- `create_company(db, data: CompanyCreate) -> Company`
- `update_company(db, company_id, data: CompanyUpdate) -> Company`
- `delete_company(db, company_id) -> None` — soft-delete
- `update_sunat_credentials(db, company_id, data: CompanySunatCredentialsUpdate) -> None` — cifra y guarda
- `get_company(db, company_id) -> Company`
- `list_companies(db, page, page_size) -> PaginatedResponse[CompanyResponse]`

#### `api_key_service.py`
- `create_api_key(db, company_id, data: APIKeyCreate) -> tuple[APIKey, str]` — retorna modelo + key en claro (solo una vez)
- `verify_api_key(db, raw_key: str) -> Company` — hash, busca, valida expiración, actualiza `last_used_at`
- `revoke_api_key(db, company_id, key_id) -> None` — soft-delete
- `list_api_keys(db, company_id) -> list[APIKeyResponse]`

#### `certificate_service.py`
- `upload_certificate(db, company_id, file_bytes: bytes, password: str) -> DigitalCertificate`
  - valida extensión y tamaño
  - carga PFX con `cryptography`, extrae `serial_number`, `valid_from`, `valid_until`
  - cifra `password` con Fernet
  - desactiva certificado anterior
  - guarda archivo en disco
- `get_active_certificate(db, company_id) -> DigitalCertificate`
- `load_pfx(cert: DigitalCertificate) -> tuple[private_key, certificate, chain]` — descifra contraseña, carga PFX

#### `series_service.py`
- `create_series(db, company_id, data: DocumentSeriesCreate) -> DocumentSeries`
- `get_next_number(db, series_id) -> int` — `UPDATE document_series SET current_number = current_number + 1 WHERE id = ? RETURNING current_number` (atómico)
- `get_series(db, company_id, document_type, series_str) -> DocumentSeries`
- `list_series(db, company_id) -> list[DocumentSeriesResponse]`

#### `document_service.py`
- `calculate_totals(items: list[DocumentItemCreate]) -> DocumentTotals` — calcula todos los totales desde los ítems
- `validate_totals(provided, calculated) -> None` — verifica tolerancia ±0.01
- `create_company_snapshot(db, company: Company) -> CompanySnapshot`
- `create_customer_snapshot(db, customer: CustomerCreate | None) -> CustomerSnapshot | None`
- `get_document(db, company_id, document_id) -> ElectronicDocument`
- `list_documents(db, company_id, filters, page, page_size) -> PaginatedResponse[DocumentResponse]`
- `update_document_status(db, document_id, status, sunat_data) -> None`

#### `invoice_service.py`
- `emit_invoice(db, company_id, data: InvoiceCreate) -> InvoiceResponse`
  1. Valida idempotencia (`X-Idempotency-Key`)
  2. Obtiene serie activa `F___`
  3. `calculate_totals(data.items)`
  4. `get_next_number(series)` (atómico)
  5. Crea snapshots de empresa y cliente
  6. Persiste `ElectronicDocument` + ítems + cuotas → `status = PENDING`
  7. `xml_sign_service.generate_and_sign(document)` → XML firmado
  8. `file_storage_service.save_xml(company_id, filename, xml_bytes)`
  9. `sunat_client_service.send_bill(company_id, filename, zip_bytes)` → CDR
  10. Parsea CDR → actualiza `status`, `sunat_code`, `sunat_description`, `accepted_at`
  11. `file_storage_service.save_cdr(company_id, filename, cdr_bytes)`
  12. Registra en `audit_logs`
  13. Guarda idempotencia
  14. Retorna `InvoiceResponse`

#### `receipt_service.py`
- `emit_receipt(db, company_id, data: ReceiptCreate) -> ReceiptResponse`
  - Pasos 1–8 igual que invoice_service (con serie `B___`)
  - No llama a SUNAT directamente → `status = SIGNED`
  - Retorna `ReceiptResponse`

#### `daily_summary_service.py`
- `create_daily_summary(db, company_id, data: DailySummaryCreate) -> DailySummaryResponse`
  - Valida boletas
  - Genera RC XML
  - Firma y envía `sendSummary`
  - Guarda ticket
- `poll_ticket_status(db, company_id, daily_summary_id) -> DailySummaryResponse`
  - `sunat_client_service.get_status(ticket)` → CDR
  - Actualiza boletas a `ACCEPTED`

#### `voided_document_service.py`
- `create_voided_document(db, company_id, data: VoidedDocumentCreate) -> VoidedDocumentResponse`
- `poll_ticket_status(db, company_id, voided_document_id) -> VoidedDocumentResponse`

#### `xml_sign_service.py`
- `build_invoice_xml(document, company_snapshot, customer_snapshot, items, installments) -> bytes`
- `build_credit_note_xml(...) -> bytes`
- `build_debit_note_xml(...) -> bytes`
- `build_summary_xml(daily_summary, items) -> bytes`
- `build_voided_xml(voided_document, items) -> bytes`
- `sign_xml(xml_bytes: bytes, private_key, certificate) -> bytes` — aplica XMLDSig en `ext:UBLExtension`

#### `sunat_client_service.py`
- `send_bill(ruc: str, filename: str, zip_content: bytes) -> bytes` — retorna CDR bytes
- `send_summary(ruc: str, filename: str, zip_content: bytes) -> str` — retorna ticket
- `get_status(ruc: str, ticket: str) -> bytes` — retorna CDR bytes
- `get_status_cdr(ruc: str, doc_type: str, series: str, number: int) -> bytes`
- Internamente: prepara el ZIP del XML, construye el envelope SOAP, hace POST con `httpx`, parsea respuesta.

#### `file_storage_service.py`
- `save_xml(company_id, filename, content: bytes) -> str` — retorna path
- `save_cdr(company_id, filename, content: bytes) -> str`
- `save_pdf(company_id, filename, content: bytes) -> str`
- `get_file(path: str) -> bytes`
- Estructura en disco: `storage/{company_id}/{YYYY}/{MM}/{filename}.{ext}`

#### `crypto_service.py`
- `encrypt(plaintext: str) -> str` — Fernet con `SECRET_KEY`
- `decrypt(ciphertext: str) -> str`
- Usado para `sol_password_secret` y `password_secret` de certificados.

#### `audit_service.py`
- `log(db, company_id, action, status, document_id=None, message=None, request=None) -> None`
- Se llama desde los servicios en puntos clave; no falla si hay error (try/except interno).

---

## 8. API REST — Endpoints

Prefijo: `/api/v1` · Autenticación: `X-API-Key: <key>` en todas salvo `/health`.

### Empresas
```
GET    /companies                        listar (paginado)
POST   /companies                        crear empresa
GET    /companies/{id}                   obtener empresa
PATCH  /companies/{id}                   actualizar datos
DELETE /companies/{id}                   soft-delete
PATCH  /companies/{id}/sunat-credentials actualizar SOL user/password
```

### API Keys
```
GET    /companies/{id}/api-keys          listar
POST   /companies/{id}/api-keys          crear (retorna key en claro, única vez)
DELETE /companies/{id}/api-keys/{key_id} revocar
```

### Certificados
```
GET    /companies/{id}/certificates      listar
POST   /companies/{id}/certificates      upload PFX (multipart/form-data)
DELETE /companies/{id}/certificates/{cert_id} soft-delete
```

### Series
```
GET    /companies/{id}/series            listar
POST   /companies/{id}/series            crear
PATCH  /companies/{id}/series/{series_id} activar/desactivar
```

### Comprobantes
```
GET    /documents                        listar (filtros: type, status, date range, series)
GET    /documents/{id}                   detalle completo
GET    /documents/{id}/xml               descargar XML firmado
GET    /documents/{id}/cdr               descargar CDR
GET    /documents/{id}/pdf               descargar PDF
POST   /documents/{id}/status            refrescar estado desde SUNAT
```

### Facturas
```
POST   /invoices                         emitir factura
GET    /invoices/{id}                    detalle
```

### Boletas
```
POST   /receipts                         emitir boleta
GET    /receipts/{id}                    detalle
```

### Notas de Crédito
```
POST   /credit-notes                     emitir nota de crédito
GET    /credit-notes/{id}                detalle
```

### Notas de Débito
```
POST   /debit-notes                      emitir nota de débito
GET    /debit-notes/{id}                 detalle
```

### Resúmenes Diarios
```
POST   /daily-summaries                  crear resumen diario (RC)
GET    /daily-summaries/{id}             estado
POST   /daily-summaries/{id}/poll        consultar ticket SUNAT
```

### Comunicaciones de Baja
```
POST   /voided-documents                 crear comunicación de baja (RA)
GET    /voided-documents/{id}            estado
POST   /voided-documents/{id}/poll       consultar ticket SUNAT
```

### Auditoría
```
GET    /audit-logs                       listar logs (filtros: action, status, date)
```

### Health
```
GET    /health                           estado de la app (sin auth)
```

---

## 9. Módulo XML (`app/xml/`)

```
app/xml/
├── __init__.py
├── namespaces.py        # constantes de todos los namespaces UBL 2.1 + SUNAT
├── ubl_invoice.py       # genera XML Invoice (Factura tipo 01 y Boleta tipo 03)
├── ubl_credit_note.py   # genera XML CreditNote (tipo 07)
├── ubl_debit_note.py    # genera XML DebitNote (tipo 08)
├── ubl_summary.py       # genera XML SummaryDocuments (RC)
├── ubl_voided.py        # genera XML VoidedDocuments (RA)
├── xml_signer.py        # aplica firma XMLDSig usando signxml + cryptography
├── cdr_parser.py        # parsea el CDR de respuesta SUNAT → extrae código y descripción
└── zip_helper.py        # empaqueta XML en ZIP para envío al WS
```

**Patrón de construcción XML:**
- Usar `lxml.etree` para construir el árbol XML.
- Cada builder recibe los datos ya validados (modelos SQLAlchemy o dataclasses intermedias).
- Retorna `bytes` con encoding UTF-8 y declaración XML.
- El signer recibe los `bytes` y retorna `bytes` con la firma embebida.

---

## 10. Módulo Services (`app/services/`)

```
app/services/
├── __init__.py
├── company_service.py
├── api_key_service.py
├── certificate_service.py
├── series_service.py
├── document_service.py
├── invoice_service.py
├── receipt_service.py
├── credit_note_service.py
├── debit_note_service.py
├── daily_summary_service.py
├── voided_document_service.py
├── xml_sign_service.py          # orquesta build + sign
├── sunat_client_service.py      # SOAP client
├── file_storage_service.py
├── crypto_service.py
└── audit_service.py
```

**Convenciones:**
- Todos los servicios reciben `db: Session` como primer argumento.
- Nunca hacen `db.commit()` — el commit lo hace el endpoint (o el contexto de la request).
- Excepción: `series_service.get_next_number` usa su propia transacción atómica.
- Las excepciones de negocio se lanzan como `HTTPException` desde el endpoint, no desde el servicio (el servicio lanza excepciones de dominio propias).

---

## 11. Módulo Catalogs (`app/catalogs/`)

```
app/catalogs/
├── __init__.py
├── cat01_document_types.py      # "01" Factura, "03" Boleta, "07" NC, "08" ND
├── cat03_unit_codes.py          # NIU, KGM, LTR, C62, etc.
├── cat06_identity_docs.py       # DNI, RUC, Pasaporte, etc.
├── cat07_tax_affectation.py     # 10 Gravado, 20 Exonerado, 30 Inafecto, 40 Exportación
├── cat09_credit_note_reasons.py # 01-12 motivos NC
├── cat10_debit_note_reasons.py  # 01-12 motivos ND
├── cat16_price_types.py         # 01 precio con IGV, 02 valor referencial
└── cat51_operation_types.py     # 0101 Venta interna, 0200 exportación, etc.
```

Son diccionarios Python puros: `{código: descripción}`. Sin lógica, sin imports pesados. Los schemas los referencian vía los Enums de `common.py`, pero los builders XML los usan directamente para mapear códigos a descripciones en los nodos de texto.

---

## 12. Seguridad y Autenticación

### Flujo de autenticación

```
Request → Middleware/Dependency
    │
    ├── Lee cabecera X-API-Key
    ├── hash SHA-256 del key recibido
    ├── SELECT * FROM api_keys WHERE key_hash = ? AND active = true
    ├── Verifica expires_at > now() (si tiene expiración)
    ├── UPDATE api_keys SET last_used_at = now() WHERE id = ?
    └── Inyecta company_id en el contexto del request
```

### Dependency FastAPI

```python
# app/core/dependencies.py
async def get_current_company(
    x_api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db),
) -> Company:
    company = api_key_service.verify_api_key(db, x_api_key)
    if not company:
        raise HTTPException(status_code=401, detail="Invalid or expired API Key")
    return company
```

### Cifrado de secretos

```python
# app/services/crypto_service.py
from cryptography.fernet import Fernet

def get_fernet() -> Fernet:
    key = base64.urlsafe_b64encode(settings.SECRET_KEY[:32].encode().ljust(32)[:32])
    return Fernet(key)
```

---

## 13. Manejo de Errores

### Códigos HTTP

| Situación | HTTP |
|-----------|------|
| API Key inválida / expirada | 401 |
| Recurso no pertenece a la empresa | 403 |
| Recurso no encontrado | 404 |
| Validación de datos (Pydantic) | 422 |
| RUC inválido, dígito verificador | 422 |
| Idempotency Key duplicada activa | 409 |
| Error al firmar XML | 500 |
| SUNAT rechazó el documento | 200 + `status = REJECTED` en body |
| SUNAT no disponible (timeout) | 200 + `status = SENT` en body (se reintenta) |

### Formato de Error

```json
{
  "error_code": "INVALID_RUC",
  "message": "El RUC proporcionado no tiene un dígito verificador válido.",
  "details": { "ruc": "20123456780" }
}
```

---

## 14. Orden de Implementación

### Fase 1 — Infraestructura (ya hecho parcialmente)
- [x] Modelos SQLAlchemy (`app/models/`)
- [x] Schemas Pydantic (`app/schemas/`)
- [x] Config + Database (`app/core/`)
- [ ] Migraciones Alembic (`alembic init alembic`)
- [ ] `pyrightconfig.json` y linting

### Fase 2 — Core servicios sin SUNAT
1. `crypto_service.py`
2. `file_storage_service.py`
3. `audit_service.py`
4. `company_service.py` + router `/companies`
5. `api_key_service.py` + router `/api-keys` + dependency `get_current_company`
6. `certificate_service.py` + router `/certificates`
7. `series_service.py` + router `/series`

### Fase 3 — Catálogos y XML
1. `app/catalogs/` — todos los catálogos
2. `app/xml/namespaces.py`
3. `app/xml/ubl_invoice.py` (Factura tipo 01) — el más complejo, base de los demás
4. `app/xml/xml_signer.py`
5. `app/xml/cdr_parser.py`
6. `app/xml/zip_helper.py`
7. Prueba offline: generar XML válido y verificar firma sin enviar a SUNAT

### Fase 4 — Cliente SUNAT
1. `sunat_client_service.py` — endpoint beta primero
2. Prueba de extremo a extremo en ambiente BETA SUNAT
3. `app/xml/ubl_credit_note.py`, `ubl_debit_note.py`
4. `app/xml/ubl_summary.py`, `ubl_voided.py`

### Fase 5 — Servicios de emisión
1. `document_service.py` (calcular totales, snapshots)
2. `xml_sign_service.py` (orquestador)
3. `invoice_service.py` + router `/invoices`
4. `receipt_service.py` + router `/receipts`
5. `credit_note_service.py` + router `/credit-notes`
6. `debit_note_service.py` + router `/debit-notes`
7. `daily_summary_service.py` + router `/daily-summaries`
8. `voided_document_service.py` + router `/voided-documents`

### Fase 6 — Pulido
1. Generación de PDF (biblioteca externa: `weasyprint` o `reportlab`)
2. Router `/documents` con filtros y descarga de archivos
3. Router `/audit-logs`
4. Tests de integración
5. Configuración producción (env vars, HTTPS, logging)

---

## Apéndice — URLs Web Service SUNAT

| Ambiente | URL WSDL |
|----------|----------|
| Beta (homologación) | `https://e-beta.sunat.gob.pe/ol-ti-itcpfegem-beta/billService?wsdl` |
| Producción | `https://e-factura.sunat.gob.pe/ol-ti-itcpfegem/billService?wsdl` |

### Operaciones SOAP

| Operación | Descripción | Tipo de doc |
|-----------|-------------|-------------|
| `sendBill` | Envío síncrono, retorna CDR inmediato | Factura, NC, ND |
| `sendSummary` | Envío asíncrono, retorna ticket | RC (boletas), RA (bajas) |
| `getStatus` | Consulta ticket → retorna CDR cuando listo | Tras sendSummary |
| `getStatusCdr` | Consulta estado de doc ya enviado | Cualquier tipo |

### Estructura SOAP `sendBill`

```xml
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                  xmlns:ser="http://service.sunat.gob.pe">
  <soapenv:Header>
    <wsse:Security xmlns:wsse="...">
      <wsse:UsernameToken>
        <wsse:Username>{RUC}{SOL_USER}</wsse:Username>
        <wsse:Password>{SOL_PASSWORD}</wsse:Password>
      </wsse:UsernameToken>
    </wsse:Security>
  </soapenv:Header>
  <soapenv:Body>
    <ser:sendBill>
      <fileName>{filename}.zip</fileName>
      <contentFile>{base64(zip_content)}</contentFile>
    </ser:sendBill>
  </soapenv:Body>
</soapenv:Envelope>
```

El `Username` es `{RUC}{sol_user}` (concatenados sin separador).
La respuesta contiene `applicationResponse` con el CDR en base64.

---

*Este documento es la fuente de verdad del proyecto. Actualizar cada vez que cambie un requerimiento o se tome una decisión de diseño.*
