"""Cache, queue retry, embeddings, vector store and memory."""


from app.core import queue
from app.core.cache import MemoryCache
from app.services.embeddings import HashingEmbeddings
from app.services.vectorstore import cosine


def test_memory_cache_ttl_and_incr():
    cache = MemoryCache()
    cache.set("k", {"a": 1}, ttl_seconds=60)
    assert cache.get("k") == {"a": 1}
    cache.delete("k")
    assert cache.get("k") is None
    assert cache.incr_window("counter", 60) == 1
    assert cache.incr_window("counter", 60) == 2


def test_queue_retries_then_dead_letters(client):
    import asyncio

    attempts: list[int] = []

    async def flaky(payload: dict) -> None:
        attempts.append(1)
        if len(attempts) < 2:
            raise RuntimeError("transient failure")

    queue.register_handler("test.flaky", flaky)

    async def run() -> None:
        await queue.enqueue("test.flaky", {})
        await queue.drain_for_tests()          # attempt 1 fails, schedules retry
        await asyncio.sleep(2.2)               # allow the delayed re-enqueue to land
        await queue.drain_for_tests()          # attempt 2 succeeds

    asyncio.run(run())
    assert len(attempts) == 2


def test_hashing_embeddings_deterministic_and_normalized():
    import asyncio

    provider = HashingEmbeddings()
    [v1], [v2] = (
        asyncio.run(provider.embed(["website project budget"])),
        asyncio.run(provider.embed(["website project budget"])),
    )
    assert v1 == v2
    assert abs(sum(x * x for x in v1) - 1.0) < 1e-6

    [a, b, c] = asyncio.run(
        provider.embed(["website design project", "designing websites", "banana smoothie recipe"])
    )
    assert cosine(a, b) > cosine(a, c)  # related texts land closer


def test_semantic_kb_search_end_to_end(client, auth_headers):
    created = client.post(
        "/api/kb", headers=auth_headers,
        json={"title": "Do you offer maintenance after launch?",
              "content": "Yes — every project includes 30 days of free support, and we "
                         "offer ongoing maintenance retainers after that."},
    ).json()
    # Index is built on create; a semantically-phrased query must find it.
    hits = client.get("/api/kb/search", headers=auth_headers,
                      params={"q": "is there support offered after the launch"}).json()
    assert any(h["id"] == created["id"] for h in hits)

    resp = client.post("/api/kb/reindex", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["indexed"] >= 1


def test_notification_center_inapp_and_deliveries(client, auth_headers):
    # Driving a chat to completion creates in-app notifications for staff.
    resp = client.post("/api/chat/start", json={"client_name": "Notif Test"})
    conversation_id = resp.json()["conversation_id"]
    for answer in ["Website", "Site for a cafe", "$2500", "Flexible", "cafe@x.co", "no"]:
        client.post(f"/api/chat/{conversation_id}/msg", json={"text": answer})

    inbox = client.get("/api/notifications", headers=auth_headers).json()
    assert any(n["event"] == "lead.created" for n in inbox)

    unread = [n for n in inbox if not n["read"]]
    assert unread
    first = unread[0]
    marked = client.post(f"/api/notifications/{first['id']}/read", headers=auth_headers).json()
    assert marked["read"] == 1

    assert client.post("/api/notifications/read-all", headers=auth_headers).status_code == 204
    inbox = client.get("/api/notifications", headers=auth_headers,
                       params={"unread_only": True}).json()
    assert inbox == []

    # Email deliveries (client confirmation) are logged with a status.
    deliveries = client.get("/api/notifications/deliveries", headers=auth_headers).json()
    assert any(d["channel"] == "email" and d["recipient"] == "cafe@x.co" for d in deliveries)


def test_memory_context_compresses_long_conversations(client, db_session):
    import asyncio

    from app.models import Conversation, Message
    from app.services import memory

    conversation = Conversation(state={"answers": {"service": "Website", "budget": 3000}})
    db_session.add(conversation)
    db_session.flush()
    for i in range(20):
        db_session.add(Message(conversation_id=conversation.id,
                               sender="user" if i % 2 else "bot",
                               text=f"Message number {i} with some substantial content here."))
    db_session.commit()
    db_session.refresh(conversation)

    context = asyncio.run(memory.build_context(db_session, conversation))
    assert context.summary  # long-term memory built from older messages
    assert len(context.messages) <= memory.SHORT_TERM_MESSAGES + 1
    assert context.estimated_tokens <= memory.TOKEN_BUDGET
    # Rolling summary persisted for the next turn.
    db_session.refresh(conversation)
    assert conversation.state.get("memory", {}).get("summary")
