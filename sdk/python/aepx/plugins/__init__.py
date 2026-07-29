from aepx.plugins.base import AepxPlugin
from aepx.plugins.did import DIDPlugin
from aepx.plugins.connectors import ConnectorsPlugin
from aepx.plugins.trust import TrustPlugin
from aepx.plugins.ledger import LedgerPlugin
from aepx.plugins.audit import AuditPlugin
from aepx.plugins.chain import ChainPlugin
from aepx.plugins.oracle import OraclePlugin

# Attached to every AepxClient at construction; third-party plugins load
# separately via the aepx.plugins entry point group (client.py).
# ChainPlugin must come after ConnectorsPlugin — it delegates to it (RFC-0008).
BUILTIN_PLUGINS = [DIDPlugin, ConnectorsPlugin, TrustPlugin, LedgerPlugin, AuditPlugin,
                   ChainPlugin, OraclePlugin]

__all__ = ["AepxPlugin", "DIDPlugin", "ConnectorsPlugin", "TrustPlugin", "LedgerPlugin",
           "AuditPlugin", "ChainPlugin", "OraclePlugin", "BUILTIN_PLUGINS"]
