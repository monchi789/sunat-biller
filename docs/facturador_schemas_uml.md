# Schemas Pydantic — Facturador Electrónico (con validaciones)

Notación: `Field(...)` muestra las restricciones tal como se aplicarían
en Pydantic (`min_length`, `max_length`, `pattern`, `ge`/`le`/`gt`/`lt`,
`max_digits`/`decimal_places`). Las reglas que dependen de más de un
campo (no se pueden expresar en un solo `Field`) están al final de cada
schema, o en la sección "Validaciones cruzadas" al final del archivo.

## Jerarquía de herencia

```text
DocumentCreateBase                       DocumentResponseBase
        │                                         │
        ├── InvoiceCreate                         ├── DocumentResponse
        ├── ReceiptCreate                          ├── InvoiceResponse
        ├── CreditNoteCreate*                       ├── ReceiptResponse
        └── DebitNoteCreate*                         ├── CreditNoteResponse*
                                                       └── DebitNoteResponse*

CompanyBase
        │
        ├── CompanyCreate
        └── CompanyResponse
  (CompanyUpdate queda fuera de esta jerarquía: todos los campos opcionales)
```

---

## 1. common.py

Los enums no requieren `Field()` adicional — el propio enum ya
restringe los valores posibles a nivel de Pydantic. Los que están
ligados a un catálogo oficial de SUNAT lo indican explícitamente; si
mañana falta un valor, se agrega ahí, nunca como `string` libre.

### DocumentType

Catálogo 01 SUNAT (Tipo de Documento) — solo los tipos que emite este sistema.

```text
SCHEMA: DocumentType

Type:
    Enum

Values:
    INVOICE        : "01"   -- Factura
    RECEIPT        : "03"   -- Boleta de venta
    CREDIT_NOTE    : "07"   -- Nota de crédito
    DEBIT_NOTE     : "08"   -- Nota de débito
```

### CurrencyCode

ISO 4217.

```text
SCHEMA: CurrencyCode

Type:
    Enum

Values:
    PEN   -- Sol peruano
    USD   -- Dólar americano
    EUR   -- Euro
```

### UnitCode

Catálogo 03 SUNAT (UN/ECE Rec. 20) — subset de las más usadas; agregar más según el rubro del negocio.

```text
SCHEMA: UnitCode

Type:
    Enum

Values:
    NIU   -- Unidad (Bienes)
    KGM   -- Kilogramo
    GRM   -- Gramo
    LTR   -- Litro
    MLT   -- Mililitro
    MTR   -- Metro
    MTK   -- Metro cuadrado
    MTQ   -- Metro cúbico
    C62   -- Unidad (Servicios)
    BX    -- Caja
    PK    -- Paquete
    DZN   -- Docena
    SET   -- Conjunto/Set
    KT    -- Kit
    PR    -- Par
    ZZ    -- Unidad no incluida en el catálogo
```

### IdentityDocumentType

Catálogo 06 SUNAT (Tipo de Documento de Identidad) — completo.

```text
SCHEMA: IdentityDocumentType

Type:
    Enum

Values:
    OTHER              : "0"   -- Doc. trib. no domiciliado, sin RUC
    DNI                : "1"   -- Documento Nacional de Identidad
    FOREIGNER_ID       : "4"   -- Carnet de extranjería
    RUC                : "6"   -- Registro Único de Contribuyentes
    PASSPORT           : "7"   -- Pasaporte
    DIPLOMATIC_ID       : "A"   -- Cédula diplomática de identidad
    RESIDENCE_COUNTRY_ID : "B"   -- Doc. de identidad del país de residencia (no domiciliado)
    ANDEAN_MIGRATION_CARD : "C"   -- TAM - Tarjeta Andina de Migración
```
En la práctica, para `InvoiceCreate` normalmente solo aplica `RUC`, y
para `ReceiptCreate` lo más común es `DNI`, `RUC`, `FOREIGNER_ID` o
`PASSPORT` — los demás son casos borde (diplomáticos, turistas con TAM).

### DocumentStatus

Estado interno del ciclo de vida del comprobante (no es un catálogo SUNAT, es del sistema).

