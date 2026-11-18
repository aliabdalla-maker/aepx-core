"""Dev/CI harness: serves web/out and proxies /api/* to the control plane.
Env: AAV_CONSOLE_OUT (default web/out), AAV_API (default http://127.0.0.1:8000)."""
import os
from pathlib import Path

import httpx
from starlette.applications import Starlette
from starlette.responses import FileResponse, Response
from starlette.routing import Route

OUT = Path(os.environ.get("AAV_CONSOLE_OUT", "web/out"))
API = os.environ.get("AAV_API", "http://127.0.0.1:8000")
HOP = ("content-encoding", "content-length", "transfer-encoding")


async def handler(request):
    p = request.url.path
    if p.startswith("/api/"):
        async with httpx.AsyncClient(base_url=API) as c:
            r = await c.request(request.method, p[4:], params=request.query_params, content=await request.body(),
                                headers={k: v for k, v in request.headers.items() if k.lower() not in ("host", "content-length")})
        return Response(r.content, r.status_code, headers={k: v for k, v in r.headers.items() if k.lower() not in HOP})
    f = OUT / p.lstrip("/")
    if f.is_dir():
        f = f / "index.html"
    if not f.exists():
        f = OUT / "404.html"
    return FileResponse(f)


app = Starlette(routes=[Route("/{path:path}", handler, methods=["GET", "POST", "PUT", "PATCH", "DELETE"])])
