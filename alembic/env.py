"""
Alembic environment configuration.

Carga la URL de la base de datos desde la configuracion
del proyecto (backend.config.settings) en vez del alembic.ini,
y registra los modelos para autogenerate.
"""

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

# ── Configuracion de Alembic ────────────────────────────────
config = context.config

# Configurar logging desde alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ── Cargar URL de la base de datos desde settings ────────────
from backend.config import settings  # noqa: E402

config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

# ── Importar modelos para autogenerate ───────────────────────
from backend.models.database import Base  # noqa: E402

# Importar todos los modelos para que Alembic los detecte
import backend.models.performance  # noqa: E402, F401
import backend.models.strategy_state  # noqa: E402, F401
import backend.models.trade  # noqa: E402, F401

target_metadata = Base.metadata


# ── Migraciones offline ─────────────────────────────────────


def run_migrations_offline() -> None:
    """
    Run migrations in 'offline' mode.

    Genera SQL sin conectarse a la base de datos.
    Util para revisar el SQL antes de ejecutarlo.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,  # Necesario para SQLite (ALTER TABLE limitado)
    )

    with context.begin_transaction():
        context.run_migrations()


# ── Migraciones online ──────────────────────────────────────


def run_migrations_online() -> None:
    """
    Run migrations in 'online' mode.

    Se conecta a la base de datos y ejecuta las migraciones.
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,  # Necesario para SQLite (ALTER TABLE limitado)
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