```text
SCHEMA: DocumentStatus

Type:
    Enum

Values:
    DRAFT                        -- creado, aún no procesado
    PENDING                      -- en cola para generar XML/firmar
    PROCESSING                    -- generando XML / firmando
    SIGNED                        -- XML firmado, listo para enviar
    SENT                          -- enviado a SUNAT, esperando respuesta
    ACCEPTED                      -- aceptado por SUNAT
    ACCEPTED_WITH_OBSERVATION      -- aceptado con observaciones
    REJECTED                      -- rechazado por SUNAT
    ERROR                          -- error técnico en el proceso
    CANCELLED                      -- cancelado antes de enviar
    VOIDED                          -- dado de baja (comunicación de baja aceptada)
```

### SunatStatus

Estado específico de la respuesta de SUNAT (independiente del `DocumentStatus` general).

```text
SCHEMA: SunatStatus

Type:
    Enum

Values:
    PENDING
    SENT
    ACCEPTED
    ACCEPTED_WITH_OBSERVATION
    REJECTED
    ERROR
```

### SunatEnvironment

```text
SCHEMA: SunatEnvironment

Type:
    Enum

Values:
    BETA         -- ambiente de homologación/pruebas SUNAT
    PRODUCTION   -- ambiente productivo
```

### TaxAffectationType

Catálogo 07 SUNAT — completo (Tipo de Afectación del IGV).

```text
SCHEMA: TaxAffectationType

Type:
    Enum

Values:
    TAXED_ONEROUS               : "10"   -- Gravado - Operación Onerosa
    TAXED_WITHDRAWAL_PRIZE       : "11"   -- Gravado - Retiro por premio
    TAXED_WITHDRAWAL_DONATION     : "12"   -- Gravado - Retiro por donación
    TAXED_WITHDRAWAL_BONUS         : "13"   -- Gravado - Retiro por bonificación
    TAXED_WITHDRAWAL                 : "14"   -- Gravado - Retiro
    TAXED_WITHDRAWAL_ADS               : "15"   -- Gravado - Retiro por publicidad
    TAXED_BONUS                          : "16"   -- Gravado - Bonificaciones
    TAXED_WITHDRAWAL_EMPLOYEE              : "17"   -- Gravado - Retiro por entrega a trabajadores
    EXONERATED_ONEROUS                       : "20"   -- Exonerado - Operación Onerosa
    EXONERATED_FREE                            : "21"   -- Exonerado - Transferencia gratuita
    UNAFFECTED_ONEROUS                           : "30"   -- Inafecto - Operación Onerosa
    UNAFFECTED_WITHDRAWAL_BONUS                    : "31"   -- Inafecto - Retiro por Bonificación
    UNAFFECTED_WITHDRAWAL                            : "32"   -- Inafecto - Retiro
    UNAFFECTED_SAMPLES                                 : "33"   -- Inafecto - Retiro por Muestras Médicas
    UNAFFECTED_COLLECTIVE_AGR                            : "34"   -- Inafecto - Retiro por Convenio Colectivo
    UNAFFECTED_PRIZE                                       : "35"   -- Inafecto - Retiro por premio
    UNAFFECTED_ADS                                           : "36"   -- Inafecto - Retiro por publicidad
    EXPORT                                                     : "40"   -- Exportación
```
En un MVP, los valores realmente frecuentes son `10` (venta gravada
normal), `20`/`21` (exonerado), `30` (inafecto) y `40` (exportación) —
el resto son casos de retiro de bienes poco comunes, pero conviene
tenerlos tipados para no rechazar el XML si aparecen.

### PriceType

Catálogo 16 SUNAT — completo (solo tiene 2 valores).

```text
SCHEMA: PriceType

Type:
    Enum

Values:
    UNIT_PRICE_WITH_TAX      : "01"   -- Precio unitario (incluye IGV)
    REFERENCE_VALUE_NO_TAX   : "02"   -- Valor referencial (operación no onerosa: retiros, bonificaciones)
```

### OperationType

Catálogo 51 SUNAT — subset ampliado con los casos más comunes (agregar más según lo que factures).

