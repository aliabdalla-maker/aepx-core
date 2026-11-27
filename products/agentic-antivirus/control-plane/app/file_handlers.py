"""Verified format handlers for the virtual file system (VFS-07, VFS-08).

Every handler reads a stored, already malware-scanned blob and never executes or renders it server-side:
- Office Open XML (docx, xlsx, pptx): text / cell extraction from the package XML with the standard library.
  Hardened against zip bombs (member count, per-member and total inflated-size caps) and XML entity attacks
  (any DOCTYPE is refused before parsing).
- Archives (zip, tar, gzip): a listing of entries only; nothing is extracted to disk.
- PDF, images, audio, video: served inline with their real MIME type, nosniff and a restrictive CSP, so the
  browser's own sandboxed viewer or media player renders them.
"""
from __future__ import annotations

import csv
import gzip
import io
import re
import tarfile
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
PPTX = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
OFFICE = (DOCX, XLSX, PPTX)
ARCHIVES = ("application/zip", "application/x-tar", "application/gzip")
INLINE_MEDIA_PREFIXES = ("image/", "audio/", "video/")

MAX_MEMBERS = 5000
MAX_MEMBER_BYTES = 20 * 1024 * 1024
MAX_TOTAL_BYTES = 60 * 1024 * 1024
MAX_LIST = 1000
MAX_ROWS = 5000
MAX_TEXT = 1024 * 1024

_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_S = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
_R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"


class HandlerError(ValueError):
    """The file does not parse as its format, or exceeds a safety limit."""


class _Pkg:
    def __init__(self, path: Path):
        try:
            self.z = zipfile.ZipFile(path)
        except (zipfile.BadZipFile, OSError) as exc:
            raise HandlerError("not a valid Office Open XML package") from exc
        infos = self.z.infolist()
        if len(infos) > MAX_MEMBERS:
            raise HandlerError("too many members in package")
        if sum(i.file_size for i in infos) > MAX_TOTAL_BYTES:
            raise HandlerError("package inflates beyond the safety limit")
        self.names = {i.filename for i in infos}

    def xml(self, name: str) -> ET.Element:
        if name not in self.names:
            raise HandlerError(f"missing part {name}")
        info = self.z.getinfo(name)
        if info.file_size > MAX_MEMBER_BYTES:
            raise HandlerError(f"part {name} exceeds the safety limit")
        data = self.z.read(name)
        if b"<!DOCTYPE" in data[:4096].upper() or b"<!ENTITY" in data.upper():
            raise HandlerError("DTDs and entities are not allowed in Office XML")
        try:
            return ET.fromstring(data)
        except ET.ParseError as exc:
            raise HandlerError(f"part {name} is not well-formed XML") from exc

    def close(self) -> None:
        self.z.close()


def _natural(name: str) -> tuple:
    return tuple(int(t) if t.isdigit() else t for t in re.split(r"(\d+)", name))


def docx_text(path: Path) -> str:
    pkg = _Pkg(path)
    try:
        root = pkg.xml("word/document.xml")
        paras = ["".join(t.text or "" for t in p.iter(f"{_W}t")) for p in root.iter(f"{_W}p")]
        return "\n".join(paras)[:MAX_TEXT]
    finally:
        pkg.close()


def pptx_slides(path: Path) -> list[dict]:
    pkg = _Pkg(path)
    try:
        slides = sorted((n for n in pkg.names if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)), key=_natural)
        out = []
        for i, name in enumerate(slides, 1):
            root = pkg.xml(name)
            lines = ["".join(t.text or "" for t in p.iter(f"{_A}t")) for p in root.iter(f"{_A}p")]
            out.append({"slide": i, "text": "\n".join(line for line in lines if line)})
        return out
    finally:
        pkg.close()


def _col_index(ref: str) -> int:
    n = 0
    for ch in re.match(r"[A-Z]+", ref).group(0):
        n = n * 26 + ord(ch) - 64
    return n - 1


