---
name: run-frontend-next
description: Build, run, and drive the frontend/next Next.js web app (Butler.works — DART financial dashboard). Use when asked to start the frontend, run the dev server, take a screenshot of a page, or click through/test its UI.
---

Next.js 15 (App Router, Turbopack) single-page dashboard. All navigation
is client-side state, not URL routes — one `/` page whose Header tabs
swap the rendered component (see `src/app/InteractiveLayout.js`). It
calls the `simple_fast_api` backend (see that project's own
`run-simple-fast-api` skill) at `NEXT_PUBLIC_API_BASE_URL` (default
`http://localhost:8000`) for all data.

`chromium-cli` is not available in this environment, so driving happens
via a small Playwright REPL at
`.claude/skills/run-frontend-next/driver.mjs` — same idea as
`chromium-cli` (nav/click/fill/screenshot piped over stdin), just
hand-rolled with `playwright`'s `chromium.launch()` directly.

All paths below are relative to `frontend/next/`.

## Prerequisites

Node 20 (tested with v20.14.0) and npm. No OS packages were needed on
macOS; on Linux you'd additionally need Chromium's shared libs, but this
was verified on Darwin only.

## Setup

```bash
npm install                      # installs playwright (devDependency) too
npx playwright install chromium  # downloads the Chromium binary (~170MB)
```

The backend needs to be running for any page that fetches data (i.e.
everything except the empty shell). From the repo root:

```bash
cd ../../simple_fast_api
.claude/skills/run-simple-fast-api/smoke.sh &   # or: source .venv/bin/activate && TELEGRAM_BOT_TOKEN="" python main.py
```

Set `NEXT_PUBLIC_API_BASE_URL` in `.env.local` if the backend isn't on
`http://localhost:8000`.

## Build

No separate production build needed for driving the dev server. If you
need a production build: `npm run build`.

## Run (agent path)

Start the dev server in the background, then drive it with the
Playwright REPL:

```bash
npm run dev > /tmp/next_dev.log 2>&1 &
until curl -sf http://localhost:3000 > /dev/null; do sleep 1; done
```

Pipe a script to the driver's stdin (it queues commands and runs them
strictly in order — see Gotchas):

```bash
node .claude/skills/run-frontend-next/driver.mjs <<'EOF'
launch
nav /
ss 01-home
click-text 배당 분석
fill input 삼성전자
click-text 조회
wait canvas
ss 02-dividend-result
console --errors
quit
EOF
```

This is a verified real run: it switches to the "배당 분석" (dividend)
tab, searches "삼성전자" (Samsung Electronics), waits for the Chart.js
`<canvas>` to appear, and screenshots the rendered bar chart. Screenshots
land in `/tmp/shots/` (override with `SCREENSHOT_DIR`).

### Commands

| command | what it does |
|---|---|
| `launch` | launch headless Chromium, open a page |
| `nav <path-or-url>` | navigate; bare path is resolved against `DEV_URL` (default `http://localhost:3000`) |
| `ss [name]` | screenshot → `/tmp/shots/<name>.png` |
| `click <css-sel>` | Playwright `.click()` |
| `click-text <text>` | click first element containing `<text>` |
| `fill <css-sel> <value>` | fill an input |
| `press <key>` | keyboard press |
| `wait <css-sel>` | wait up to 10s for a selector |
| `wait-for-text <text>` | wait up to 10s for text to appear anywhere on the page |
| `text [css-sel]` | print `innerText` of selector (or `body`) |
| `eval <js-expr>` | evaluate JS in the page, print JSON result |
| `console --errors` | print captured console errors / page errors since `launch` |
| `quit` | close the browser |

Stop the dev server with `pkill -f "next dev"` when done.

## Run (human path)

```bash
npm run dev
# → http://localhost:3000 . Ctrl-C to stop.
```

## Test

No test suite configured in `package.json` (only `dev`/`build`/`start`/`lint`).

---

## Gotchas

- **Piped/heredoc input races the async handlers.** Node's `readline`
  fires `line` events for every buffered line without waiting for a
  previous line's `async` handler to resolve, so commands like `nav`
  would run before `launch`'s `chromium.launch()` had actually
  finished, silently failing with `ERROR: launch first`. The driver
  fixes this by chaining every command through a single `queue`
  promise. Don't remove that — reverting to a bare `await fn()` inside
  the `line` handler brings the race back.
- **`close` fires before the queue drains.** With piped/redirected
  stdin, the `close` event fires as soon as EOF is hit — often *before*
  a slow command (like `launch`) has completed — and used to call
  `process.exit(0)` immediately, killing the process mid-flight. The
  fix: `rl.on('close', ...)` awaits the same `queue` promise first.
- **Don't wait on ambiguous text for "did the data load" checks.** The
  static heading is literally "배당 분석" (dividend *analysis*, the tab
  name) and the loading spinner's placeholder text also contains "배당"
  — waiting on `wait-for-text 배당` matches instantly, before the async
  fetch resolves, and you screenshot the loading spinner instead of the
  result. Wait on something that only exists post-load, e.g. `wait
  canvas` (the Chart.js chart) or the specific resolved-name heading
  text (`"{company} — 배당금 추이"`).
- **All routing is client-side state, not URL routes.** There's no
  `/dividend` URL to `nav` to directly — every page (`AnalysisPage`,
  `DividendPage`, etc.) is a `switch` branch in
  `src/app/InteractiveLayout.js`, and you reach it by clicking the
  matching tab label in the Header (`click-text <tab-label>`), not by
  navigating a path.
- **Empty results if the backend isn't running or has no cached data**
  for the company you search — you'll get a fetch error/empty chart, not
  a hard crash. Check `curl http://localhost:8000/cache/status` from
  the backend to pick an already-cached company (`삼성전자` was cached
  at the time this was written) if you want a fast, quota-free result.
- **First `nav` after `npm run dev` can be slow** (Turbopack compiles
  routes on demand) — this wasn't an issue in practice (page.js is
  trivial), but if you add heavier routes, prefer `wait <selector>`
  over a fixed `sleep`.
- **A pre-existing hydration-mismatch warning always shows up in
  `console --errors`** on the company-search input (`style={{caret-color:
  "transparent"}}` differs between SSR and client render). It appeared
  identically across multiple clean runs of this driver, unrelated to
  anything the driver does — don't mistake it for a regression you
  caused. The chart still renders correctly despite it (verified via
  screenshot).

## Troubleshooting

- **`ERROR: launch first` on every command right after starting the
  driver**: you hit the readline race described in Gotchas — make sure
  you're running the driver as committed (with the `queue` chaining),
  not an ad-hoc rewrite.
- **Screenshot shows the "조회 중..." spinner instead of the chart**:
  you waited on text that also appears in the loading state. Wait on
  `canvas` or the post-load heading instead (see Gotchas).
- **Chart is blank / fetch fails in `console --errors`**: the backend
  (`simple_fast_api`) isn't running, or `NEXT_PUBLIC_API_BASE_URL` in
  `.env.local` doesn't point at it. Start the backend first (see
  Setup).