```text
SCHEMA: OperationType

Type:
    Enum

Values:
    DOMESTIC_SALE                     : "0101"   -- Venta interna
    DOMESTIC_SALE_ADVANCE               : "0102"   -- Venta interna - Anticipos
    DOMESTIC_SALE_ADVANCE_PERCEP          : "0103"   -- Venta interna - Anticipo valorizado, con percepción
    DOMESTIC_GOODS_TRANSFER_NO_AMOUNT       : "0112"   -- Sustenta traslado de bienes (sin monto)
    DOMESTIC_SALE_ITINERANT                   : "0113"   -- Venta interna itinerante
    EXPORT_GOODS                                : "0200"   -- Exportación de bienes
    EXPORT_SERVICES                               : "0201"   -- Exportación de servicios
    DETRACTION                                      : "1001"   -- Operación sujeta a detracción
    DETRACTION_HIDROBIOLOGICO                         : "1002"   -- Detracción - recursos hidrobiológicos
    DETRACTION_TRANSPORT_GOODS                          : "1003"   -- Detracción - transporte de bienes vía terrestre
    DETRACTION_TRANSPORT_PASSENGERS                       : "1004"   -- Detracción - transporte público de pasajeros
    PERCEPTION                                              : "2001"   -- Operación sujeta a percepción
```

### CreditNoteReasonType

Catálogo 09 SUNAT (Tipo de Nota de Crédito) — usar en `reason_code` cuando `DocumentReferenceCreate` se llena dentro de un `CreditNoteCreate`.

```text
SCHEMA: CreditNoteReasonType

Type:
    Enum

Values:
    OPERATION_CANCELLATION       : "01"   -- Anulación de la operación
    RUC_ERROR                      : "02"   -- Anulación por error en el RUC
    DESCRIPTION_ERROR                : "03"   -- Corrección por error en la descripción
    GLOBAL_DISCOUNT                    : "04"   -- Descuento global
    ITEM_DISCOUNT                        : "05"   -- Descuento por ítem
    TOTAL_RETURN                           : "06"   -- Devolución total
    ITEM_RETURN                              : "07"   -- Devolución por ítem
    BONUS                                      : "08"   -- Bonificación
    VALUE_DECREASE                               : "09"   -- Disminución en el valor
    OTHERS                                         : "10"   -- Otros conceptos
    EXPORT_ADJUSTMENT                                : "11"   -- Ajustes de operaciones de exportación
    IVAP_ADJUSTMENT                                    : "12"   -- Ajustes afectos al IVAP
```

### DebitNoteReasonType

Catálogo 10 SUNAT (Tipo de Nota de Débito) — usar en `reason_code` cuando `DocumentReferenceCreate` se llena dentro de un `DebitNoteCreate`.

```text
SCHEMA: DebitNoteReasonType

Type:
    Enum

Values:
    LATE_INTEREST          : "01"   -- Intereses por mora
    VALUE_INCREASE            : "02"   -- Aumento en el valor
    PENALTY                     : "03"   -- Penalidades u otros conceptos
    EXPORT_ADJUSTMENT              : "10"   -- Ajustes de operaciones de exportación
    IVAP_ADJUSTMENT                  : "11"   -- Ajustes afectos al IVAP
    OTHERS                             : "12"   -- Otros conceptos
```

### FileType

```text
SCHEMA: FileType

Type:
    Enum

Values:
    XML
    PDF
    CDR
```

### DailySummaryItemStatus

Estado del ítem dentro de un Resumen Diario (RC) o Comunicación de Baja (RA).

```text
SCHEMA: DailySummaryItemStatus

Type:
    Enum

Values:
    ADD        : "1"   -- Agrega el comprobante al resumen
    MODIFY     : "2"   -- Modifica un comprobante ya enviado
    VOID       : "3"   -- Da de baja el comprobante dentro del resumen
```

### PaymentTerms

```text
SCHEMA: PaymentTerms

Type:
    Enum

Values:
    CASH      : "Contado"
    CREDIT    : "Credito"
```

### SubmissionType

```text
SCHEMA: SubmissionType

Type:
    Enum

Values:
    SEND_BILL         -- envío individual (factura/nota)
    SEND_SUMMARY      -- resumen diario de boletas
    SEND_VOIDED       -- comunicación de baja
    GET_STATUS        -- consulta de ticket
    GET_STATUS_CDR    -- consulta de CDR
```

