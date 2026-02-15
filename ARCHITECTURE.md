# AutomatizacionesOle — Documentacion Tecnica Completa

> Bot de trading automatizado con Alpaca Markets, dashboard React en tiempo real,
> estrategia "Reversa Rango Asia" para BTC/USD, y Expert Advisor para MetaTrader 5.

---

## Tabla de Contenidos

1. [Vision General](#1-vision-general)
2. [Stack Tecnologico](#2-stack-tecnologico)
3. [Estructura del Proyecto](#3-estructura-del-proyecto)
4. [Arquitectura del Sistema](#4-arquitectura-del-sistema)
5. [Backend — Capa por Capa](#5-backend--capa-por-capa)
   - 5.1 [Configuracion (`config.py`)](#51-configuracion)
   - 5.2 [Entry Point (`main.py`)](#52-entry-point)
   - 5.3 [Core — Motor de Trading (`core/engine.py`)](#53-core--motor-de-trading)
   - 5.4 [Core — Risk Manager (`core/risk_manager.py`)](#54-core--risk-manager)
   - 5.5 [Core — Backtester (`core/backtester.py`)](#55-core--backtester)
   - 5.6 [Broker — Interfaz y Alpaca (`broker/`)](#56-broker--interfaz-y-alpaca)
   - 5.7 [Estrategias (`strategies/`)](#57-estrategias)
   - 5.8 [Datos de Mercado (`data/`)](#58-datos-de-mercado)
   - 5.9 [Modelos de Base de Datos (`models/`)](#59-modelos-de-base-de-datos)
   - 5.10 [API REST y WebSocket (`api/`)](#510-api-rest-y-websocket)
6. [Estrategia: Reversa Rango Asia](#6-estrategia-reversa-rango-asia)
7. [Frontend — Dashboard React](#7-frontend--dashboard-react)
8. [MetaTrader 5 — Expert Advisor](#8-metatrader-5--expert-advisor)
9. [Flujo de Datos en Tiempo Real](#9-flujo-de-datos-en-tiempo-real)
10. [Configuracion y Despliegue](#10-configuracion-y-despliegue)
11. [Decisiones de Diseno Clave](#11-decisiones-de-diseno-clave)
12. [Limitaciones Conocidas y Trabajo Futuro](#12-limitaciones-conocidas-y-trabajo-futuro)

---

## 1. Vision General

**AutomatizacionesOle** es un sistema de trading algoritmico que:

- Conecta con **Alpaca Markets** (paper o live) para ejecutar operaciones automatizadas.
- Implementa una arquitectura de **estrategias pluggable** donde se pueden agregar nuevas estrategias sin tocar el motor principal.
- Ofrece un **dashboard web en tiempo real** con graficos de rendimiento, tabla de trades, feed en vivo de eventos y control de estrategias.
- Incluye un **backtester** para validar estrategias con datos historicos.
- Proporciona un **Expert Advisor MQL5** equivalente para MetaTrader 5.

La primera estrategia implementada es **"Reversa Rango Asia"** — opera reversiones en BTC/USD (M5) cuando el precio toca los extremos del rango formado durante la sesion asiatica (00:00–07:00 hora de Madrid).

---

## 2. Stack Tecnologico

### Backend (Python 3.12)
| Componente | Tecnologia |
|---|---|
| Web Framework | FastAPI + Uvicorn |
| Base de Datos | SQLite + SQLAlchemy (ORM) |
| Migraciones | Alembic |
| Broker API | alpaca-py (SDK oficial) |
| Datos Historicos | yfinance, pandas |
| Indicadores | pandas-ta |
| Async | asyncio nativo |
| Logging | loguru |
| Config | pydantic-settings (.env) |

### Frontend (TypeScript)
| Componente | Tecnologia |
|---|---|
| Framework | React 18 |
| Bundler | Vite |
| Estilos | Tailwind CSS |
| Graficos | Recharts |
| Iconos | Lucide React |
| Utilidades CSS | clsx |

### MetaTrader 5
| Componente | Tecnologia |
|---|---|
| Lenguaje | MQL5 |
| Libreria | Trade.mqh (nativa MT5) |

---

## 3. Estructura del Proyecto

```
AutomatizacionesOle/
├── .env                          # Variables de entorno (NO en git)
├── .env.example                  # Plantilla de variables de entorno
├── .gitignore                    # Exclusiones de git
├── README.md                     # README basico
├── ARCHITECTURE.md               # << ESTE DOCUMENTO
├── alembic.ini                   # Config de migraciones Alembic
├── alembic/                      # Migraciones de base de datos
│   ├── env.py
│   ├── script.py.mako
│   └── versions/                 # Scripts de migracion
│
├── backend/                      # ══ BACKEND PYTHON ══
│   ├── __init__.py
│   ├── main.py                   # Entry point FastAPI (lifespan, rutas, CORS)
│   ├── config.py                 # Configuracion centralizada (Pydantic Settings)
│   ├── requirements.txt          # Dependencias Python
│   │
│   ├── api/                      # Capa API (REST + WebSocket)
│   │   ├── __init__.py
│   │   ├── dependencies.py       # Inyeccion de dependencias (singleton Engine)
│   │   ├── websocket.py          # WebSocket server + ConnectionManager
│   │   └── routes/
│   │       ├── __init__.py
│   │       ├── account.py        # GET /api/account, posiciones, ordenes, mercado
│   │       ├── strategies.py     # CRUD estrategias + start/stop
│   │       ├── trades.py         # Historial de trades con filtros
│   │       └── performance.py    # Metricas, equity curve, engine status
│   │
│   ├── broker/                   # Capa Broker (abstraccion + Alpaca)
│   │   ├── __init__.py
│   │   ├── broker_interface.py   # ABC: BrokerInterface + data classes
│   │   └── alpaca_client.py      # Implementacion Alpaca (stocks + crypto)
│   │
│   ├── core/                     # Nucleo del sistema
│   │   ├── __init__.py
│   │   ├── engine.py             # TradingEngine — orquestador principal
│   │   ├── risk_manager.py       # RiskManager — validacion pre-orden
│   │   ├── backtester.py         # Backtester — simulacion historica
│   │   └── scheduler.py          # Placeholder para scheduler (futuro)
│   │
│   ├── data/                     # Capa de Datos
│   │   ├── __init__.py
│   │   ├── market_data.py        # MarketDataService — agregador con cache
│   │   ├── indicators.py         # Indicadores tecnicos (SMA, RSI, ATR, etc.)
│   │   ├── storage.py            # Almacenamiento local en Parquet
│   │   └── yahoo_provider.py     # Proveedor Yahoo Finance
│   │
│   ├── models/                   # Modelos SQLAlchemy
│   │   ├── __init__.py
│   │   ├── database.py           # Engine SQLAlchemy, Base, sesiones
│   │   ├── trade.py              # Modelo Trade (historial de operaciones)
│   │   ├── performance.py        # Modelo PerformanceSnapshot
│   │   └── strategy_state.py     # Modelo StrategyRun (ciclos start/stop)
│   │
│   └── strategies/               # Estrategias de Trading
│       ├── __init__.py
│       ├── base_strategy.py      # ABC: BaseStrategy + Signal enum
│       ├── registry.py           # StrategyRegistry (auto-discovery)
│       ├── asia_range_reversal.py # ** Reversa Rango Asia (BTC/USD M5)
│       ├── sma_crossover.py      # Ejemplo: cruce de medias moviles
│       └── rsi_strategy.py       # Ejemplo: RSI overbought/oversold
│
├── frontend/                     # ══ FRONTEND REACT ══
│   ├── index.html                # HTML entry point
│   ├── package.json              # Dependencias NPM
│   ├── vite.config.ts            # Config Vite (proxy API + WS)
│   ├── tsconfig.json             # Config TypeScript
│   ├── tailwind.config.js        # Config Tailwind (paleta dark custom)
│   ├── postcss.config.js         # Config PostCSS
│   └── src/
│       ├── main.tsx              # Entry point React
│       ├── App.tsx               # Shell principal (header + status + Dashboard)
│       ├── index.css             # Estilos globales Tailwind + clases custom
│       ├── types.ts              # Interfaces TypeScript (Account, Trade, etc.)
│       ├── vite-env.d.ts         # Tipos Vite
│       ├── services/
│       │   └── api.ts            # Cliente HTTP para todos los endpoints
│       ├── hooks/
│       │   ├── useWebSocket.ts   # Hook WebSocket con auto-reconnect
│       │   └── usePolling.ts     # Hook generico de polling periodico
│       └── components/
│           ├── Dashboard.tsx     # Layout principal del dashboard
│           ├── AccountSummary.tsx # Metricas de cuenta (equity, P&L, etc.)
│           ├── StrategyCard.tsx  # Card de estrategia con start/stop
│           ├── PerformanceChart.tsx # Graficos equity curve + daily P&L
│           ├── TradeTable.tsx    # Tabla paginada con filtros
│           └── LiveFeed.tsx      # Feed de eventos WebSocket en vivo
│
├── mt5/                          # ══ METATRADER 5 ══
│   └── AsiaRangeReversal_M5.mq5 # Expert Advisor equivalente
│
└── logs/                         # Logs de ejecucion (auto-generados)
    └── trading_bot_YYYY-MM-DD.log
```

---

## 4. Arquitectura del Sistema

```
┌─────────────────────────────────────────────────────────┐
│                    FRONTEND (React)                      │
│  localhost:5173                                          │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────────┐  │
│  │ Account  │ │ Strategy │ │ Perf.    │ │ Trade     │  │
│  │ Summary  │ │ Cards    │ │ Charts   │ │ Table     │  │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └─────┬─────┘  │
│       │ polling     │ polling    │ polling      │ polling│
│  ┌────┴─────────────┴────────────┴──────────────┴─────┐ │
│  │              usePolling + useWebSocket               │ │
│  └──────────────────┬───────────────────────────────────┘│
└─────────────────────┼────────────────────────────────────┘
          REST /api/* │  WS /ws/live
                      ▼
┌─────────────────────────────────────────────────────────┐
│                   BACKEND (FastAPI)                       │
│  localhost:8000                                          │
│                                                          │
│  ┌── API Layer ──────────────────────────────────────┐  │
│  │  routes/account  routes/strategies  routes/trades  │  │
│  │  routes/performance       websocket.py             │  │
│  └───────────────────────┬───────────────────────────┘  │
│                          │ dependencies.py               │
│  ┌── Core Layer ─────────┴───────────────────────────┐  │
│  │                                                    │  │
│  │  ┌──────────────────────────────────────────────┐ │  │
│  │  │            TradingEngine                      │ │  │
│  │  │                                               │ │  │
│  │  │  ┌─────────┐  ┌────────────┐  ┌───────────┐ │ │  │
│  │  │  │Strategy │  │   Risk     │  │  Market   │ │ │  │
│  │  │  │Registry │  │  Manager   │  │  Data Svc │ │ │  │
│  │  │  └────┬────┘  └─────┬──────┘  └─────┬─────┘ │ │  │
│  │  │       │              │               │        │ │  │
│  │  │  ┌────┴────┐   ┌────┴────┐    ┌─────┴─────┐ │ │  │
│  │  │  │Strategies│  │  Broker  │   │  Storage  │ │ │  │
│  │  │  │(plugins) │  │Interface │   │  + Yahoo  │ │ │  │
│  │  │  └─────────┘   └────┬────┘    └───────────┘ │ │  │
│  │  └──────────────────────┼───────────────────────┘ │  │
│  └─────────────────────────┼─────────────────────────┘  │
│                            │                             │
│  ┌── Broker Layer ─────────┴─────────────────────────┐  │
│  │              AlpacaClient                          │  │
│  │   (stocks + crypto, bracket orders, market data)   │  │
│  └────────────────────┬──────────────────────────────┘  │
│                       │                                  │
│  ┌── Data Layer ──────┴──────────────────────────────┐  │
│  │  SQLite (trades, performance, strategy_runs)       │  │
│  │  Parquet files (cached OHLCV bars)                 │  │
│  └───────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
                        │
                        ▼
              ┌──────────────────┐
              │  Alpaca Markets  │
              │  (Paper / Live)  │
              └──────────────────┘
```

**Flujo principal:** Frontend → REST API → TradingEngine → Strategy → Signal → RiskManager → Broker → Alpaca

---

## 5. Backend — Capa por Capa

### 5.1 Configuracion

**Archivo:** `backend/config.py`

Usa `pydantic-settings` para cargar variables de entorno desde `.env`.

```python
class Settings(BaseSettings):
    ALPACA_API_KEY: str
    ALPACA_SECRET_KEY: str
    ALPACA_BASE_URL: str = "https://paper-api.alpaca.markets"
    DATABASE_URL: str = "sqlite:///./trading_bot.db"
    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"
    MAX_DAILY_LOSS_PCT: float = 2.0
    MAX_POSITION_SIZE_PCT: float = 5.0
    MAX_TRADES_PER_DAY: int = 50
```

Propiedades computadas clave:
- `is_paper` → detecta si estamos en paper mode mirando la URL
- `alpaca_base_url_clean` → quita `/v2` del final de la URL

Patron: **singleton** via `get_settings()` con `@lru_cache`.

---

### 5.2 Entry Point

**Archivo:** `backend/main.py`

FastAPI app con `lifespan` (ciclo de vida asincrono):

1. **Startup:**
   - Configura logging (loguru → archivo rotativo + consola).
   - Inicializa base de datos (`init_db()`).
   - Crea `AlpacaClient`, `MarketDataService`, `RiskManager`.
   - Crea y arranca `TradingEngine`.
   - Registra `engine_event_handler` del WebSocket como callback del engine.
   - Inyecta engine en `dependencies.set_engine()`.

2. **Shutdown:**
   - Detiene el TradingEngine gracefully.

3. **Middleware:** CORS habilitado para `localhost:5173` y `:3000`.

4. **Routers:** Incluye todas las rutas de `/api/*` y el endpoint `/ws/live`.

---

### 5.3 Core — Motor de Trading

**Archivo:** `backend/core/engine.py` (~1000 lineas)

El `TradingEngine` es el **orquestador central** del sistema. Gestiona:

- **Ciclo de vida** de estrategias (start/stop/error)
- **Bucles asincronos** por estrategia (una `asyncio.Task` por cada estrategia activa)
- **Flujo de señales**: datos → estrategia → señal → risk check → orden
- **Eventos** para notificar al WebSocket y al dashboard

**Estados del engine** (`EngineStatus`):
```
STOPPED → INITIALIZING → RUNNING → SHUTTING_DOWN → STOPPED
                                  → ERROR
```

**Metodos clave:**

| Metodo | Funcion |
|---|---|
| `initialize()` | Descubre estrategias, verifica broker, prepara todo |
| `start_strategy(name)` | Crea una asyncio.Task que ejecuta `_strategy_loop()` |
| `stop_strategy(name)` | Cancela la task y limpia estado |
| `_strategy_loop()` | Bucle infinito: sleep(intervalo) → `_execute_cycle()` |
| `_execute_cycle()` | Pide datos → calcula señales → procesa señales |
| `_process_signal()` | Evalua risk → envia orden al broker |

**Punto critico — `_process_signal()`:**
```python
# 1. Consulta risk manager
risk_check = self._risk_manager.evaluate_order(...)

# 2. Si aprobado, lee bracket_params de la estrategia (si existen)
bracket = getattr(strategy, '_bracket_params', None)

# 3. Envia orden al broker con SL/TP
order = await self._broker.submit_order(
    symbol=symbol,
    side=side,
    qty=qty,
    take_profit_price=bracket.get("take_profit"),
    stop_loss_price=bracket.get("stop_loss"),
    time_in_force="gtc" if is_crypto else "day"
)
```

**Punto critico — `skip_market_check`:**
El engine normalmente verifica `is_market_open()` antes de ejecutar el ciclo. Las estrategias crypto (como Asia Range Reversal) ponen `skip_market_check = True` en la clase para saltarse esta verificacion (crypto opera 24/7).

---

### 5.4 Core — Risk Manager

**Archivo:** `backend/core/risk_manager.py` (~540 lineas)

Cadena de verificaciones pre-orden:

1. **Daily Loss Limit** — maximo 2% de perdida diaria
2. **Trades Limit** — maximo 50 trades/dia
3. **Position Size** — maximo 5% del equity en una posicion
4. **Open Positions** — maximo 20 posiciones simultaneas
5. **Buying Power** — minimo 10% de buying power libre

Retorna `RiskCheck(approved=True/False, reason="...")`.

Tambien calcula **position sizing** optimo basado en equity y limites.

---

### 5.5 Core — Backtester

**Archivo:** `backend/core/backtester.py` (~787 lineas)

Simula ejecucion de estrategias en datos historicos.

**Principio fundamental:** NO hay look-ahead bias. Las señales generadas en la barra `i` se ejecutan al `open` de la barra `i+1`.

**Flujo:**
1. Carga datos historicos via `MarketDataService`
2. Para cada barra, construye una ventana de datos
3. Pasa la ventana a `strategy.calculate_signals()`
4. Ejecuta las señales en la siguiente barra
5. Calcula metricas: Sharpe ratio, max drawdown, win rate, profit factor, etc.

---

### 5.6 Broker — Interfaz y Alpaca

#### `broker/broker_interface.py`

ABC (Abstract Base Class) que define el contrato del broker:

```python
class BrokerInterface(ABC):
    async def get_account() -> AccountInfo
    async def submit_order(symbol, side, qty, ..., take_profit_price, stop_loss_price) -> Order
    async def get_bars(symbol, timeframe, limit) -> pd.DataFrame
    async def get_latest_price(symbol) -> float
    async def is_market_open() -> bool
    # ... mas metodos
```

Data classes estandarizadas: `AccountInfo`, `Position`, `Order`, `OrderSide`, `OrderType`, etc.

**Patron:** Strategy Pattern + Dependency Inversion — el engine depende de la interfaz, no de Alpaca directamente.

#### `broker/alpaca_client.py` (~534 lineas)

Implementacion concreta de `BrokerInterface` para Alpaca:

**Puntos criticos:**

1. **Deteccion de crypto:** Los simbolos con `/` (ej: `BTC/USD`) se tratan como crypto:
   ```python
   def _is_crypto(self, symbol: str) -> bool:
       return "/" in symbol
   ```
   Esto determina que cliente SDK usar (`CryptoHistoricalDataClient` vs `StockHistoricalDataClient`).

2. **Bracket Orders:** Para ordenes con SL/TP se usa `OrderClass.BRACKET`:
   ```python
   MarketOrderRequest(
       symbol=symbol,
       qty=qty,
       side=side,
       time_in_force=tif,
       order_class=OrderClass.BRACKET,
       take_profit=TakeProfitRequest(limit_price=tp),
       stop_loss=StopLossRequest(stop_price=sl),
   )
   ```

3. **Async wrapper:** El SDK de Alpaca es sincrono, asi que se envuelve con `asyncio.to_thread()`:
   ```python
   async def _run_sync(self, func, *args):
       return await asyncio.to_thread(func, *args)
   ```

---

### 5.7 Estrategias

#### `strategies/base_strategy.py`

Clase base abstracta que toda estrategia debe heredar:

```python
class BaseStrategy(ABC):
    # Atributos de clase (obligatorios en subclases)
    name: str               # Nombre unico (ej: "reversa_rango_asia")
    description: str        # Descripcion humana
    symbols: list[str]      # Simbolos que opera (ej: ["BTC/USD"])
    timeframe: str          # Timeframe (ej: "5Min")
    skip_market_check: bool = False  # True para crypto (24/7)

    # Metodos abstractos
    def calculate_signals(self, data: dict[str, pd.DataFrame]) -> dict[str, Signal]
    def get_parameters(self) -> dict[str, Any]

    # Hooks opcionales
    def on_trade_executed(self, trade: dict)
    def on_start(self)
    def on_stop(self)
```

`Signal` es un enum: `BUY`, `SELL`, `HOLD`.

#### `strategies/registry.py`

**Auto-discovery:** Al iniciar, escanea todos los `.py` en `strategies/`, importa los modulos, y registra cualquier subclase de `BaseStrategy`:

```python
def discover(self):
    for module in pkgutil.iter_modules([strategies_path]):
        imported = importlib.import_module(f"backend.strategies.{module.name}")
        for cls in [... subclasses of BaseStrategy ...]:
            self.register(cls)
```

Patron: **singleton por estrategia** — `get_strategy(name)` retorna siempre la misma instancia.

**Para crear una nueva estrategia:** basta con crear un `.py` en `backend/strategies/` con una clase que herede de `BaseStrategy`. El registry la descubrira automaticamente.

#### Estrategias incluidas:

| Estrategia | Archivo | Descripcion |
|---|---|---|
| **Reversa Rango Asia** | `asia_range_reversal.py` | Estrategia principal (ver seccion 6) |
| SMA Crossover | `sma_crossover.py` | Ejemplo: cruce de medias 20/50 |
| RSI Strategy | `rsi_strategy.py` | Ejemplo: RSI overbought/oversold |

---

### 5.8 Datos de Mercado

#### `data/market_data.py`

Servicio unificado con **smart fetch** (busca en orden: cache → local → Yahoo → Alpaca):

```python
class MarketDataService:
    async def get_bars(symbol, timeframe, limit) -> pd.DataFrame      # Live
    async def get_bars_for_symbols(symbols, timeframe, limit) -> dict  # Multi-symbol
    def get_historical_data(symbol, timeframe, start, end) -> pd.DataFrame  # Backtest
```

Cache en memoria con TTL configurable (default 60s).

#### `data/indicators.py`

Wrapper sobre `pandas-ta` con funciones tipo `add_sma(df, period)`, `add_rsi(df, period)`, etc. Todas mutan el DataFrame in-place y usan naming consistente (`SMA_20`, `RSI_14`, etc.).

#### `data/storage.py`

Almacenamiento local en formato **Parquet** organizado por simbolo/timeframe. Soporta actualizaciones incrementales con deduplicacion.

#### `data/yahoo_provider.py`

Proveedor de datos historicos via `yfinance`. Usado principalmente por el backtester.

---

### 5.9 Modelos de Base de Datos

SQLite con SQLAlchemy ORM. Tres tablas principales:

| Modelo | Tabla | Proposito |
|---|---|---|
| `Trade` | `trades` | Cada orden ejecutada (symbol, side, qty, P&L, status, etc.) |
| `PerformanceSnapshot` | `performance_snapshots` | Fotos periodicas de equity, P&L, metricas |
| `StrategyRun` | `strategy_runs` | Cada ciclo start/stop de una estrategia (con metricas) |

`database.py` configura el engine SQLAlchemy con:
- SQLite WAL mode (mejor concurrencia)
- Foreign keys habilitados
- Session factory para inyeccion en FastAPI

---

### 5.10 API REST y WebSocket

#### Endpoints REST

| Ruta | Metodo | Funcion |
|---|---|---|
| `/api/account` | GET | Info de cuenta (equity, cash, P&L) |
| `/api/account/positions` | GET | Posiciones abiertas |
| `/api/account/orders` | GET | Ordenes activas |
| `/api/account/market` | GET | Estado del mercado |
| `/api/strategies` | GET | Lista todas las estrategias |
| `/api/strategies/{name}` | GET | Detalle de una estrategia |
| `/api/strategies/{name}/start` | POST | Arrancar estrategia |
| `/api/strategies/{name}/stop` | POST | Detener estrategia |
| `/api/strategies/{name}/params` | PUT | Actualizar parametros |
| `/api/trades` | GET | Historial con filtros y paginacion |
| `/api/trades/summary` | GET | Resumen agregado |
| `/api/performance` | GET | Metricas de rendimiento |
| `/api/performance/equity-curve` | GET | Curva de equity |
| `/api/performance/engine-status` | GET | Estado del engine y estrategias |

#### WebSocket (`/ws/live`)

`ConnectionManager` gestiona las conexiones. Cada evento del engine se retransmite a todos los clientes conectados:

- `order_submitted` — nueva orden enviada
- `signal_generated` — señal BUY/SELL/HOLD
- `strategy_started` / `strategy_stopped`
- `risk_rejected` — orden rechazada por risk manager
- `engine_error`

Soporta **canales**: el cliente puede suscribirse solo a ciertos tipos de eventos.

#### Inyeccion de Dependencias (`dependencies.py`)

Patron singleton: `main.py` llama `set_engine(engine)` al startup, y las rutas usan `Depends(get_engine)` para acceder al engine.

---

## 6. Estrategia: Reversa Rango Asia

**Archivo:** `backend/strategies/asia_range_reversal.py` (~704 lineas)

### Concepto

Opera reversiones en los extremos del rango que BTC/USD forma durante la sesion asiatica (00:00–07:00 hora de Madrid). Cuando el precio toca el maximo del rango → SELL. Cuando toca el minimo → BUY.

### Maquina de Estados

```
Estado A: "Construyendo Asia" (00:00–06:59 Madrid)
    └→ Acumula AsiaHigh/AsiaLow de las velas M5
    └→ Aplica filtro de outliers (mechas anomalas)

Estado B: "Asia Congelada" (07:00–07:29)
    └→ Calcula ATR_Asia (media simple de True Ranges)
    └→ Valida filtros de calidad:
         ✓ Min 78 velas (de 84 posibles)
         ✓ AsiaRange >= 0.8 * ATR_Asia
         ✓ ATR_Asia > 0
    └→ Si pasa filtros: day_enabled = True

Estado C: "Buscando Entrada" (07:30–12:00)
    └→ Si Bid >= AsiaHigh → SELL
    └→ Si Ask <= AsiaLow  → BUY
    └→ Filtro spread: spread <= 0.25 * ATR_Asia
    └→ Si ambos toques en misma barra: desempata por cercania
    └→ Al entrar: SL/TP a ± 2*ATR_Asia (RR 1:1)

Estado D: "Cerrado" (>=12:00 o trade_taken=true)
    └→ No hace nada hasta el dia siguiente
```

### Parametros Configurables

| Parametro | Default | Funcion |
|---|---|---|
| `atr_multiplier` | 2.0 | Multiplicador ATR para SL/TP |
| `min_asia_candles` | 78 | Min velas requeridas (93% de 84) |
| `min_range_ratio` | 0.8 | Ratio minimo AsiaRange/ATR |
| `max_spread_ratio` | 0.25 | Ratio maximo spread/ATR |
| `max_trades_per_day` | 1 | Max operaciones por dia |
| `wick_outlier_multiplier` | 5.0 | Umbral deteccion mechas anomalas |

### Filtro de Outliers (Mechas Anomalas)

Los datos de crypto en Alpaca a veces contienen "flash wicks" — mechas extremas en velas de baja liquidez que no reflejan el precio real. El filtro:

1. Calcula el rango (H-L) de cada vela Asia.
2. Calcula la **mediana** de esos rangos.
3. Si una vela tiene rango > `wick_outlier_multiplier` × mediana → **recorta** sus H/L al cuerpo (max/min de open/close).
4. El conteo de velas NO se reduce (se preserva para el filtro de min velas).

### Bracket Orders

La estrategia almacena los niveles SL/TP en `self._bracket_params`:
```python
self._bracket_params = {
    "take_profit": round(tp, 2),
    "stop_loss": round(sl, 2),
}
```
El engine lee estos parametros en `_process_signal()` y los pasa al broker, que ejecuta una orden `BRACKET` de Alpaca (market entry + limit TP + stop SL, todo atomico).

---

## 7. Frontend — Dashboard React

### Arquitectura de Componentes

```
App.tsx
├── useWebSocket(/ws/live)         # Conexion WS persistente
├── usePolling(getEngineStatus)    # Estado engine cada 10s
├── Header (status badges)
└── Dashboard.tsx
    ├── AccountSummary.tsx         # Polling: account (8s), market (30s), perf (15s)
    ├── PerformanceChart.tsx       # Polling: equity curve (15s)
    │   ├── Area Chart (equity)
    │   └── Bar Chart (daily P&L)
    ├── LiveFeed.tsx               # Events del WebSocket (ultimos 50)
    ├── StrategyCard.tsx × N       # Polling: strategies (8s)
    │   └── Start/Stop buttons → POST /api/strategies/{name}/start|stop
    └── TradeTable.tsx             # Polling: trades (10s)
        └── Filtros: strategy, symbol, side, status, fechas
```

### Comunicacion con Backend

1. **REST Polling:** Cada componente usa `usePolling(fetcher, interval)` para actualizar datos periodicamente. Los intervalos varian: 8s para datos criticos (account, strategies), 15s para graficos, 30s para datos lentos (market status).

2. **WebSocket:** Una unica conexion WS desde `App.tsx`. Los eventos se pasan como prop a `LiveFeed.tsx`. Soporta auto-reconnect con backoff exponencial (1s → 2s → 4s → ... → 30s max).

### Proxy en Desarrollo

`vite.config.ts` configura proxy para que el frontend pueda llamar al backend sin CORS issues:
```typescript
proxy: {
    '/api': { target: 'http://localhost:8000' },
    '/ws':  { target: 'ws://localhost:8000', ws: true },
}
```

### Estilos

Tailwind CSS con paleta dark custom (`dark-50` a `dark-950`). Clases custom en `index.css`: `.card`, `.badge`, `.btn`, `.stat`.

---

## 8. MetaTrader 5 — Expert Advisor

**Archivo:** `mt5/AsiaRangeReversal_M5.mq5` (~775 lineas)

Traduccion fiel de la estrategia Python a MQL5 para ejecutar en MetaTrader 5.

### Diferencias clave con la version Python

| Aspecto | Python (Alpaca) | MQL5 (MT5) |
|---|---|---|
| Spread | Estimado (2% del bar range) | **Real** (Bid/Ask nativos) |
| Timezone | `zoneinfo` nativo | Offset manual broker→Madrid (con auto-DST) |
| Ordenes | Bracket via Alpaca SDK | `CTrade` con SL/TP integrados |
| Datos | DataFrame pandas | Arrays `MqlRates` via `CopyRates()` |
| Visual | Dashboard React | Lineas H/L en grafico + `Comment()` panel |
| Lote | Calculado por engine | **Fijo** (configurable en inputs) |

### Configuracion del Offset Horario

MT5 muestra timestamps en la hora del servidor del broker (no UTC). El EA necesita convertir a hora Madrid:

- `InpBrokerGMTOffset`: Offset GMT del servidor (ej: 2 para UTC+2).
- `InpAutoDetectDST`: Si `true`, calcula automaticamente si Madrid esta en CET (UTC+1, invierno) o CEST (UTC+2, verano).

### Instalacion

1. Copiar `AsiaRangeReversal_M5.mq5` a `[Datos MT5]/MQL5/Experts/`
2. Compilar en MetaEditor (F7)
3. Arrastrar al grafico BTCUSD M5
4. Configurar `InpBrokerGMTOffset` segun broker
5. Activar "Allow Algo Trading"

---

## 9. Flujo de Datos en Tiempo Real

```
Cada 5 minutos (intervalo M5):

1. TradingEngine._strategy_loop() despierta
2. Engine pide datos: broker.get_bars("BTC/USD", "5Min", 200)
3. AlpacaClient detecta "/" → usa CryptoHistoricalDataClient
4. DataFrame OHLCV llega al engine
5. Engine pasa {symbol: DataFrame} a strategy.calculate_signals()
6. AsiaRangeReversal:
   a. Localiza timestamps a Europe/Madrid
   b. Evalua estado de la maquina de estados
   c. Si estado C y no trade_taken:
      - Lee ultima barra
      - Compara H/L con AsiaHigh/AsiaLow
      - Si toca extremo y spread OK → retorna Signal.BUY o SELL
7. Engine recibe señal → llama risk_manager.evaluate_order()
8. Si aprobada → lee strategy._bracket_params (SL/TP)
9. Engine → broker.submit_order(symbol, side, qty, tp, sl, tif="gtc")
10. AlpacaClient → MarketOrderRequest con OrderClass.BRACKET
11. Alpaca ejecuta: entry + TP limit + SL stop
12. Engine emite evento → WebSocket → Dashboard actualiza
```

---

## 10. Configuracion y Despliegue

### Variables de Entorno (`.env`)

```bash
# Alpaca API (paper o live)
ALPACA_API_KEY=PK...
ALPACA_SECRET_KEY=Cv...
ALPACA_BASE_URL=https://paper-api.alpaca.markets/v2

# Base de datos
DATABASE_URL=sqlite:///./trading_bot.db

# Aplicacion
APP_ENV=development
LOG_LEVEL=INFO
```

### Arrancar el Sistema

```bash
# 1. Backend
cd AutomatizacionesOle
pip install -r backend/requirements.txt
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload

# 2. Frontend
cd frontend
npm install
npm run dev

# 3. Abrir dashboard
# http://localhost:5173
```

### Para Produccion

- Cambiar `ALPACA_BASE_URL` a `https://api.alpaca.markets/v2` (live)
- Cambiar `APP_ENV=production`
- Usar `--no-reload` en uvicorn
- Considerar PostgreSQL en vez de SQLite
- Configurar HTTPS con reverse proxy (nginx/caddy)

---

## 11. Decisiones de Diseno Clave

### 1. Estrategias como plugins
Las estrategias se descubren automaticamente. Crear una nueva es tan simple como agregar un `.py` en `strategies/` con una clase que herede de `BaseStrategy`. No hace falta tocar ni el engine, ni la API, ni el frontend.

### 2. Broker como interfaz abstracta
`BrokerInterface` permite cambiar de Alpaca a otro broker (Interactive Brokers, Binance, etc.) sin tocar el core. Solo hay que implementar la interfaz.

### 3. Async por estrategia
Cada estrategia corre en su propia `asyncio.Task` con su propio intervalo. Esto permite tener estrategias en diferentes timeframes corriendo simultaneamente sin bloquearse.

### 4. skip_market_check
Crypto opera 24/7 pero los mercados de stocks tienen horario. En vez de complicar el engine, cada estrategia declara `skip_market_check = True/False` y el engine respeta esa configuracion.

### 5. Bracket orders desde la estrategia
La estrategia calcula SL/TP y los almacena en `_bracket_params`. El engine los lee y los pasa al broker. Esto mantiene la logica de niveles en la estrategia (donde pertenece) sin acoplar el engine a la implementacion de SL/TP.

### 6. Filtro de outliers por mediana
Para protegerse de datos sucios (flash wicks en crypto), se usa la mediana de rangos como referencia (robusta ante outliers) en vez de la media. El recorte al cuerpo (open/close) preserva datos utiles sin descartar la vela entera.

### 7. Timezone explicita
Toda la logica temporal de la estrategia Asia se ejecuta en `Europe/Madrid` con conversion explicita. Esto asegura que el horario de verano (CET/CEST) se maneja correctamente sin depender del timezone del servidor.

### 8. Event-driven WebSocket
El engine emite eventos (`on_event` callbacks) que el WebSocket retransmite. El frontend nunca hace polling agresivo para datos criticos como ordenes — los recibe en tiempo real.

---

## 12. Limitaciones Conocidas y Trabajo Futuro

### Limitaciones Actuales
- **SQLite** no es ideal para produccion con multiples escritores concurrentes.
- **scheduler.py** esta vacio (placeholder) — no hay programacion de tareas aun.
- **Backtester** no simula slippage ni comisiones realistamente.
- **Risk Manager** no persiste estado entre reinicios del servidor.
- **MT5 EA** requiere configuracion manual del offset horario del broker.
- **No hay tests automatizados** (unit/integration).
- **No hay autenticacion** en la API/dashboard.

### Trabajo Futuro Potencial
- Añadir mas estrategias (momentum, mean reversion, etc.).
- Implementar scheduler para tareas periodicas (snapshots de performance, limpieza de logs).
- Migrar a PostgreSQL para produccion.
- Añadir autenticacion JWT al dashboard.
- Implementar alertas (Telegram, email, Discord).
- Tests automatizados con pytest.
- Docker compose para despliegue simplificado.
- Optimizar backtester con vectorizacion (sin loop bar-a-bar).
