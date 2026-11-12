"""Governed CrewAI and MCP adapters. No external calls without explicit server-side enablement."""
import ipaddress
import os
from urllib.parse import urlsplit

from .supervisor import route_model
from .providers import configured_model

APPROVED_SERVERS = ("knowledge", "github-readonly")


def allowed_mcp_endpoint(name: str) -> str:
    if name not in APPROVED_SERVERS:
        raise PermissionError("MCP server not approved")
    endpoint = os.getenv("IDE_MCP_" + name.upper().replace("-", "_") + "_URL", "")
    parsed = urlsplit(endpoint)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
        raise RuntimeError("MCP endpoint must be explicitly configured with HTTPS")
    try:
        if not ipaddress.ip_address(parsed.hostname).is_global:
            raise RuntimeError("Private or loopback MCP endpoint denied")
    except ValueError:
        if parsed.hostname in ("localhost",) or parsed.hostname.endswith((".local", ".internal")):
            raise RuntimeError("Internal MCP hostname denied")
    return endpoint


def approved_mcp_tool(name: str, tool: str) -> str:
    allowed_mcp_endpoint(name)
    tools = {x.strip() for x in os.getenv("IDE_MCP_" + name.upper().replace("-", "_") + "_TOOLS", "").split(",") if x.strip()}
    if tool not in tools:
        raise PermissionError("MCP tool not allowlisted")
    return tool


async def invoke_mcp_tool(name: str, tool: str, arguments: dict, *, db=None, tenant_id=None, run_id=None) -> object:
    if os.getenv("IDE_EXTERNAL_EXECUTION_ENABLED") != "true" or os.getenv("IDE_MCP_EXECUTION_ENABLED") != "true":
        raise PermissionError("MCP execution disabled")
    from .egress210 import assert_network_isolated
    assert_network_isolated()
    if len(str(arguments)) > 4000:
        raise ValueError("MCP arguments too large")
    approved_mcp_tool(name, tool)
    if db is None or not tenant_id or not run_id:
        raise PermissionError("Tenant-bound single-use approval context required")
    from .transport211 import sdk_async_http_client, approved_proxy_url
    approved_proxy_url()
    token = os.getenv("IDE_MCP_" + name.upper().replace("-", "_") + "_TOKEN", "")
    if not token:
        raise RuntimeError("MCP service token required")
    # Reserve and audit before dispatch; retries never repeat an uncertain call.
    from .phase22 import consume_tool
    from .mcp_execution214 import begin_dispatch, complete_dispatch, mark_unknown
    approval_id = consume_tool(db, tenant_id, run_id, name, tool, arguments)
    begin_dispatch(db, tenant_id, run_id, approval_id)
    # A network-level egress proxy is mandatory; URL checks alone cannot prevent
    # DNS rebinding or a resolved private address. No direct connections allowed.
    import httpx
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client
    try:
        async with sdk_async_http_client() as http:
            http.headers["Authorization"] = f"Bearer {token}"
            # Stable key is available for future provider-specific idempotency
            # support; do not assume an arbitrary MCP server honors it.
            async with streamable_http_client(allowed_mcp_endpoint(name), http_client=http) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool(tool, arguments=arguments)
        complete_dispatch(db, tenant_id, run_id, approval_id, True)
        return result
    except BaseException:
        # Timeouts, cancellations and worker exceptions may occur after remote
        # side effects. Quarantine the outcome rather than automatically replay.
        mark_unknown(db, tenant_id, run_id, approval_id)
        raise


def execute_crewai_plan(task: str, provider: str) -> str:
    if os.getenv("IDE_EXTERNAL_EXECUTION_ENABLED") != "true" or os.getenv("IDE_CREWAI_EXECUTION_ENABLED") != "true":
        raise PermissionError("CrewAI execution disabled")
    from .egress210 import assert_network_isolated
    assert_network_isolated()
    if provider == "unconfigured" or provider != route_model(provider):
        raise RuntimeError("Provider not enabled")
    model = configured_model(provider)
    from crewai import Agent, Crew, Process, Task, LLM
    # Explicit model prevents CrewAI from silently falling back to OpenAI.
    prefixes = {"openai": "", "anthropic": "anthropic/", "gemini": "gemini/", "oci": "oci/"}
    llm = LLM(model=prefixes[provider] + model, max_tokens=1200, timeout=30)
    agents = [Agent(role=role, goal=goal, backstory="Governed AEP-X engineering analyst",
                    llm=llm, allow_delegation=False, tools=[], verbose=False)
              for role, goal in [("Requirements analyst", "Clarify requirements"),
                                 ("Solution architect", "Design secure architecture"),
                                 ("Security reviewer", "Review risks and tests")]]
    tasks = [Task(description=f"{goal}. Request: {task[:4000]}",
                  expected_output="Plain-text analysis only", agent=agent)
             for agent, goal in zip(agents, ["Analyse requirements", "Propose architecture", "Review security"])]
    return str(Crew(agents=agents, tasks=tasks, process=Process.sequential, verbose=False).kickoff())