### ErrorResponse

```text
SCHEMA: ErrorResponse

Fields:
    error_code    : string = Field(min_length=1, max_length=50)
    message       : string = Field(min_length=1, max_length=500)
    details       : dict | None
```

### PaginatedResponse

```text
SCHEMA: PaginatedResponse[T]

Fields:
    items         : list[T]
    total         : int   = Field(ge=0)
    page          : int   = Field(ge=1)
    page_size     : int   = Field(ge=1, le=100)
```

---

## 2. company.py

### CompanyBase

```text
SCHEMA: CompanyBase

Fields:
    business_name     : string      = Field(min_length=1, max_length=255)
    commercial_name   : string | None = Field(default=None, max_length=255)
    address           : string      = Field(min_length=1, max_length=500)
    ubigeo            : string      = Field(pattern=r"^\d{6}$")
    department        : string | None = Field(default=None, max_length=100)
    province          : string | None = Field(default=None, max_length=100)
    district          : string | None = Field(default=None, max_length=100)
    country_code      : string      = Field(pattern=r"^[A-Z]{2}$")   -- ISO 3166-1 alpha-2
```

### CompanyCreate

```text
SCHEMA: CompanyCreate(CompanyBase)

Fields:
    ruc               : string = Field(pattern=r"^\d{11}$")
```
Validación adicional (no expresable en `Field`): el dígito verificador
del RUC debe ser válido según el algoritmo módulo 11 de SUNAT — usar un
`field_validator` dedicado, no solo `pattern`.

### CompanyUpdate

```text
SCHEMA: CompanyUpdate

Fields:
    business_name     : string | None = Field(default=None, min_length=1, max_length=255)
    commercial_name   : string | None = Field(default=None, max_length=255)
    address           : string | None = Field(default=None, min_length=1, max_length=500)
    ubigeo            : string | None = Field(default=None, pattern=r"^\d{6}$")
    department        : string | None = Field(default=None, max_length=100)
    province          : string | None = Field(default=None, max_length=100)
    district          : string | None = Field(default=None, max_length=100)
    country_code      : string | None = Field(default=None, pattern=r"^[A-Z]{2}$")
    active            : bool | None
```

### CompanyResponse

```text
SCHEMA: CompanyResponse(CompanyBase)

Fields:
    id                : UUID
    ruc               : string = Field(pattern=r"^\d{11}$")
    active             : bool
    created_at         : datetime
    updated_at         : datetime
```

### CompanySunatCredentialsUpdate

```text
SCHEMA: CompanySunatCredentialsUpdate

Fields:
    sol_user          : string = Field(min_length=1, max_length=50)
    sol_password      : string = Field(min_length=8, max_length=100)
```

---

## 3. api_key.py

### APIKeyCreate

```text
SCHEMA: APIKeyCreate

Fields:
    name              : string       = Field(min_length=1, max_length=100)
    expires_at        : datetime | None
```
Validador: si `expires_at` viene informado, debe ser una fecha futura
(`expires_at > now()`).

### APIKeyResponse

```text
SCHEMA: APIKeyResponse

Fields:
    id                : UUID
    name              : string       = Field(max_length=100)
    active            : bool
    expires_at        : datetime | None
    last_used_at      : datetime | None
    created_at        : datetime
```

### APIKeyCreatedResponse

```text
SCHEMA: APIKeyCreatedResponse

Fields:
    key               : string   -- generado por el sistema, sin Field adicional
```

---

## 4. certificate.py

### CertificateCreate

```text
SCHEMA: CertificateCreate

Fields (multipart/form-data):
    file               : UploadFile   -- validar extensión (.pfx / .p12) y content-type;
                                       -- tamaño máximo recomendado: 5 MB
    password           : string       = Field(min_length=1, max_length=255)
```

### CertificateResponse

```text
SCHEMA: CertificateResponse

Fields:
    id                : UUID
    serial_number     : string | None = Field(default=None, max_length=255)
    valid_from        : datetime | None
    valid_until       : datetime | None
    active            : bool
    created_at        : datetime
```

---

## 5. series.py

