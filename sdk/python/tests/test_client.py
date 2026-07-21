import pytest

from aepx import AepxClient, AepxPlugin


def test_envelope_has_all_rfc0001_fields():
    client = AepxClient()
    env = client.envelope("aepx://agent/a", "aepx://connector/b", {"k": "v"})
    assert set(env) == {"version", "messageId", "timestamp", "sender", "receiver",
                        "messageType", "payload", "metadata"}
    assert env["version"] == "1.0"
    assert env["messageType"] == "request"
    assert env["payload"] == {"k": "v"}


def test_envelope_message_ids_are_unique():
    client = AepxClient()
    a = client.envelope("aepx://agent/a", "aepx://connector/b", {})
    b = client.envelope("aepx://agent/a", "aepx://connector/b", {})
    assert a["messageId"] != b["messageId"]


def test_builtin_plugins_attached():
    client = AepxClient()
    for name in ("did", "connectors", "trust", "ledger", "audit"):
        assert name in client.plugins
        assert getattr(client, name) is client.plugins[name]
        assert client.plugins[name].client is client


def test_use_custom_plugin():
    class EchoPlugin(AepxPlugin):
        name = "echo"

        def say(self, msg):
            return msg

    client = AepxClient()
    client.use(EchoPlugin())
    assert client.echo.say("hi") == "hi"
    assert "echo" in client.plugins


def test_use_rejects_bad_plugin_name():
    class Nameless(AepxPlugin):
        name = "not an identifier"

    with pytest.raises(ValueError):
        AepxClient().use(Nameless())


def test_use_rejects_attribute_collision():
    class Collides(AepxPlugin):
        name = "bus_url"

    with pytest.raises(ValueError):
        AepxClient().use(Collides())


def test_entry_point_discovery_loads_builtins_without_error():
    # With the sdk installed (editable in CI), the five built-ins are also
    # published as aepx.plugins entry points — discovery must at minimum
    # not blow up, and never remove the always-attached built-ins.
    client = AepxClient(discover_plugins=True)
    for name in ("did", "connectors", "trust", "ledger", "audit"):
        assert name in client.plugins


def test_send_posts_envelope_to_bus(fake_api):
    fake_api.on("POST", "/bus/route", body={"connector": "ml"})
    client = AepxClient()
    resp = client.send(client.envelope("aepx://agent/a", "aepx://connector/ml", {}))
    assert resp.status_code == 200
    method, path, kwargs = fake_api.calls[-1]
    assert (method, path) == ("POST", "/bus/route")
    assert kwargs["json"]["receiver"] == "aepx://connector/ml"
