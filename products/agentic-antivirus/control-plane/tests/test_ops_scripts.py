"""Deployment scripts exercised for real (Phase 2: OCI-10, OCI-16, RA-12, RA-13, CI-14/15).

A `docker` shim on PATH stands in for the container runtime only: `docker compose config` goes to the real Docker
CLI (so guard.py validates the true merged config), and every database command runs the real PostgreSQL tools
(pg_dump, pg_restore, psql) against the scratch test server. openssl, sha256sum, git and the scripts themselves
are the production ones, unmodified.
"""
from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import textwrap

import psycopg
import pytest

from conftest import ADMIN_DSN, DB_NAME, PRODUCT

DEPLOY = PRODUCT / "deploy"
REAL_DOCKER = shutil.which("docker")
pytestmark = pytest.mark.skipif(not REAL_DOCKER or not shutil.which("pg_dump") or not shutil.which("openssl"),
                                reason="needs the docker CLI, PostgreSQL client tools and openssl")

SHIM = textwrap.dedent('''\
    #!/usr/bin/env python3
    """docker shim for tests: runtime commands map to local PostgreSQL; `compose config` uses the real CLI."""
    import os, subprocess, sys
    a = sys.argv[1:]
    open(os.environ["SHIM_LOG"], "a").write(" ".join(a) + "\\n")
    base = os.environ["SHIM_PG_BASE"]            # e.g. "host=/tmp/pg port=55432 user=postgres"
    live = os.environ["SHIM_LIVE_DB"]
    def pg(db): return f"{base} dbname={db}"
    def run(cmd, **kw): sys.exit(subprocess.run(cmd, **kw).returncode)
    if a[:1] == ["compose"]:
        rest = [x for x in a[1:]]
        if "config" in rest:
            run([os.environ["SHIM_REAL_DOCKER"], *a])
        if "exec" in rest:
            i = rest.index("exec"); args = [x for x in rest[i + 1:] if x != "-T"]
            svc, cmd = args[0], args[1:]
            if svc == "postgres":
                if cmd[0] == "pg_isready": sys.exit(0)
                if cmd[0] == "pg_dump": run(["pg_dump", "--format=custom", pg(live)])
                if cmd[0] == "psql":
                    q = cmd[cmd.index("-tAc") + 1] if "-tAc" in cmd else None
                    run(["psql", pg(live), "-tAc", q]) if q else sys.exit(0)
                if cmd[0] == "sh": sys.stdin.read(); sys.exit(0)       # migrate.sh: schema already current
            if svc == "web" and cmd[0] == "wget":
                url = cmd[-1]
                if url.endswith("/api/ready"):
                    print('{"ready":%s}' % os.environ.get("SHIM_READY", "true")); sys.exit(0)
                if url.endswith("/api/health"):
                    print('{"status":"ok","build":"%s"}' % os.environ.get("SHIM_BUILD", "")); sys.exit(0)
                print("<html>login</html>"); sys.exit(0)
            sys.exit(0)                                                # publish-baseline etc.
        sys.exit(0)                                                    # up / logs / stop
    if a[0] == "run":                                                  # throwaway restore container
        name = a[a.index("--name") + 1]
        subprocess.run(["psql", pg("postgres"), "-qc", f'CREATE DATABASE "{name}"'], check=True)
        print(name); sys.exit(0)
    if a[0] == "stop":
        subprocess.run(["psql", pg("postgres"), "-qc", f'DROP DATABASE IF EXISTS "{a[1]}" WITH (FORCE)'])
        sys.exit(0)
    if a[0] == "exec":
        args = [x for x in a[1:] if x not in ("-i", "-T")]
        name, cmd = args[0], args[1:]
        if cmd[0] == "pg_isready": sys.exit(0)
        if cmd[0] == "pg_restore": run(["pg_restore", "--no-owner", "--exit-on-error", "-d", pg(name)])
        if cmd[0] == "psql":
            if "-c" in cmd and "CREATE ROLE" in cmd[cmd.index("-c") + 1]: sys.exit(0)  # roles are cluster-wide here
            q = cmd[cmd.index("-tAc") + 1]
            run(["psql", pg(name), "-tAc", q])
    sys.exit(f"shim: unhandled docker {a}")
''')


@pytest.fixture()
def shim(tmp_path, database):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    p = bindir / "docker"
    p.write_text(SHIM)
    p.chmod(p.stat().st_mode | stat.S_IXUSR)
    info = psycopg.conninfo.conninfo_to_dict(ADMIN_DSN)
    base = " ".join(f"{k}={v}" for k, v in info.items() if k in ("host", "port", "user", "password"))
    passfile = tmp_path / "backup.pass"
    passfile.write_text("rehearsal passphrase " + "x" * 24)
    passfile.chmod(0o600)
    env = dict(os.environ, PATH=f"{bindir}:{os.environ['PATH']}", SHIM_LOG=str(tmp_path / "docker.log"),
               SHIM_PG_BASE=base, SHIM_LIVE_DB=DB_NAME, SHIM_REAL_DOCKER=REAL_DOCKER,
               AAV_BACKUP_PASSPHRASE_FILE=str(passfile), AAV_BACKUP_DIR=str(tmp_path / "backups"),
               AAV_EVIDENCE_DIR=str(tmp_path / "evidence"), AAV_COMPOSE_DIR=str(DEPLOY))
    return env, tmp_path


