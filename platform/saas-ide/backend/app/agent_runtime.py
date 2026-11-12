"""Opt-in CrewAI execution and MCP discovery. All external execution is disabled by default."""
import os
from typing import Any

from .supervisor import plan_steps, route_model

# Never expose arbitrary MCP endpoints to an untrusted user; admin owns allowlist.
def allowed_mcp_endpoint(name: str) -> str:
    if name not in ("knowledge", "github-readonly"):
        raise PermissionError("MCP server not approved")
    endpoint = os.getenv("IDE_MCP_" + name.upper().replace("-", "_") + "_URL", "")
    if not endpoint.startswith("https://"):
        raise RuntimeError("MCP endpoint must be explicitly configured with HTTPS")
    return endpoint


async def discover_mcp_tools(name: str) -> list[str]:
    url = allowed_mcp_endpoint(name)
    from mcp import Client
    async with Client(url) as client:
        tools = await client.list_tools()
        return [t.name for t in tools.tools]


def execute_crewai_plan(task: str, provider: str) -> str:
    """CrewAI execution requires explicit server-side opt-in and configured LLM."""
    if os.getenv("IDE_CREWAI_EXECUTION_ENABLED") != "true":
        raise PermissionError("CrewAI execution disabled until sandbox and security review")
    if provider == "unconfigured" or provider != route_model(provider):
        raise RuntimeError("Provider not configured")
    # Model credentials are supplied by the service environment, never the user.
    # Restrict crew to text-only roles; no tools, delegation, or code execution.
    from crewai import Agent, Crew, Process, Task
    agents = [
        Agent(role=role, goal=goal, backstory="AEP-X governed software engineering assistant",
              allow_delegation=False, tools=[], verbose=False)
        for role, goal in [
            ("Requirements analyst", "Clarify requirements"),
            ("Solution architect", "Design a secure solution"),
            ("Security reviewer", "Identify security risks"),
        ]
    ]
    tasks = [Task(description=f"{goal}. User request: {task}",
                  expected_output="Concise plain-text analysis", agent=agent)
             for agent, goal in zip(agents, ["Analyse requirements", "Propose architecture", "Review security"])]
    crew = Crew(agents=agents, tasks=tasks, process=Process.sequential, verbose=False)
    return str(crew.kickoff())
