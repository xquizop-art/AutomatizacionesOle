"""
Configuracion de la aplicacion.
Carga variables de entorno con pydantic-settings.

Uso:
    from backend.config import settings
    print(settings.ALPACA_API_KEY)
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Configuracion central del bot de trading.
    Todas las variables se cargan desde el archivo .env
    ubicado en la raiz del proyecto.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # ── Alpaca API ──────────────────────────────────────────────
    ALPACA_API_KEY: str = Field(
        ...,
        description="API key de Alpaca (paper o live)",
    )
    ALPACA_SECRET_KEY: str = Field(
        ...,
        description="Secret key de Alpaca (paper o live)",
    )
    ALPACA_BASE_URL: str = Field(
        default="https://paper-api.alpaca.markets",
        description="URL base de Alpaca. Paper: https://paper-api.alpaca.markets, Live: https://api.alpaca.markets",
    )

    # ── Database ────────────────────────────────────────────────
    DATABASE_URL: str = Field(
        default="sqlite:///./trading_bot.db",
        description="URL de conexion a la base de datos (SQLite por defecto)",
    )

    # ── App ─────────────────────────────────────────────────────
    APP_ENV: Literal["development", "staging", "production"] = Field(
        default="development",
        description="Entorno de la aplicacion",
    )
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO",
        description="Nivel de logging",
    )

    # ── Risk defaults ───────────────────────────────────────────
    MAX_DAILY_LOSS_PCT: float = Field(
        default=2.0,
        description="Perdida maxima diaria permitida en porcentaje del equity",
    )
    MAX_POSITION_SIZE_PCT: float = Field(
        default=5.0,
        description="Tamanio maximo de una posicion en porcentaje del equity",
    )
    MAX_TRADES_PER_DAY: int = Field(
        default=50,
        description="Numero maximo de operaciones por dia",
    )

    # ── Propiedades computadas ──────────────────────────────────

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_paper(self) -> bool:
        """Determina si estamos en modo paper basandose en la URL."""
        return "paper" in self.ALPACA_BASE_URL.lower()

    @computed_field  # type: ignore[prop-decorator]
    @property
    def alpaca_base_url_clean(self) -> str:
        """
        URL base sin sufijo /v2 ni trailing slash.
        alpaca-py maneja el versionado internamente.
        """
        url = self.ALPACA_BASE_URL.rstrip("/")
        if url.endswith("/v2"):
            url = url[:-3]
        return url


@lru_cache
def get_settings() -> Settings:
    """
    Singleton cacheado de la configuracion.
    Usa lru_cache para no releer .env en cada llamada.
    """
    return Settings()  # type: ignore[call-arg]


# Atajo para importar directamente: `from backend.config import settings`
settings = get_settings()
