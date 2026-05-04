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
    MCP_API_URL: URL of the Django REST API (default: http://web:8000)
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

API_URL = os.environ.get("MCP_API_URL", "http://web:8000")

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
def get_test_plans(project_name: str = "", search: str = "") -> str:
    """List all test plans with optional filtering.

    Args:
        project_name: Filter by project name (partial match)
        search: Search in plan names

    Returns:
        JSON string with paginated list of test plans
    """
    params = {}
    if project_name:
        params["project_name"] = project_name
    if search:
        params["search"] = search
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
def get_test_steps(plan_id: int, page: int = None, page_size: int = None) -> str:
    """Get test steps for a test plan with pagination support.

    Args:
        plan_id: The ID of the test plan
        page: Page number (default: 1)
        page_size: Number of items per page (default: 5)

    Returns:
        JSON string with paginated list of test steps
    """
    params = {"plan": plan_id}
    if page is not None:
        params["page"] = page
    if page_size is not None:
        params["page_size"] = page_size
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
    order_index: int = 0,
    active: bool = True,
) -> str:
    """Create a new test step within a test plan.

    Args:
        plan_id: The ID of the test plan
        name: Name of the step
        action_description: What action to perform
        expected_outcome: What should happen after this step
        preconditions: Conditions that must be met before executing
        order_index: Position in the step sequence
        active: Whether this step is active

    Returns:
        JSON string with the created test step data
    """
    with _client() as client:
        resp = client.post(
            "/api/test-steps/",
            json={
                "plan": plan_id,
                "name": name,
                "action_description": action_description,
                "expected_outcome": expected_outcome,
                "preconditions": preconditions,
                "order_index": order_index,
                "active": active,
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


# ─── Test Runs ────────────────────────────────────────────────────────────────


@mcp.tool()
def create_test_run(plan_id: int, agent_id: str = "") -> str:
    """Create a new test run for a test plan.

    Args:
        plan_id: The ID of the test plan
        agent_id: Identifier of the agent executing this run

    Returns:
        JSON string with the created test run data
    """
    with _client() as client:
        resp = client.post(
            "/api/test-runs/",
            json={
                "plan": plan_id,
                "agent_id": agent_id,
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
        status: Result status - 'passed', 'failed', or 'skipped'
        log_message: Execution log or notes

    Returns:
        JSON string with the created step result data
    """
    if status not in ("passed", "failed", "skipped"):
        return json.dumps(
            {"error": f"Invalid status '{status}'. Must be passed, failed, or skipped."}
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
def get_step_results(run_id: int) -> str:
    """Get all step results for a test run.

    Args:
        run_id: The ID of the test run

    Returns:
        JSON string with paginated list of step results
    """
    with _client() as client:
        resp = client.get("/api/step-results/", params={"run": run_id})
        resp.raise_for_status()
        return json.dumps(resp.json())


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
) -> str:
    """Register a finding/discovery from a test run.

    Use for interesting observations not tied to a specific test step.

    Args:
        run_id: The ID of the test run this finding relates to
        title: Short title of the finding
        description: Detailed description of the finding
        category: One of info, suggestion, recommendation, critical

    Returns:
        JSON string with the created finding data
    """
    if category not in ("info", "suggestion", "recommendation", "critical"):
        return json.dumps(
            {"error": f"Invalid category '{category}'. Must be info, suggestion, recommendation, or critical."}
        )

    with _client() as client:
        resp = client.post(
            "/api/findings/",
            json={
                "run": run_id,
                "title": title,
                "description": description,
                "category": category,
            },
        )
        resp.raise_for_status()
        return json.dumps(resp.json())


@mcp.tool()
def get_findings(run_id: int) -> str:
    """List all findings for a test run.

    Args:
        run_id: The ID of the test run

    Returns:
        JSON string with list of findings
    """
    with _client() as client:
        resp = client.get("/api/findings/", params={"run": run_id})
        resp.raise_for_status()
        return json.dumps(resp.json())


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
