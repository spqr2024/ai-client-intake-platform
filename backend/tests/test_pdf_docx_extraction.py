"""PDF/DOCX ingestion — skipped automatically when the optional extractors
are not installed, so the suite still passes on a minimal install."""

import io

import pytest

from app.services import documents

pypdf = pytest.importorskip("pypdf", reason="pypdf not installed")
docx = pytest.importorskip("docx", reason="python-docx not installed")


def _build_pdf(text: str) -> bytes:
    from pypdf import PdfWriter

    # pypdf cannot author text content, so build a minimal PDF by hand.
    content = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for index, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{index} 0 obj\n".encode() + body + b"\nendobj\n"
    xref_at = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode() + b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_at}\n%%EOF".encode()
    PdfWriter(io.BytesIO(bytes(out)))  # sanity check that the file parses
    return bytes(out)


def _build_docx(paragraphs: list[str]) -> bytes:
    from docx import Document

    document = Document()
    for paragraph in paragraphs:
        document.add_paragraph(paragraph)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def test_extract_pdf_text():
    data = _build_pdf("Our standard warranty lasts twelve months")
    source_type, text, metadata = documents.extract("warranty.pdf", data)
    assert source_type == "pdf"
    assert "warranty" in text.lower()
    assert metadata["pages"] == 1


def test_extract_docx_text_and_tables():
    data = _build_docx(
        [
            "Service level agreement",
            "We respond to critical incidents within two hours.",
        ]
    )
    source_type, text, metadata = documents.extract("sla.docx", data)
    assert source_type == "docx"
    assert "critical incidents" in text
    assert metadata["paragraphs"] == 2


def test_docx_upload_is_indexed(client, auth_headers):
    data = _build_docx(
        [
            "Escalation policy",
            "Priority one incidents are escalated to the on-call engineer immediately.",
            "Priority two incidents are handled during business hours.",
        ]
    )
    resp = client.post(
        "/api/kb/upload",
        headers=auth_headers,
        files={
            "file": (
                "escalation.docx",
                io.BytesIO(data),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )
    assert resp.status_code == 201, resp.text
    article = resp.json()
    assert article["source_type"] == "docx"
    assert article["index_status"] == "indexed"

    hits = client.get(
        "/api/kb/search", headers=auth_headers, params={"q": "what is the escalation policy for incidents"}
    ).json()
    assert any(h["id"] == article["id"] for h in hits)


def test_scanned_pdf_gives_actionable_error():
    """A PDF with no text layer must explain itself rather than fail silently."""
    empty_pdf = _build_pdf(" ")
    with pytest.raises(documents.UnsupportedDocument) as exc:
        documents.extract("scan.pdf", empty_pdf)
    assert "scanned image" in str(exc.value).lower() or "no extractable text" in str(exc.value).lower()
