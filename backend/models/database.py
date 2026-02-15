"""
Setup de SQLAlchemy y conexion a la base de datos.
SQLite por defecto, migracion a PostgreSQL cuando escale.

Uso:
    from backend.models.database import Base, SessionLocal, engine, get_db

    # Como dependency en FastAPI:
    @app.get("/example")
    def example(db: Session = Depends(get_db)):
        ...

    # Crear todas las tablas (desarrollo):
    from backend.models.database import init_db
    init_db()
"""

from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from backend.config import settings


# ── Base declarativa (SQLAlchemy 2.0) ────────────────────────
class Base(DeclarativeBase):
    """Clase base para todos los modelos SQLAlchemy."""

    pass


# ── Engine ───────────────────────────────────────────────────

# SQLite necesita check_same_thread=False para funcionar con FastAPI
# (multiples threads pueden acceder a la misma conexion).
_connect_args = {}
if settings.DATABASE_URL.startswith("sqlite"):
    _connect_args["check_same_thread"] = False

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=_connect_args,
    echo=(settings.APP_ENV == "development"),  # SQL logging en desarrollo
    pool_pre_ping=True,  # Verifica conexion antes de usarla
)


# ── Habilitar WAL y foreign keys para SQLite ─────────────────
if settings.DATABASE_URL.startswith("sqlite"):

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):
        """
        Activa WAL mode (mejor concurrencia) y foreign keys en SQLite.
        """
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.execute("PRAGMA foreign_keys=ON;")
        cursor.close()


# ── Session factory ──────────────────────────────────────────

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)


# ── Dependency para FastAPI ──────────────────────────────────


def get_db() -> Generator[Session, None, None]:
    """
    Genera una sesion de base de datos para inyeccion de dependencias.
    Se cierra automaticamente al finalizar el request.

    Uso con FastAPI:
        @app.get("/items")
        def get_items(db: Session = Depends(get_db)):
            return db.query(Item).all()
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── Inicializacion (crear tablas) ────────────────────────────


def init_db() -> None:
    """
    Crea todas las tablas en la base de datos.

    NOTA: En produccion, usar Alembic para migraciones en vez
    de crear tablas directamente. Esta funcion es util para
    desarrollo y testing rapido.
    """
    # Importar todos los modelos para que SQLAlchemy los registre
    import backend.models.performance  # noqa: F401
    import backend.models.strategy_state  # noqa: F401
    import backend.models.trade  # noqa: F401

    Base.metadata.create_all(bind=engine)
