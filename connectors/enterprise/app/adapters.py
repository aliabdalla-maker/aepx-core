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


class SalesforceAdapter:
    def execute(self, payload: dict) -> dict:
        op = payload.get("op")
        if op == "lookup_contact":
            # Swap for a real `simple_salesforce` call once credentials exist.
            return {
                "op": op,
                "result": {"id": "003xx0000004TmiAAE", "name": "Jane Doe", "email": "jane.doe@example.com"},
                "source": "connector:salesforce",
                "confidence": 0.95,
                "maturity": "specialized",
            }
        return {"op": op, "error": "unsupported operation in this adapter"}


SPECIALIZED = {"salesforce": SalesforceAdapter()}
