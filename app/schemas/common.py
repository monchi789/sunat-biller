from enum import Enum
from typing import ClassVar

from pydantic import BaseModel, Field
from pydantic.config import ConfigDict


class BaseSchema(BaseModel):
    """
    ConfigDict for the BaseSchema.
    """
    model_config: ClassVar[ConfigDict] = ConfigDict(
        from_attributes=True,
    )


class DocumentType(str, Enum):
    """
    Document types supported by SUNAT.
    """
    INVOICE = "01"
    RECEIPT = "03"
    CREDIT_NOTE = "07"
    DEBIT_NOTE = "08"


class CurrencyCode(str, Enum):
    """
    Currency codes supported by SUNAT.
    """
    PEN = "PEN"
    USD = "USD"
    EUR = "EUR"


class UnitCode(str, Enum):
    """
    Unit codes supported by SUNAT.
    """
    NIU = "NIU"
    KGM = "KGM"
    GRM = "GRM"
    LTR = "LTR"
    MLT = "MLT"
    MTR = "MTR"
    MTK = "MTK"
    MTQ = "MTQ"
    C62 = "C62"
    BX = "BX"
    PK = "PK"
    DZN = "DZN"
    SET = "SET"
    KT = "KT"
    PR = "PR"
    ZZ = "ZZ"


class IdentityDocumentType(str, Enum):
    """
    Identity document types supported by SUNAT.
    """
    OTHER = "0"
    DNI = "1"
    FOREIGNER_ID = "4"
    RUC = "6"
    PASSPORT = "7"
    DIPLOMATIC_ID = "A"
    RESIDENCE_COUNTRY_ID = "B"
    ANDEAN_MIGRATION_CARD = "C"


class DocumentStatus(str, Enum):
    """
    Document statuses supported by SUNAT.
    """
    DRAFT = "DRAFT"
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    SIGNED = "SIGNED"
    SENT = "SENT"
    ACCEPTED = "ACCEPTED"
    ACCEPTED_WITH_OBSERVATION = "ACCEPTED_WITH_OBSERVATION"
    REJECTED = "REJECTED"
    ERROR = "ERROR"
    CANCELLED = "CANCELLED"
    VOIDED = "VOIDED"


class SunatStatus(str, Enum):
    """
    SUNAT statuses supported by the application.
    """
    PENDING = "PENDING"
    SENT = "SENT"
    ACCEPTED = "ACCEPTED"
    ACCEPTED_WITH_OBSERVATION = "ACCEPTED_WITH_OBSERVATION"
    REJECTED = "REJECTED"
    ERROR = "ERROR"


class SunatEnvironment(str, Enum):
    """
    SUNAT environments supported by the application.
    """
    BETA = "BETA"
    PRODUCTION = "PRODUCTION"


class TaxAffectationType(str, Enum):
    """
    Tax affectation types supported by SUNAT (Catalog 07).

    Names follow the official SUNAT catalog exactly. Descriptions live in
    ``app.catalogs.cat07_tax_affectation``; the tax scheme each code maps to
    (TaxCategory / TaxScheme / TaxTypeCode) lives in ``app.catalogs.tax_schemes``.
    """
    TAXED_ONEROUS = "10"
    TAXED_WITHDRAWAL_PRIZE = "11"
    TAXED_WITHDRAWAL_DONATION = "12"
    TAXED_WITHDRAWAL = "13"
    TAXED_WITHDRAWAL_ADS = "14"
    TAXED_BONUS = "15"
    TAXED_WITHDRAWAL_EMPLOYEE = "16"
    TAXED_IVAP = "17"
    EXONERATED_ONEROUS = "20"
    EXONERATED_FREE = "21"
    UNAFFECTED_ONEROUS = "30"
    UNAFFECTED_WITHDRAWAL_BONUS = "31"
    UNAFFECTED_WITHDRAWAL = "32"
    UNAFFECTED_SAMPLES = "33"
    UNAFFECTED_COLLECTIVE_AGR = "34"
    UNAFFECTED_PRIZE = "35"
    UNAFFECTED_ADS = "36"
    EXPORT = "40"


class PriceType(str, Enum):
    """
    Price types supported by SUNAT.
    """
    UNIT_PRICE_WITH_TAX = "01"
    REFERENCE_VALUE_NO_TAX = "02"


class OperationType(str, Enum):
    """
    Operation types supported by SUNAT.
    """
    DOMESTIC_SALE = "0101"
    DOMESTIC_SALE_ADVANCE = "0102"
    DOMESTIC_SALE_ADVANCE_PERCEP = "0103"
    DOMESTIC_GOODS_TRANSFER_NO_AMOUNT = "0112"
    DOMESTIC_SALE_ITINERANT = "0113"
    EXPORT_GOODS = "0200"
    EXPORT_SERVICES = "0201"
    DETRACTION = "1001"
    DETRACTION_HIDROBIOLOGICO = "1002"
    DETRACTION_TRANSPORT_GOODS = "1003"
    DETRACTION_TRANSPORT_PASSENGERS = "1004"
    PERCEPTION = "2001"


class CreditNoteReasonType(str, Enum):
    """
    Credit note reason types supported by SUNAT.
    """
    OPERATION_CANCELLATION = "01"
    RUC_ERROR = "02"
    DESCRIPTION_ERROR = "03"
    GLOBAL_DISCOUNT = "04"
    ITEM_DISCOUNT = "05"
    TOTAL_RETURN = "06"
    ITEM_RETURN = "07"
    BONUS = "08"
    VALUE_DECREASE = "09"
    OTHERS = "10"
    EXPORT_ADJUSTMENT = "11"
    IVAP_ADJUSTMENT = "12"


class DebitNoteReasonType(str, Enum):
    """
    Debit note reason types supported by SUNAT.
    """
    LATE_INTEREST = "01"
    VALUE_INCREASE = "02"
    PENALTY = "03"
    EXPORT_ADJUSTMENT = "10"
    IVAP_ADJUSTMENT = "11"
    OTHERS = "12"


class FileType(str, Enum):
    XML = "XML"
    PDF = "PDF"
    CDR = "CDR"


class DailySummaryItemStatus(str, Enum):
    ADD = "1"
    MODIFY = "2"
    VOID = "3"


class PaymentTerms(str, Enum):
    CASH = "Contado"
    CREDIT = "Credito"


class SubmissionType(str, Enum):
    SEND_BILL = "SEND_BILL"
    SEND_SUMMARY = "SEND_SUMMARY"
    SEND_VOIDED = "SEND_VOIDED"
    GET_STATUS = "GET_STATUS"
    GET_STATUS_CDR = "GET_STATUS_CDR"


class ErrorResponse(BaseModel):
    error_code: str = Field(min_length=1, max_length=50)
    message: str = Field(min_length=1, max_length=500)
    details: dict[str, object] | None = None


class PaginatedResponse[T](BaseModel):
    items: list[T]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)
