"""Minimal dependency-free PDF writer for tabular exports (DSH-06)."""
from __future__ import annotations


def _esc(s: str) -> str:
    return s.encode("latin-1", "replace").decode("latin-1").replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def table_pdf(title: str, rows: list[list[str]], rows_per_page: int = 48) -> bytes:
    pages = [rows[i:i + rows_per_page] for i in range(0, max(len(rows), 1), rows_per_page)] or [[]]
    objs: list[bytes] = []
    font_id = 3
    page_ids, content_ids = [], []
    next_id = 4
    for _ in pages:
        page_ids.append(next_id)
        content_ids.append(next_id + 1)
        next_id += 2
    objs.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objs.append(f"<< /Type /Pages /Kids [{' '.join(f'{i} 0 R' for i in page_ids)}] /Count {len(pages)} >>".encode())
    objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    for n, page in enumerate(pages):
        lines = [f"BT /F1 14 Tf 40 800 Td ({_esc(title)}) Tj ET"]
        y = 770
        for r in page:
            text = "   ".join(str(c) for c in r)[:110]
            lines.append(f"BT /F1 9 Tf 40 {y} Td ({_esc(text)}) Tj ET")
            y -= 15
        stream = "\n".join(lines).encode("latin-1", "replace")
        objs.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 {font_id} 0 R >> >> "
                    f"/Contents {content_ids[n]} 0 R >>".encode())
        objs.append(b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream")
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, o in enumerate(objs, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + o + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)
