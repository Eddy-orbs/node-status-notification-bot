# node-status-notification-bot

A Python Telegram monitoring bot. It periodically checks the `Boyar` status for registered Ethereum addresses (or, in manager mode, for all nodes) and sends a notification only when a status changes from **Green → Yellow**.

## Features

- `/start`: Bot introduction and command overview
- `/set address <ethereum_address>`:
  - Validates the address (`0x` + 40 hex characters)
  - Stores and looks up addresses internally without the `0x` prefix, lowercased
  - Saves the address and enables monitoring (if the address exists in the current status JSON)
  - Saves the current status as the baseline (`last_status`)
  - No alert immediately after registration
- `/stop`: Disables monitoring for the current user (for whichever mode is active)
- `/status`: Shows monitoring mode, address (single mode), ON/OFF, and last status where applicable
- `/resume`: Restarts monitoring for the active mode and resets the baseline from the current JSON (no immediate alert)
- `/monitorAll on|off`:
  - `on`: Enables manager-style monitoring of all nodes under `AllRegisteredNodes` (single-address settings stay in the DB; manager mode takes priority while on)
  - `off`: Turns off manager monitoring; if a saved single address exists and is present in the JSON, single-address monitoring resumes
- Scheduled checks:
  - Default interval: **1800 seconds (30 minutes)**
  - Fetches `STATUS_JSON_URL` **once per cycle** and reuses the payload for all active users
  - **Green → Yellow** transitions trigger Telegram alerts
  - Other changes update baselines without notifying
  - Missing paths or addresses are handled safely as `UNKNOWN`

## Project layout

- `app/main.py`: App bootstrap, polling, scheduler registration
- `app/bot_handlers.py`: Handlers for `/start`, `/set`, `/stop`, `/status`, `/resume`, `/monitorAll`
- `app/monitor_service.py`: JSON fetch, status evaluation, alert rules
- `app/storage.py`: SQLite schema and queries
- `app/config.py`: `.env` loading and settings
- `app/models.py`: Constants and validation helpers
- `main.py`: Entry point
- `Dockerfile`
- `docker-compose.yml`
- `.env.example`

## Environment variables

1. Copy the example file:

```bash
cp .env.example .env
```

2. Edit `.env`:

```env
TELEGRAM_BOT_TOKEN=your_real_telegram_bot_token
STATUS_JSON_URL=https://status.orbs.network/json
CHECK_INTERVAL_SECONDS=1800
SQLITE_DB_PATH=/app/data/app.db
LOG_LEVEL=INFO
```

## Running locally

> For consistency between your laptop and server, running with Docker Compose is recommended.

```bash
docker compose up --build
```

Run in the background:

```bash
docker compose up -d --build
```

View logs:

```bash
docker compose logs -f app
```

Stop:

```bash
docker compose down
```

## Docker Compose behavior

- Single `app` service
- Injects variables from `.env` via `env_file`
- Mounts host `./data` to `/app/data` in the container
- `restart: unless-stopped`
- Logs go to stdout/stderr

## Data storage

- SQLite path inside the container: `/app/data/app.db`
- On the host: `./data/app.db`
- The `./data` directory persists across container recreation, so the database is kept

## Example deployment (Ubuntu server)

```bash
# 1) Place the project on the server (e.g. git clone or rsync)

# 2) Prepare environment file
cp .env.example .env
# Set TELEGRAM_BOT_TOKEN in .env

# 3) Run
docker compose up -d --build

# 4) Check status and logs
docker compose ps
docker compose logs -f app
```

## Common commands

```bash
# Rebuild and (re)start containers
docker compose up -d --build

# Follow app logs
docker compose logs -f app

# Stop the stack
docker compose down

# Restart only the app container
docker compose restart app
```
