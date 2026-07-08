"""Adapter registry for this category service.

One coarse-grained service per category, one adapter per external system
(SOA-Architecture.md §3.1). StubAdapter answers for every catalogued
connector that doesn't yet have a specialized implementation — swap a stub
for a real adapter class here when credentials and a sandbox exist; nothing
else (bus, catalogue, compose) needs to change.
"""


class StubAdapter:
    def __init__(self, name: str, category: str):
        self.name = name
        self.category = category

    def execute(self, payload: dict) -> dict:
        op = payload.get("op", "default")
        return {
            "op": op,
            "result": f"[stub response from connector '{self.name}' ({self.category}) for op '{op}']",
            "source": f"connector:{self.name}",
            "confidence": 0.5,
            "maturity": "stub",
        }


import os
import httpx


class GitHubAdapter:
    """Real api.github.com calls. Unauthenticated (60 req/hr) works for any
    public repo out of the box; set GITHUB_TOKEN in Vault/env to raise the
    limit to 5000/hr and reach private repos — no code change needed either
    way. Falls back to a canonical stub if the API is unreachable or the
    unauthenticated rate limit is exhausted, same pattern as the ML
    connector's Ollama fallback."""

    def __init__(self):
        self.token = os.getenv("GITHUB_TOKEN")

    def execute(self, payload: dict) -> dict:
        op = payload.get("op")
        if op == "list_open_issues":
            repo = payload.get("repo", "octocat/Hello-World")
            headers = {"Accept": "application/vnd.github+json"}
            if self.token:
                headers["Authorization"] = f"Bearer {self.token}"
            try:
                resp = httpx.get(
                    f"https://api.github.com/repos/{repo}/issues",
                    params={"state": "open", "per_page": 5},
                    headers=headers,
                    timeout=10.0,
                )
                resp.raise_for_status()
                issues = resp.json()
                return {
                    "op": op,
                    "repo": repo,
                    "result": [
                        {"number": i["number"], "title": i["title"], "state": i["state"]}
                        for i in issues if "pull_request" not in i
                    ],
                    "source": "connector:github",
                    "confidence": 0.95,
                    "maturity": "specialized",
                }
            except Exception as e:
                return {
                    "op": op,
                    "repo": repo,
                    "result": f"[fallback: GitHub API unreachable ({type(e).__name__}) for '{repo}']",
                    "source": "connector:github",
                    "confidence": 0.3,
                    "maturity": "specialized_degraded",
                }
        return {"op": op, "error": "unsupported operation in this adapter"}


SPECIALIZED = {"github": GitHubAdapter()}
