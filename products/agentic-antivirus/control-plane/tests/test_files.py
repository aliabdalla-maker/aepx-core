"""VFS-01..17 and the file-handler capability matrix (DLV-19)."""
import io
import tarfile
import zipfile

import pytest

from conftest import eicar


@pytest.fixture
def fs(new_account, baseline_bundle):
    return new_account("fs")


def up(a, name, data, parent=None):
    params = {"parent_id": parent} if parent else {}
    return a.post("/v1/files/upload", params=params, files={"file": (name, data)})


def test_upload_scan_sniff_version_download(fs):
    r = up(fs, "notes.txt", b"hello")
    assert r.status_code == 201 and r.json()["mime"] == "text/plain"
    nid = r.json()["id"]
    r2 = up(fs, "notes.txt", b"hello again")
    assert r2.json()["id"] == nid and r2.json()["version"] == 2
    assert [v["version"] for v in fs.get(f"/v1/files/{nid}/versions").json()] == [2, 1]
    d = fs.get(f"/v1/files/{nid}/download")
    assert d.content == b"hello again" and d.headers["x-content-type-options"] == "nosniff"
    assert d.headers["content-type"] == "application/octet-stream"
    assert fs.get(f"/v1/files/{nid}/download", params={"version": 1}).content == b"hello"
    assert fs.post(f"/v1/files/{nid}/verify").json()["ok"] is True
    png = up(fs, "pic.txt", b"\x89PNG\r\n\x1a\n" + b"0" * 20)
    assert png.json()["mime"] == "image/png"  # content wins over the extension
    exe = up(fs, "readme.pdf", b"MZ\x90\x00" + b"\x00" * 60)
    assert exe.json()["mime"] == "application/x-msdownload"


def test_malware_upload_rejected_and_audited(fs):
    r = up(fs, "free.exe", eicar())
    assert r.status_code == 422 and r.json()["detail"]["scan_status"] == "infected"
    assert any(e["action"] == "file.upload_rejected" for e in fs.get("/v1/audit").json())
    assert fs.get("/v1/files").json() == []


def test_size_limit_and_quota(fs):
    assert up(fs, "big.bin", b"0" * (2 * 1024 * 1024 + 1)).status_code == 413
    for i in range(2):
        assert up(fs, f"f{i}.bin", bytes([i]) * (2 * 1024 * 1024 - 10)).status_code == 201
    assert up(fs, "f3.bin", b"\x07" * (2 * 1024 * 1024 - 10)).status_code == 507


@pytest.mark.parametrize("name", ["../etc/passwd", "a/b", "..", ".", "a\\b", "x\x00y"])
def test_bad_names_rejected(fs, name):
    assert fs.post("/v1/files/folders", json={"name": name}).status_code == 422


def test_folder_crud_move_copy_trash_restore_retention_purge(fs):
    a = fs.post("/v1/files/folders", json={"name": "cases"}).json()["id"]
    b = fs.post("/v1/files/folders", json={"name": "inc-1", "parent_id": a}).json()["id"]
    assert fs.post("/v1/files/folders", json={"name": "cases"}).status_code == 409
    f = up(fs, "log.csv", b"host,score\nws1,5\n", parent=b).json()["id"]
    assert fs.patch(f"/v1/files/{a}", json={"parent_id": b}).status_code == 422  # into itself
    assert fs.patch(f"/v1/files/{f}", json={"name": "evidence.csv"}).status_code == 200
    c = fs.post(f"/v1/files/{a}/copy", json={}).json()["id"]
    names = sorted(n["name"] for n in fs.get("/v1/files").json())
    assert names == ["cases", "cases (copy)"]
    assert fs.get("/v1/files", params={"q": "evidence"}).json()[0]["name"] == "evidence.csv"
    assert fs.get("/v1/files", params={"q": "evidence", "mime": "text/csv"}).json()
    assert fs.get("/v1/files", params={"sort": "size_bytes", "order": "desc", "parent_id": b}).status_code == 200
    assert fs.put(f"/v1/files/{c}/retention", json={"days": 30}).status_code == 200
    fs.delete(f"/v1/files/{c}")
    assert fs.delete(f"/v1/files/{c}/purge").status_code == 423  # retained
    fs.delete(f"/v1/files/{a}")
    assert fs.get("/v1/files").json() == []
    assert {n["name"] for n in fs.get("/v1/files", params={"trashed": True, "q": ""}).json()} >= {"cases", "evidence.csv"}
    assert fs.post(f"/v1/files/{f}/restore").status_code == 409  # parent still trashed
    assert fs.post(f"/v1/files/{a}/restore").status_code == 200
    assert fs.get(f"/v1/files/{f}/download").content == b"host,score\nws1,5\n"
    fs.put(f"/v1/files/{c}/retention", json={"days": 0})
    assert fs.delete(f"/v1/files/{c}/purge").status_code == 200


