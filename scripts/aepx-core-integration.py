#!/usr/bin/env python3
"""Dependency-free, read-only core HTTP acceptance probes. No privileged actions."""
import argparse, datetime, json, sys, time, urllib.request, urllib.error
from pathlib import Path

SERVICES = ("gateway","identity","trust","registry","memory","cache","governance")
def probe(name, base, attempts, delay):
    result={"service":name,"url":base+"/openapi.json","passed":False,"attempts":0}
    for i in range(1,attempts+1):
        result["attempts"]=i
        try:
            with urllib.request.urlopen(result["url"],timeout=8) as r:
                body=r.read(1048576)
                data=json.loads(body)
                if r.status!=200 or not isinstance(data,dict) or not data.get("openapi") or not isinstance(data.get("paths"),dict):
                    raise ValueError("Missing OpenAPI version or paths")
                result.update(passed=True,title=data.get("info",{}).get("title",""),path_count=len(data["paths"]))
                result.pop("error",None)
                return result
        except Exception as e:
            result["error"]=f"{type(e).__name__}: {str(e)[:250]}"
            if i<attempts: time.sleep(delay)
    return result

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--host",default="127.0.0.1")
    p.add_argument("--attempts",type=int,default=12)
    p.add_argument("--delay",type=float,default=2)
    p.add_argument("--output",default="artifacts/aepx-core-integration.json")
    args=p.parse_args()
    if args.attempts<1 or args.delay<0: p.error("invalid retries")
    # Ports correspond to the checked-in development Compose file.
    ports={"gateway":8000,"identity":8001,"trust":8002,"registry":8003,"memory":8004,"cache":8005,"governance":8009}
    results=[probe(name,f"http://{args.host}:{ports[name]}",args.attempts,args.delay) for name in SERVICES]
    report={"timestamp_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "scope":"Read-only OpenAPI availability, not business workflow or production acceptance",
            "results":results,"passed":sum(x["passed"] for x in results),"total":len(results)}
    output=Path(args.output);output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,indent=2)+"\n")
    for r in results:print(("PASS" if r["passed"] else "FAIL"),r["service"],r.get("error",""))
    print(f"Report: {output}; {report['passed']}/{report['total']} passed")
    return 0 if report["passed"]==report["total"] else 1
if __name__=="__main__":sys.exit(main())