def xlsx_sheets(path: Path) -> list[dict]:
    pkg = _Pkg(path)
    try:
        shared = []
        if "xl/sharedStrings.xml" in pkg.names:
            shared = ["".join(t.text or "" for t in si.iter(f"{_S}t")) for si in pkg.xml("xl/sharedStrings.xml").iter(f"{_S}si")]
        wb = pkg.xml("xl/workbook.xml")
        rels = {}
        if "xl/_rels/workbook.xml.rels" in pkg.names:
            for rel in pkg.xml("xl/_rels/workbook.xml.rels"):
                rels[rel.get("Id")] = "xl/" + rel.get("Target", "").lstrip("/").removeprefix("xl/")
        sheets = []
        for i, s in enumerate(wb.iter(f"{_S}sheet"), 1):
            part = rels.get(s.get(f"{_R}id"), f"xl/worksheets/sheet{i}.xml")
            rows, truncated = [], False
            for r in pkg.xml(part).iter(f"{_S}row"):
                if len(rows) >= MAX_ROWS:
                    truncated = True
                    break
                vals: dict[int, str] = {}
                for c in r.iter(f"{_S}c"):
                    t, v = c.get("t"), c.find(f"{_S}v")
                    if t == "inlineStr":
                        val = "".join(x.text or "" for x in c.iter(f"{_S}t"))
                    elif v is None:
                        val = ""
                    elif t == "s":
                        idx = int(v.text or 0)
                        val = shared[idx] if 0 <= idx < len(shared) else ""
                    else:
                        val = v.text or ""
                    vals[_col_index(c.get("r", "A1")) if c.get("r") else len(vals)] = val
                width = max(vals) + 1 if vals else 0
                rows.append([vals.get(j, "") for j in range(width)])
            sheets.append({"name": s.get("name", f"Sheet{i}"), "rows": rows, "truncated": truncated})
        return sheets
    finally:
        pkg.close()


def archive_listing(path: Path, mime: str) -> dict:
    entries = []
    try:
        if mime == "application/zip":
            with zipfile.ZipFile(path) as z:
                infos = z.infolist()
                entries = [{"name": i.filename, "size": i.file_size, "compressed": i.compress_size,
                            "dir": i.is_dir()} for i in infos[:MAX_LIST]]
                total = len(infos)
        elif mime == "application/x-tar":
            with tarfile.open(path, "r:") as t:
                members = t.getmembers()
                entries = [{"name": m.name, "size": m.size, "dir": m.isdir(), "link": m.issym() or m.islnk()}
                           for m in members[:MAX_LIST]]
                total = len(members)
        elif mime == "application/gzip":
            try:
                with tarfile.open(path, "r:gz") as t:
                    members = t.getmembers()
                    entries = [{"name": m.name, "size": m.size, "dir": m.isdir(), "link": m.issym() or m.islnk()}
                               for m in members[:MAX_LIST]]
                    total = len(members)
            except tarfile.TarError:
                with gzip.open(path) as g:
                    size = 0
                    while chunk := g.read(1024 * 1024):
                        size += len(chunk)
                        if size > MAX_TOTAL_BYTES:
                            break
                entries, total = [{"name": Path(path).stem, "size": size, "dir": False}], 1
        else:
            raise HandlerError("not an archive")
    except (zipfile.BadZipFile, tarfile.TarError, OSError, EOFError) as exc:
        raise HandlerError("archive is corrupt or unreadable") from exc
    return {"entries": entries, "total": total, "truncated": total > MAX_LIST}


def preview(path: Path, mime: str) -> dict:
    if mime == DOCX:
        return {"mime": mime, "kind": "document", "text": docx_text(path)}
    if mime == PPTX:
        return {"mime": mime, "kind": "presentation", "slides": pptx_slides(path)}
    if mime == XLSX:
        return {"mime": mime, "kind": "spreadsheet", "sheets": xlsx_sheets(path)}
    if mime in ARCHIVES:
        return {"mime": mime, "kind": "archive", **archive_listing(path, mime)}
    raise HandlerError("no structured preview for this format")


def convert(path: Path, mime: str, to: str) -> bytes:
    if mime == DOCX and to == "text/plain":
        return docx_text(path).encode()
    if mime == PPTX and to == "text/plain":
        return "\n\n".join(f"--- Slide {s['slide']} ---\n{s['text']}" for s in pptx_slides(path)).encode()
    if mime == XLSX and to == "text/csv":
        sheets = xlsx_sheets(path)
        buf = io.StringIO()
        csv.writer(buf).writerows(sheets[0]["rows"] if sheets else [])
        return buf.getvalue().encode()
    raise HandlerError("conversion not supported")


def inline_media(mime: str) -> bool:
    return mime == "application/pdf" or mime.startswith(INLINE_MEDIA_PREFIXES)


def inline_headers(mime: str) -> dict:
    # Sandbox everything except PDF, whose built-in browser viewer does not run inside a CSP sandbox; PDF gets a
    # deny-all CSP instead (no scripts, frames, forms or network from the document's origin).
    csp = "default-src 'none'; img-src 'self' data:; media-src 'self'; style-src 'unsafe-inline'"
    return {"X-Content-Type-Options": "nosniff", "Content-Disposition": "inline",
            "Content-Security-Policy": csp if mime == "application/pdf" else "sandbox; " + csp,
            "Cross-Origin-Resource-Policy": "same-origin"}
