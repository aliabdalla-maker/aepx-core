#!/usr/bin/env python3
"""Read-only OCI staging smoke test. Loopback only; no mutation or public probing."""
import argparse
import json
import urllib.error
import urllib.request

def probe(url,timeout=5):
    try:
        with urllib.request.urlopen(urllib.request.Request(url,method="GET"),timeout=timeout) as response:
            body=response.read(65536)
            return {"ok":200<=response.status<300,"status":response.status,
                    "body":body.decode("utf-8","replace")[:200]}
    except (urllib.error.URLError,TimeoutError,OSError) as exc:
        return {"ok":False,"error":type(exc).__name__}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--base-url",default="http://127.0.0.1:8000")
    args=parser.parse_args()
    if args.base_url.rstrip("/") not in ("http://127.0.0.1:8000","http://localhost:8000"):
        parser.error("only local staging gateway permitted")
    result=probe(args.base_url.rstrip("/")+"/health")
    print(json.dumps({"target":"local gateway health","result":result},indent=2))
    return 0 if result["ok"] else 1

if __name__=="__main__":
    raise SystemExit(main())
