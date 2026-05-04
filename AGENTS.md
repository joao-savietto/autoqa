# AutoQA — Agent Instructions

## Stack
Django 5.1 + DRF, SQLite, Tailwind CSS, HTMX, fastmcp MCP server, Selenium Chromium.

## Project Layout
- `backend/` — Django project config (`backend.settings` is the settings module)
- `core/` — Single Django app: all models, views, API viewsets, serializers, tests
- `mcp_server/` — Standalone MCP server (streamable-http) that wraps the Django REST API via httpx
- `agents/` — Agent persona files, copied to OpenCode config by `setup.sh`
- `templates/` — Django templates (HTMX partials in `partials/`)
- `static_src/input.css` → `staticfiles/css/output.css` (Tailwind pipeline)

## Setup

**Docker (primary):** `bash setup.sh` — starts compose, creates superuser interactively, generates API keys, registers MCP in OpenCode config at `~/.config/opencode/config.json`.

**Local dev:** `bash run_dev.sh` — creates venv, installs deps, generates `.env`, builds Tailwind, runs migrations. Then `python manage.py createsuperuser` + `python manage.py runserver` (port 8000).

**Full stack Docker:** `docker compose up --build` (web:8234, mcp_server:3157, chrome:9222/4444/7900). Docker is self-contained — multi-stage Dockerfile builds Tailwind, entrypoint runs migrate + collectstatic.

## Commands
| Task | Command |
|------|---------|
| Run tests | `python manage.py test` (all in `core/tests.py`) |
| Run single test | `python manage.py test core.tests.TestPlanModelTest` |
| Migrate | `python manage.py migrate` |
| Build CSS | `npm run build:css` |
| Watch CSS | `npm run watch:css` |
| Collect static | `python manage.py collectstatic --noinput` |

## Security Testing

AutoQA supports autonomous security assessments alongside QA testing. A `plan_type` field (`qa`/`security`) on TestPlan distinguishes between the two.

### Docker Service
- **kali**: `kalilinux/kali-rolling` image with 4GB memory limit. Shared volume at `./security_output` stores scan results.

### MCP Tools
| Tool | Description |
|------|-------------|
| `run_security_scan(target, phase, tools, run_id)` | Execute security tools via Kali container |
| `get_security_report(run_id)` | Retrieve scan results from shared volume |
| `get_kali_status()` | Check Kali container health and available tools |

### Agent & Command Files
| File | Purpose |
|------|---------|
| `agents/SecurityAnalyst.md` | Security analyst agent persona (6-phase routine, codebase-based discovery) |
| `agents/runsecurity.md` | Command to trigger `/runsecurity` |
| `agents/BlackBoxAnalyst.md` | Black-box analyst agent persona (Chrome DevTools + JS discovery) |
| `agents/runblackbox.md` | Command to trigger `/runblackbox` |

### Two Security Assessment Modes

| Mode | Agent | Discovery Method | Best For |
|------|-------|-----------------|----------|
| **Codebase-based** | SecurityAnalyst | Reads source code via `@explore` subagent | Projects where agent has filesystem access |
| **Black-box** | BlackBoxAnalyst | Chrome DevTools + JS file analysis | Deployed apps, third-party systems, no code access |

### Security Routine (6 Phases)
1. **Reconnaissance** — nmap, whatweb, httpx, subfinder
2. **Vulnerability Assessment** — nuclei, gobuster, ffuf, nikto
3. **Authentication Testing** — hydra (rate-limited), session analysis
4. **Input Validation** — sqlmap (read-only), manual XSS/XXE checks
5. **Configuration Security** — testssl, header analysis, CORS
6. **Reporting** — synthesize findings into incidents

### Safety Constraints
- Read-only modes only (sqlmap `--batch --crawl`, no exploit modules)
- Rate-limited tools (hydra max 3 threads)
- No destructive actions (no data deletion, no privilege escalation)
- Target whitelist enforcement

## Tailwind CSS
Source: `static_src/input.css`. Output: `staticfiles/css/output.css`.
Content paths: `./templates/**/*.html`, `./core/**/*.py`. Rebuild after template changes.

## Docker Services
- **web** — Django + gunicorn on `:8234`. Entrypoint runs `migrate` + `collectstatic`, then gunicorn with `--reload`. `CHROME_HOST` overridden to `chrome` in compose.
- **mcp_server** — FastMCP server on `:3157` (streamable-http). `MCP_API_URL` points to `http://web:8234`.
- **chrome** — `selenium/standalone-chromium:latest` with CDP on `:9222`.

For live CSS development, run `npm run watch:css` on the host in a separate terminal.

## API
All endpoints under `/api/`. DRF viewsets for TestPlan, TestStep, TestRun, RunStepResult, Incident, APIKey.
Auth: Session (web UI) or API key (`rest_framework_api_key`) for agents/MCP. Custom `IsAuthenticatedOrAPIKey` permission.
Chrome CDP endpoint: `GET /api/chrome-connection/` returns `{connection_string, host, port}`.
API key management UI at `/api-keys/` (superuser only).

Local dev default: Django on `:8000`, MCP on `:3157`. Docker: Django on `:8234`, MCP on `:3157`.

## MCP Server
`mcp_server/server.py` — HTTP/streamable-http transport on port 3157. Separate Dockerfile.
MCP clients pass the REST API key via the `X-API-Key` header. Server forwards it as `Authorization: Api-Key <key>` to Django.
`MCP_API_URL` defaults to `http://web:8000` (overridden to `http://web:8234` in compose).

## Models (core app)
`TestPlan` → `TestStep` (ordered, active flag) → `TestRun` → `RunStepResult` → `Incident`.
See `core/models.py` for full schema.

## Env
`.env` via `django-environ`. Required: `SECRET_KEY`, `DATABASE_URL`, `DEBUG`.
Chrome: `CHROME_HOST`, `CHROME_DEBUG_PORT`. MCP: `MCP_API_URL`.
See `.env.example` for full template.

## Scope Boundary
AutoQA is a **state tracker only**. It does NOT control browsers, parse code, or execute tests.
Agents connect to Chrome CDP independently and report results back via MCP/REST.

## Gotchas
- First-time launch: if no users exist, `/` and `/login/` redirect to `/register/`. The first registered user becomes superuser+staff automatically.
- `TestStep` has a `unique_together` constraint on `(plan, order_index)`. Reordering steps uses the `reorder` action on the TestStepViewSet.
- `RunStepResult` has a `unique_together` constraint on `(run, step)` — you can't log a result twice for the same step in the same run.
- `TestRun.completed_at` is set server-side by the `complete` action; don't set it manually.
- The MCP server extracts `X-API-Key` from the request via middleware and forwards it as `Authorization: Api-Key <key>` to Django. Don't pass the key directly in MCP tool calls — it's handled by the transport layer.
- `staticfiles/` is git-ignored; `staticfiles/css/output.css` is built from `static_src/input.css` by Tailwind.
- `db.sqlite3` is git-ignored. Local dev uses SQLite; Docker also uses SQLite by default.
- `entrypoint.sh` runs `migrate --noinput` and `collectstatic --noinput` on every container start.
- The `complete` endpoint on TestRunViewSet sets `completed_at = timezone.now()` — do not set it in the request body.