### DocumentSeriesCreate

```text
SCHEMA: DocumentSeriesCreate

Fields:
    document_type     : DocumentType
    series            : string = Field(pattern=r"^[A-Z]\d{3}$")   -- ej. "F001", "B001"
    current_number    : int    = Field(ge=0, le=99_999_999)        -- máx. 8 dígitos SUNAT
```

### DocumentSeriesUpdate

```text
SCHEMA: DocumentSeriesUpdate

Fields:
    active            : bool | None
```

### DocumentSeriesResponse

```text
SCHEMA: DocumentSeriesResponse

Fields:
    id                : UUID
    company_id        : UUID
    document_type     : DocumentType
    series            : string = Field(pattern=r"^[A-Z]\d{3}$")
    current_number    : int    = Field(ge=0, le=99_999_999)
    active            : bool
```

---

## 6. customer.py

### CustomerCreate

```text
SCHEMA: CustomerCreate

Fields:
    document_type     : IdentityDocumentType
    document_number   : string = Field(min_length=1, max_length=15)
    name              : string = Field(min_length=1, max_length=255)
    address           : string | None = Field(default=None, max_length=500)
    ubigeo            : string | None = Field(default=None, pattern=r"^\d{6}$")
    country_code      : string = Field(pattern=r"^[A-Z]{2}$")
```
Validador cruzado (`document_type` ↔ `document_number`, no expresable
en un solo `Field`):
- `DNI` → exactamente 8 dígitos numéricos
- `RUC` → exactamente 11 dígitos numéricos
- `FOREIGNER_ID` / `PASSPORT` / `OTHER` → de 1 a 15 caracteres alfanuméricos

---

## 7. document_item.py

### DocumentItemCreate

```text
SCHEMA: DocumentItemCreate

Fields:
    line_number       : int     = Field(ge=1)
    product_code      : string | None = Field(default=None, max_length=100)
    description       : string  = Field(min_length=1, max_length=500)

    quantity          : Decimal = Field(gt=0, max_digits=18, decimal_places=6)
    unit_code         : UnitCode

    unit_value        : Decimal = Field(ge=0, max_digits=18, decimal_places=6)
    unit_price        : Decimal = Field(ge=0, max_digits=18, decimal_places=6)

    discount          : Decimal = Field(ge=0, max_digits=18, decimal_places=2)
    subtotal          : Decimal = Field(max_digits=18, decimal_places=2)

    taxable_amount    : Decimal = Field(ge=0, max_digits=18, decimal_places=2)
    igv_amount        : Decimal = Field(ge=0, max_digits=18, decimal_places=2)
    isc_amount        : Decimal = Field(ge=0, max_digits=18, decimal_places=2)
    icbper_amount       : Decimal = Field(ge=0, max_digits=18, decimal_places=2, default=0)
    other_tax_amount  : Decimal = Field(ge=0, max_digits=18, decimal_places=2)

    total             : Decimal = Field(max_digits=18, decimal_places=2)

    tax_affectation   : TaxAffectationType
    price_type          : PriceType
```
Validador cruzado: `total == subtotal - discount + igv_amount +
isc_amount + icbper_amount + other_tax_amount` (con tolerancia de
redondeo de 0.01). Recalcularlo en el backend en vez de confiar
ciegamente en lo que manda el cliente.

### InstallmentCreate

```text
SCHEMA: InstallmentCreate

Fields:
    installment_number : int     = Field(ge=1)
    due_date            : date
    amount               : Decimal = Field(gt=0, max_digits=18, decimal_places=2)
```
Validador cruzado (a nivel de `DocumentCreateBase`): `due_date` de cada
cuota debe ser `>= issue_date`, y `sum(amount)` de todas las cuotas debe
igualar el `total` del documento.

---

## 8. document_reference.py

### DocumentReferenceCreate

