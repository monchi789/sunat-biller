# Modelos del Facturador Electrónico

## 1. Company

```text
MODEL: Company

Fields:
    id                : UUID              PK
    ruc               : VARCHAR(11)       UNIQUE NOT NULL
    business_name     : VARCHAR(255)      NOT NULL
    commercial_name   : VARCHAR(255)      NULL
    address           : VARCHAR(500)      NOT NULL
    ubigeo            : VARCHAR(6)        NOT NULL
    department        : VARCHAR(100)      NULL
    province          : VARCHAR(100)      NULL
    district          : VARCHAR(100)      NULL
    country_code      : VARCHAR(2)        NOT NULL
    active            : BOOLEAN           NOT NULL

    sol_user                 : VARCHAR(50)       NULL
    sol_password_secret      : TEXT              NULL

    submission_mode           : VARCHAR(20)      NOT NULL DEFAULT 'SUNAT_DIRECT'  -- SUNAT_DIRECT | OSE
    ose_provider               : VARCHAR(50)      NULL
    ose_client_id               : VARCHAR(255)     NULL
    ose_client_secret_secret   : TEXT              NULL

    created_at        : TIMESTAMP         NOT NULL
    updated_at        : TIMESTAMP         NOT NULL

Relationships:
    Company 1 ──── N DocumentSeries
    Company 1 ──── N DigitalCertificate
    Company 1 ──── N APIKey
    Company 1 ──── N ElectronicDocument
    Company 1 ──── N DailySummary
    Company 1 ──── N VoidedDocument
```

## 2. APIKey

```text
MODEL: APIKey

Fields:
    id                : UUID              PK
    company_id        : UUID              FK → Company.id
    name              : VARCHAR(100)      NOT NULL
    key_hash          : VARCHAR(128)      UNIQUE NOT NULL
    active            : BOOLEAN           NOT NULL
    expires_at        : TIMESTAMP         NULL
    last_used_at      : TIMESTAMP         NULL
    created_at        : TIMESTAMP         NOT NULL

Relationships:
    APIKey N ──── 1 Company
```

## 3. DigitalCertificate

```text
MODEL: DigitalCertificate

Fields:
    id                : UUID              PK
    company_id        : UUID              FK → Company.id
    certificate_path  : VARCHAR(500)      NOT NULL
    password_secret   : TEXT              NOT NULL
    serial_number     : VARCHAR(255)      NULL
    valid_from        : TIMESTAMP         NULL
    valid_until       : TIMESTAMP         NULL
    active            : BOOLEAN           NOT NULL
    created_at        : TIMESTAMP         NOT NULL

Constraints:
    UNIQUE PARTIAL INDEX (company_id) WHERE active = true

Relationships:
    DigitalCertificate N ──── 1 Company
```

## 4. DocumentSeries

```text
MODEL: DocumentSeries

Fields:
    id                : UUID              PK
    company_id        : UUID              FK → Company.id
    document_type     : VARCHAR(2)        NOT NULL
    series            : VARCHAR(4)        NOT NULL
    current_number    : BIGINT            NOT NULL
    active            : BOOLEAN           NOT NULL
    created_at        : TIMESTAMP         NOT NULL
    updated_at        : TIMESTAMP         NOT NULL

Constraints:
    UNIQUE(company_id, document_type, series)

Relationships:
    DocumentSeries N ──── 1 Company
    DocumentSeries 1 ──── N ElectronicDocument
```

## 5. CompanySnapshot

```text
MODEL: CompanySnapshot

Fields:
    id                : UUID              PK
    ruc               : VARCHAR(11)       NOT NULL
    business_name     : VARCHAR(255)      NOT NULL
    commercial_name   : VARCHAR(255)      NULL
    address           : VARCHAR(500)      NULL
    ubigeo            : VARCHAR(6)        NULL
    country_code      : VARCHAR(2)        NOT NULL
    created_at        : TIMESTAMP         NOT NULL

Relationships:
    CompanySnapshot 1 ──── N ElectronicDocument
```

## 6. CustomerSnapshot

```text
MODEL: CustomerSnapshot

Fields:
    id                  : UUID            PK
    document_type       : VARCHAR(2)      NOT NULL
    document_number     : VARCHAR(20)     NOT NULL
    name                : VARCHAR(255)    NOT NULL
    address             : VARCHAR(500)    NULL
    ubigeo              : VARCHAR(6)      NULL
    country_code        : VARCHAR(2)      NOT NULL
    created_at          : TIMESTAMP       NOT NULL

Relationships:
    CustomerSnapshot 1 ──── N ElectronicDocument
```

