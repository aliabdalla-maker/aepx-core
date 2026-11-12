"""Verify real nested TLS through authenticated CONNECT; no provider API calls."""
import socket
import ssl
import time

gateway_ca="/certs/gateway.crt"
provider_ca="/certs/provider.crt"
token="offline-integration-token-1234567890"
for attempt in range(20):
    try:
        raw=socket.create_connection(("gateway",8080),timeout=3)
        break
    except OSError:
        if attempt==19: raise
        time.sleep(1)

outer=ssl.create_default_context(cafile=gateway_ca).wrap_socket(raw,server_hostname="gateway")
outer.sendall(("CONNECT provider.example:443 HTTP/1.1\r\nProxy-Authorization: Bearer "+token+"\r\n\r\n").encode())
reply=b""
while b"\r\n\r\n" not in reply:
    reply+=outer.recv(4096)
assert reply.startswith(b"HTTP/1.1 200"),reply
outer.close()
# Nested TLS requires SSL-over-SSL BIO support; httpx supplies it for SDK use.
import httpx
ctx=ssl.create_default_context(cafile=provider_ca)
proxyctx=ssl.create_default_context(cafile=gateway_ca)
with httpx.Client(proxy=httpx.Proxy("https://gateway:8080",ssl_context=proxyctx,headers={"Proxy-Authorization":"Bearer "+token}),verify=ctx,trust_env=False,timeout=10) as client:
    response=client.get("https://provider.example/")
    assert response.status_code==200,response.text
    assert response.json()=={"mock":"ok","offline":True}
# SDKs use their real HTTPX transport through the same authenticated
# proxy, but receive only synthetic responses from the local mock.
from openai import OpenAI
from anthropic import Anthropic
def sdk_http_client():
    return httpx.Client(
        proxy=httpx.Proxy("https://gateway:8080",ssl_context=proxyctx,
                          headers={"Proxy-Authorization":"Bearer "+token}),
        verify=ctx,trust_env=False,timeout=10)
with sdk_http_client() as transport:
    sdk=OpenAI(api_key="offline-test-key",base_url="https://provider.example/v1",
               http_client=transport,max_retries=0)
    result=sdk.chat.completions.create(model="mock-model",
                 messages=[{"role":"user","content":"offline test"}])
    assert result.choices[0].message.content=="offline-openai-ok"
with sdk_http_client() as transport:
    sdk=Anthropic(api_key="offline-test-key",base_url="https://provider.example",
                  http_client=transport,max_retries=0)
    result=sdk.messages.create(model="mock-model",max_tokens=16,
                               messages=[{"role":"user","content":"offline test"}])
    assert result.content[0].text=="offline-anthropic-ok"
print("Authenticated gateway TLS, mock provider, OpenAI SDK and Anthropic SDK verified offline")


# Negative acceptance: the gateway must reject missing and invalid bearer tokens.
def connect_status(authorization):
    raw=socket.create_connection(("gateway",8080),timeout=5)
    with ssl.create_default_context(cafile=gateway_ca).wrap_socket(raw,server_hostname="gateway") as tls:
        tls.settimeout(5)
        header="CONNECT provider.example:443 HTTP/1.1\r\n"
        if authorization is not None:
            header+="Proxy-Authorization: "+authorization+"\r\n"
        tls.sendall((header+"\r\n").encode())
        return tls.recv(4096)
for invalid in (None,"Bearer invalid-test-credential"):
    assert connect_status(invalid).startswith(b"HTTP/1.1 403"),"Unauthenticated CONNECT accepted"

# The gateway cannot be used to reach an unapproved destination.
def denied_destination():
    raw=socket.create_connection(("gateway",8080),timeout=5)
    with ssl.create_default_context(cafile=gateway_ca).wrap_socket(raw,server_hostname="gateway") as tls:
        tls.settimeout(5)
        tls.sendall(("CONNECT metadata.internal:443 HTTP/1.1\r\nProxy-Authorization: Bearer "+token+"\r\n\r\n").encode())
        return tls.recv(4096)
assert denied_destination().startswith(b"HTTP/1.1 403"),"Unapproved destination accepted"

# A trusted gateway certificate must not override upstream provider trust.
with httpx.Client(proxy=httpx.Proxy("https://gateway:8080",ssl_context=proxyctx,
                  headers={"Proxy-Authorization":"Bearer "+token}),
                  verify=ssl.create_default_context(),trust_env=False,timeout=10) as client:
    try:
        client.get("https://provider.example/")
    except (httpx.ConnectError,httpx.ConnectTimeout) as exc:
        assert "CERTIFICATE_VERIFY_FAILED" in str(exc),str(exc)
    else:
        raise AssertionError("Untrusted provider TLS certificate accepted")

# A valid upstream certificate must not override gateway trust.
with httpx.Client(proxy=httpx.Proxy("https://gateway:8080",
                  ssl_context=ssl.create_default_context(),
                  headers={"Proxy-Authorization":"Bearer "+token}),
                  verify=ctx,trust_env=False,timeout=10) as client:
    try:
        client.get("https://provider.example/")
    except (httpx.ConnectError,httpx.ConnectTimeout) as exc:
        assert "CERTIFICATE_VERIFY_FAILED" in str(exc),str(exc)
    else:
        raise AssertionError("Untrusted gateway TLS certificate accepted")
print("Negative authentication, destination and both TLS trust boundaries verified")

# Offline MCP JSON-RPC transport acceptance (not an MCP SDK conformance test).
# The mock never executes external tools or accesses real provider endpoints.
with sdk_http_client() as transport:
    listed=transport.post("https://provider.example/mcp",
        json={"jsonrpc":"2.0","id":101,"method":"tools/list","params":{}})
    listed.raise_for_status()
    assert listed.json()["result"]["tools"][0]["name"]=="offline_echo"
    invoked=transport.post("https://provider.example/mcp",
        json={"jsonrpc":"2.0","id":102,"method":"tools/call",
              "params":{"name":"offline_echo","arguments":{"value":"gateway"}}})
    invoked.raise_for_status()
    result=invoked.json()
    assert result["id"]==102
    assert result["result"]["content"][0]["text"]=="offline:gateway"
    assert result["result"]["isError"] is False
print("Offline MCP JSON-RPC tool discovery and synthetic tool invocation verified")
