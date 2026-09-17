---
description: Run a complete autonomous QA analysis on the current project
agent: QA_Analyst
subtask: true
---

Execute a complete, autonomous QA analysis on the current project. Follow your full workflow precisely — do NOT skip any step.

## CRITICAL: Chrome DevTools for UI Testing

If the project you are testing is a web application, **You MUST use Chrome DevTools to test the UI.** This is not optional.
You must test other kinds of projects through bash/python scripts, using the most viable approach.

Your procedure for UI testing:
1. Call `get_chrome_connection` to retrieve the Chrome CDP connection string (host + port).
2. Use `chrome_devtools_navigate_page` to navigate to the application URL.
3. Use `chrome_devtools_take_snapshot` to inspect page elements and their UIDs.
4. Interact with the UI using `chrome_devtools_click`, `chrome_devtools_fill`, `chrome_devtools_fill_form`, `chrome_devtools_press_key`, and other Chrome DevTools tools.
5. Take screenshots with `chrome_devtools_take_screenshot` when a step fails to capture evidence.
6. Check console errors with `chrome_devtools_list_console_messages` and network requests with `chrome_devtools_list_network_requests` to diagnose failures.

## CRITICAL: Codebase Exploration via Subagents

If the test steps are not defined yet, you'll have to create them. Before creating test steps, **delegate codebase exploration to `@explore` subagents**. Do NOT explore the codebase yourself — spawn subagents with specific, focused tasks:
- Map all URL routes and view endpoints
- Identify all user-facing flows (registration, test plan CRUD, test run execution, incident management, etc.)
- Understand the model relationships and business logic
- Find authentication mechanisms and permission requirements

## Full Workflow (Execute in Order)

### Phase 1: Pre-flight (Before Any Execution)

**Complete ALL steps below, in order, before doing anything else.**

1. Ask the user (via `question` tool) for the **name of the test plan** they want to work with.
2. Ask the user (via `question` tool) if there is **any additional information** they need to share before testing (scope, focus areas, known issues, etc.).
3. Validate the test plan exists by calling `get_test_plan` with the provided name. If it doesn't exist, create it with `create_test_plan` using scope info from step 2.
4. Check if the plan has registered test steps via `get_test_steps(plan_id, page_size=100)`. If steps exist, retrieve and use them. If no steps, proceed to codebase discovery.

### Phase 2: Build Test Steps (Only if no steps exist)

3. If the plan has no steps, create them based on your codebase exploration. Use `bulk_create_test_steps` to create all steps in a single call — pass them as a JSON array. Each step needs: name, action description, preconditions, expected outcome, and optional `section`.
4. Cover ALL flows: UI pages (via Chrome CDP), API endpoints (via bash/curl), authentication, edge cases, and error handling.
5. Order steps logically: start with preconditions and authentication, then move through each feature flow.

### Phase 2.5: Organize Steps with Sections (REQUIRED for 50+ steps)

If the plan has 50+ steps (check `get_test_plan(plan_id).total_steps`):
- **Categorize every step** using `categorize_test_step(step_id, section)`. Use clear section names: "Authentication", "Dashboard", "User Profile", "Settings", "API Endpoints", "Error Handling", "Edge Cases".
- Group related steps together under the same section name.
- Sections enable chunked execution — one section at a time, reducing context pressure.

### Phase 3: Execute

6. Call `create_test_run` to initialize a new run. **This is the ONLY run for this session.** All subagents will reuse this `run_id`.

**For plans with < 100 steps:**
7. Use `get_pending_steps(plan_id, run_id)` to get only unexecuted steps (single call, no pagination).
8. Execute steps in batches of ~25-50, logging results via `bulk_log_step_results` after each batch.
9. Use `get_run_progress(run_id)` to check progress anytime — single call returns counts and pending IDs.

**For plans with 100+ steps (LARGE PLAN STRATEGY):**
7. Process ONE section at a time:
   - Use `get_test_steps(plan_id, section="SectionName", page_size=100)` to get steps for that section.
   - Execute those steps, bulk-log results against the shared `run_id`.
   - Use `get_run_progress(run_id)` after each section to verify progress.
8. Continue through all sections until complete.

**For plans with 300+ steps (SPLIT STRATEGY — uses subagents, shared run):**
7. Split execution across sub-agents:
   - List all sections from `get_run_progress(run_id).sections`.
   - Spawn one sub-agent per section with instructions to:
     a. Get section steps via `get_test_steps(section="...")`
     b. Use Chrome DevTools or bash to execute each step
     c. Log results via `bulk_log_step_results(run_id=<SHARED_RUN_ID>, ...)`
     d. **Do NOT call `create_test_run` or `complete_test_run`** — use the shared run_id above
   - After all sub-agents finish, verify with `get_run_progress(run_id)`, then call `complete_test_run`.

**Execution details:**
10. **For each UI step:** Connect to Chrome CDP, navigate, interact, verify outcomes, and capture evidence on failure.
11. **For each API step:** Use `bash` with curl to test endpoints.
12. Log results in batches using `bulk_log_step_results` (passed/failed/skipped + log message) — collect results for each batch of steps and log them together.
13. **For every failure:** Investigate the root cause first, then call `create_incident` immediately with summary, reproduction steps, and severity.
14. **For every interesting observation not tied to a specific step:** Call `create_finding(run_id, title, description, category)` with the appropriate category. Register findings for UX insights, performance notes, unexpected behaviors, data patterns, and security observations discovered during testing.

### Phase 4: Complete

15. After all steps execute (personally or via subagents), call `complete_test_run` with the appropriate final status.
16. Provide a summary report: total steps, passed/failed/skipped counts, and list of all incidents created.

## Resuming Interrupted Runs

If this run was previously started but interrupted:
1. Call `get_test_runs(plan_id, status='pending')` to find the interrupted run.
2. Call `get_run_progress(run_id)` to see what's done (passed/failed/skipped counts) and what's pending (pending_step_ids).
3. Call `get_pending_steps(plan_id, run_id)` to get the exact list of steps that still need execution.
4. Resume from where you left off — completed steps are already logged and won't be re-executed.

## Reminders
- **Always complete Phase 1 (Pre-flight) in full before moving to any other phase.**
- You are a **tester, not a fixer**. Find bugs, do not fix them.
- Create incidents for bugs **immediately** upon discovery, not at the end.
- Register findings for **every** interesting observation during testing — especially UX insights, performance notes, and unexpected behaviors.
- **Use bulk operations:** `bulk_create_test_steps` for creating steps, `bulk_log_step_results` for logging results. These reduce N API calls to 1.
- **Use progress tools, not pagination:** `get_pending_steps(run_id)` for remaining work, `get_run_progress(run_id)` for status overview. One call each.
- **Use sections for large plans:** categorize steps, process one section at a time, split across sub-agents for 300+ steps.
- Be thorough: test happy paths, edge cases, and error conditions.