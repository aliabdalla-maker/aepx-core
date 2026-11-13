#!/usr/bin/env python3
"""Read-only/negative-path acceptance for existing AEP-X APIs; no live tool execution."""
import argparse, datetime, json, pathlib, sys, urllib.parse, urllib.request, urllib.error
def call(base,path,method="GET",body=None):
    data=json.dumps(body).encode() if body is not None else None
    req=urllib.request.Request(base+path,data=data,method=method,headers={"Content-Type":"application/json"})
    try:
        with urllib.request.urlopen(req,timeout=8) as r:
            raw=r.read(1024*1024)
            return r.status,json.loads(raw)
    except urllib.error.HTTPError as e:
        raw=e.read(4096)
        try: detail=json.loads(raw)
        except ValueError: detail={"error":"non-json HTTP error"}
        return e.code,detail
def run(base):
    results=[]
    def record(name,ok,detail):
        results.append({"check":name,"passed":bool(ok),"detail":str(detail)[:180]})
    # Policy: safe risk allowed, high risk denied, invalid risk denied.
    for risk,expected in (("S0",True),("S4",False),("INVALID",False)):
        try:
            status,data=call(base["governance"],"/policy/evaluate?"+urllib.parse.urlencode({"risk_level":risk}),"POST")
            record("governance_"+risk,status==200 and data.get("allowed") is expected,{"http":status,"allowed":data.get("allowed")})
        except Exception as e:record("governance_"+risk,False,type(e).__name__)
    # RAG scaffold: read-only negative retrieval must not fabricate sources.
    try:
        status,data=call(base["knowledge"],"/knowledge/search?"+urllib.parse.urlencode({"query":"aepx_nonexistent_acceptance_marker_9e3c","limit":5}),"POST")
        record("rag_negative_retrieval",status==200 and data.get("results")==[],{"http":status,"hits":len(data.get("results",[]))})
    except Exception as e:record("rag_negative_retrieval",False,type(e).__name__)
    # Missing workflow must not be reported as successful.
    try:
        status,data=call(base["workflow"],"/workflows/00000000-0000-0000-0000-000000000000/execute","POST")
        record("workflow_missing_id_rejected",status in (400,404,422),{"http":status})
    except Exception as e:record("workflow_missing_id_rejected",False,type(e).__name__)
    return results
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--host",default="127.0.0.1")
    p.add_argument("--output",default="artifacts/aepx-agentic-acceptance.json")
    a=p.parse_args()
    bases={name:f"http://{a.host}:{port}" for name,port in {"governance":8009,"knowledge":8010,"workflow":8007}.items()}
    results=run(bases)
    report={"timestamp_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "scope":"Existing governance, knowledge and workflow negative-path probes only; NOT CrewAI/MCP/HITL end-to-end",
            "results":results,"passed":sum(x["passed"] for x in results),"total":len(results)}
    out=pathlib.Path(a.output);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report,indent=2)+"\n")
    for r in results:print("PASS" if r["passed"] else "FAIL",r["check"],r["detail"])
    print(f"Evidence: {out}; {report['passed']}/{report['total']} passed")
    return 0 if report["passed"]==report["total"] else 1
if __name__=="__main__":sys.exit(main())
