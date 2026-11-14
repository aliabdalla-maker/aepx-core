"""Opt-in two-session PostgreSQL approval replay race on disposable localhost DB.

No migration, provider, Docker, cloud, or external service actions.
"""
import argparse
import os
import re
import selectors
import subprocess
import sys
import uuid

TENANT="11111111-1111-4111-8111-111111111111"
def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--execute",action="store_true",required=True)
    parser.add_argument("database")
    args=parser.parse_args()
    if not re.fullmatch(r"aepx_test_[a-z0-9_]{1,40}",args.database):
        parser.error("disposable aepx_test_ database required")
    if os.environ.get("PGHOST","127.0.0.1") not in ("127.0.0.1","localhost"):
        parser.error("remote PGHOST denied")
    for name in ("PGSERVICE","PGSERVICEFILE","PGDATABASE","PGHOSTADDR","PGOPTIONS","PGCONNECT_TIMEOUT"):
        if os.environ.get(name):
            parser.error(name+" must be unset")
    env=os.environ.copy()
    env["PGHOST"]="127.0.0.1"
    env["PGCONNECT_TIMEOUT"]="5"
    cmd=["psql","-X","-A","-t","-v","ON_ERROR_STOP=1","--dbname",args.database]
    def run(sql,check=True):
        return subprocess.run(cmd,input=sql,text=True,capture_output=True,env=env,check=check,timeout=30)
    nonce=str(uuid.uuid4())
    iteration=(uuid.uuid4().int % 10000)+1
    scope=f"SET app.tenant_id='{TENANT}';"
    preflight="""DO $x$ DECLARE b boolean; a boolean; c boolean;
BEGIN
 SELECT rolsuper OR rolbypassrls INTO b FROM pg_roles WHERE rolname=current_user;
 IF b IS DISTINCT FROM false THEN RAISE EXCEPTION 'non-BYPASSRLS role required'; END IF;
 SELECT relrowsecurity,relforcerowsecurity INTO a,c
 FROM pg_class WHERE oid='aepx_iteration.approval_nonce'::regclass;
 IF a IS DISTINCT FROM true OR c IS DISTINCT FROM true THEN RAISE EXCEPTION 'approval RLS required'; END IF;
 SELECT relrowsecurity,relforcerowsecurity INTO a,c
 FROM pg_class WHERE oid='aepx_iteration.work_item'::regclass;
 IF a IS DISTINCT FROM true OR c IS DISTINCT FROM true THEN RAISE EXCEPTION 'work item RLS required'; END IF;
END $x$;"""
    setup=(scope+preflight+"BEGIN;"+f"""
INSERT INTO aepx_iteration.work_item(tenant_id,iteration_number,stage,fence,lease_owner,lease_expires_at)
VALUES ('{TENANT}',{iteration},'reviewed',7,'worker-one',clock_timestamp()+interval '90 seconds');
INSERT INTO aepx_iteration.approval_nonce(tenant_id,iteration_number,nonce,lease_fence,reviewer_id,expires_at)
VALUES ('{TENANT}',{iteration},'{nonce}',7,'reviewer-one',clock_timestamp()+interval '90 seconds');
""")
    setup += "COMMIT;"
    cleanup=(scope+f"DELETE FROM aepx_iteration.approval_nonce WHERE tenant_id='{TENANT}' AND nonce='{nonce}';"
             +f"DELETE FROM aepx_iteration.work_item WHERE tenant_id='{TENANT}' AND iteration_number={iteration};")
    first=None
    second=None
    created=False
    try:
        run(setup)
        created=True
        consume=f"DO $consume$ BEGIN PERFORM aepx_iteration.consume_approval('{TENANT}',{iteration},'{nonce}',7,'reviewer-one'); END $consume$;"
        # Session 1 holds row locks after consuming; session 2 blocks until commit.
        first=subprocess.Popen(cmd,stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE,text=True,env=env,bufsize=1)
        first.stdin.write(scope+"BEGIN;"+consume+"\n\\echo FIRST_CONSUMED\n")
        first.stdin.flush()
        # Bound the first-session readiness wait: a stalled psql must not hang CI.
        with selectors.DefaultSelector() as ready:
            ready.register(first.stdout,selectors.EVENT_READ)
            if not ready.select(timeout=10):
                raise RuntimeError("first session readiness timed out")
        line=first.stdout.readline()
        if "FIRST_CONSUMED" not in line:
            raise RuntimeError("first session did not confirm consumption")
        second=subprocess.Popen(cmd,stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,text=True,env=env)
        try:
            out2,err2=second.communicate(scope+consume,timeout=15)
        except subprocess.TimeoutExpired:
            # The second connection should block on the row lock.
            first.stdin.write("COMMIT;\n")
            first.stdin.flush()
            out2,err2=second.communicate(timeout=15)
        else:
            raise AssertionError("second session did not wait for first transaction")
        first.stdin.close()
        first.wait(timeout=15)
        if first.returncode!=0 or second.returncode==0:
            raise AssertionError("expected first success and second replay denial: "+err2[:500])
        if "approval missing expired mismatched or consumed" not in err2:
            raise AssertionError("unexpected second-session failure: "+err2[:500])
        count=run(scope+f"SELECT count(*) FROM aepx_iteration.approval_nonce WHERE tenant_id='{TENANT}' AND nonce='{nonce}' AND consumed_at IS NOT NULL;").stdout.strip()
        if count!="1":
            raise AssertionError("expected exactly one consumed nonce, got "+count)
        print("PASS: one transaction consumed approval; concurrent replay denied")
    finally:
        for process in (second,first):
            if process is not None and process.poll() is None:
                process.kill()
                process.wait(timeout=5)
        if created:
            run(cleanup)

if __name__=="__main__":
    try:
        main()
    except (subprocess.SubprocessError,RuntimeError,AssertionError) as exc:
        print("FAIL:",exc,file=sys.stderr)
        sys.exit(1)
