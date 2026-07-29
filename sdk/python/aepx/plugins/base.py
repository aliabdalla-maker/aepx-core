"""Plugin contract — RFC-0007.

A plugin is any object with an identifier-safe ``name`` and an
``attach(client)`` method; after ``client.use(plugin)`` it is reachable as
``client.<name>``. Third-party packages publish theirs under the
``aepx.plugins`` entry point group and ``AepxClient(discover_plugins=True)``
picks them up automatically.
"""


class AepxPlugin:
    name = "plugin"

    def attach(self, client) -> None:
        self.client = client

    def _get(self, url: str, **kwargs):
        return self.client._request("GET", url, **kwargs)

    def _post(self, url: str, **kwargs):
        return self.client._request("POST", url, **kwargs)
