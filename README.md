# AutomatizacionesOle - Bot de Trading con Alpaca

Sistema de trading automatizado con arquitectura modular de estrategias, API REST, WebSocket en tiempo real y dashboard web.

## Arquitectura

```
backend/          → Motor de trading, API FastAPI, estrategias
frontend/         → Dashboard React + TypeScript
```

## Quick Start

### 1. Configurar variables de entorno

```bash
cp .env.example .env
# Editar .env con tus API keys de Alpaca
```

### 2. Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Linux/Mac

pip install -r requirements.txt
python main.py
```

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

## Estructura del Proyecto

```
AutomatizacionesOle/
├── backend/
│   ├── main.py                  # Entry point FastAPI
│   ├── config.py                # Configuracion (API keys, DB, etc.)
│   ├── requirements.txt
│   ├── core/
│   │   ├── engine.py            # Orquestador principal
│   │   ├── scheduler.py         # Programacion de ejecucion
│   │   └── risk_manager.py      # Gestion de riesgo
│   ├── strategies/
│   │   ├── base_strategy.py     # Clase abstracta BaseStrategy
│   │   ├── sma_crossover.py     # Cruce de medias moviles
│   │   ├── rsi_strategy.py      # RSI Strategy
│   │   └── registry.py          # Auto-descubrimiento de estrategias
│   ├── broker/
│   │   ├── alpaca_client.py     # Wrapper sobre alpaca-py SDK
│   │   └── broker_interface.py  # Interfaz abstracta
│   ├── data/
│   │   ├── market_data.py       # Datos en tiempo real e historicos
│   │   └── indicators.py        # Calculos tecnicos (SMA, RSI, MACD)
│   ├── api/
│   │   ├── routes/
│   │   │   ├── strategies.py    # CRUD estrategias, start/stop
│   │   │   ├── trades.py        # Historial de operaciones
│   │   │   ├── performance.py   # Metricas y rendimiento
│   │   │   └── account.py       # Info de la cuenta Alpaca
│   │   └── websocket.py         # WS para updates en tiempo real
│   └── models/
│       ├── database.py          # Setup SQLAlchemy / SQLite
│       ├── trade.py             # Modelo Trade
│       ├── strategy_state.py    # Estado persistente de cada estrategia
│       └── performance.py       # Modelo de metricas
├── frontend/
│   ├── package.json
│   └── src/
│       ├── App.tsx
│       ├── components/
│       ├── hooks/
│       └── services/
├── .env.example
├── .gitignore
└── README.md
```

## Estrategias

El sistema usa un patron de plugins. Para crear una nueva estrategia:

1. Crear un archivo en `backend/strategies/`
2. Heredar de `BaseStrategy`
3. Implementar `calculate_signals()` y `get_parameters()`

La estrategia se descubre automaticamente al iniciar el sistema.

## API Endpoints

| Metodo | Ruta | Descripcion |
|--------|------|-------------|
| GET | `/api/strategies` | Lista de estrategias |
| POST | `/api/strategies/{name}/start` | Arrancar estrategia |
| POST | `/api/strategies/{name}/stop` | Parar estrategia |
| GET | `/api/strategies/{name}/performance` | Metricas |
| GET | `/api/trades` | Historial de operaciones |
| GET | `/api/account` | Info de cuenta |
| WS | `/ws/live` | Stream en tiempo real |

## Entorno

- **Paper Trading**: `ALPACA_BASE_URL=https://paper-api.alpaca.markets`
- **Live Trading**: `ALPACA_BASE_URL=https://api.alpaca.markets`

> **IMPORTANTE**: Siempre probar primero en paper trading antes de usar dinero real.

## Licencia

Proyecto privado.
