"""Configuración de la aplicación, cargada desde entorno / `.env`."""

from __future__ import annotations

from decimal import Decimal
from enum import Enum
from functools import cached_property
from pathlib import Path

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppEnvironment(str, Enum):
    """Entorno de **despliegue**, distinto del ambiente de SUNAT.

    Son dos ejes independientes: durante la homologación se opera en
    `production` apuntando al SUNAT `BETA`. Confundirlos haría que un despliegue
    productivo contra beta arrancara sin exigir secretos reales.
    """

    DEVELOPMENT = "development"
    PRODUCTION = "production"


class SunatEnvironmentSetting(str, Enum):
    """A qué billService se envía. Nada que ver con `AppEnvironment`."""

    BETA = "BETA"
    PRODUCTION = "PRODUCTION"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Aplicación ───────────────────────────────────────────────────────────
    APP_ENV: AppEnvironment = AppEnvironment.DEVELOPMENT
    DEBUG: bool = False
    API_PORT: int = 7890
    API_V1_PREFIX: str = "/api/v1"
    PROJECT_NAME: str = "sunat-biller"
    VERSION: str = "0.1.0"

    SECRET_KEY: str = "change-me-in-production"
    ENCRYPTION_KEY: str = ""

    ADMIN_TOKEN: str = ""
    """Autoriza el aprovisionamiento: crear empresas y emitir sus API keys.

    Existe porque hay un huevo y la gallina: toda API key pertenece a una
    empresa, así que la primera empresa no puede autenticarse con una.
    """

    CORS_ORIGINS: str = ""

    # ── Base de datos ────────────────────────────────────────────────────────
    DATABASE_URL: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/sunat_biller"
    TEST_DATABASE_URL: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/sunat_biller_test"

    # ── Redis ────────────────────────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"

    # ── Almacenamiento ───────────────────────────────────────────────────────
    STORAGE_ROOT: Path = Path("./data/storage")
    CERTIFICATE_ROOT: Path = Path("./data/certificates")
    MAX_CERTIFICATE_SIZE_MB: int = Field(default=5, ge=1, le=50)

    # ── SUNAT ────────────────────────────────────────────────────────────────
    SUNAT_ENVIRONMENT: SunatEnvironmentSetting = SunatEnvironmentSetting.BETA
    SUNAT_BETA_URL: str = "https://e-beta.sunat.gob.pe/ol-ti-itcpfegem-beta/billService"
    SUNAT_PRODUCTION_URL: str = "https://e-factura.sunat.gob.pe/ol-ti-itcpfegem/billService"
    SUNAT_TIMEOUT_SECONDS: float = Field(default=30.0, gt=0)

    # ── Reglas tributarias ───────────────────────────────────────────────────
    IGV_RATE: Decimal = Field(default=Decimal("0.18"), ge=0, le=1)
    ICBPER_RATE: Decimal = Field(default=Decimal("0.50"), ge=0)
    RECEIPT_CUSTOMER_THRESHOLD: Decimal = Field(default=Decimal("700.00"), ge=0)
    MAX_ISSUE_BACKDATE_DAYS: int = Field(default=3, ge=0)

    # ── Idempotencia ─────────────────────────────────────────────────────────
    IDEMPOTENCY_TTL_HOURS: int = Field(default=24, ge=1)

    # ── Webhooks ─────────────────────────────────────────────────────────────
    WEBHOOK_TIMEOUT_SECONDS: float = Field(default=10.0, gt=0)
    WEBHOOK_MAX_ATTEMPTS: int = Field(default=6, ge=1)

    # ── Derivados ────────────────────────────────────────────────────────────

    @property
    def sunat_url(self) -> str:
        """URL del billService según el ambiente configurado."""
        if self.sunat_is_production:
            return self.SUNAT_PRODUCTION_URL
        return self.SUNAT_BETA_URL

    @property
    def is_production(self) -> bool:
        """Entorno de despliegue productivo. **No** mira el ambiente de SUNAT."""
        return self.APP_ENV is AppEnvironment.PRODUCTION

    @property
    def sunat_is_production(self) -> bool:
        """Si se envía al billService de producción de SUNAT."""
        return self.SUNAT_ENVIRONMENT is SunatEnvironmentSetting.PRODUCTION

    @property
    def docs_enabled(self) -> bool:
        """En producción no se publican `/docs`, `/redoc` ni el esquema OpenAPI."""
        return not self.is_production

    @cached_property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    # ── Validación ───────────────────────────────────────────────────────────

    @field_validator("API_V1_PREFIX")
    @classmethod
    def _prefix_must_not_end_with_slash(cls, value: str) -> str:
        return value.rstrip("/")

    @model_validator(mode="after")
    def _require_secrets_in_production(self) -> Settings:
        """Con `APP_ENV=production` no se arranca con secretos por defecto o ausentes.

        `ENCRYPTION_KEY` cifra credenciales SOL y contraseñas de certificados: sin
        ella el servicio no puede operar de forma segura, y con una derivada de un
        `SECRET_KEY` débil tampoco. Se falla temprano y ruidosamente.
        """
        if self.is_production:
            if not self.ENCRYPTION_KEY:
                raise ValueError("ENCRYPTION_KEY es obligatoria cuando APP_ENV=production")
            if self.SECRET_KEY == "change-me-in-production":
                raise ValueError("SECRET_KEY debe cambiarse antes de operar con APP_ENV=production")
            if not self.ADMIN_TOKEN:
                raise ValueError("ADMIN_TOKEN es obligatorio cuando APP_ENV=production")
        return self


settings = Settings()
