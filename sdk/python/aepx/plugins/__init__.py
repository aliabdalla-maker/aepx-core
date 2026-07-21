from aepx.plugins.base import AepxPlugin
from aepx.plugins.did import DIDPlugin
from aepx.plugins.connectors import ConnectorsPlugin
from aepx.plugins.trust import TrustPlugin
from aepx.plugins.ledger import LedgerPlugin
from aepx.plugins.audit import AuditPlugin

# Attached to every AepxClient at construction; third-party plugins load
# separately via the aepx.plugins entry point group (client.py).
BUILTIN_PLUGINS = [DIDPlugin, ConnectorsPlugin, TrustPlugin, LedgerPlugin, AuditPlugin]

__all__ = ["AepxPlugin", "DIDPlugin", "ConnectorsPlugin", "TrustPlugin", "LedgerPlugin", "AuditPlugin", "BUILTIN_PLUGINS"]
