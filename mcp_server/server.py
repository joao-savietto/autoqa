"""
AutoQA MCP Server

MCP server (HTTP/streamable-http transport) that wraps the Django REST API.
Uses fastmcp to expose tools for AI coding agents.

The MCP client (e.g. Claude Code) must pass the REST API key via the
X-API-Key header on each request. The server forwards it as the
Authorization header to the Django API.

Docker:
    docker compose up --build mcp_server

Environment variables:
    MCP_API_URL: URL of the Django REST API (default: http://localhost:8234)
"""

import json
import os
import sys
from contextvars import ContextVar

import httpx
from starlette.middleware import Middleware
from starlette.requests import Request

# Add project root to path so we can import settings
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings")

from fastmcp import FastMCP

API_URL = os.environ.get("MCP_API_URL", "http://localhost:8234")

# ContextVar to hold the API key from the current HTTP request
_current_api_key: ContextVar[str | None] = ContextVar("current_api_key", default=None)


class ApiKeyMiddleware:
    """Extract X-API-Key header from incoming MCP requests and store it
    in a ContextVar so tool functions can access it."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            from starlette.requests import Request as StarletteRequest

            request = StarletteRequest(scope)
            api_key = request.headers.get("x-api-key")
            _current_api_key.set(api_key)
        await self.app(scope, receive, send)


mcp = FastMCP(
    name="AutoQA MCP Server",
    version="1.0.0",
    instructions="AutoQA platform for tracking QA test plans, steps, runs, and incidents.",
)


def _headers():
    """Return auth headers for API requests, derived from the client's
    X-API-Key header."""
    api_key = _current_api_key.get()
    if api_key:
        return {"Authorization": f"Api-Key {api_key}"}
    return {}


def _client():
    """Return an httpx client configured for the Django API."""
    return httpx.Client(base_url=API_URL, headers=_headers(), timeout=30.0)


# Valid RunStepResult statuses (shared by log/update tools).
VALID_STATUSES = ("passed", "failed", "skipped", "blocked")


def _fetch_all_results(client, url, base_params, max_pages=50):
    """Walk REST pages (page=1,2,...) following 'next' and return the
    combined list of all result objects. Bounded to max_pages to guard
    against infinite loops."""
    items = []
    for page in range(1, max_pages + 1):
        params = dict(base_params)
        params["page"] = page
        resp = client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()
        items.extend(data.get("results", []))
        if data.get("next") is None:
            break
    return items


# ─── Test Plans ───────────────────────────────────────────────────────────────


@mcp.tool()
def create_test_plan(
    name: str,
    project_name: str = "",
    plan_type: str = "qa",
    test_scope: str = "",
    exclude_scope: str = "",
) -> str:
    """Create a new test plan.

    Args:
        name: Name of the test plan
        project_name: Associated project name
        plan_type: Type of plan - 'qa' or 'security'
        test_scope: What is included in this test plan
        exclude_scope: What is explicitly excluded

    Returns:
        JSON string with the created test plan data
    """
    with _client() as client:
        resp = client.post(
            "/api/test-plans/",
            json={
                "name": name,
                "project_name": project_name,
                "plan_type": plan_type,
                "test_scope": test_scope,
                "exclude_scope": exclude_scope,
            },
        )
        resp.raise_for_status()
        data = resp.json()["results"][0] if "results" in resp.json() else resp.json()
        return json.dumps(data)


@mcp.tool()
def get_test_plans(project_name: str = "", search: str = "", keyword: str = "") -> str:
    """List all test plans with optional filtering.

    Args:
        project_name: Filter by project name (partial match)
        search: Search in plan names
        keyword: Search keyword matching name, project_name, test_scope, or exclude_scope (OR logic)

    Returns:
        JSON string with paginated list of test plans
    """
    params = {}
    if project_name:
        params["project_name"] = project_name
    if search:
        params["search"] = search
    if keyword:
        params["keyword"] = keyword
    with _client() as client:
        resp = client.get("/api/test-plans/", params=params)
        resp.raise_for_status()
        return json.dumps(resp.json())


@mcp.tool()
def get_test_plan(plan_id: int) -> str:
    """Get a single test plan by ID.

    Args:
        plan_id: The ID of the test plan

    Returns:
        JSON string with the test plan data
    """
    with _client() as client:
        resp = client.get(f"/api/test-plans/{plan_id}/")
        resp.raise_for_status()
        return json.dumps(resp.json())


@mcp.tool()
def update_test_plan(
    plan_id: int,
    name: str = None,
    project_name: str = None,
    plan_type: str = None,
    test_scope: str = None,
    exclude_scope: str = None,
) -> str:
    """Update a test plan. Only provided fields will be updated.

    Args:
        plan_id: The ID of the test plan
        name: New name
        project_name: New project name
        plan_type: New plan type - 'qa' or 'security'
        test_scope: New test scope
        exclude_scope: New exclude scope

    Returns:
        JSON string with the updated test plan data
    """
    data = {}
    if name is not None:
        data["name"] = name
    if project_name is not None:
        data["project_name"] = project_name
    if plan_type is not None:
        data["plan_type"] = plan_type
    if test_scope is not None:
        data["test_scope"] = test_scope
    if exclude_scope is not None:
        data["exclude_scope"] = exclude_scope

    with _client() as client:
        resp = client.patch(f"/api/test-plans/{plan_id}/", json=data)
        resp.raise_for_status()
        return json.dumps(resp.json())


@mcp.tool()
def delete_test_plan(plan_id: int) -> str:
    """Delete a test plan and all associated data.

    Args:
        plan_id: The ID of the test plan to delete

    Returns:
        Confirmation message
    """
    with _client() as client:
        resp = client.delete(f"/api/test-plans/{plan_id}/")
        resp.raise_for_status()
        return json.dumps({"status": "deleted", "plan_id": plan_id})


# ─── Test Steps ───────────────────────────────────────────────────────────────


@mcp.tool()
def get_test_steps(
    plan_id: int, page: int = None, page_size: int = None, keyword: str = "", section: str = ""
) -> str:
    """Get test steps for a test plan with pagination support.

    Args:
        plan_id: The ID of the test plan
        page: Page number (default: 1)
        page_size: Number of items per page (default: 50, max: 100)
        keyword: Search keyword matching name or action_description (OR logic)
        section: Filter steps by section/category (e.g. "Authentication", "Dashboard")

    Returns:
        JSON string with paginated list of test steps
    """
    params = {"plan": plan_id}
    if page is not None:
        params["page"] = page
    if page_size is not None:
        params["page_size"] = page_size
    if keyword:
        params["keyword"] = keyword
    if section:
        params["section"] = section
    with _client() as client:
        resp = client.get("/api/test-steps/", params=params)
        resp.raise_for_status()
        return json.dumps(resp.json())


@mcp.tool()
def create_test_step(
    plan_id: int,
    name: str,
    action_description: str,
    expected_outcome: str,
    preconditions: str = "",
    section: str = "",
    order_index: int = -1,
    active: bool = True,
) -> str:
    """Create a new test step within a test plan.

    Args:
        plan_id: The ID of the test plan
        name: Name of the step
        action_description: What action to perform
        expected_outcome: What should happen after this step
        preconditions: Conditions that must be met before executing
        section: Grouping category (e.g. "Authentication", "Dashboard")
        order_index: Position in the step sequence (default: auto-assigned)
        active: Whether this step is active

    Returns:
        JSON string with the created test step data
    """
    data = {
        "plan": plan_id,
        "name": name,
        "action_description": action_description,
        "expected_outcome": expected_outcome,
        "preconditions": preconditions,
        "active": active,
    }
    if section:
        data["section"] = section
    if order_index >= 0:
        data["order_index"] = order_index
    with _client() as client:
        resp = client.post(
            "/api/test-steps/",
            json=data,
        )
        resp.raise_for_status()
        return json.dumps(resp.json())


@mcp.tool()
def bulk_create_test_steps(
    plan_id: int,
    steps: str,
) -> str:
    """Create multiple test steps for a plan in a single request.

    Much more efficient than calling create_test_step repeatedly.

    Args:
        plan_id: The ID of the test plan
        steps: JSON string containing a list of step objects. Each step has:
            - name (required): Name of the step
            - action_description (required): What action to perform
            - expected_outcome (required): What should happen after this step
            - preconditions (optional): Conditions before executing
            - section (optional): Grouping category (e.g. "Authentication", "Dashboard")
            - order_index (optional): Position in sequence (auto-assigned if omitted)
            - active (optional, default true): Whether this step is active

    Example steps parameter:
        '[{"name": "Step 1", "action_description": "Do X", "expected_outcome": "X happens",
           "section": "Authentication"},
          {"name": "Step 2", "action_description": "Do Y", "expected_outcome": "Y happens"}]'

    Returns:
        JSON string with count of created steps and their serialized data
    """
    try:
        steps_list = json.loads(steps)
    except json.JSONDecodeError:
        return json.dumps({"error": "Invalid JSON in 'steps' parameter."})

    if not isinstance(steps_list, list) or len(steps_list) == 0:
        return json.dumps({"error": "'steps' must be a non-empty JSON array."})

    with _client() as client:
        resp = client.post(
            "/api/test-steps/bulk-create/",
            json={
                "plan": plan_id,
                "steps": steps_list,
            },
        )
        resp.raise_for_status()
        return json.dumps(resp.json())


@mcp.tool()
def update_test_step(
    step_id: int,
    name: str = None,
    action_description: str = None,
    expected_outcome: str = None,
    preconditions: str = None,
    order_index: int = None,
    active: bool = None,
    section: str = None,
) -> str:
    """Update a test step. Only provided fields will be updated.

    Args:
        step_id: The ID of the test step
        name: New name
        action_description: New action description
        expected_outcome: New expected outcome
        preconditions: New preconditions
        order_index: New position in sequence
        active: Whether this step is active
        section: Grouping category for the step

    Returns:
        JSON string with the updated test step data
    """
    data = {}
    if name is not None:
        data["name"] = name
    if action_description is not None:
        data["action_description"] = action_description
    if expected_outcome is not None:
        data["expected_outcome"] = expected_outcome
    if preconditions is not None:
        data["preconditions"] = preconditions
    if order_index is not None:
        data["order_index"] = order_index
    if active is not None:
        data["active"] = active
    if section is not None:
        data["section"] = section

    with _client() as client:
        resp = client.patch(f"/api/test-steps/{step_id}/", json=data)
        resp.raise_for_status()
        return json.dumps(resp.json())


@mcp.tool()
def delete_test_step(step_id: int) -> str:
    """Delete a test step.

    Args:
        step_id: The ID of the test step to delete

    Returns:
        Confirmation message
    """
    with _client() as client:
        resp = client.delete(f"/api/test-steps/{step_id}/")
        resp.raise_for_status()
        return json.dumps({"status": "deleted", "step_id": step_id})


@mcp.tool()
def get_pending_steps(plan_id: int, run_id: int = None) -> str:
    """Get test steps that have NOT yet been executed for a run.

    Returns all active steps that don't have a RunStepResult in the given run.
    If run_id is omitted, returns all active steps for the plan.
    Much more efficient than paginating through all steps and results separately.

    Args:
        plan_id: The ID of the test plan
        run_id: The ID of the test run (optional — if omitted returns all active steps)

    Returns:
        JSON string with count and list of pending/remaining step objects
    """
    params = {"plan": plan_id, "run": run_id} if run_id else {"plan": plan_id}
    with _client() as client:
        resp = client.get("/api/test-steps/pending_steps/", params=params)
        resp.raise_for_status()
        return json.dumps(resp.json())


@mcp.tool()
def categorize_test_step(step_id: int, section: str) -> str:
    """Assign a section/category to a test step for organization.

    Use sections like "Authentication", "Dashboard", "Reports", "API Endpoints",
    "Error Handling" to group steps in large test plans (100+ steps).

    Args:
        step_id: The ID of the test step
        section: Section name to assign

    Returns:
        JSON string with the updated test step data
    """
    with _client() as client:
        resp = client.patch(
            f"/api/test-steps/{step_id}/",
            json={"section": section},
        )
        resp.raise_for_status()
        return json.dumps(resp.json())


# ─── Test Runs ────────────────────────────────────────────────────────────────


@mcp.tool()
def create_test_run(plan_id: int, agent_id: str = "", section: str = "") -> str:
    """Create a new test run for a test plan.

    For large plans (100+ steps), use the section parameter to scope the run
    to a specific section. Multiple agents can run different sections in parallel.

    Args:
        plan_id: The ID of the test plan
        agent_id: Identifier of the agent executing this run
        section: Optional section scope — agents should note this in agent_id

    Returns:
        JSON string with the created test run data
    """
    with _client() as client:
        resp = client.post(
            "/api/test-runs/",
            json={
                "plan": plan_id,
                "agent_id": f"{agent_id} [{section}]" if section else agent_id,
            },
        )
        resp.raise_for_status()
        return json.dumps(resp.json())


@mcp.tool()
def get_test_runs(plan_id: int = None, status: str = None) -> str:
    """List test runs with optional filtering.

    Args:
        plan_id: Filter by test plan ID
        status: Filter by status (pending/running/completed/failed)

    Returns:
        JSON string with paginated list of test runs
    """
    params = {}
    if plan_id is not None:
        params["plan"] = plan_id
    if status:
        params["status"] = status

    with _client() as client:
        resp = client.get("/api/test-runs/", params=params)
        resp.raise_for_status()
        return json.dumps(resp.json())


@mcp.tool()
def complete_test_run(run_id: int, status: str = "completed") -> str:
    """Mark a test run as completed or failed.

    Args:
        run_id: The ID of the test run
        status: Final status - 'completed' or 'failed'

    Returns:
        JSON string with the updated test run data
    """
    with _client() as client:
        resp = client.post(
            f"/api/test-runs/{run_id}/complete/",
            json={"status": status},
        )
        resp.raise_for_status()
        return json.dumps(resp.json())


@mcp.tool()
def reopen_test_run(run_id: int) -> str:
    """Reopen a completed/failed test run so its steps can be executed again.

    Sets the run status back to 'running' and clears completed_at, so new
    step results can be logged without creating a duplicate run.
    Idempotent: reopening an already-running run is a no-op.

    Args:
        run_id: The ID of the test run

    Returns:
        JSON string with the updated test run data, or an error object
        if the run does not exist
    """
    with _client() as client:
        try:
            resp = client.post(f"/api/test-runs/{run_id}/reopen/", json={})
            resp.raise_for_status()
        except httpx.HTTPStatusError:
            if resp.status_code == 404:
                return json.dumps({"error": f"Run {run_id} not found"})
            raise
        return json.dumps(resp.json())


@mcp.tool()
def get_run_progress(run_id: int) -> str:
    """Get execution progress summary for a test run.

    Single-call alternative to manually paginating through step results.
    Returns counts (total, passed, failed, skipped, pending), the IDs
    of pending steps, and available sections.

    Args:
        run_id: The ID of the test run

    Returns:
        JSON string with progress summary
    """
    with _client() as client:
        resp = client.get(f"/api/test-runs/{run_id}/progress/")
        resp.raise_for_status()
        return json.dumps(resp.json())


@mcp.tool()
def export_run(run_ids: str, format: str = "xlsx", exclude_skipped: bool = False) -> str:
    """Export one or more test runs as a consolidated XLSX or CSV file.

    Useful for building a single report across multiple runs (e.g.
    section-scoped runs of the same plan) without leaving the platform.

    XLSX contains one sheet per run ("Run <id>"), a "Findings" sheet
    across all runs, and a "Summary" sheet with per-run counts.
    CSV is a flat table: run_id,step_id,step_name,status,log_message,created_at.

    Args:
        run_ids: Comma-separated run ids, e.g. "128,130"
        format: 'xlsx' (default) or 'csv'
        exclude_skipped: If true, omit skipped results from the export

    Returns:
        JSON string with filename, size_bytes, content_type, and
        content_base64 (base64-encoded file contents), or an error object
        if the export fails
    """
    import base64

    params = {
        "runs": run_ids,
        "format": format,
        "exclude_skipped": "true" if exclude_skipped else "false",
    }
    with _client() as client:
        try:
            resp = client.get("/api/test-runs/export/", params=params)
            resp.raise_for_status()
        except httpx.HTTPStatusError:
            if resp.status_code in (400, 404):
                return json.dumps(
                    {"error": f"Export failed (HTTP {resp.status_code}). Check run ids and format."}
                )
            raise
        content = resp.content
        filename = f"autoqa_export_{run_ids}.{format if format in ('xlsx', 'csv') else 'xlsx'}"
        return json.dumps({
            "filename": filename,
            "size_bytes": len(content),
            "content_type": resp.headers.get("content-type", ""),
            "content_base64": base64.b64encode(content).decode("ascii"),
        })


# ─── Step Results ─────────────────────────────────────────────────────────────


@mcp.tool()
def log_step_result(
    run_id: int,
    step_id: int,
    status: str,
    log_message: str = "",
) -> str:
    """Log the result of executing a test step within a run.

    Args:
        run_id: The ID of the test run
        step_id: The ID of the test step
        status: Result status - 'passed', 'failed', 'skipped', or 'blocked'
                 (use 'blocked' when a step could not be executed due to a
                 missing credential, data, or environment)
        log_message: Execution log or notes

    Returns:
        JSON string with the created step result data
    """
    if status not in VALID_STATUSES:
        return json.dumps(
            {"error": f"Invalid status '{status}'. Must be one of: {', '.join(VALID_STATUSES)}."}
        )

    with _client() as client:
        resp = client.post(
            "/api/step-results/",
            json={
                "run": run_id,
                "step": step_id,
                "status": status,
                "log_message": log_message,
            },
        )
        resp.raise_for_status()
        return json.dumps(resp.json())


@mcp.tool()
def bulk_log_step_results(
    run_id: int,
    results: str,
) -> str:
    """Log multiple step results for a run in a single request.

    Much more efficient than calling log_step_result repeatedly.
    Skips results that already exist for a given (run, step) pair.

    Args:
        run_id: The ID of the test run
        results: JSON string containing a list of result objects. Each result has:
            - step (required): The ID of the test step
            - status (required): 'passed', 'failed', 'skipped', or 'blocked'
            - log_message (optional): Execution log or notes

    Example results parameter:
        '[{"step": 1, "status": "passed", "log_message": "OK"},
          {"step": 2, "status": "failed", "log_message": "Error found"},
          {"step": 3, "status": "skipped"},
          {"step": 4, "status": "blocked", "log_message": "missing API key"}]'

    Returns:
        JSON string with count of created results, skipped items, and serialized data
    """
    try:
        results_list = json.loads(results)
    except json.JSONDecodeError:
        return json.dumps({"error": "Invalid JSON in 'results' parameter."})

    if not isinstance(results_list, list) or len(results_list) == 0:
        return json.dumps({"error": "'results' must be a non-empty JSON array."})

    with _client() as client:
        resp = client.post(
            "/api/step-results/bulk-log/",
            json={
                "run": run_id,
                "results": results_list,
            },
        )
        resp.raise_for_status()
        return json.dumps(resp.json())


@mcp.tool()
def update_step_result(
    run_id: int,
    step_id: int,
    status: str = None,
    log_message: str = None,
) -> str:
    """Update an existing step result's status and/or log message.

    Use this to correct a wrong status or amend the log of a step that
    was already logged in a run. The result must already exist — log it
    first with log_step_result if it doesn't.

    Args:
        run_id: The ID of the test run
        step_id: The ID of the test step
        status: New result status - 'passed', 'failed', 'skipped', or 'blocked'
        log_message: New execution log or notes

    Returns:
        JSON string with the patched result data, or an error object if
        no result exists for the (run, step) pair
    """
    data = {}
    if status is not None:
        if status not in VALID_STATUSES:
            return json.dumps(
                {"error": f"Invalid status '{status}'. Must be one of: {', '.join(VALID_STATUSES)}."}
            )
        data["status"] = status
    if log_message is not None:
        data["log_message"] = log_message

    with _client() as client:
        resp = client.get("/api/step-results/", params={"run": run_id, "step": step_id})
        resp.raise_for_status()
        results = resp.json().get("results", [])
        if not results:
            return json.dumps(
                {
                    "error": (
                        f"No result for run {run_id} step {step_id} "
                        "(log it first with log_step_result)"
                    )
                }
            )
        result_id = results[0]["id"]
        resp = client.patch(f"/api/step-results/{result_id}/", json=data)
        resp.raise_for_status()
        return json.dumps(resp.json())


@mcp.tool()
def delete_step_result(run_id: int, step_id: int) -> str:
    """Delete an existing step result from a run.

    The step becomes pending again and can be re-executed and re-logged.

    Args:
        run_id: The ID of the test run
        step_id: The ID of the test step

    Returns:
        JSON string {"deleted": <result_id>}, or an error object if no
        result exists for the (run, step) pair
    """
    with _client() as client:
        resp = client.get("/api/step-results/", params={"run": run_id, "step": step_id})
        resp.raise_for_status()
        results = resp.json().get("results", [])
        if not results:
            return json.dumps(
                {"error": f"No result for run {run_id} step {step_id}"}
            )
        result_id = results[0]["id"]
        resp = client.delete(f"/api/step-results/{result_id}/")
        resp.raise_for_status()
        return json.dumps({"deleted": result_id})


@mcp.tool()
def get_step_results(run_id: int, status: str = None, page: int = None, page_size: int = None) -> str:
    """Get step results for a test run, optionally filtered by status.

    By default returns ALL results for the run as ONE JSON array (REST
    pagination is walked automatically). Pass page= to get a single REST
    page in the legacy paginated dict shape instead.

    Args:
        run_id: The ID of the test run
        status: Filter by result status - 'passed', 'failed', 'skipped', or 'blocked'
        page: If set, return only this single REST page as a paginated dict
              (with results/next/previous) instead of the combined array
        page_size: (all-mode only) Truncate the combined array to the first
              N items (clamped to 1..100). Ignored when page is set.

    Returns:
        JSON string: array of ALL result objects (default) or a single
        paginated page dict (when page is set)
    """
    base_params = {"run": run_id}
    if status:
        base_params["status"] = status
    with _client() as client:
        if page is not None:
            params = dict(base_params)
            params["page"] = page
            resp = client.get("/api/step-results/", params=params)
            resp.raise_for_status()
            return json.dumps(resp.json())
        items = _fetch_all_results(client, "/api/step-results/", base_params)
    if page_size is not None:
        try:
            n = int(page_size)
        except (TypeError, ValueError):
            n = 100
        n = max(1, min(100, n))
        items = items[:n]
    return json.dumps(items)


# ─── Incidents ────────────────────────────────────────────────────────────────


@mcp.tool()
def create_incident(
    run_step_result_id: int,
    summary: str,
    reproduction_steps: str,
    severity: str = "medium",
    assigned_to: int = None,
) -> str:
    """Create a new incident (bug) from a failed step result.

    Args:
        run_step_result_id: The ID of the step result this incident is linked to
        summary: Brief description of the issue
        reproduction_steps: Steps to reproduce the issue
        severity: Issue severity - 'low', 'medium', or 'high'
        assigned_to: User ID to assign this incident to

    Returns:
        JSON string with the created incident data
    """
    if severity not in ("low", "medium", "high"):
        return json.dumps(
            {"error": f"Invalid severity '{severity}'. Must be low, medium, or high."}
        )

    data = {
        "run_step_result": run_step_result_id,
        "summary": summary,
        "reproduction_steps": reproduction_steps,
        "severity": severity,
    }
    if assigned_to is not None:
        data["assigned_to"] = assigned_to

    with _client() as client:
        resp = client.post("/api/incidents/", json=data)
        resp.raise_for_status()
        return json.dumps(resp.json())


@mcp.tool()
def get_incidents(
    resolved: bool = None,
    severity: str = None,
) -> str:
    """List incidents with optional filtering.

    Args:
        resolved: Filter by resolved status (true/false)
        severity: Filter by severity (low/medium/high)

    Returns:
        JSON string with paginated list of incidents
    """
    params = {}
    if resolved is not None:
        params["resolved"] = resolved
    if severity:
        params["severity"] = severity

    with _client() as client:
        resp = client.get("/api/incidents/", params=params)
        resp.raise_for_status()
        return json.dumps(resp.json())


# ─── Findings ─────────────────────────────────────────────────────────────────


@mcp.tool()
def create_finding(
    run_id: int,
    title: str,
    description: str,
    category: str = "info",
    step_ids: list | None = None,
) -> str:
    """Register a finding/discovery from a test run.

    Use for interesting observations; link related test steps via step_ids.

    Args:
        run_id: The ID of the test run this finding relates to
        title: Short title of the finding
        description: Detailed description of the finding
        category: One of info, suggestion, recommendation, critical
        step_ids: Optional list of test step IDs this finding relates to

    Returns:
        JSON string with the created finding data
    """
    if category not in ("info", "suggestion", "recommendation", "critical"):
        return json.dumps(
            {
                "error": f"Invalid category '{category}'. Must be info, suggestion, recommendation, or critical."
            }
        )

    data = {
        "run": run_id,
        "title": title,
        "description": description,
        "category": category,
    }
    if step_ids:
        data["step_ids"] = step_ids

    with _client() as client:
        resp = client.post("/api/findings/", json=data)
        resp.raise_for_status()
        return json.dumps(resp.json())


@mcp.tool()
def get_findings(run_id: int = None, category: str = None, project_name: str = None) -> str:
    """List findings, optionally filtered by run, category, or project.

    All filters are optional and combined with AND logic. With no filters
    this returns ALL findings across all runs/projects.

    Args:
        run_id: Filter by the ID of the test run
        category: Filter by category - info, suggestion, recommendation, critical
        project_name: Filter by the plan's project name (exact match)

    Returns:
        JSON string with an array of finding objects (all pages combined)
    """
    params = {}
    if run_id is not None:
        params["run"] = run_id
    if category:
        params["category"] = category
    if project_name:
        params["project_name"] = project_name
    with _client() as client:
        items = _fetch_all_results(client, "/api/findings/", params)
    return json.dumps(items)


@mcp.tool()
def get_project_summary(project_name: str) -> str:
    """Build a read-only summary report for a project in a single call.

    Aggregates the project's plans, all its runs (with per-run status
    counts and pass rate), findings by category, and incidents by
    severity. Read-only: uses only existing GET endpoints.

    Args:
        project_name: Project name to summarize (exact match on the plan's
                      project_name, case-insensitive)

    Returns:
        JSON string:
        {
          "project_name": "...",
          "plans": [{"id": 27, "name": "...", "total_steps": 38}],
          "runs": [{"run_id": 128, "plan_id": 27, "status": "completed",
                    "total_steps": 38, "passed": 19, "failed": 0,
                    "skipped": 19, "blocked": 0, "pending": 0,
                    "pass_rate": 1.0}],
          "findings_by_category": {"critical": 1, "info": 2},
          "incidents_by_severity": {"low": 0, "medium": 0, "high": 1, "critical": 0}
        }
        pass_rate is passed / (passed + failed); null when there are no
        passed+failed steps. An unknown project returns empty plans/runs
        and empty findings/incidents dicts (not an error).
    """
    with _client() as client:
        # Plans: REST filter is partial-match, so narrow to exact
        # (case-insensitive) matches client-side.
        plan_hits = _fetch_all_results(
            client, "/api/test-plans/", {"project_name": project_name}
        )
        plans = [
            p for p in plan_hits
            if (p.get("project_name") or "").lower() == project_name.lower()
        ]

        # All runs of the project's plans (page-walked per plan).
        runs = []
        for plan in plans:
            runs.extend(
                _fetch_all_results(client, "/api/test-runs/", {"plan": plan["id"]})
            )

        # Per-run counts via the progress endpoint.
        run_summaries = []
        for run in runs:
            resp = client.get(f"/api/test-runs/{run['id']}/progress/")
            resp.raise_for_status()
            p = resp.json()
            passed = p.get("passed", 0)
            failed = p.get("failed", 0)
            denom = passed + failed
            run_summaries.append({
                "run_id": run["id"],
                "plan_id": run["plan"],
                "status": run["status"],
                "total_steps": p.get("total_steps", 0),
                "passed": passed,
                "failed": failed,
                "skipped": p.get("skipped", 0),
                "blocked": p.get("blocked", 0),
                "pending": p.get("pending", 0),
                "pass_rate": (passed / denom) if denom else None,
            })

        run_ids = {r["run_id"] for r in run_summaries}

        if not run_ids:
            findings_by_category = {}
            incidents_by_severity = {}
        else:
            # Findings: fetch all, filter client-side to the project's runs.
            findings_by_category = {}
            for f in _fetch_all_results(client, "/api/findings/", {}):
                if f.get("run") in run_ids:
                    cat = f.get("category")
                    findings_by_category[cat] = findings_by_category.get(cat, 0) + 1

            # Incidents: fetch all; map to runs via the project's step results.
            result_ids = set()
            for run_id in run_ids:
                for r in _fetch_all_results(
                    client, "/api/step-results/", {"run": run_id}
                ):
                    result_ids.add(r["id"])
            incidents_by_severity = {"low": 0, "medium": 0, "high": 0, "critical": 0}
            for inc in _fetch_all_results(client, "/api/incidents/", {}):
                if inc.get("run_step_result") in result_ids:
                    sev = inc.get("severity")
                    incidents_by_severity[sev] = incidents_by_severity.get(sev, 0) + 1

    return json.dumps({
        "project_name": project_name,
        "plans": [
            {"id": p["id"], "name": p["name"], "total_steps": p.get("total_steps", 0)}
            for p in plans
        ],
        "runs": run_summaries,
        "findings_by_category": findings_by_category,
        "incidents_by_severity": incidents_by_severity,
    })


if __name__ == "__main__":
    import logging

    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("mcp_server")
    logger.info(f"Starting AutoQA MCP Server (API: {API_URL})")
    mcp.run(
        transport="streamable-http",
        host="0.0.0.0",
        port=3157,
        middleware=[Middleware(ApiKeyMiddleware)],
        json_response=True,
    )
