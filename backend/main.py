"""
AutomatizacionesOle - Bot de Trading con Alpaca
Entry point: servidor FastAPI.

Inicia el servidor con:
    cd backend
    uvicorn main:app --reload --host 0.0.0.0 --port 8000

O directamente:
    python -m backend.main
"""

from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from backend.config import settings
from backend.models.database import init_db


# ── Logging setup ────────────────────────────────────────────────


def _setup_logging() -> None:
    """Configura loguru con el nivel definido en settings."""
    logger.remove()  # Remove default handler
    logger.add(
        sys.stderr,
        level=settings.LOG_LEVEL,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
            "<level>{message}</level>"
        ),
        colorize=True,
    )
    logger.add(
        "logs/trading_bot_{time:YYYY-MM-DD}.log",
        level="DEBUG",
        rotation="1 day",
        retention="30 days",
        compression="zip",
        format=(
            "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | "
            "{name}:{function}:{line} | {message}"
        ),
    )


# ── Application lifecycle ────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Maneja el ciclo de vida de la aplicacion:
        - Startup: inicializa DB, engine, registra event callbacks.
        - Shutdown: detiene engine gracefully.
    """
    _setup_logging()
    logger.info("═══ Iniciando AutomatizacionesOle Trading Bot ═══")
    logger.info(f"Entorno: {settings.APP_ENV}")
    logger.info(f"Paper mode: {settings.is_paper}")
    logger.info(f"Base URL: {settings.alpaca_base_url_clean}")

    # ── 1. Inicializar base de datos ──────────────────────
    logger.info("Inicializando base de datos...")
    init_db()
    logger.info("Base de datos lista")

    # ── 2. Crear e inicializar TradingEngine ──────────────
    from backend.api.dependencies import set_engine
    from backend.api.websocket import ws_manager
    from backend.core.engine import TradingEngine

    engine = TradingEngine()

    # Registrar callback de WebSocket para eventos del engine
    engine.on_event(ws_manager.engine_event_handler)

    try:
        await engine.initialize()
        logger.info("TradingEngine inicializado correctamente")
    except Exception as e:
        logger.error(
            f"Error inicializando TradingEngine: {e}. "
            "El servidor arrancara pero el engine no estara disponible "
            "hasta reiniciar con credenciales validas."
        )

    # Registrar la instancia del engine para las dependencias
    set_engine(engine)

    logger.info("═══ Servidor listo ═══")

    yield  # ── La aplicacion corre aqui ──

    # ── Shutdown ──────────────────────────────────────────
    logger.info("═══ Deteniendo servidor ═══")
    try:
        await engine.stop()
    except Exception as e:
        logger.error(f"Error deteniendo engine: {e}")
    logger.info("═══ Servidor detenido ═══")


# ── FastAPI app ───────────────────────────────────────────────────


app = FastAPI(
    title="AutomatizacionesOle - Trading Bot API",
    description=(
        "API REST y WebSocket para gestionar un bot de trading "
        "automatizado con Alpaca Markets. Permite controlar estrategias, "
        "consultar trades, metricas de rendimiento y recibir updates "
        "en tiempo real."
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)


# ── CORS (permitir acceso desde el frontend) ─────────────────────


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",    # Vite dev server
        "http://localhost:3000",    # React dev server alternativo
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Registrar routers ────────────────────────────────────────────


from backend.api.routes.account import router as account_router
from backend.api.routes.performance import router as performance_router
from backend.api.routes.strategies import router as strategies_router
from backend.api.routes.trades import router as trades_router

app.include_router(strategies_router)
app.include_router(trades_router)
app.include_router(performance_router)
app.include_router(account_router)


# ── WebSocket endpoint ───────────────────────────────────────────


from backend.api.websocket import websocket_endpoint

app.add_api_websocket_route("/ws/live", websocket_endpoint)


# ── Health check ─────────────────────────────────────────────────


@app.get(
    "/health",
    tags=["system"],
    summary="Health check",
    description="Verifica que el servidor esta activo.",
)
async def health_check():
    """Endpoint de health check."""
    from backend.api.dependencies import get_engine
    from backend.api.websocket import ws_manager

    try:
        engine = get_engine()
        engine_status = engine.status.value
    except Exception:
        engine_status = "unavailable"

    return {
        "status": "ok",
        "engine": engine_status,
        "paper_mode": settings.is_paper,
        "environment": settings.APP_ENV,
        "websocket_connections": ws_manager.connection_count,
    }


@app.get(
    "/",
    tags=["system"],
    summary="Root",
    description="Informacion basica del API.",
)
async def root():
    """Endpoint raiz con informacion del API."""
    return {
        "name": "AutomatizacionesOle Trading Bot",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health",
        "websocket": "/ws/live",
        "endpoints": {
            "strategies": "/api/strategies",
            "trades": "/api/trades",
            "performance": "/api/performance",
            "account": "/api/account",
        },
    }


# ── Entry point directo ──────────────────────────────────────────


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=8000,
        reload=(settings.APP_ENV == "development"),
        log_level=settings.LOG_LEVEL.lower(),
    )
