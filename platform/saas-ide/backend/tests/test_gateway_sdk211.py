"""Real provider SDK HTTP stacks through an offline authenticated TLS CONNECT fixture.

No real API keys, paid calls, public DNS or external execution. SDK responses are
minimal fixtures and are only asserted at HTTP transport level.
"""
import httpx
import pytest
from test_gateway_tls211 import tls_gateway  # shared offline fixture

def transport(proxy,ca):
    return httpx.Client(proxy=httpx.Proxy(proxy,headers={"Proxy-Authorization":"Bearer "+"t"*40}),
                        verify=ca,trust_env=False,follow_redirects=False,timeout=5)

def test_real_openai_sdk_uses_gateway(tls_gateway):
    openai=pytest.importorskip("openai")
    proxy,ca,seen=tls_gateway
    with transport(proxy,ca) as http:
        with openai.OpenAI(api_key="offline-test-key",base_url="https://provider.example/v1",
                           http_client=http,max_retries=0) as sdk:
            # SDK's own HTTP request machinery, response status and headers.
            response=sdk.with_raw_response.responses.create(model="offline-model",input="offline")
            assert response.status_code==200
    assert any(b"POST /v1/responses" in x for x in seen)

def test_real_anthropic_sdk_uses_gateway(tls_gateway):
    anthropic=pytest.importorskip("anthropic")
    proxy,ca,seen=tls_gateway
    with transport(proxy,ca) as http:
        with anthropic.Anthropic(api_key="offline-test-key",base_url="https://provider.example",
                                 http_client=http,max_retries=0) as sdk:
            response=sdk.messages.with_raw_response.create(
                model="offline-model",max_tokens=4,messages=[{"role":"user","content":"offline"}])
            assert response.status_code==200
    assert any(b"POST /v1/messages" in x for x in seen)

def test_sdk_tls_invalid_certificate_rejected(tls_gateway):
    openai=pytest.importorskip("openai")
    proxy,ca,seen=tls_gateway
    with httpx.Client(proxy=httpx.Proxy(proxy,headers={"Proxy-Authorization":"Bearer "+"t"*40}),
                      verify=True,trust_env=False,timeout=5) as http:
        with openai.OpenAI(api_key="offline-test-key",base_url="https://provider.example/v1",
                           http_client=http,max_retries=0) as sdk:
            with pytest.raises(openai.APIConnectionError):
                sdk.responses.create(model="offline-model",input="offline")