## 7. ElectronicDocument

```text
MODEL: ElectronicDocument

Fields:
    id                    : UUID              PK

    company_id            : UUID              FK → Company.id
    series_id             : UUID              FK → DocumentSeries.id

    company_snapshot_id   : UUID              FK → CompanySnapshot.id
    customer_snapshot_id  : UUID              FK → CustomerSnapshot.id  NULL

    document_type         : VARCHAR(2)        NOT NULL
    series                : VARCHAR(4)        NOT NULL
    number                : BIGINT            NOT NULL

    issue_date            : DATE              NOT NULL
    issue_time            : TIME              NULL
    currency              : VARCHAR(3)        NOT NULL

    operation_type          : VARCHAR(4)        NOT NULL DEFAULT '0101'
    payment_terms            : VARCHAR(10)       NOT NULL DEFAULT 'Contado'

    subtotal              : DECIMAL(18,2)     NOT NULL
    discount_total        : DECIMAL(18,2)     NOT NULL

    taxable_total         : DECIMAL(18,2)     NOT NULL
    exempt_total          : DECIMAL(18,2)     NOT NULL
    unaffected_total      : DECIMAL(18,2)     NOT NULL
    export_total          : DECIMAL(18,2)     NOT NULL
    free_total              : DECIMAL(18,2)     NOT NULL

    igv_total             : DECIMAL(18,2)     NOT NULL
    isc_total             : DECIMAL(18,2)     NOT NULL
    icbper_total             : DECIMAL(18,2)     NOT NULL DEFAULT 0
    other_tax_total       : DECIMAL(18,2)     NOT NULL

    total                 : DECIMAL(18,2)     NOT NULL

    status                : VARCHAR(50)       NOT NULL

    sunat_status          : VARCHAR(50)       NULL
    sunat_code            : VARCHAR(20)       NULL
    sunat_description     : TEXT              NULL

    xml_hash              : VARCHAR(64)       NULL
    filename              : VARCHAR(255)      NULL

    sent_at               : TIMESTAMP         NULL
    accepted_at             : TIMESTAMP         NULL
    voided_at                : TIMESTAMP         NULL

    created_at            : TIMESTAMP         NOT NULL
    updated_at            : TIMESTAMP         NOT NULL

Constraints:
    UNIQUE(company_id, document_type, series, number)

Indexes:
    INDEX(company_id, status)
    INDEX(sunat_status)
    INDEX(company_id, issue_date)

Relationships:
    ElectronicDocument N ──── 1 Company
    ElectronicDocument N ──── 1 DocumentSeries
    ElectronicDocument N ──── 1 CompanySnapshot
    ElectronicDocument N ──── 0..1 CustomerSnapshot

    ElectronicDocument 1 ──── N DocumentItem
    ElectronicDocument 1 ──── N DocumentReference
    ElectronicDocument 1 ──── N SunatSubmission
    ElectronicDocument 1 ──── N DocumentFile
    ElectronicDocument 1 ──── N AuditLog
    ElectronicDocument 1 ──── N DocumentInstallment

    ElectronicDocument 1 ──── N DailySummaryItem
    ElectronicDocument 1 ──── N VoidedDocumentItem
    ElectronicDocument 1 ──── 0..1 IdempotencyKey
```

`customer_snapshot_id` es nullable únicamente para `document_type = RECEIPT` (boleta a público en general). Para `INVOICE`, `CREDIT_NOTE` y `DEBIT_NOTE` debe validarse como obligatorio a nivel de aplicación.

## 8. DocumentItem

```text
MODEL: DocumentItem

Fields:
    id                    : UUID              PK
    document_id           : UUID              FK → ElectronicDocument.id

    line_number           : INTEGER           NOT NULL
    product_code          : VARCHAR(100)      NULL
    description           : TEXT              NOT NULL

    quantity              : DECIMAL(18,6)     NOT NULL
    unit_code             : VARCHAR(3)        NOT NULL

    unit_value             : DECIMAL(18,6)     NOT NULL
    unit_price             : DECIMAL(18,6)     NOT NULL

    discount              : DECIMAL(18,2)     NOT NULL
    subtotal              : DECIMAL(18,2)     NOT NULL

    taxable_amount        : DECIMAL(18,2)     NOT NULL
    igv_amount            : DECIMAL(18,2)     NOT NULL
    isc_amount            : DECIMAL(18,2)     NOT NULL
    icbper_amount           : DECIMAL(18,2)     NOT NULL DEFAULT 0
    other_tax_amount      : DECIMAL(18,2)     NOT NULL

    total                 : DECIMAL(18,2)     NOT NULL

    tax_affectation       : VARCHAR(2)        NOT NULL
    price_type              : VARCHAR(2)        NOT NULL

    created_at             : TIMESTAMP         NOT NULL

Relationships:
    DocumentItem N ──── 1 ElectronicDocument
```

