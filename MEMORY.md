# Memory Index — autoqa

_Pointers only. Full facts live in FTS memory (region `autoqa`) — recall before acting._

- TestStep order_index auto-assignment on create (serializer + MCP) — recall before touching step creation
- Skip-steps range endpoint (`skip_steps` action + MCP tool) — recall before run-skip work
- Gotcha: MCP dropped `section` on step create (fixed 2026-09-16) + fastmcp 3.x required in venv — recall before MCP server edits
- AutoQA plan 'Skip Steps & Section Create' (plan_id=24) — recall before QA runs on this project

## ⚠️ Gotchas
- `mcp_server/requirements.txt` (fastmcp>=3.0) is the source of truth for the MCP venv — the project venv drifted to fastmcp 2.10.6 and broke imports; use 3.x
- `mcp_autoqa_bulk_log_step_results` MCP tool is broken server-side — log results one-by-one via `log_step_result`
- Live dev backend runs via `venv/bin/python manage.py runserver 8000` (Django auto-reload picks up API changes)
