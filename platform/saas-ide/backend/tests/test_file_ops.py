"""Rename/move files and folders, delete folders: atomic, versioned, audited, role- and tenant-checked."""
import os

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from tests.test_postgres_integration import headers, main, prepared_db, tokens  # noqa: F401


def setup(client, token, files):
    h = headers(token, "alpha")
    pid = client.post("/api/v1/projects", json={"name": "file ops"}, headers=h).json()["id"]
    for path, content in files.items():
        assert client.put(f"/api/v1/projects/{pid}/files/{path}", json={"content": content}, headers=h).status_code == 200
    return pid, h


def paths(client, pid, h):
    return sorted(f["path"] for f in client.get(f"/api/v1/projects/{pid}/files", headers=h).json())


def move(client, pid, h, src, dst):
    return client.post(f"/api/v1/projects/{pid}/files-move", json={"from_path": src, "to_path": dst}, headers=h)


def test_rename_file_keeps_content_and_history(prepared_db, tokens):
    c = TestClient(main.app)
    pid, h = setup(c, tokens(), {"src/a.py": "print(1)"})
    r = move(c, pid, h, "src/a.py", "src/b.py")
    assert r.status_code == 200 and r.json()["count"] == 1
    assert "src/b.py" in paths(c, pid, h) and "src/a.py" not in paths(c, pid, h)
    files = {f["path"]: f["content"] for f in c.get(f"/api/v1/projects/{pid}/files", headers=h).json()}
    assert files["src/b.py"] == "print(1)"
    old = c.get(f"/api/v1/projects/{pid}/history", params={"path": "src/a.py"}, headers=h).json()
    new = c.get(f"/api/v1/projects/{pid}/history", params={"path": "src/b.py"}, headers=h).json()
    assert old[0]["op"] == "delete" and new[0]["op"] == "save"


def test_move_folder_moves_every_file_and_only_that_folder(prepared_db, tokens):
    c = TestClient(main.app)
    pid, h = setup(c, tokens(), {"lib/x.py": "x", "lib/sub/y.py": "y", "library/z.py": "z", "lib.md": "m"})
    r = move(c, pid, h, "lib", "pkg/lib")
    assert r.status_code == 200 and r.json()["count"] == 2
    got = paths(c, pid, h)
    assert {"pkg/lib/x.py", "pkg/lib/sub/y.py", "library/z.py", "lib.md"} <= set(got)
    assert not any(p.startswith("lib/") for p in got)


def test_overlapping_move_succeeds(prepared_db, tokens):
    c = TestClient(main.app)
    pid, h = setup(c, tokens(), {"a/x/y": "1", "a/x/x/y": "2"})
    r = move(c, pid, h, "a/x", "a")
    # a/x/y -> a/y ; a/x/x/y -> a/x/y (an old path in the moved set): must not collide
    assert r.status_code == 200
    files = {f["path"]: f["content"] for f in c.get(f"/api/v1/projects/{pid}/files", headers=h).json()}
    assert files["a/y"] == "1" and files["a/x/y"] == "2"


def test_refuses_conflicts_self_moves_traversal_and_missing(prepared_db, tokens):
    c = TestClient(main.app)
    pid, h = setup(c, tokens(), {"a.py": "a", "b.py": "b", "dir/c.py": "c"})
    assert move(c, pid, h, "a.py", "b.py").status_code == 409
    assert move(c, pid, h, "a.py", "a.py").status_code == 400
    assert move(c, pid, h, "dir", "dir/inner").status_code == 400
    assert move(c, pid, h, "a.py", "../escape.py").status_code == 400
    assert move(c, pid, h, "nope.py", "x.py").status_code == 404
    assert {"a.py", "b.py", "dir/c.py"} <= set(paths(c, pid, h))  # nothing changed
    files = {f["path"]: f["content"] for f in c.get(f"/api/v1/projects/{pid}/files", headers=h).json()}
    assert files["a.py"] == "a" and files["b.py"] == "b"


def test_delete_folder_is_versioned_and_scoped(prepared_db, tokens):
    c = TestClient(main.app)
    pid, h = setup(c, tokens(), {"tmp/a": "1", "tmp/b/c": "2", "tmpfile": "keep"})
    r = c.delete(f"/api/v1/projects/{pid}/folders/tmp", headers=h)
    assert r.status_code == 200 and r.json()["deleted"] == 2
    assert "tmpfile" in paths(c, pid, h) and not any(p.startswith("tmp/") for p in paths(c, pid, h))
    hist = c.get(f"/api/v1/projects/{pid}/history", params={"path": "tmp/b/c"}, headers=h).json()
    assert hist[0]["op"] == "delete"
    assert c.delete(f"/api/v1/projects/{pid}/folders/tmp", headers=h).status_code == 404


def test_roles_and_tenants_are_enforced(prepared_db, tokens):
    admin = create_engine(os.environ["IDE_TEST_ADMIN_DATABASE_URL"])
    with admin.begin() as db:
        db.execute(text("""INSERT INTO ide_memberships (tenant_id, subject, role) VALUES ('alpha','user-media','media_editor')
            ON CONFLICT DO NOTHING"""))
    admin.dispose()
    c = TestClient(main.app)
    pid, h = setup(c, tokens(), {"src/app.py": "code", "media/clip.json": "{}"})
    media = headers(tokens("user-media"), "alpha")
    assert move(c, pid, media, "src/app.py", "media/app.py").status_code == 403      # may not touch src/
    assert move(c, pid, media, "media/clip.json", "src/clip.json").status_code == 403  # may not write src/
    assert move(c, pid, media, "media/clip.json", "media/clip2.json").status_code == 200
    viewer = headers(tokens("user-beta"), "beta")
    assert move(c, pid, viewer, "src/app.py", "src/b.py").status_code in (403, 404)
    assert c.delete(f"/api/v1/projects/{pid}/folders/src", headers=viewer).status_code in (403, 404)
    assert "src/app.py" in paths(c, pid, h)


def test_move_is_audited(prepared_db, tokens):
    c = TestClient(main.app)
    pid, h = setup(c, tokens(), {"one.txt": "1"})
    assert move(c, pid, h, "one.txt", "two.txt").status_code == 200
    admin = create_engine(os.environ["IDE_TEST_ADMIN_DATABASE_URL"])
    with admin.connect() as db:
        row = db.execute(text("SELECT detail FROM ide_audit_events WHERE action='file.move' ORDER BY id DESC LIMIT 1")).first()
    admin.dispose()
    assert row and row[0] == "to two.txt (1 file)"