## 9. DocumentInstallment

```text
MODEL: DocumentInstallment

Fields:
    id                    : UUID              PK
    document_id           : UUID              FK → ElectronicDocument.id

    installment_number    : INTEGER           NOT NULL
    due_date               : DATE              NOT NULL
    amount                 : DECIMAL(18,2)     NOT NULL

    created_at             : TIMESTAMP         NOT NULL

Constraints:
    UNIQUE(document_id, installment_number)

Relationships:
    DocumentInstallment N ──── 1 ElectronicDocument
```

## 10. DocumentReference

```text
MODEL: DocumentReference

Fields:
    id                       : UUID             PK
    document_id              : UUID             FK → ElectronicDocument.id

    reference_document_type  : VARCHAR(2)       NOT NULL
    reference_series         : VARCHAR(4)       NOT NULL
    reference_number         : BIGINT            NOT NULL

    reason_code              : VARCHAR(10)      NOT NULL
    reason_description       : TEXT             NOT NULL

Relationships:
    DocumentReference N ──── 1 ElectronicDocument
```

## 11. SunatSubmission

```text
MODEL: SunatSubmission

Fields:
    id                    : UUID              PK
    document_id           : UUID              FK → ElectronicDocument.id

    filename              : VARCHAR(255)      NOT NULL
    environment           : VARCHAR(20)       NOT NULL
    submission_type       : VARCHAR(50)       NOT NULL

    ticket                : VARCHAR(100)      NULL

    status                : VARCHAR(50)       NOT NULL

    sunat_code            : VARCHAR(20)       NULL
    sunat_description     : TEXT              NULL

    sent_at               : TIMESTAMP         NULL
    responded_at          : TIMESTAMP         NULL

Relationships:
    SunatSubmission N ──── 1 ElectronicDocument
```

## 12. DocumentFile

```text
MODEL: DocumentFile

Fields:
    id                    : UUID              PK
    document_id           : UUID              FK → ElectronicDocument.id

    file_type             : VARCHAR(20)       NOT NULL
    storage_path          : VARCHAR(500)      NOT NULL
    filename              : VARCHAR(255)      NOT NULL
    mime_type              : VARCHAR(100)      NOT NULL
    file_size              : BIGINT            NOT NULL
    sha256                : VARCHAR(64)       NOT NULL

    created_at             : TIMESTAMP         NOT NULL

Relationships:
    DocumentFile N ──── 1 ElectronicDocument
```

## 13. DailySummary

```text
MODEL: DailySummary

Fields:
    id                    : UUID              PK
    company_id            : UUID              FK → Company.id

    reference_date        : DATE              NOT NULL
    identifier            : VARCHAR(50)       NOT NULL

    ticket                : VARCHAR(100)      NULL
    status                : VARCHAR(50)       NOT NULL
    sunat_code              : VARCHAR(20)       NULL
    sunat_description        : TEXT              NULL

    created_at             : TIMESTAMP         NOT NULL

Constraints:
    UNIQUE(company_id, identifier)

Relationships:
    DailySummary N ──── 1 Company
    DailySummary 1 ──── N DailySummaryItem
```

## 14. DailySummaryItem

```text
MODEL: DailySummaryItem

Fields:
    id                    : UUID              PK
    daily_summary_id      : UUID              FK → DailySummary.id
    document_id           : UUID              FK → ElectronicDocument.id

    item_status              : VARCHAR(2)        NOT NULL
    sunat_item_description    : TEXT              NULL

    created_at             : TIMESTAMP         NOT NULL

Constraints:
    UNIQUE(daily_summary_id, document_id)

Relationships:
    DailySummaryItem N ──── 1 DailySummary
    DailySummaryItem N ──── 1 ElectronicDocument
```

## 15. VoidedDocument

```text
MODEL: VoidedDocument

Fields:
    id                    : UUID              PK
    company_id            : UUID              FK → Company.id

    reference_date        : DATE              NOT NULL
    identifier            : VARCHAR(50)       NOT NULL

    ticket                : VARCHAR(100)      NULL
    status                : VARCHAR(50)       NOT NULL
    sunat_code              : VARCHAR(20)       NULL
    sunat_description        : TEXT              NULL

    created_at             : TIMESTAMP         NOT NULL

Constraints:
    UNIQUE(company_id, identifier)

Relationships:
    VoidedDocument N ──── 1 Company
    VoidedDocument 1 ──── N VoidedDocumentItem
```

