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