def test_handlers_preview_edit_convert_gated(fs):
    caps = fs.get("/v1/files/handlers").json()
    assert caps["handlers"]["text/csv"]["convert"] == ["application/json"]
    assert caps["handlers"]["application/vnd.openxmlformats-officedocument.wordprocessingml.document"]["verified"] is True
    csv_id = up(fs, "t.csv", b"a,b\n1,2\n").json()["id"]
    assert fs.get(f"/v1/files/{csv_id}/preview").json()["text"].startswith("a,b")
    j = fs.post(f"/v1/files/{csv_id}/convert", params={"to": "application/json"}).json()
    assert fs.get(f"/v1/files/{j['id']}/download").json() == [{"a": "1", "b": "2"}]
    back = fs.post(f"/v1/files/{j['id']}/convert", params={"to": "text/csv"})
    assert back.status_code == 409  # t.csv already exists
    assert fs.put(f"/v1/files/{j['id']}/content", json={"content": "{not json"}).status_code == 422
    assert fs.put(f"/v1/files/{j['id']}/content", json={"content": "[]"}).json()["version"] == 2
    docx = up(fs, "r.docx", b"PK\x03\x04" + b"\x00" * 40).json()
    assert docx["mime"].endswith("wordprocessingml.document")
    assert fs.get(f"/v1/files/{docx['id']}/preview").status_code == 422  # verified handler, corrupt package
    assert fs.put(f"/v1/files/{docx['id']}/content", json={"content": "x"}).status_code == 415
    blob = up(fs, "data.xyz", b"\x00\x01\x02binary").json()
    assert blob["mime"] == "application/octet-stream"  # opaque but stored
    assert fs.post(f"/v1/files/{blob['id']}/convert", params={"to": "text/csv"}).status_code == 415


def _zip(entries):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data in entries:
            z.writestr(name, data)
    return buf.getvalue()


def test_bulk_import_export_and_archive_attacks(fs):
    good = _zip([("case/a.txt", b"A"), ("case/sub/b.txt", b"B")])
    assert fs.post("/v1/files/import", files={"file": ("x.zip", good)}).json() == {"imported": 2}
    case = next(n for n in fs.get("/v1/files").json() if n["name"] == "case")["id"]
    for fmt in ("zip", "tar", "tar.gz"):
        r = fs.get(f"/v1/files/{case}/export", params={"fmt": fmt})
        assert r.status_code == 200
        if fmt == "zip":
            with zipfile.ZipFile(io.BytesIO(r.content)) as z:
                assert sorted(z.namelist()) == ["case/a.txt", "case/sub/b.txt"]
        else:
            with tarfile.open(fileobj=io.BytesIO(r.content)) as t:
                assert sorted(t.getnames()) == ["case/a.txt", "case/sub/b.txt"]
    for bad in (_zip([("../evil.txt", b"x")]), _zip([("/abs.txt", b"x")]), _zip([("C:/win.txt", b"x")])):
        assert fs.post("/v1/files/import", files={"file": ("b.zip", bad)}).status_code == 422
    zi = zipfile.ZipInfo("link")
    zi.external_attr = (0o120777 << 16)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(zi, "/etc/passwd")
    assert fs.post("/v1/files/import", files={"file": ("s.zip", buf.getvalue())}).status_code == 422
    tbuf = io.BytesIO()
    with tarfile.open(fileobj=tbuf, mode="w") as t:
        ti = tarfile.TarInfo("ln")
        ti.type, ti.linkname = tarfile.SYMTYPE, "/etc/shadow"
        t.addfile(ti)
    assert fs.post("/v1/files/import", files={"file": ("s.tar", tbuf.getvalue())}).status_code == 422
    infected = _zip([("ok.txt", b"fine"), ("bad.com", eicar())])
    assert fs.post("/v1/files/import", files={"file": ("i.zip", infected)}).status_code == 422


def test_files_are_tenant_isolated(fs, new_account):
    other = new_account("fs2")
    nid = up(fs, "secret.txt", b"tenant A only").json()["id"]
    assert other.get(f"/v1/files/{nid}/download").status_code == 404
    assert other.get("/v1/files").json() == []
