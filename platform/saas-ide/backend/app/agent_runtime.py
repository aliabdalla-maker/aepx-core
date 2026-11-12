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
    if len(str(arguments)) > 4000:
        raise ValueError("MCP arguments too large")
    approved_mcp_tool(name, tool)
    if db is None or not tenant_id or not run_id:
        raise PermissionError("Tenant-bound single-use approval context required")
    # Consume exact-argument approval before any network access. This is at-most-once
    # dispatch, not exactly-once remote execution.
    from .phase22 import consume_tool
    consume_tool(db, tenant_id, run_id, name, tool, arguments)
    token = os.getenv("IDE_MCP_" + name.upper().replace("-", "_") + "_TOKEN", "")
    if not token:
        raise RuntimeError("MCP service token required")
    # A network-level egress proxy is mandatory; URL checks alone cannot prevent
    # DNS rebinding or a resolved private address. No direct connections allowed.
    proxy = os.getenv("IDE_MCP_EGRESS_PROXY", "")
    if not proxy.startswith("https://"):
        raise PermissionError("Approved HTTPS egress proxy required")
    import httpx
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client
    async with httpx.AsyncClient(headers={"Authorization": f"Bearer {token}"}, timeout=15,
                                 follow_redirects=False, trust_env=False, proxy=proxy) as http:
        async with streamable_http_client(allowed_mcp_endpoint(name), http_client=http) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                return await session.call_tool(tool, arguments=arguments)


def execute_crewai_plan(task: str, provider: str) -> str:
    if os.getenv("IDE_EXTERNAL_EXECUTION_ENABLED") != "true" or os.getenv("IDE_CREWAI_EXECUTION_ENABLED") != "true":
        raise PermissionError("CrewAI execution disabled")
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
