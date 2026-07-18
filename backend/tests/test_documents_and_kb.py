"""Document extraction, chunking, KB versions, indexing status and stats."""

import io

import pytest

from app.services import documents


def test_chunking_splits_long_text_with_overlap():
    paragraphs = [f"Paragraph {i} " + "word " * 60 for i in range(8)]
    chunks = documents.chunk_text("\n\n".join(paragraphs))
    assert len(chunks) > 1
    assert all(len(c) <= documents.CHUNK_TARGET_CHARS * 1.6 for c in chunks)
    # No content is lost: every paragraph marker still appears somewhere.
    joined = " ".join(chunks)
    for i in range(8):
        assert f"Paragraph {i}" in joined


def test_chunking_keeps_short_text_intact():
    assert documents.chunk_text("Short answer.") == ["Short answer."]
    assert documents.chunk_text("   ") == []


def test_chunking_splits_oversized_paragraph_on_sentences():
    paragraph = " ".join(f"This is sentence number {i}." for i in range(120))
    chunks = documents.chunk_text(paragraph)
    assert len(chunks) > 1


def test_extract_markdown_strips_syntax():
    raw = b"# Title\n\nSome **bold** text with a [link](https://example.com).\n\n```code fence```"
    source_type, text, metadata = documents.extract("guide.md", raw)
    assert source_type == "md"
    assert "**" not in text and "#" not in text
    assert "link" in text
    assert metadata["characters"] > 0


def test_extract_plain_text():
    source_type, text, _ = documents.extract("notes.txt", b"Plain content here")
    assert source_type == "txt"
    assert text == "Plain content here"


def test_extract_rejects_unknown_type():
    with pytest.raises(documents.UnsupportedDocument) as exc:
        documents.extract("archive.7z", b"data")
    assert "Unsupported file type" in str(exc.value)


def test_extract_rejects_empty_file():
    with pytest.raises(documents.UnsupportedDocument):
        documents.extract("empty.txt", b"   ")


def test_upload_markdown_document_indexes_it(client, auth_headers):
    content = (
        "# Refund policy\n\n"
        "Clients may request a full refund within 14 days of the kickoff meeting. "
        "After development starts, refunds are prorated against completed milestones.\n\n"
        "## Exceptions\n\nCustom hardware purchases are non-refundable."
    )
    resp = client.post(
        "/api/kb/upload",
        headers=auth_headers,
        files={"file": ("refund-policy.md", io.BytesIO(content.encode()), "text/markdown")},
    )
    assert resp.status_code == 201, resp.text
    article = resp.json()
    assert article["source_type"] == "md"
    assert article["source_filename"] == "refund-policy.md"
    assert article["index_status"] == "indexed"
    assert article["chunk_count"] >= 1
    assert article["doc_metadata"]["characters"] > 0

    # The uploaded document is retrievable by a paraphrased question.
    # NOTE: the default offline embedder is a deterministic feature-hasher, not
    # a semantic model — it matches morphological variants ("refund"/"refunds",
    # "kickoff"), not true synonyms ("money back"). Configuring a real
    # EMBEDDING_PROVIDER is what buys synonym recall; the pipeline itself is
    # identical either way.
    hits = client.get(
        "/api/kb/search",
        headers=auth_headers,
        params={"q": "what is the refund policy after the kickoff meeting"},
    ).json()
    assert any(h["id"] == article["id"] for h in hits)


def test_upload_rejects_unsupported_type(client, auth_headers):
    resp = client.post(
        "/api/kb/upload",
        headers=auth_headers,
        files={"file": ("thing.exe", io.BytesIO(b"MZ"), "application/octet-stream")},
    )
    assert resp.status_code == 415


def test_article_versions_and_restore(client, auth_headers):
    created = client.post(
        "/api/kb",
        headers=auth_headers,
        json={"title": "Support hours", "content": "We answer 9-5 CET on weekdays."},
    ).json()

    client.put(
        f"/api/kb/{created['id']}",
        headers=auth_headers,
        json={"title": "Support hours", "content": "We answer 24/7.", "language": "en"},
    )
    updated = client.get("/api/kb", headers=auth_headers).json()
    current = next(a for a in updated if a["id"] == created["id"])
    assert current["version"] == 2
    assert "24/7" in current["content"]

    versions = client.get(f"/api/kb/{created['id']}/versions", headers=auth_headers).json()
    assert len(versions) == 1
    assert "9-5 CET" in versions[0]["content"]

    restored = client.post(f"/api/kb/{created['id']}/versions/1/restore", headers=auth_headers).json()
    assert "9-5 CET" in restored["content"]
    assert restored["version"] == 3  # rollback is recorded as a new version


def test_kb_stats_track_searches_and_misses(client, auth_headers):
    client.post(
        "/api/kb",
        headers=auth_headers,
        json={
            "title": "Onboarding process",
            "content": "Onboarding starts with a kickoff call and a shared Slack channel.",
        },
    )
    client.get("/api/kb/search", headers=auth_headers, params={"q": "how does onboarding work"})
    client.get("/api/kb/search", headers=auth_headers, params={"q": "do you sell industrial diamonds"})

    stats = client.get("/api/kb/stats", headers=auth_headers).json()
    assert stats["total_searches"] >= 2
    assert 0.0 <= stats["hit_rate"] <= 1.0
    assert stats["indexed_chunks"] >= 1
    assert "indexed" in stats["articles_by_status"]
    assert any(q["query"] for q in stats["unanswered_queries"])


def test_formats_endpoint_reports_availability(client, auth_headers):
    body = client.get("/api/kb/formats", headers=auth_headers).json()
    assert body["formats"][".md"] is True
    assert body["formats"][".txt"] is True
    assert ".pdf" in body["formats"]  # availability depends on pypdf being installed
    assert body["max_mb"] > 0


def test_single_article_reindex(client, auth_headers):
    article = client.post(
        "/api/kb", headers=auth_headers, json={"title": "Reindex me", "content": "Some indexable content."}
    ).json()
    resp = client.post(f"/api/kb/{article['id']}/reindex", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["index_status"] == "indexed"
