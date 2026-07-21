"""AepxClient — the protocol-level client (RFC-0001, RFC-0007).

Builds canonical message envelopes and sends them through the Connector
Bus, the platform's structural enforcement point for Law 2 (Trust Before
Execution) and Law 8 (Auditability). Plugins extend the client with
per-subsystem APIs — five ship built in (did, connectors, trust, ledger,
audit) and third parties add their own via the ``aepx.plugins`` entry
point group; see plugins/base.py.
"""
import time
import uuid

import httpx

# Host-port defaults per the Operational Manual §4.2 port map — the right
# values when talking to a `docker compose up` stack from the host. Inside
# the cluster, pass the service-name URLs explicitly.
DEFAULT_URLS = {
    "gateway_url": "http://localhost:8000",
    "identity_url": "http://localhost:8001",
    "trust_url": "http://localhost:8002",
    "registry_url": "http://localhost:8003",
    "governance_url": "http://localhost:8009",
    "bus_url": "http://localhost:8020",
}

ENTRY_POINT_GROUP = "aepx.plugins"


class AepxClient:
    def __init__(self, gateway_url=None, identity_url=None, trust_url=None,
                 registry_url=None, governance_url=None, bus_url=None,
                 timeout: float = 10.0, discover_plugins: bool = False):
        self.gateway_url = (gateway_url or DEFAULT_URLS["gateway_url"]).rstrip("/")
        self.identity_url = (identity_url or DEFAULT_URLS["identity_url"]).rstrip("/")
        self.trust_url = (trust_url or DEFAULT_URLS["trust_url"]).rstrip("/")
        self.registry_url = (registry_url or DEFAULT_URLS["registry_url"]).rstrip("/")
        self.governance_url = (governance_url or DEFAULT_URLS["governance_url"]).rstrip("/")
        self.bus_url = (bus_url or DEFAULT_URLS["bus_url"]).rstrip("/")
        self.timeout = timeout
        self.plugins: dict[str, "object"] = {}

        from aepx.plugins import BUILTIN_PLUGINS
        for plugin_cls in BUILTIN_PLUGINS:
            self.use(plugin_cls())
        if discover_plugins:
            for plugin in _discover_entry_point_plugins():
                self.use(plugin)

    # -- HTTP -------------------------------------------------------------
    def _request(self, method: str, url: str, **kwargs) -> httpx.Response:
        kwargs.setdefault("timeout", self.timeout)
        return httpx.request(method, url, **kwargs)

    # -- RFC-0001 ---------------------------------------------------------
    def envelope(self, sender: str, receiver: str, payload: dict,
                 message_type: str = "request", metadata: dict | None = None) -> dict:
        return {
            "version": "1.0",
            "messageId": str(uuid.uuid4()),
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "sender": sender,
            "receiver": receiver,
            "messageType": message_type,
            "payload": payload,
            "metadata": metadata or {},
        }

    def send(self, envelope: dict) -> httpx.Response:
        # Returned raw (not .json()'d): a 403 here is a meaningful protocol
        # outcome (trust/policy denial with a governance reason), not an
        # error to be swallowed.
        return self._request("POST", f"{self.bus_url}/bus/route", json=envelope)

    # -- Plugins (RFC-0007) -------------------------------------------------
    def use(self, plugin) -> "AepxClient":
        name = getattr(plugin, "name", None)
        if not name or not name.isidentifier():
            raise ValueError(f"plugin {plugin!r} needs a valid identifier 'name' attribute")
        if hasattr(self, name) and name not in self.plugins:
            raise ValueError(f"plugin name '{name}' collides with an AepxClient attribute")
        plugin.attach(self)
        self.plugins[name] = plugin
        setattr(self, name, plugin)
        return self


def _discover_entry_point_plugins() -> list:
    # Best-effort: a broken third-party plugin must never break client
    # construction for everyone else.
    from importlib.metadata import entry_points
    plugins = []
    try:
        for ep in entry_points(group=ENTRY_POINT_GROUP):
            try:
                plugins.append(ep.load()())
            except Exception:
                continue
    except Exception:
        pass
    return plugins
