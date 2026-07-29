"""RFC-0008 AI->chain — SDK convenience over the blockchain connector.

Thin wrapper around the connectors plugin: an agent reading or writing a
smart contract is just a governed connector invocation (aepx://connector/
ethereum), so this goes through the exact same trust -> policy ->
circuit-breaker chain as any other connector call — a chain *write* is a
*governed* action, not a raw key operation. Requires the ConnectorsPlugin
to be attached (it is, by default).
"""
from aepx.plugins.base import AepxPlugin


class ChainPlugin(AepxPlugin):
    name = "chain"

    def read(self, address: str, abi: list, function: str, args: list | None = None,
             connector: str = "ethereum", sender: str = "aepx://agent/sdk") -> dict:
        """Call a view/pure contract function (no gas, no key)."""
        payload = {"op": "contract_read", "address": address, "abi": abi,
                   "function": function, "args": args or []}
        return self.client.connectors.invoke(connector, payload, sender=sender)

    def write(self, address: str, abi: list, function: str, args: list | None = None,
              connector: str = "ethereum", sender: str = "aepx://agent/sdk") -> dict:
        """Send a state-changing contract transaction. The platform signs it
        with EVM_PRIVATE_KEY on the connector side; degrades clearly if that
        key is unset (RFC-0008 §6)."""
        payload = {"op": "contract_write", "address": address, "abi": abi,
                   "function": function, "args": args or []}
        return self.client.connectors.invoke(connector, payload, sender=sender)

    def rpc(self, method: str, params: list | None = None,
            connector: str = "ethereum", sender: str = "aepx://agent/sdk") -> dict:
        """Raw JSON-RPC (e.g. eth_blockNumber) through the same governed path."""
        payload = {"method": method, "params": params or []}
        return self.client.connectors.invoke(connector, payload, sender=sender)