def test_backup_is_encrypted_and_restore_rehearsal_matches_live(shim, new_account):
    env, tmp = shim
    new_account("admin")   # make sure the live database has a tenant to restore
    out = subprocess.run([str(DEPLOY / "backup.sh")], env=env, capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    dumps = sorted((tmp / "backups").glob("aav-*.dump.enc"))
    assert len(dumps) == 1
    raw = dumps[0].read_bytes()
    assert raw[:8] == b"Salted__" and b"PGDMP" not in raw[:64]      # openssl-encrypted, not a plain dump
    r = subprocess.run([str(DEPLOY / "restore-rehearsal.sh"), str(dumps[0])], env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    ev = json.loads(next((tmp / "evidence").glob("restore-*.json")).read_text())
    assert ev["passed"] is True and ev["restore_seconds"] >= 0
    by = {t["table"]: t for t in ev["tables"]}
    assert int(by["tenants"]["restored"]) >= 1
    assert by["tenants"]["restored"] == by["tenants"]["live_now"]


def test_restore_rehearsal_refuses_a_tampered_backup(shim):
    env, tmp = shim
    subprocess.run([str(DEPLOY / "backup.sh")], env=env, check=True, capture_output=True)
    dump = next((tmp / "backups").glob("aav-*.dump.enc"))
    with open(dump, "r+b") as f:
        f.seek(100)
        f.write(b"\x00\x01\x02")
    r = subprocess.run([str(DEPLOY / "restore-rehearsal.sh"), str(dump)], env=env, capture_output=True, text=True)
    assert r.returncode != 0 and "FAILED" in (r.stdout + r.stderr)


@pytest.fixture()
def deploy_repo(shim):
    """A throwaway git checkout of the deploy directory, so deploy.sh can verify HEAD and keep its markers."""
    env, tmp = shim
    repo = tmp / "repo"
    shutil.copytree(DEPLOY, repo, ignore=shutil.ignore_patterns(".last-verified-sha*", ".staged-shas"))
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "-c", "user.email=t@example.com", "-c", "user.name=t", "commit", "-qam", "x",
                    "--allow-empty"], cwd=repo, check=True)
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "-c", "user.email=t@example.com", "-c", "user.name=t", "commit", "-qm", "deploy"],
                   cwd=repo, check=True)
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    envfile = tmp / "aav.env"
    envfile.write_text("AAV_POSTGRES_PASSWORD=p\nAAV_APP_DB_PASSWORD=q\n"
                       f"AAV_SIGNING_KEY_PATH={repo / 'guard.py'}\n")
    env = dict(env, AAV_ENV_FILE=str(envfile), SHIM_BUILD=sha[:12])
    env.pop("AAV_COMPOSE_DIR")
    return env, repo, sha


def _deploy(env, repo, sha, target, **extra):
    return subprocess.run([str(repo / "deploy.sh"), sha, target], env=dict(env, **extra), cwd=repo,
                          capture_output=True, text=True)


def test_production_refuses_a_commit_that_skipped_staging(deploy_repo):
    env, repo, sha = deploy_repo
    r = _deploy(env, repo, sha, "production")
    assert r.returncode == 3 and "has not passed staging" in r.stderr
    assert not (repo / ".last-verified-sha").exists()


def test_staging_then_production_with_backup(deploy_repo):
    env, repo, sha = deploy_repo
    st = _deploy(env, repo, sha, "staging")
    assert st.returncode == 0, st.stdout + st.stderr
    assert (repo / ".last-verified-sha-staging").read_text().strip() == sha
    assert sha in (repo / ".staged-shas").read_text().split()
    no_backup = _deploy({k: v for k, v in env.items() if k != "AAV_BACKUP_PASSPHRASE_FILE"}, repo, sha, "production")
    assert no_backup.returncode == 4 and "never deploys without a backup" in no_backup.stderr
    pr = _deploy(env, repo, sha, "production")
    assert pr.returncode == 0, pr.stdout + pr.stderr
    assert (repo / ".last-verified-sha").read_text().strip() == sha
    assert list((tmp_backups := (repo.parent / "backups")).glob("aav-*.dump.enc")), tmp_backups


def test_failed_readiness_does_not_mark_the_release_verified(deploy_repo):
    env, repo, sha = deploy_repo
    r = _deploy(env, repo, sha, "staging", SHIM_READY="false", AAV_READY_TRIES="2", AAV_READY_SLEEP="0")
    assert r.returncode == 1 and "rolling back" in r.stderr
    assert not (repo / ".last-verified-sha-staging").exists()
    assert not (repo / ".staged-shas").exists()


def test_skip_staging_override_is_recorded(deploy_repo):
    env, repo, sha = deploy_repo
    r = _deploy(env, repo, sha, "production", AAV_SKIP_STAGING="1")
    assert r.returncode == 0, r.stdout + r.stderr
    assert f"{sha} skip-staging" in (repo / ".staging-overrides").read_text()


def test_guard_accepts_every_overlay_and_rejects_a_public_port(tmp_path):
    env = {k: v for k, v in os.environ.items() if k not in ("COMPOSE_FILE", "AAV_COMPOSE_DIR")}
    for files in ("compose.yml", "compose.yml:compose.cohost.yml", "compose.yml:compose.staging.yml"):
        r = subprocess.run(["python3", str(DEPLOY / "guard.py")], env=dict(env, COMPOSE_FILE=files),
                           capture_output=True, text=True)
        assert r.returncode == 0, (files, r.stdout, r.stderr)
    bad = DEPLOY / "compose.test-public.yml"
    bad.write_text("services:\n  web:\n    ports: !override [\"0.0.0.0:18481:8080\"]\n")
    try:
        r = subprocess.run(["python3", str(DEPLOY / "guard.py")],
                           env=dict(env, COMPOSE_FILE="compose.yml:compose.test-public.yml"),
                           capture_output=True, text=True)
        assert r.returncode == 1 and "not loopback-only" in r.stdout
    finally:
        bad.unlink()
