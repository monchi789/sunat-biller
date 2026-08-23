from datetime import date as Date
from decimal import Decimal

from pydantic import Field

from app.schemas.common import BaseSchema, PriceType, TaxAffectationType, UnitCode


class DocumentItemCreate(BaseSchema):
    """Una línea del comprobante.

    Solo hacen falta los datos del negocio: cantidad, unidad, valor (o precio) y
    afectación. **Todos los importes tributarios son opcionales** porque el
    backend los recalcula siempre — confiar en los del cliente contradiría
    RF-05.2. Si se envían, se validan contra lo calculado con tolerancia ±0.01 y
    se rechaza la emisión si no cuadran.
    """

    line_number: int = Field(ge=1, description="Número de línea, empezando en 1.")
    product_code: str | None = Field(default=None, max_length=100)
    description: str = Field(min_length=1, max_length=500)

    quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=6)
    unit_code: UnitCode = Field(
        default=UnitCode.NIU, description="Catálogo 03. NIU para bienes, ZZ para servicios."
    )

    unit_value: Decimal | None = Field(
        default=None, ge=0, max_digits=18, decimal_places=6,
        description="Valor unitario SIN IGV. Alternativa a `unit_price`.",
    )
    unit_price: Decimal | None = Field(
        default=None, ge=0, max_digits=18, decimal_places=6,
        description="Precio unitario CON IGV. Alternativa a `unit_value`.",
    )

    discount: Decimal = Field(default=Decimal(0), ge=0, max_digits=18, decimal_places=2)

    tax_affectation: TaxAffectationType = Field(
        default=TaxAffectationType.TAXED_ONEROUS, description="Catálogo 07."
    )
    price_type: PriceType | None = Field(
        default=None,
        description="Catálogo 16. Se deduce de la afectación si no se envía.",
    )

    icbper_applies: bool = Field(
        default=False, description="Marca la línea como afecta al impuesto a las bolsas plásticas."
    )

    # ── Importes calculados por el backend ──────────────────────────────────
    # Opcionales. Enviarlos activa una verificación cruzada, no los usa tal cual.
    subtotal: Decimal | None = Field(default=None, max_digits=18, decimal_places=2)
    taxable_amount: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=2)
    igv_amount: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=2)
    isc_amount: Decimal = Field(default=Decimal(0), ge=0, max_digits=18, decimal_places=2)
    icbper_amount: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=2)
    other_tax_amount: Decimal = Field(default=Decimal(0), ge=0, max_digits=18, decimal_places=2)
    total: Decimal | None = Field(default=None, max_digits=18, decimal_places=2)


class InstallmentCreate(BaseSchema):
    installment_number: int = Field(ge=1)
    due_date: Date
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
