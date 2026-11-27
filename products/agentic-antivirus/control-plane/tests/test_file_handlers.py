"""Verified format handlers (VFS-07, VFS-08): Office text/cell extraction, archive listings, inline PDF/media,
conversions, and the safety limits (zip bombs, XML entities)."""
import io
import tarfile
import zipfile

import pytest

from app import file_handlers as fh


@pytest.fixture
def fs(new_account, baseline_bundle):
    return new_account("fh")


def up(a, name, data):
    r = a.post("/v1/files/upload", files={"file": (name, data)})
    assert r.status_code == 201, r.text
    return r.json()


def _pkg(parts: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        for name, data in parts.items():
            z.writestr(name, data)
    return buf.getvalue()


W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
S = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
R = 'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
A = 'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"'


def docx(paras):
    body = "".join(f"<w:p><w:r><w:t>{p}</w:t></w:r></w:p>" for p in paras)
    return _pkg({"word/document.xml": f"<w:document {W}><w:body>{body}</w:body></w:document>"})


def xlsx():
    return _pkg({
        "xl/workbook.xml": f'<workbook {S} {R}><sheets><sheet name="Findings" sheetId="1" r:id="rId1"/></sheets></workbook>',
        "xl/_rels/workbook.xml.rels": '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                                      '<Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>',
        "xl/sharedStrings.xml": f'<sst {S}><si><t>host</t></si><si><t>score</t></si><si><t>finance-lt</t></si></sst>',
        "xl/worksheets/sheet1.xml": f'<worksheet {S}><sheetData>'
                                    '<row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c></row>'
                                    '<row r="2"><c r="A2" t="s"><v>2</v></c><c r="C2"><v>97</v></c></row>'
                                    '</sheetData></worksheet>'})


def pptx():
    def slide(t):
        return f"<p:sld xmlns:p='x' {A}><a:p><a:r><a:t>{t}</a:t></a:r></a:p></p:sld>"
    return _pkg({"ppt/slides/slide1.xml": slide("Incident summary"), "ppt/slides/slide2.xml": slide("Next steps"),
                 "ppt/slides/slide10.xml": slide("Appendix")})


def test_office_preview_and_conversion(fs):
    d = up(fs, "report.docx", docx(["Containment complete", "Root cause: phishing"]))
    pv = fs.get(f"/v1/files/{d['id']}/preview").json()
    assert pv["kind"] == "document" and pv["text"] == "Containment complete\nRoot cause: phishing"
    t = fs.post(f"/v1/files/{d['id']}/convert", params={"to": "text/plain"}).json()
    assert t["name"] == "report.txt"
    assert fs.get(f"/v1/files/{t['id']}/download").content == b"Containment complete\nRoot cause: phishing"

    x = up(fs, "scores.xlsx", xlsx())
    sheets = fs.get(f"/v1/files/{x['id']}/preview").json()["sheets"]
    assert sheets[0]["name"] == "Findings"
    assert sheets[0]["rows"] == [["host", "score"], ["finance-lt", "", "97"]]
    c = fs.post(f"/v1/files/{x['id']}/convert", params={"to": "text/csv"}).json()
    assert fs.get(f"/v1/files/{c['id']}/download").content.decode().splitlines() == ["host,score", "finance-lt,,97"]

    p = up(fs, "deck.pptx", pptx())
    slides = fs.get(f"/v1/files/{p['id']}/preview").json()["slides"]
    assert [s["text"] for s in slides] == ["Incident summary", "Next steps", "Appendix"]   # natural order
    assert fs.post(f"/v1/files/{p['id']}/convert", params={"to": "text/csv"}).status_code == 415
    assert fs.put(f"/v1/files/{p['id']}/content", json={"content": "x"}).status_code == 415   # no edit handler


def test_office_xml_entity_and_zip_bomb_refused(fs, tmp_path):
    evil = _pkg({"word/document.xml": '<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]>'
                                      f'<w:document {W}><w:body><w:p><w:r><w:t>&a;</w:t></w:r></w:p></w:body></w:document>'})
    e = up(fs, "evil.docx", evil)
    r = fs.get(f"/v1/files/{e['id']}/preview")
    assert r.status_code == 422 and "DTD" in r.json()["detail"]
    bomb = tmp_path / "bomb.docx"
    with zipfile.ZipFile(bomb, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("word/document.xml", b"<a>" + b" " * (fh.MAX_TOTAL_BYTES + 10) + b"</a>")
    with pytest.raises(fh.HandlerError, match="safety limit"):
        fh.docx_text(bomb)


def test_archive_listings_never_extract(fs):
    zbuf = io.BytesIO()
    with zipfile.ZipFile(zbuf, "w") as z:
        z.writestr("evidence/a.txt", "a")
        z.writestr("../escape.txt", "x")
    pv = fs.get(f"/v1/files/{up(fs, 'e.zip', zbuf.getvalue())['id']}/preview").json()
    assert pv["kind"] == "archive" and {e["name"] for e in pv["entries"]} == {"evidence/a.txt", "../escape.txt"}
    tbuf = io.BytesIO()
    with tarfile.open(fileobj=tbuf, mode="w:gz") as t:
        data = b"log line\n"
        info = tarfile.TarInfo("logs/app.log")
        info.size = len(data)
        t.addfile(info, io.BytesIO(data))
    pv = fs.get(f"/v1/files/{up(fs, 'logs.tar.gz', tbuf.getvalue())['id']}/preview").json()
    assert pv["entries"][0] == {"name": "logs/app.log", "size": 9, "dir": False, "link": False}


def test_pdf_and_media_are_served_inline_with_hardened_headers(fs):
    pdf = up(fs, "policy.pdf", b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF")
    r = fs.get(f"/v1/files/{pdf['id']}/preview")
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    assert r.headers["x-content-type-options"] == "nosniff" and "default-src 'none'" in r.headers["content-security-policy"]
    mp4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 4096
    v = up(fs, "clip.mp4", mp4)
    assert v["mime"] == "video/mp4"
    full = fs.get(f"/v1/files/{v['id']}/preview")
    assert full.headers["content-type"] == "video/mp4" and full.headers["content-security-policy"].startswith("sandbox")
    part = fs.get(f"/v1/files/{v['id']}/preview", headers={"Range": "bytes=0-15"})
    assert part.status_code == 206 and part.content == mp4[:16]
    wav = up(fs, "call.wav", b"RIFF\x24\x00\x00\x00WAVEfmt " + b"\x00" * 64)
    assert wav["mime"] == "audio/wav"
    assert fs.get(f"/v1/files/{wav['id']}/preview").headers["content-type"] == "audio/wav"


def test_handler_matrix_has_every_required_format_verified(fs):
    caps = fs.get("/v1/files/handlers").json()["handlers"]
    required = ["text/plain", "text/csv", "application/json", "application/xml", "application/pdf", fh.DOCX, fh.XLSX,
                fh.PPTX, "image/png", "image/jpeg", "audio/mpeg", "video/mp4", "application/zip", "application/x-tar"]
    for m in required:   # VFS-08: text, CSV, JSON, XML, PDF, office, images, audio, video, archives
        assert caps[m]["verified"] and caps[m]["preview"], m