```text
SCHEMA: DocumentReferenceCreate

Fields:
    reference_document_type : DocumentType
    reference_series        : string = Field(pattern=r"^[A-Z]\d{3}$")
    reference_number        : int    = Field(ge=1, le=99_999_999)
    reason_code              : CreditNoteReasonType | DebitNoteReasonType
    reason_description        : string = Field(min_length=1, max_length=500)
```
`reason_code` se tipa como `CreditNoteReasonType` cuando el schema se
usa dentro de `CreditNoteCreate`, y como `DebitNoteReasonType` cuando se
usa dentro de `DebitNoteCreate` — en la práctica esto se resuelve mejor
con dos schemas concretos (`CreditNoteReferenceCreate` /
`DebitNoteReferenceCreate`) en vez de una unión, para que Pydantic
valide el catálogo correcto según el endpoint sin ambigüedad.

Validador cruzado: `reference_document_type` solo puede ser `INVOICE` o
`RECEIPT` — una nota no puede referenciar a otra nota.

---

## 9. document.py

### DocumentCreateBase

```text
SCHEMA: DocumentCreateBase

Fields:
    issue_date         : date
    issue_time          : time | None
    currency            : CurrencyCode
    operation_type       : OperationType   = OperationType.DOMESTIC_SALE
    payment_terms         : PaymentTerms     = PaymentTerms.CASH
    installments           : list[InstallmentCreate] | None = Field(default=None, max_length=36)
    customer               : CustomerCreate | None
    items                   : list[DocumentItemCreate] = Field(min_length=1, max_length=500)
```
Validadores cruzados:
- `issue_date` no puede ser posterior a hoy, ni anterior a hoy en más de
  los días que SUNAT permita para emisión extemporánea (verificar plazo
  vigente; usualmente unos pocos días).
- Si `payment_terms == CREDIT` → `installments` es obligatorio y no
  vacío; si `payment_terms == CASH` → `installments` debe venir vacío o
  nulo.
- `sum(item.total for item in items)` debe ser consistente con los
  totales calculados a nivel de documento (recalculado en backend, no
  confiado del cliente).

### DocumentResponseBase

```text
SCHEMA: DocumentResponseBase

Fields:
    id                    : UUID

    document_type         : DocumentType
    series                : string = Field(pattern=r"^[A-Z]\d{3}$")
    number                : int    = Field(ge=1, le=99_999_999)

    issue_date            : date
    issue_time            : time | None
    currency              : CurrencyCode
    operation_type          : OperationType
    payment_terms            : PaymentTerms
    installments              : list[InstallmentCreate]

    customer               : CustomerCreate | None
    items                   : list[DocumentItemCreate]

    subtotal              : Decimal = Field(max_digits=18, decimal_places=2)
    discount_total        : Decimal = Field(ge=0, max_digits=18, decimal_places=2)

    taxable_total         : Decimal = Field(ge=0, max_digits=18, decimal_places=2)
    exempt_total          : Decimal = Field(ge=0, max_digits=18, decimal_places=2)
    unaffected_total      : Decimal = Field(ge=0, max_digits=18, decimal_places=2)
    export_total          : Decimal = Field(ge=0, max_digits=18, decimal_places=2)
    free_total              : Decimal = Field(ge=0, max_digits=18, decimal_places=2)

    igv_total             : Decimal = Field(ge=0, max_digits=18, decimal_places=2)
    isc_total             : Decimal = Field(ge=0, max_digits=18, decimal_places=2)
    icbper_total             : Decimal = Field(ge=0, max_digits=18, decimal_places=2)
    other_tax_total       : Decimal = Field(ge=0, max_digits=18, decimal_places=2)

    total                 : Decimal = Field(gt=0, max_digits=18, decimal_places=2)

    status                : DocumentStatus

    sunat_status          : SunatStatus | None
    sunat_code            : string | None = Field(default=None, max_length=20)
    sunat_description     : string | None = Field(default=None, max_length=1000)

    xml_hash              : string | None = Field(default=None, pattern=r"^[A-Za-z0-9+/=]{20,}$")
    filename                : string | None = Field(default=None, max_length=255)

    sent_at                 : datetime | None
    accepted_at              : datetime | None
    voided_at                 : datetime | None

    created_at            : datetime
    updated_at            : datetime
```

### DocumentResponse

```text
SCHEMA: DocumentResponse(DocumentResponseBase)
    -- sin campos adicionales; usado en GET /documents y GET /documents/{id}
```

---

## 10. invoice.py

### InvoiceCreate

