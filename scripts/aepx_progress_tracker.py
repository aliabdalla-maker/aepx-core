"""Offline, evidence-gated AEP-X milestone progress calculator.

Input is an explicit JSON manifest containing unverified claims. This does NOT query GitHub,
verify signatures, or assert that referenced tests really ran.
"""
import argparse
import json
from pathlib import Path

WEIGHTS={
 "architecture":10,
 "core_application":15,
 "security":20,
 "postgres_execution":15,
 "docker_oci":10,
 "autonomous_engineering":15,
 "ci_observability":10,
 "scale_recovery":5,
}
STATES={"not_started":0,"code_committed":25,"tests_verified":70,"accepted":100}
class ProgressDenied(ValueError):
 pass

def calculate(manifest):
 if not isinstance(manifest,dict) or set(manifest)!={"schema_version","milestones"}:
  raise ProgressDenied("invalid manifest")
 if type(manifest["schema_version"]) is not int or manifest["schema_version"]!=1:
  raise ProgressDenied("unsupported manifest version")
 milestones=manifest["milestones"]
 if not isinstance(milestones,dict) or set(milestones)!=set(WEIGHTS):
  raise ProgressDenied("missing or unexpected milestones")
 total=0
 details=[]
 for name,weight in WEIGHTS.items():
  item=milestones[name]
  if not isinstance(item,dict) or set(item)!={"status","evidence"}:
   raise ProgressDenied("invalid milestone "+name)
  status=item["status"]
  evidence=item["evidence"]
  if not isinstance(status,str) or status not in STATES:
   raise ProgressDenied("invalid status "+name)
  if not isinstance(evidence,list) or len(evidence)>20 or any(
      not isinstance(x,str) or not x.strip() or len(x)>512 for x in evidence):
   raise ProgressDenied("invalid evidence "+name)
  if status!="not_started" and not evidence:
   raise ProgressDenied("evidence required "+name)
  if status=="not_started" and evidence:
   raise ProgressDenied("not_started cannot claim evidence")
  score=weight*STATES[status]/100
  total+=score
  details.append({"milestone":name,"weight":weight,"status":status,
                  "weighted_points":score,"evidence":evidence})
 return {"progress_percent":round(total,2),
         "claimed_progress_percent":round(total,2),
         "independently_verified_percent":0,
         "max_percent":100,
         "verification":"unverified_manifest_claims",
         "warning":"Claimed progress is NOT verified; evidence strings are not checked",
         "milestones":details}

def main():
 parser=argparse.ArgumentParser()
 parser.add_argument("manifest",type=Path)
 args=parser.parse_args()
 result=calculate(json.loads(args.manifest.read_text(encoding="utf-8")))
 print(json.dumps(result,indent=2,sort_keys=True))
if __name__=="__main__":
 main()
