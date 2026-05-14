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
4. Check if the plan has registered test steps via `get_test_steps`. If steps exist, retrieve and use them. If no steps, proceed to codebase discovery.

### Phase 2: Build Test Steps (Only if no steps exist)
3. If the plan has no steps, create them based on your codebase exploration. Each step needs: name, action description, preconditions, and expected outcome.
4. Cover ALL flows: UI pages (via Chrome CDP), API endpoints (via bash/curl), authentication, edge cases, and error handling.
5. Order steps logically: start with preconditions and authentication, then move through each feature flow.

### Phase 3: Execute
6. Call `create_test_run` to initialize a new run.
7. Retrieve steps in small batches with `get_test_steps`.
8. **For each UI step:** Connect to Chrome CDP, navigate, interact, verify outcomes, and capture evidence on failure.
9. **For each API step:** Use `bash` with curl to test endpoints.
10. Log every result immediately with `log_step_result` (passed/failed/skipped + log message).
11. **For every failure:** Investigate the root cause first, then call `create_incident` immediately with summary, reproduction steps, and severity.
12. **For every interesting observation not tied to a specific step:** Call `create_finding(run_id, title, description, category)` with the appropriate category. Register findings for UX insights, performance notes, unexpected behaviors, data patterns, and security observations discovered during testing.

### Phase 4: Complete
13. After all steps execute, call `complete_test_run` with the appropriate final status.
14. Provide a summary report: total steps, passed/failed/skipped counts, and list of all incidents created.

## Reminders
- **Always complete Phase 1 (Pre-flight) in full before moving to any other phase.**
- You are a **tester, not a fixer**. Find bugs, do not fix them.
- Create incidents for bugs **immediately** upon discovery, not at the end.
- Register findings for **every** interesting observation during testing — especially UX insights, performance notes, and unexpected behaviors.
- Be thorough: test happy paths, edge cases, and error conditions.