```text
SCHEMA: InvoiceCreate(DocumentCreateBase)

Fields:
    customer : CustomerCreate   -- obligatorio (sobrescribe la base)
```
Validador cruzado: `customer.document_type` debe ser `RUC` (una factura
no se emite a DNI en el caso general — solo RUC de persona natural o
jurídica con negocio).

### InvoiceResponse

```text
SCHEMA: InvoiceResponse(DocumentResponseBase)
    -- sin campos adicionales
```

---

## 11. receipt.py

### ReceiptCreate

```text
SCHEMA: ReceiptCreate(DocumentCreateBase)
    -- customer se mantiene opcional (heredado)
```
Validador cruzado: si el `total` calculado supera el umbral SUNAT
vigente para identificación obligatoria del cliente en boletas, `customer`
pasa a ser requerido (verificar el monto vigente, cambia por norma).

### ReceiptResponse

```text
SCHEMA: ReceiptResponse(DocumentResponseBase)
    -- sin campos adicionales
```

---

## 12. credit_note.py

### CreditNoteCreate

```text
SCHEMA: CreditNoteCreate(DocumentCreateBase)

Fields:
    customer  : CustomerCreate
    reference : DocumentReferenceCreate
```
Validador cruzado: `reason_code` de `reference` debe pertenecer al
catálogo 09 SUNAT (motivos de nota de crédito: anulación, devolución,
descuento, etc.).

### CreditNoteResponse

```text
SCHEMA: CreditNoteResponse(DocumentResponseBase)

Fields:
    reference : DocumentReferenceCreate
```

---

## 13. debit_note.py

### DebitNoteCreate

```text
SCHEMA: DebitNoteCreate(DocumentCreateBase)

Fields:
    customer  : CustomerCreate
    reference : DocumentReferenceCreate
```
Validador cruzado: `reason_code` de `reference` debe pertenecer al
catálogo 10 SUNAT (motivos de nota de débito: interés, mora, aumento de
valor, etc.).

### DebitNoteResponse

```text
SCHEMA: DebitNoteResponse(DocumentResponseBase)

Fields:
    reference : DocumentReferenceCreate
```

---

## 14. sunat.py

### SunatSubmissionResponse

```text
SCHEMA: SunatSubmissionResponse

Fields:
    id                    : UUID
    filename              : string = Field(max_length=255)
    environment           : SunatEnvironment
    submission_type       : SubmissionType
    ticket                : string | None = Field(default=None, max_length=100)
    status                : SunatStatus
    sunat_code            : string | None = Field(default=None, max_length=20)
    sunat_description     : string | None = Field(default=None, max_length=1000)
    sent_at               : datetime | None
    responded_at          : datetime | None
```

---

## 15. document_file.py

### DocumentFileResponse

```text
SCHEMA: DocumentFileResponse

Fields:
    id                    : UUID
    document_id           : UUID
    file_type              : FileType
    filename               : string = Field(max_length=255)
    mime_type                : string = Field(max_length=100)
    file_size                : int    = Field(gt=0, le=20_000_000)   -- 20 MB tope razonable
    sha256                    : string = Field(pattern=r"^[a-f0-9]{64}$")
    created_at                : datetime
```

---

## 16. daily_summary.py

### DailySummaryCreate

```text
SCHEMA: DailySummaryCreate

Fields:
    reference_date        : date
    document_ids            : list[UUID] = Field(min_length=1, max_length=500)
```
Validador cruzado: todos los `document_ids` deben ser boletas
(`document_type = RECEIPT`) emitidas en `reference_date` y pertenecer a
la misma empresa autenticada; no debe haber duplicados en la lista.

### DailySummaryItemResponse

```text
SCHEMA: DailySummaryItemResponse

Fields:
    document_id              : UUID
    item_status                : DailySummaryItemStatus
    sunat_item_description       : string | None = Field(default=None, max_length=500)
```

### DailySummaryResponse

```text
SCHEMA: DailySummaryResponse

Fields:
    id                    : UUID
    reference_date        : date
    identifier            : string = Field(max_length=50)
    ticket                : string | None = Field(default=None, max_length=100)
    status                : string = Field(max_length=50)
    sunat_code               : string | None = Field(default=None, max_length=20)
    sunat_description         : string | None = Field(default=None, max_length=1000)
    items                      : list[DailySummaryItemResponse]
    created_at              : datetime
```