## 16. VoidedDocumentItem

```text
MODEL: VoidedDocumentItem

Fields:
    id                    : UUID              PK
    voided_document_id    : UUID              FK → VoidedDocument.id
    document_id           : UUID              FK → ElectronicDocument.id

    reason                 : TEXT              NOT NULL

    created_at             : TIMESTAMP         NOT NULL

Constraints:
    UNIQUE(voided_document_id, document_id)

Relationships:
    VoidedDocumentItem N ──── 1 VoidedDocument
    VoidedDocumentItem N ──── 1 ElectronicDocument
```

## 17. IdempotencyKey

```text
MODEL: IdempotencyKey

Fields:
    id                    : UUID              PK

    company_id            : UUID              FK → Company.id
    document_id           : UUID              FK → ElectronicDocument.id  NULL

    key                   : VARCHAR(255)      NOT NULL

    response_status       : INTEGER           NOT NULL
    response_body         : TEXT              NOT NULL

    created_at             : TIMESTAMP         NOT NULL
    expires_at             : TIMESTAMP         NULL

Constraints:
    UNIQUE(company_id, key)

Relationships:
    IdempotencyKey N ──── 1 Company
    IdempotencyKey N ──── 0..1 ElectronicDocument
```

## 18. AuditLog

```text
MODEL: AuditLog

Fields:
    id                    : UUID              PK

    company_id             : UUID              FK → Company.id
    document_id           : UUID              FK → ElectronicDocument.id  NULL
    entity_type              : VARCHAR(50)       NULL
    entity_id                 : UUID              NULL

    action                : VARCHAR(100)      NOT NULL
    status                : VARCHAR(50)       NOT NULL
    message               : TEXT              NULL

    ip_address             : VARCHAR(45)       NULL
    user_agent             : VARCHAR(500)     NULL

    created_at             : TIMESTAMP         NOT NULL

Relationships:
    AuditLog N ──── 1 Company
    AuditLog N ──── 0..1 ElectronicDocument
```

---

# Relaciones

```text
Company
│
├── 1:N ── APIKey
├── 1:N ── DigitalCertificate
├── 1:N ── DocumentSeries
├── 1:N ── CompanySnapshot
├── 1:N ── ElectronicDocument
├── 1:N ── DailySummary
├── 1:N ── VoidedDocument
└── 1:N ── IdempotencyKey

DocumentSeries
└── 1:N ── ElectronicDocument

ElectronicDocument
│
├── N:1 ── Company
├── N:1 ── DocumentSeries
├── N:1 ── CompanySnapshot
├── N:0..1 ── CustomerSnapshot
│
├── 1:N ── DocumentItem
├── 1:N ── DocumentInstallment
├── 1:N ── DocumentReference
├── 1:N ── SunatSubmission
├── 1:N ── DocumentFile
├── 1:N ── AuditLog
├── 1:N ── DailySummaryItem
├── 1:N ── VoidedDocumentItem
└── 1:0..1 ── IdempotencyKey

DailySummary
└── 1:N ── DailySummaryItem ──── N:1 ── ElectronicDocument

VoidedDocument
└── 1:N ── VoidedDocumentItem ──── N:1 ── ElectronicDocument
```

# Jerarquía de ElectronicDocument

```text
ElectronicDocument
│
├── Header
│   ├── document_type
│   ├── series
│   ├── number
│   ├── issue_date
│   ├── issue_time
│   ├── currency
│   ├── operation_type
│   └── payment_terms
│
├── CompanySnapshot
│   ├── ruc
│   ├── business_name
│   ├── address
│   └── ubigeo
│
├── CustomerSnapshot (0..1)
│   ├── document_type
│   ├── document_number
│   ├── name
│   ├── address
│   └── ubigeo
│
├── DocumentItem[]
│   ├── product_code
│   ├── description
│   ├── quantity
│   ├── unit_code
│   ├── unit_value
│   ├── unit_price
│   ├── discount
│   ├── tax_affectation
│   ├── igv_amount
│   └── total
│
├── DocumentInstallment[]
│   ├── installment_number
│   ├── due_date
│   └── amount
│
├── Totals
│   ├── subtotal
│   ├── discount_total
│   ├── taxable_total
│   ├── exempt_total
│   ├── unaffected_total
│   ├── free_total
│   ├── igv_total
│   ├── isc_total
│   ├── icbper_total
│   └── total
│
├── DocumentReference[]
├── SunatSubmission[]
├── DocumentFile[]
└── AuditLog[]
```
