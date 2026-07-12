---
name: run-simple-fast-api
description: Build, run, and drive the simple_fast_api FastAPI server (DART report analyzer + Telegram bot). Use when asked to start simple_fast_api, run its server, test its endpoints, or check that the Telegram bot integration works.
---

FastAPI server that downloads DART (Korean financial disclosure) reports,
computes dividend/valuation/scoring analysis, and exposes a Gemini-backed
Telegram bot on top of it. Drive it via
`.claude/skills/run-simple-fast-api/smoke.sh` — it launches the server in
the background, curls representative endpoints, and tears it down.

All paths below are relative to `simple_fast_api/`.

## Prerequisites

Python 3.12 (tested with 3.12.3) and `pip`. No system packages beyond a
normal Python toolchain were needed.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -q -r requirements.txt
```

### Environment

`.env` in this directory already has real values checked in locally (not
committed to git). `main.py` raises `ValueError` at startup if
`DART_API_KEY` or `GEMINI_API_KEY` are empty — both must be set to start
the app at all.

| Variable | Required | Notes |
|---|---|---|
| `DART_API_KEY` | Yes | Korean DART OpenAPI key — startup fails without it |
| `GEMINI_API_KEY` | Yes | Startup fails without it |
| `TELEGRAM_BOT_TOKEN` | No | If set, the app starts **live long-polling** against that real bot on startup. Leave empty to run the HTTP API only. |
| `WEBHOOK_URL` / `WEBHOOK_SECRET_TOKEN` | No | Only used if you switch the bot to webhook mode; not exercised by the driver |

**This repo's `.env` has a real `TELEGRAM_BOT_TOKEN`.** Starting the app
with it set connects to the actual Telegram bot and starts polling for
real updates — do this only if you intend to interact with the live bot.
The driver script blanks it out by default (see below).

## Build

No separate build step (interpreted Python).

## Run (agent path)

```bash
.claude/skills/run-simple-fast-api/smoke.sh
```

What it does:
1. Creates/reuses `.venv`, installs `requirements.txt`.
2. Launches `python main.py` in the background with `TELEGRAM_BOT_TOKEN`
   temporarily blanked (so it does **not** connect to the live Telegram
   bot), logging to `/tmp/simple_fast_api_smoke.log`.
3. Polls `GET /` until the server answers (up to 60s — the first run is
   slow because matplotlib builds its font cache).
4. Curls `/`, `/cache/status`, `/dividend-data/{company}`, and
   `/valuation/{company}` (company defaults to `삼성전자`, already
   present in the on-disk cache from prior runs) and prints the JSON.
5. Kills the server on exit (including on failure, via `trap`).

Options:

```bash
COMPANY=SK하이닉스 ./smoke.sh   # use a different company for the data checks
PORT=8001 ./smoke.sh           # run on a different port
ENABLE_BOT=1 ./smoke.sh        # ALSO start live Telegram polling — only do this deliberately
```

Interactive docs (Swagger UI) are at `http://127.0.0.1:8000/docs` while
the server is running.

## Run (human path)

```bash
source .venv/bin/activate
python main.py
# → http://127.0.0.1:8000 , Ctrl-C to stop
```

Runs in the foreground; the bot will poll live if `TELEGRAM_BOT_TOKEN`
is set in `.env`. Prefer the smoke script for agent use.

## Test

No automated test suite exists in this directory (no `pytest`/`tests/`
found).

---

## Gotchas

- **Startup hard-fails on missing keys.** `main.py` raises `ValueError`
  before the app object is even created if `DART_API_KEY` or
  `GEMINI_API_KEY` is empty — there's no way to boot the HTTP API without
  both, even if you only want to test unrelated endpoints.
- **First launch is slow and silent.** The process prints nothing for
  ~15-20s while matplotlib builds its font cache (`Matplotlib is building
  the font cache; this may take a moment.`), then goes quiet again until
  Uvicorn logs "Application startup complete." A short readiness poll
  will time out during this window — the driver polls for up to 60s.
- **A real Telegram bot token lives in this repo's `.env`.** Launching
  `main.py` normally starts live long-polling against it immediately
  (`bot_app.updater.start_polling(...)` in the lifespan hook) and also
  registers cron jobs (daily 09:00 KST notification, 30-min filing-alert
  poll). The smoke driver avoids this by overriding
  `TELEGRAM_BOT_TOKEN=""` for the subprocess; only pass `ENABLE_BOT=1` if
  you actually want to talk to the live bot.
- **Endpoints hit real external services.** `/dividend-data`,
  `/valuation`, etc. call the real DART OpenAPI and Yahoo Finance
  (`yfinance`) with the real key from `.env` — there's no mock mode.
  Pick already-cached companies (check `/cache/status` first) to avoid
  unnecessary external calls; `삼성전자` was cached from prior use at the
  time this skill was written.

## Troubleshooting

- **`curl` to `/` fails for the first ~20s after launch**: normal — the
  server is still building the matplotlib font cache and hasn't started
  Uvicorn yet. Keep polling; check `/tmp/simple_fast_api_smoke.log` if it
  never comes up.
- **`ValueError: DART_API_KEY가 설정되지 않았습니다...`** on launch: the
  `.env` file's `DART_API_KEY` or `GEMINI_API_KEY` is empty. Populate it
  — there's no bypass in code.