---

## 17. voided_document.py

### VoidedDocumentItemCreate

```text
SCHEMA: VoidedDocumentItemCreate

Fields:
    document_id   : UUID
    reason         : string = Field(min_length=1, max_length=500)
```

### VoidedDocumentCreate

```text
SCHEMA: VoidedDocumentCreate

Fields:
    reference_date        : date
    items                    : list[VoidedDocumentItemCreate] = Field(min_length=1, max_length=500)
```
Validador cruzado: `document_id` no debe repetirse dentro de `items`, y
cada documento referenciado debe estar en un estado que permita ser dado
de baja (`ACCEPTED` o `ACCEPTED_WITH_OBSERVATION`, no ya `VOIDED`).

### VoidedDocumentItemResponse

```text
SCHEMA: VoidedDocumentItemResponse

Fields:
    document_id   : UUID
    reason         : string = Field(max_length=500)
```

### VoidedDocumentResponse

```text
SCHEMA: VoidedDocumentResponse

Fields:
    id                    : UUID
    reference_date        : date
    identifier            : string = Field(max_length=50)
    ticket                : string | None = Field(default=None, max_length=100)
    status                : string = Field(max_length=50)
    sunat_code               : string | None = Field(default=None, max_length=20)
    sunat_description         : string | None = Field(default=None, max_length=1000)
    items                      : list[VoidedDocumentItemResponse]
    created_at              : datetime
```

---

## 18. idempotency.py

### IdempotencyResponse

```text
SCHEMA: IdempotencyResponse

Fields:
    id                    : UUID
    key                   : string = Field(min_length=1, max_length=255)
    document_id           : UUID | None
    response_status       : int    = Field(ge=100, le=599)
    created_at             : datetime
    expires_at             : datetime | None
```

---

## 19. audit.py

### AuditLogResponse

```text
SCHEMA: AuditLogResponse

Fields:
    id                    : UUID
    company_id              : UUID
    document_id           : UUID | None
    entity_type               : string | None = Field(default=None, max_length=50)
    entity_id                  : UUID | None
    action                : string = Field(min_length=1, max_length=100)
    status                : string = Field(max_length=50)
    message               : string | None = Field(default=None, max_length=2000)
    ip_address             : string | None = Field(default=None, max_length=45)  -- IPv4 o IPv6
    user_agent             : string | None = Field(default=None, max_length=500)
    created_at             : datetime
```

---

# Validaciones cruzadas (resumen)

Estas reglas no se pueden expresar con un solo `Field()` porque
dependen de más de un campo, y deben implementarse como
`@model_validator` en Pydantic:

| Schema | Regla |
|---|---|
| `CompanyCreate` | Dígito verificador del RUC válido (módulo 11 SUNAT) |
| `CustomerCreate` | Largo de `document_number` según `document_type` (DNI=8, RUC=11) |
| `DocumentItemCreate` | `total == subtotal - discount + igv_amount + isc_amount + icbper_amount + other_tax_amount` (±0.01) |
| `InstallmentCreate` (lista, en `DocumentCreateBase`) | `due_date >= issue_date`; `sum(amount) == total` del documento |
| `DocumentCreateBase` | Si `payment_terms == CREDIT` → `installments` obligatorio y no vacío; si `CASH` → vacío/nulo |
| `DocumentCreateBase` | `issue_date` dentro del rango permitido por SUNAT (no futura, no muy antigua) |
| `InvoiceCreate` | `customer.document_type == RUC` |
| `ReceiptCreate` | `customer` requerido si `total` supera el umbral SUNAT vigente |
| `CreditNoteCreate` / `DebitNoteCreate` | `reference.reference_document_type` solo puede ser `INVOICE` o `RECEIPT`; `reason_code` dentro del catálogo correspondiente (09 / 10) |
| `DailySummaryCreate` | Todos los `document_ids` son boletas de `reference_date`, misma empresa, sin duplicados |
| `VoidedDocumentCreate` | Sin `document_id` duplicados; documentos en estado válido para baja |
