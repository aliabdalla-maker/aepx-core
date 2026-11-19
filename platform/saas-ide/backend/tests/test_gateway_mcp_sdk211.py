"""Real MCP streamable HTTP session against the offline TLS-over-CONNECT fixture."""
import asyncio
import httpx
import pytest
from test_gateway_tls211 import tls_gateway

def test_real_mcp_session_initialize_and_call_tool(tls_gateway):
    pytest.importorskip("mcp")
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client
    proxy,ca,seen=tls_gateway
    async def exercise():
        async with httpx.AsyncClient(
            proxy=httpx.Proxy(proxy,headers={"Proxy-Authorization":"Bearer "+"t"*40}),
            verify=ca,trust_env=False,follow_redirects=False,timeout=5) as client:
            async with streamable_http_client("https://provider.example/mcp",http_client=client) as (read,write,_):
                async with ClientSession(read,write) as session:
                    result=await session.initialize()
                    assert result.serverInfo.name=="offline-mcp"
                    tool=await session.call_tool("ping",arguments={})
                    assert any(getattr(item,"text",None)=="offline-tool-result" for item in tool.content)
    asyncio.run(exercise())
    assert sum(b"POST /mcp" in entry for entry in seen)>=2
