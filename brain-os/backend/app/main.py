"""BrainOS FastAPI app: streaming chat, ingestion, freshness, gaps, PII, exports, analytics. LLM-agnostic."""
from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager
from typing import Any

from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.core.config import load_config
from app.db.connection import get_pool
from app.store import DocumentRegistry, VectorStore
from app.store.registry_repo import DocumentRegistry as InMemoryRegistry
from app.store.vector import InMemoryVectorStore
from app.providers import get_llm_provider
from app.services import (
    ingest_document,
    stream_answer,
    semantic_diff,
    build_change_notification,
    generate_gap_report,
    full_pii_report,
    legal_verdict,
    to_jsonl,
    to_csv_rows,
    to_json_schema,
    to_parquet_bytes,
    log_activity,
    get_recent,
    record_unanswered,
    get_unanswered_for_report,
    clear_unanswered,
    remove_unanswered,
    start_scheduler,
    get_last_gap_report,
    stop_scheduler,
    run_watchdog,
    verify_documents,
)
from app.services.ingestion_progress import set_progress, set_done, set_error, get_progress, get_active_jobs, append_log
from app.routers import slack_router, teams_router, whatsapp_router, extension_router, web_app_router


def _get_vector_store() -> VectorStore:
    try:
        config = load_config()
        vs_cfg = config.get("vector_store", {})
        vs_type = vs_cfg.get("type", "memory")
        if vs_type == "qdrant":
            from app.store.qdrant_store import QdrantVectorStore
            return QdrantVectorStore(
                url=os.environ.get(vs_cfg.get("url_env", "QDRANT_URL")),
                host=os.environ.get(vs_cfg.get("host_env", "QDRANT_HOST")),
                port=int(os.environ.get(vs_cfg.get("port_env", "QDRANT_PORT"), 6333)),
                collection_prefix=vs_cfg.get("collection_prefix", "brainos"),
                vector_size=vs_cfg.get("vector_size", 1536),
            )
        if vs_type == "pinecone":
            from app.store.pinecone_store import PineconeVectorStore
            return PineconeVectorStore(
                namespace_prefix=vs_cfg.get("namespace_prefix", "brainos"),
            )
    except Exception:
        pass
    return InMemoryVectorStore()


def _get_registry():
    if os.environ.get("DATABASE_URL"):
        try:
            from app.db.registry_pg import DocumentRegistryPostgres
            return DocumentRegistryPostgres()
        except Exception:
            pass
    return InMemoryRegistry()


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.db.connection import init_db, close_db
    app.state.config = load_config()
    use_pg = await init_db()
    app.state.registry = _get_registry()
    app.state.vector_store = _get_vector_store()

    async def get_unanswered():
        return await get_unanswered_for_report(limit=200)

    async def save_gap_report(report: dict):
        if not use_pg or not os.environ.get("DATABASE_URL"):
            return
        from app.db.connection import get_pool
        pool = await get_pool()
        if pool:
            async with pool.acquire() as conn:
                await conn.execute(
                    "INSERT INTO gap_reports (tenant_id, report) VALUES ($1, $2)",
                    "default",
                    json.dumps(report),
                )

    start_scheduler(
        generate_report_fn=lambda q: generate_gap_report(
            q,
            app.state.config,
            answered_count=sum(1 for e in get_recent(limit=5000, tenant_id="default") if (e.get("action") if isinstance(e, dict) else "") == "READY"),
        ),
        get_unanswered_fn=get_unanswered,
        save_report_fn=save_gap_report,
        cron_weekday="mon",
        hour=9,
        minute=0,
    )
    yield
    stop_scheduler()
    await close_db()


app = FastAPI(title="BrainOS", description="Make AI Know Your Business", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(slack_router)
app.include_router(teams_router)
app.include_router(whatsapp_router)
app.include_router(extension_router)
app.include_router(web_app_router)

# ZAYA Web App Widget: embeddable script + demo (web-app-widget at repo root, or /app/web-app-widget in Docker)
_widget_dir = Path(os.environ.get("WEB_APP_WIDGET_DIR", "")).resolve() if os.environ.get("WEB_APP_WIDGET_DIR") else Path(__file__).resolve().parent.parent.parent / "web-app-widget"
if not _widget_dir.exists():
    _widget_dir = Path("/app/web-app-widget")  # Docker volume mount
if _widget_dir.exists():
    app.mount("/static", StaticFiles(directory=str(_widget_dir), html=True), name="zaya-widget")


# ---------- Request/Response models ----------
class IngestBody(BaseModel):
    tenant_id: str
    namespace: str
    document_name: str
    content: str
    external_id: str | None = None  # e.g. URL for freshness watchdog


class QueryBody(BaseModel):
    tenant_id: str
    namespace: str
    question: str
    persona: str | None = None  # e.g. customer_support, legal, sales, internal_expert
    pasted_context: str | None = None  # "Ask about this" — text user pasted from elsewhere
    strict_mode: bool = False  # Only from your docs; no general knowledge
    answer_language: str | None = None  # e.g. "Spanish", "Hindi" — answer in this language from same docs
    source_filter: list[str] | None = None  # Only search in these doc names or source types (e.g. ["HR", "Legal"])


class VerifyCitationsBody(BaseModel):
    tenant_id: str = "default"
    document_ids: list[str]


class GapReportBody(BaseModel):
    tenant_id: str
    questions: list[dict[str, Any]]  # [{"question": "...", "count": N}]


class PIIScanBody(BaseModel):
    text: str


class IngestUrlBody(BaseModel):
    tenant_id: str
    namespace: str
    url: str
    document_name: str | None = None  # default: derived from URL
    skip_verdict: bool = False


class IngestCrawlBody(BaseModel):
    tenant_id: str
    namespace: str
    seed_url: str
    max_depth: int = 2
    max_pages: int = 30
    use_llm_links: bool = True
    use_llm_topic: bool = True
    use_llm_clean: bool = False
    skip_verdict: bool = False
    crawl_goal: str | None = None  # User's words: e.g. "Policies only", "FAQ and pricing", "Product docs" — LLM uses for intent-aware link selection
    filter_substantive: bool = True  # If True, skip pages LLM scores as boilerplate (semantic "is this worth it?")


class LegalVerdictBody(BaseModel):
    url: str
    tos_excerpt: str | None = None
    robots_excerpt: str | None = None


# ---------- 1. Streaming AI answers ----------
@app.post("/api/chat/stream")
async def chat_stream(body: QueryBody):
    """Stream answer with tokens, citations, confidence, freshness, follow-ups. SSE. Uses episodic/user memory when available."""
    await log_activity("QUERY", body.tenant_id, {"question": body.question[:100]})
    config = getattr(app.state, "config", None) or load_config()
    vs = app.state.vector_store
    episodic_context = ""
    user_memory_context = ""
    pool = await get_pool()
    if pool:
        from app.services.memory_service import get_recent_episodic, get_user_memory
        try:
            recent = await get_recent_episodic(pool, body.tenant_id, body.namespace, limit=5)
            if recent:
                episodic_context = "\n".join(f"- {m.get('summary', '')}" for m in recent)
            um = await get_user_memory(pool, body.tenant_id, body.namespace)
            if um:
                user_memory_context = json.dumps(um)[:1500]
        except Exception:
            pass

    async def event_stream():
        try:
            async for event in stream_answer(
                body.tenant_id,
                body.namespace,
                body.question,
                config=config,
                vector_store=vs,
                persona=body.persona,
                pasted_context=body.pasted_context,
                strict_mode=body.strict_mode,
                answer_language=body.answer_language,
                source_filter=body.source_filter,
                episodic_context=episodic_context or None,
                user_memory_context=user_memory_context or None,
            ):
                yield f"data: {json.dumps(event)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'payload': {'message': str(e)}})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/chat")
async def chat_non_streaming(body: QueryBody):
    """Non-streaming: full answer + citations + confidence + follow_ups in one JSON."""
    config = getattr(app.state, "config", None) or load_config()
    vs = app.state.vector_store
    episodic_ctx = ""
    user_ctx = ""
    pool = await get_pool()
    if pool:
        from app.services.memory_service import get_recent_episodic, get_user_memory
        try:
            recent = await get_recent_episodic(pool, body.tenant_id, body.namespace, limit=5)
            if recent:
                episodic_ctx = "\n".join(f"- {m.get('summary', '')}" for m in recent)
            um = await get_user_memory(pool, body.tenant_id, body.namespace)
            if um:
                user_ctx = json.dumps(um)[:1500]
        except Exception:
            pass
    answer_text = ""
    citations = []
    confidence = 0
    follow_ups = []
    async for event in stream_answer(
        body.tenant_id,
        body.namespace,
        body.question,
        config=config,
        vector_store=vs,
        persona=body.persona,
        pasted_context=body.pasted_context,
        strict_mode=body.strict_mode,
        answer_language=body.answer_language,
        source_filter=body.source_filter,
        episodic_context=episodic_ctx or None,
        user_memory_context=user_ctx or None,
    ):
        if event["type"] == "token":
            answer_text += event["payload"].get("text", "")
        elif event["type"] == "citation":
            citations = event["payload"].get("citations", [])
        elif event["type"] == "confidence":
            confidence = event["payload"].get("score", 0)
        elif event["type"] == "follow_ups":
            follow_ups = event["payload"].get("questions", [])
    if confidence < 50 and (not answer_text or len(answer_text.strip()) < 20):
        await record_unanswered(body.tenant_id, body.namespace, body.question)
    return {
        "answer": answer_text,
        "citations": citations,
        "confidence": confidence,
        "follow_up_questions": follow_ups,
        "copy_with_citation": _format_copy_citation(answer_text, citations),
    }


def _format_copy_citation(answer: str, citations: list[dict]) -> str:
    lines = [answer]
    if citations:
        lines.append("\nSources:")
        for i, c in enumerate(citations, 1):
            lines.append(f"  [{i}] {c.get('document_name', '')}" + (f" (page {c.get('page', 'N/A')})" if c.get('page') else ""))
    return "\n".join(lines)


# ---------- Chat extras: simplify, suggest question, compare ----------
class SimplifyBody(BaseModel):
    answer: str
    citations: list[dict] | None = None


@app.post("/api/chat/simplify")
async def simplify_answer(body: SimplifyBody):
    """Rewrite the answer in plain English for a newcomer (Explain like I'm new)."""
    llm = get_llm_provider(getattr(app.state, "config", None) or load_config())
    system = "You are a helpful editor. Rewrite the following answer so a complete newcomer can understand it. Keep the same facts and citations; use simpler words and short sentences. Do not add new information. Output only the rewritten answer."
    out = await llm.complete(
        [{"role": "system", "content": system}, {"role": "user", "content": (body.answer or "")[:8000]}],
        stream=False,
        max_tokens=2048,
    )
    return {"simplified": (out or "").strip(), "citations": body.citations}


@app.get("/api/chat/suggest-question")
async def suggest_question(
    tenant_id: str = Query("default"),
    namespace: str = Query("main"),
):
    """Smart default question for empty chat: suggest one based on KB content (e.g. top doc types)."""
    try:
        records = await app.state.vector_store.scroll(namespace, limit=50)
    except Exception:
        return {"suggestion": None}
    if not records:
        return {"suggestion": None}
    doc_names = []
    for r in records:
        name = r.get("document_name") or r.get("source") or ""
        if name and name not in doc_names:
            doc_names.append(name[:80])
    if not doc_names:
        return {"suggestion": None}
    llm = get_llm_provider(getattr(app.state, "config", None) or load_config())
    prompt = f"Given these document/source names from a knowledge base: {', '.join(doc_names[:15])}. Suggest ONE short question a user might ask to learn something from this knowledge. Start with 'What is our' or 'How do we' or 'Where can I'. One sentence only, no quotes."
    try:
        q = await llm.complete([{"role": "user", "content": prompt}], stream=False, max_tokens=80)
        q = (q or "").strip().strip('"')
        if len(q) > 120:
            q = q[:117] + "..."
        return {"suggestion": q if q else None}
    except Exception:
        return {"suggestion": None}


class FeedbackBody(BaseModel):
    tenant_id: str = "default"
    namespace: str = "main"
    question: str
    answer_excerpt: str | None = None
    helpful: bool
    what_wrong: str | None = None  # missing_info | wrong | outdated | other
    citation_doc_ids: list[str] | None = None  # for trust + answer_proved_wrong
    user_key: str | None = None  # for per-user preference inference; default "default"


@app.post("/api/feedback")
async def submit_feedback(body: FeedbackBody):
    """Was this helpful? + What was wrong? — closes the loop to gaps/compliance; updates trust and answer_proved_wrong; infers personal preferences."""
    pool = await get_pool()
    user_key = (body.user_key or "default").strip()[:500]
    if pool:
        async with pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO answer_feedback (tenant_id, namespace, question, answer_excerpt, helpful, what_wrong, user_key)
                   VALUES ($1, $2, $3, $4, $5, $6, $7)""",
                body.tenant_id,
                body.namespace,
                body.question[:2000],
                (body.answer_excerpt or "")[:5000],
                body.helpful,
                (body.what_wrong or "")[:100],
                user_key,
            )
        from app.services.trust_service import record_feedback, refresh_trust_scores
        from app.services.preference_inference import infer_preference_deltas, apply_inferred_preferences
        doc_ids = body.citation_doc_ids or []
        await record_feedback(pool, body.tenant_id, body.namespace, body.helpful, doc_ids)
        delta = infer_preference_deltas(body.helpful, body.what_wrong)
        await apply_inferred_preferences(pool, body.tenant_id, body.namespace, user_key, delta)
        if not body.helpful and doc_ids:
            async with pool.acquire() as conn2:
                await conn2.execute(
                    """INSERT INTO answer_proved_wrong (tenant_id, namespace, question, answer_excerpt, citation_doc_ids)
                       VALUES ($1, $2, $3, $4, $5)""",
                    body.tenant_id,
                    body.namespace,
                    body.question[:2000],
                    (body.answer_excerpt or "")[:2000],
                    doc_ids,
                )
        await refresh_trust_scores(pool, body.tenant_id, body.namespace)
        return {"saved": True}
    store = getattr(app.state, "_answer_feedback", None)
    if store is None:
        app.state._answer_feedback = []
        store = app.state._answer_feedback
    store.append({"tenant_id": body.tenant_id, "question": body.question[:200], "helpful": body.helpful, "what_wrong": body.what_wrong})
    return {"saved": True}


class SavedAnswerBody(BaseModel):
    tenant_id: str = "default"
    namespace: str = "main"
    question: str
    answer: str
    citations_json: str | None = None
    tag: str | None = None
    note: str | None = None


@app.get("/api/saved-answers")
async def list_saved_answers(tenant_id: str = Query("default"), namespace: str | None = None):
    """List saved answers (My saved answers)."""
    pool = await get_pool()
    if pool:
        async with pool.acquire() as conn:
            if namespace:
                rows = await conn.fetch("SELECT id, question, answer, citations_json, tag, note, created_at FROM saved_answers WHERE tenant_id = $1 AND namespace = $2 ORDER BY created_at DESC", tenant_id, namespace)
            else:
                rows = await conn.fetch("SELECT id, question, answer, citations_json, tag, note, created_at FROM saved_answers WHERE tenant_id = $1 ORDER BY created_at DESC", tenant_id)
            return {"items": [{"id": r["id"], "question": r["question"], "answer": r["answer"][:500], "citations_json": r["citations_json"], "tag": r["tag"], "note": r["note"], "created_at": r["created_at"].isoformat() if r["created_at"] else None} for r in rows]}
    store = getattr(app.state, "_saved_answers", None) or {}
    if store is None:
        app.state._saved_answers = {}
        store = app.state._saved_answers
    items = [v for v in store.values() if v.get("tenant_id") == tenant_id and (not namespace or v.get("namespace") == namespace)]
    items.sort(key=lambda x: x.get("created_at") or "", reverse=True)
    return {"items": [{"id": x["id"], "question": x["question"], "answer": (x.get("answer") or "")[:500], "tag": x.get("tag"), "note": x.get("note"), "created_at": x.get("created_at")} for x in items]}


@app.post("/api/saved-answers")
async def add_saved_answer(body: SavedAnswerBody):
    """Save this answer to My saved answers."""
    import uuid
    from datetime import datetime, timezone
    sid = str(uuid.uuid4())[:12]
    pool = await get_pool()
    if pool:
        async with pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO saved_answers (id, tenant_id, namespace, question, answer, citations_json, tag, note)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8)""",
                sid,
                body.tenant_id,
                body.namespace,
                body.question[:2000],
                (body.answer or "")[:100000],
                (body.citations_json or "")[:50000],
                (body.tag or "")[:200] or None,
                (body.note or "")[:2000] or None,
            )
        return {"id": sid, "question": body.question[:200], "tag": body.tag, "note": body.note}
    store = getattr(app.state, "_saved_answers", None)
    if store is None:
        app.state._saved_answers = {}
        store = app.state._saved_answers
    store[sid] = {"id": sid, "tenant_id": body.tenant_id, "namespace": body.namespace, "question": body.question, "answer": body.answer, "citations_json": body.citations_json, "tag": body.tag, "note": body.note, "created_at": datetime.now(timezone.utc).isoformat()}
    return {"id": sid, "question": body.question[:200], "tag": body.tag, "note": body.note}


@app.delete("/api/saved-answers/{answer_id}")
async def delete_saved_answer(answer_id: str, tenant_id: str = Query("default")):
    pool = await get_pool()
    if pool:
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM saved_answers WHERE id = $1 AND tenant_id = $2", answer_id, tenant_id)
        return {"deleted": True}
    store = getattr(app.state, "_saved_answers", None)
    if store and answer_id in store and store[answer_id].get("tenant_id") == tenant_id:
        del store[answer_id]
    return {"deleted": True}


@app.get("/api/analytics/related-questions")
async def related_questions(tenant_id: str = Query("default"), namespace: str = Query("main"), limit: int = Query(8, ge=1, le=20)):
    """People also asked — anonymized questions from gap/unanswered log."""
    items = await get_unanswered_for_report(tenant_id=tenant_id, namespace=namespace, limit=limit)
    return {"questions": [x.get("question", "") for x in items if x.get("question")]}


class CompareBody(BaseModel):
    tenant_id: str = "default"
    namespace: str = "main"
    document_name_1: str
    document_name_2: str
    question: str  # e.g. "Compare on returns"


@app.post("/api/chat/compare")
async def compare_docs(body: CompareBody):
    """Compare two docs/sections on a question; grounded, cited comparison."""
    from app.services.rag import stream_answer
    config = getattr(app.state, "config", None) or load_config()
    vs = app.state.vector_store
    compare_question = f"Compare and contrast: {body.document_name_1} vs {body.document_name_2} on the following: {body.question}. Say which source says what; cite by number."
    answer_text = ""
    citations = []
    async for event in stream_answer(
        body.tenant_id,
        body.namespace,
        compare_question,
        config=config,
        vector_store=vs,
        source_filter=[body.document_name_1, body.document_name_2],
    ):
        if event.get("type") == "token":
            answer_text += event.get("payload", {}).get("text", "")
        elif event.get("type") == "citation":
            citations = event.get("payload", {}).get("citations", [])
    return {"answer": answer_text, "citations": citations, "copy_with_citation": _format_copy_citation(answer_text, citations)}


class QueryCitationsBody(BaseModel):
    tenant_id: str = "default"
    namespace: str = "main"
    question: str
    cited_document_ids: list[str]


@app.post("/api/query-citations")
async def log_query_citations(body: QueryCitationsBody):
    """Log query + cited docs for crawl priority and trust (call from client when you have citations)."""
    pool = await get_pool()
    if pool:
        from app.services.crawl_priority_service import record_query_citations
        await record_query_citations(pool, body.tenant_id, body.namespace, body.question, body.cited_document_ids)
        from app.services.trust_service import record_citation
        for doc_id in body.cited_document_ids:
            await record_citation(pool, body.tenant_id, body.namespace, doc_id)
    return {"logged": True}


# ---------- Defensibility: claims, contradictions, trust, timeline, crawl priority ----------
@app.get("/api/claims")
async def list_claims_api(
    tenant_id: str = Query("default"),
    namespace: str = Query("main"),
    document_id: str | None = Query(None),
    limit: int = Query(200, ge=1, le=1000),
):
    """List claims (extracted from chunks). Optional filter by document_id."""
    from app.services.claims_service import list_claims
    pool = await get_pool()
    items = await list_claims(pool, tenant_id, namespace, document_id, limit)
    return {"claims": items}


@app.post("/api/claims/extract")
async def extract_claims_api(
    tenant_id: str = Query("default"),
    namespace: str = Query("main"),
    document_id: str | None = Query(None),
    limit_chunks: int = Query(100, ge=1, le=500),
):
    """Extract claims from chunks (LLM) and store. Optional document_id to limit to one doc."""
    from app.services.claims_service import extract_claims_from_chunk, store_claims
    pool = await get_pool()
    vs = app.state.vector_store
    try:
        chunks = await vs.scroll(namespace, limit=limit_chunks, filter_meta={"document_id": document_id} if document_id else None)
    except Exception:
        chunks = await vs.scroll(namespace, limit=limit_chunks)
    if document_id:
        chunks = [c for c in chunks if c.get("document_id") == document_id]
    created = 0
    for c in chunks[:limit_chunks]:
        ch_id = c.get("id") or ""
        doc_id = c.get("document_id") or ""
        doc_name = c.get("document_name") or ""
        content = c.get("content") or ""
        if not content.strip():
            continue
        claim_texts = await extract_claims_from_chunk(ch_id, doc_id, doc_name, content, tenant_id, namespace, app.state.config)
        if pool and claim_texts:
            ids = await store_claims(pool, tenant_id, namespace, ch_id, doc_id, doc_name, claim_texts)
            created += len(ids)
    return {"created": created, "chunks_processed": len(chunks)}


@app.get("/api/claims/timeline")
async def claim_timeline_api(
    claim_id: str | None = Query(None),
    tenant_id: str = Query("default"),
    namespace: str = Query("main"),
    claim_text_substring: str | None = Query(None),
):
    """Timeline of a claim (versions). Or 'when did this stop being true?' via claim_text_substring."""
    from app.services.claims_service import get_claim_history, when_did_stop_being_true
    pool = await get_pool()
    if claim_id:
        items = await get_claim_history(pool, claim_id)
        return {"timeline": items}
    items = await when_did_stop_being_true(pool, tenant_id, namespace, claim_text_substring, None)
    return {"claims": items}


@app.get("/api/contradictions")
async def list_contradictions_api(
    tenant_id: str = Query("default"),
    namespace: str = Query("main"),
    status: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
):
    """List detected contradictions (policies that disagree)."""
    from app.services.contradictions_service import list_contradictions
    pool = await get_pool()
    items = await list_contradictions(pool, tenant_id, namespace, status, limit)
    return {"contradictions": items}


@app.post("/api/contradictions/detect")
async def detect_contradictions_api(
    tenant_id: str = Query("default"),
    namespace: str = Query("main"),
    max_pairs: int = Query(500, ge=10, le=2000),
):
    """Run contradiction detection job (LLM compares claim pairs)."""
    from app.services.contradictions_service import detect_contradictions
    pool = await get_pool()
    inserted = await detect_contradictions(pool, tenant_id, namespace, app.state.config, max_pairs)
    return {"detected": len(inserted), "contradictions": inserted}


@app.get("/api/trust/sources")
async def list_trust_api(
    tenant_id: str = Query("default"),
    namespace: str = Query("main"),
    limit: int = Query(200, ge=1, le=500),
):
    """List source trust scores (evolved from citations and feedback)."""
    from app.services.trust_service import list_source_trust
    pool = await get_pool()
    items = await list_source_trust(pool, tenant_id, namespace, limit)
    return {"sources": items}


@app.get("/api/crawl-priority")
async def crawl_priority_api(
    tenant_id: str = Query("default"),
    namespace: str = Query("main"),
    limit: int = Query(50, ge=1, le=200),
):
    """Crawl priority: docs scored by how often they were cited (what users ask)."""
    from app.services.crawl_priority_service import get_crawl_priority_with_docs
    pool = await get_pool()
    items = await get_crawl_priority_with_docs(pool, app.state.registry, tenant_id, namespace, limit)
    return {"priority": items}


@app.get("/api/answers-proved-wrong")
async def list_answers_proved_wrong_api(
    tenant_id: str = Query("default"),
    namespace: str = Query("main"),
    limit: int = Query(50, ge=1, le=200),
):
    """List answers that were marked wrong (for down-ranking / review)."""
    pool = await get_pool()
    if not pool:
        return {"items": []}
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT id, question, answer_excerpt, citation_doc_ids, marked_at
               FROM answer_proved_wrong WHERE tenant_id = $1 AND namespace = $2 ORDER BY marked_at DESC LIMIT $3""",
            tenant_id,
            namespace,
            limit,
        )
    items = [
        {
            "id": r["id"],
            "question": r["question"],
            "answer_excerpt": (r["answer_excerpt"] or "")[:500],
            "citation_doc_ids": list(r["citation_doc_ids"] or []),
            "marked_at": r["marked_at"].isoformat() if r.get("marked_at") else None,
        }
        for r in rows
    ]
    return {"items": items}


# ---------- Persistent cognitive memory ----------
class RecordInteractionBody(BaseModel):
    tenant_id: str = "default"
    namespace: str = "main"
    question: str
    answer: str


@app.post("/api/memory/record-interaction")
async def record_interaction(body: RecordInteractionBody):
    """Memory write loop: after each chat, call this to summarize, extract facts, score importance, store in episodic memory."""
    pool = await get_pool()
    if not pool:
        return {"saved": False, "reason": "no_db"}
    from app.services.memory_service import write_episodic_after_interaction
    config = getattr(app.state, "config", None) or load_config()
    result = await write_episodic_after_interaction(
        pool, body.tenant_id, body.namespace, body.question[:2000], (body.answer or "")[:5000], config=config
    )
    return {"saved": True, "memory_id": result.get("id") if result else None}


@app.get("/api/memory/episodic")
async def get_episodic_memory(
    tenant_id: str = Query("default"),
    namespace: str = Query("main"),
    limit: int = Query(30, ge=1, le=200),
):
    """List recent episodic memory (past interactions)."""
    pool = await get_pool()
    if not pool:
        return {"items": []}
    from app.services.memory_service import get_recent_episodic
    items = await get_recent_episodic(pool, tenant_id, namespace, limit=limit)
    return {"items": items}


@app.get("/api/memory/user")
async def get_user_memory_api(
    tenant_id: str = Query("default"),
    namespace: str = Query("main"),
    user_key: str = Query("default"),
):
    """Get user/preference memory (key-value)."""
    pool = await get_pool()
    if not pool:
        return {"memory": {}}
    from app.services.memory_service import get_user_memory
    memory = await get_user_memory(pool, tenant_id, namespace, user_key=user_key)
    return {"memory": memory}


@app.get("/api/memory/dashboard")
async def get_memory_dashboard(
    tenant_id: str = Query("default"),
    namespace: str = Query("main"),
    user_key: str = Query("default"),
    episodic_limit: int = Query(50, ge=1, le=200),
    outcomes_limit: int = Query(80, ge=1, le=200),
):
    """Display-ready cognitive memory dashboard: copy, episodic, user preferences, outcomes. No client-side hardcoding."""
    pool = await get_pool()
    if not pool:
        from app.services.memory_service import DASHBOARD_COPY
        return {"copy": DASHBOARD_COPY, "episodic": [], "user_preferences": [], "outcomes": []}
    from app.services.memory_service import get_dashboard
    return await get_dashboard(
        pool, tenant_id, namespace, user_key=user_key,
        episodic_limit=episodic_limit, outcomes_limit=outcomes_limit,
    )


@app.get("/api/memory/outcomes")
async def get_outcomes_api(
    tenant_id: str = Query("default"),
    namespace: str = Query("main"),
    run_type: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    """List outcome memory (what worked vs failed) for continuous learning."""
    pool = await get_pool()
    if not pool:
        return {"items": []}
    from app.services.memory_service import get_outcomes
    items = await get_outcomes(pool, tenant_id, namespace, run_type=run_type, limit=limit)
    return {"items": items}


# ---------- Agentic goal engine (planner + executor + evaluator) ----------
class AgentPlanBody(BaseModel):
    tenant_id: str = "default"
    namespace: str = "main"
    goal: str


class AgentRunBody(BaseModel):
    tenant_id: str = "default"
    namespace: str = "main"
    goal: str
    plan_id: str | None = None


@app.post("/api/agent/plan")
async def agent_plan(body: AgentPlanBody):
    """Convert goal into task graph (LLM). Persist plan; return plan_id + tasks."""
    from app.services.planner_service import plan_goal
    config = getattr(app.state, "config", None) or load_config()
    result = await plan_goal(body.goal, config=config)
    tasks = result.get("tasks") or []
    import uuid
    plan_id = str(uuid.uuid4())[:16]
    pool = await get_pool()
    if pool:
        async with pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO agent_plans (id, tenant_id, namespace, goal, tasks, status)
                   VALUES ($1, $2, $3, $4, $5, 'pending')""",
                plan_id,
                body.tenant_id,
                body.namespace,
                body.goal[:2000],
                json.dumps([{"action": t.get("action"), "dependencies": t.get("dependencies") or []} for t in tasks]),
            )
    return {"plan_id": plan_id, "goal": body.goal, "tasks": tasks}


@app.post("/api/agent/run")
async def agent_run_stream(body: AgentRunBody):
    """Run agent: plan (if needed) + execute task graph. SSE stream with log, task_start, task_done, task_fail, evaluator, done."""
    from app.services.planner_service import plan_goal
    from app.services.agent_executor import run_plan
    from app.services.memory_service import record_outcome
    config = getattr(app.state, "config", None) or load_config()
    vs = app.state.vector_store
    plan_id = body.plan_id
    tasks = []
    if plan_id:
        pool = await get_pool()
        if pool:
            async with pool.acquire() as conn:
                row = await conn.fetchrow("SELECT goal, tasks FROM agent_plans WHERE id = $1 AND tenant_id = $2 AND namespace = $3", plan_id, body.tenant_id, body.namespace)
                if row:
                    tasks = json.loads(row["tasks"]) if isinstance(row["tasks"], str) else (row["tasks"] or [])
    if not tasks:
        result = await plan_goal(body.goal, config=config)
        tasks = result.get("tasks") or []
        if not tasks:
            tasks = [{"action": body.goal[:200], "dependencies": []}]
        import uuid
        plan_id = plan_id or str(uuid.uuid4())[:16]
        pool = await get_pool()
        if pool:
            async with pool.acquire() as conn:
                await conn.execute(
                    """INSERT INTO agent_plans (id, tenant_id, namespace, goal, tasks, status) VALUES ($1, $2, $3, $4, $5, 'pending')
                       ON CONFLICT (id) DO NOTHING""",
                    plan_id, body.tenant_id, body.namespace, body.goal[:2000], json.dumps(tasks),
                )
    run_id = None
    outcome_success = False
    steps_log: list = []

    async def event_stream():
        nonlocal run_id, outcome_success, steps_log
        try:
            async for event in run_plan(body.tenant_id, body.namespace, body.goal, tasks, vs, config=config):
                if event.get("type") == "done":
                    payload = event.get("payload") or {}
                    run_id = payload.get("run_id")
                    outcome_success = payload.get("outcome_success", False)
                    steps_log = payload.get("steps_log") or []
                yield f"data: {json.dumps(event)}\n\n"
            pool = await get_pool()
            if pool and run_id is not None:
                async with pool.acquire() as conn:
                    await conn.execute(
                        """INSERT INTO agent_runs (id, plan_id, tenant_id, namespace, goal, status, outcome_success, steps_log)
                           VALUES ($1, $2, $3, $4, $5, 'completed', $6, $7)""",
                        run_id, plan_id, body.tenant_id, body.namespace, body.goal[:2000],
                        outcome_success,
                        json.dumps(steps_log),
                    )
                await record_outcome(
                    pool, body.tenant_id, body.namespace, "agent_run", outcome_success,
                    run_id=run_id, tool_success=outcome_success, metadata={"goal": body.goal[:200]},
                )
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'payload': {'message': str(e)}})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------- 2. Ingestion (indexed knowledge base) ----------
def _make_progress_cb(doc_id: str):
    def cb(phase: str, current: int, total: int, message: str) -> None:
        set_progress(doc_id, phase, current, total, message)
    return cb


@app.post("/api/ingest")
async def ingest(body: IngestBody, wait: bool = True):
    """Ingest document. If wait=false, returns document_id immediately and ingestion runs in background; poll GET /api/ingest/status?document_id= for progress."""
    import asyncio
    import hashlib
    rec = await app.state.registry.create(
        body.tenant_id,
        body.document_name,
        "url" if body.external_id else "upload",
        external_id=body.external_id,
    )
    await log_activity("INGESTING", body.tenant_id, {"document": body.document_name}, document_id=rec.id)

    async def run_ingest():
        try:
            result = await ingest_document(
                body.tenant_id,
                body.namespace,
                rec.id,
                body.document_name,
                body.content,
                config=app.state.config,
                registry=app.state.registry,
                vector_store=app.state.vector_store,
                progress_callback=_make_progress_cb(rec.id),
            )
            if result.get("indexed"):
                h = hashlib.sha256(body.content.encode()).hexdigest()[:16]
                meta = {"content_hash": h, "namespace": body.namespace}
                if body.external_id:
                    meta["last_content"] = body.content[:50000]
                await app.state.registry.update(rec.id, metadata=meta)
                set_done(rec.id, result.get("chunks_created", 0))
            else:
                set_done(rec.id, 0)
            await log_activity("READY", body.tenant_id, {"chunks": result.get("chunks_created", 0)}, document_id=rec.id)
        except Exception as e:
            set_error(rec.id, str(e))
            raise

    if wait:
        await run_ingest()
        job = get_progress(rec.id) or {}
        return {"document_id": rec.id, "chunks_created": job.get("current", 0), "indexed": True}
    asyncio.create_task(run_ingest())
    return {"document_id": rec.id, "status": "processing", "message": "Ingestion started. Poll /api/ingest/status?document_id=" + rec.id}


@app.get("/api/ingest/status")
async def ingest_status(document_id: str = Query(..., description="Document ID from ingest response")):
    """Live ingestion progress for UI. Returns phase, current, total, message, percentage."""
    job = get_progress(document_id)
    if not job:
        return {"document_id": document_id, "phase": "unknown", "message": "No job found or already completed"}
    return job


@app.get("/api/ingest/active")
async def ingest_active(tenant_id: str | None = Query(None)):
    """List currently running ingestion jobs (for live ingestion card)."""
    return {"jobs": get_active_jobs(tenant_id)}


@app.post("/api/ingest/url")
async def ingest_url(body: IngestUrlBody):
    """Web scraping: legal check, fetch URL content (browser-like headers), ingest into knowledge base."""
    import hashlib
    from urllib.parse import urlparse
    doc_name = body.document_name or urlparse(body.url).netloc or body.url[:50]
    verdict = None
    if not body.skip_verdict:
        verdict = await legal_verdict(body.url, config=app.state.config)
        if verdict.get("verdict") == "DENIED":
            return {"ok": False, "error": "URL not allowed for scraping", "verdict": verdict}
    try:
        from app.services.fetch_url import fetch_url_content
        content = await fetch_url_content(body.url, timeout=30.0)
    except Exception as e:
        return {"ok": False, "error": str(e), "verdict": verdict}
    if not content or len(content.strip()) < 50:
        return {"ok": False, "error": "No meaningful content fetched", "verdict": verdict}
    rec = await app.state.registry.create(
        body.tenant_id,
        doc_name,
        "url",
        external_id=body.url,
    )
    await log_activity("INGESTING", body.tenant_id, {"document": doc_name, "url": body.url[:80]}, document_id=rec.id)
    result = await ingest_document(
        body.tenant_id,
        body.namespace,
        rec.id,
        doc_name,
        content[:500000],
        config=app.state.config,
        registry=app.state.registry,
        vector_store=app.state.vector_store,
    )
    if result.get("indexed"):
        h = hashlib.sha256(content[:50000].encode()).hexdigest()[:16]
        safe_excerpt = (content[:8000] or "").replace("\x00", "")
        await app.state.registry.update(rec.id, metadata={"content_hash": h, "last_content": safe_excerpt, "namespace": body.namespace})
    await log_activity("READY", body.tenant_id, {"chunks": result["chunks_created"]}, document_id=rec.id)
    return {"ok": True, "verdict": verdict, "document_id": rec.id, "chunks_created": result.get("chunks_created", 0)}


async def _crawl_and_ingest_task(
    crawl_job_id: str,
    body: IngestCrawlBody,
    registry: DocumentRegistry,
    vector_store: VectorStore,
    config: dict[str, Any],
):
    """Background task: crawl then ingest each page; progress and log go to crawl_job_id."""
    import hashlib
    from app.services.crawl_url import crawl_url
    try:
        pages = await crawl_url(
            body.seed_url,
            config=config,
            max_depth=body.max_depth,
            max_pages=body.max_pages,
            use_llm_links=body.use_llm_links,
            use_llm_topic=body.use_llm_topic,
            use_llm_clean=body.use_llm_clean,
            crawl_goal=body.crawl_goal,
            filter_substantive=body.filter_substantive,
            progress_callback=lambda msg: append_log(crawl_job_id, msg),
        )
    except Exception as e:
        set_error(crawl_job_id, str(e))
        return
    if not pages:
        set_error(crawl_job_id, "No pages crawled")
        return
    total_chunks = 0
    for i, page in enumerate(pages):
        set_progress(crawl_job_id, "ingesting", i + 1, len(pages), f"Reading page {i + 1} of {len(pages)}… Ingesting…")
        doc_name = page.get("title") or page.get("url", "")[:80]
        rec = await registry.create(
            body.tenant_id,
            doc_name,
            "url",
            external_id=page.get("url"),
        )
        await log_activity("INGESTING", body.tenant_id, {"document": doc_name, "url": page.get("url", "")[:80], "crawl": True}, document_id=rec.id)
        result = await ingest_document(
            body.tenant_id,
            body.namespace,
            rec.id,
            doc_name,
            (page.get("text") or "")[:500000],
            config=config,
            registry=registry,
            vector_store=vector_store,
            progress_callback=lambda ph, cur, tot, msg: append_log(crawl_job_id, msg),
        )
        h = hashlib.sha256((page.get("text") or "")[:50000].encode()).hexdigest()[:16]
        meta = {"content_hash": h, "namespace": body.namespace, "topic": page.get("topic"), "source_url": page.get("url"), "crawl_depth": page.get("depth", 0)}
        await registry.update(rec.id, metadata=meta)
        total_chunks += result.get("chunks_created", 0)
        await log_activity("READY", body.tenant_id, {"chunks": result.get("chunks_created", 0), "crawl": True}, document_id=rec.id)
    set_done(crawl_job_id, total_chunks)


@app.post("/api/ingest/crawl")
async def ingest_crawl(body: IngestCrawlBody):
    """LLM-guided crawl (runs in background). Returns crawl_job_id; poll GET /api/ingest/status?document_id=<crawl_job_id> for live progress and log."""
    import asyncio
    from uuid import uuid4
    if not body.skip_verdict:
        verdict = await legal_verdict(body.seed_url, config=app.state.config)
        if verdict.get("verdict") == "DENIED":
            return {"ok": False, "error": "URL not allowed for scraping", "verdict": verdict}
    crawl_job_id = "crawl-" + str(uuid4())
    set_progress(crawl_job_id, "crawling", 0, 1, "Starting crawl… Discovering pages…")
    asyncio.create_task(_crawl_and_ingest_task(
        crawl_job_id, body, app.state.registry, app.state.vector_store, app.state.config,
    ))
    return {"ok": True, "crawl_job_id": crawl_job_id, "message": "Crawl started. Poll /api/ingest/status?document_id=" + crawl_job_id}


# ---------- 3. Knowledge freshness ----------
@app.post("/api/freshness/diff")
async def freshness_diff(old_content: str = Query(...), new_content: str = Query(...)):
    """Semantic diff summary (plain English)."""
    summary = await semantic_diff(old_content, new_content, app.state.config)
    return {"semantic_summary": summary}


@app.post("/api/freshness/notification")
async def freshness_notification(
    document_name: str,
    sections_updated: int = 0,
    sections_removed: int = 0,
    semantic_summary: str = "",
):
    """Build change notification payload."""
    return await build_change_notification(document_name, sections_updated, sections_removed, semantic_summary)


# ---------- 4. Knowledge gap report ----------
@app.post("/api/gaps/report")
async def gap_report(body: GapReportBody):
    """Weekly-style gap report: clustered gaps, priority, AI fix suggestions."""
    return await generate_gap_report(body.questions, app.state.config)


@app.get("/api/gaps/report/latest")
async def gap_report_latest():
    """Last generated gap report (from scheduled job or manual run)."""
    report = get_last_gap_report()
    return {"report": report} if report else {"report": None}


@app.post("/api/gaps/report/run")
async def gap_report_run_now(tenant_id: str | None = None, namespace: str | None = None):
    """Trigger gap report now from stored unanswered questions. Completeness = answered / (answered + unanswered) * 100."""
    questions = await get_unanswered_for_report(tenant_id=tenant_id, namespace=namespace)
    events = get_recent(limit=5000, tenant_id=tenant_id or "default")
    answered_count = sum(1 for e in events if (e.get("action") if isinstance(e, dict) else "") == "READY")
    report = await generate_gap_report(questions, app.state.config, answered_count=answered_count)
    return report


class UnansweredBody(BaseModel):
    tenant_id: str
    namespace: str
    question: str


@app.post("/api/analytics/unanswered")
async def record_unanswered_endpoint(body: UnansweredBody):
    """Record an unanswered question for gap report."""
    await record_unanswered(body.tenant_id, body.namespace, body.question)
    return {"ok": True}


@app.get("/api/analytics/unanswered")
async def list_unanswered(tenant_id: str | None = None, namespace: str | None = None, limit: int = 100):
    """List stored unanswered questions."""
    items = await get_unanswered_for_report(tenant_id=tenant_id, namespace=namespace, limit=limit)
    return {"questions": items}


@app.post("/api/analytics/unanswered/clear")
async def clear_unanswered_endpoint(tenant_id: str, namespace: str | None = None):
    """Clear stored unanswered questions."""
    n = await clear_unanswered(tenant_id, namespace)
    return {"cleared": n}


@app.post("/api/gaps/check-close")
async def gaps_check_close(tenant_id: str = Query("default"), namespace: str = Query("main"), limit: int = Query(30, ge=1, le=100)):
    """Re-answer each unanswered question; if we now get a confident answer with citations, remove it from gaps (auto-close)."""
    questions = await get_unanswered_for_report(tenant_id=tenant_id, namespace=namespace, limit=limit)
    config = getattr(app.state, "config", None) or load_config()
    vs = app.state.vector_store
    closed = 0
    for item in questions:
        q = (item.get("question") or "").strip()
        if not q:
            continue
        answer_text = ""
        citations = []
        confidence = 0
        async for event in stream_answer(tenant_id, namespace, q, config=config, vector_store=vs):
            if event.get("type") == "token":
                answer_text += event.get("payload", {}).get("text", "")
            elif event.get("type") == "citation":
                citations = event.get("payload", {}).get("citations", [])
            elif event.get("type") == "confidence":
                confidence = event.get("payload", {}).get("score", 0)
        if confidence >= 50 and citations and (answer_text or "").strip() and len((answer_text or "").strip()) >= 20:
            if await remove_unanswered(tenant_id, namespace, q):
                closed += 1
    return {"checked": len(questions), "closed": closed}


# ---------- 5. Freshness watchdog ----------
@app.post("/api/freshness/watchdog")
async def run_freshness_watchdog():
    """Run freshness check for all URL sources: re-fetch, diff, re-embed."""
    results = await run_watchdog(
        app.state.registry,
        app.state.vector_store,
        app.state.config,
    )
    return {"results": results}


# ---------- 6. Deployed surfaces: REST API + Slack/Teams/WhatsApp (see routers). ----------
@app.get("/api/deploy/channel-stats")
async def deploy_channel_stats(tenant_id: str = Query("default")):
    """Per-channel stats for Deploy: connected status and query counts (from activity log)."""
    pool = await get_pool()
    slack_connected = False
    if pool:
        async with pool.acquire() as conn:
            r = await conn.fetchrow("SELECT 1 FROM connected_tools WHERE tenant_id = $1 AND provider = $2 AND status = $3", tenant_id, "slack", "connected")
            slack_connected = r is not None
    events = get_recent(limit=2000, tenant_id=tenant_id)
    queries_by_channel = {}
    for e in events:
        if isinstance(e, dict) and (e.get("action") or "") == "READY":
            ch = (e.get("details") or {}).get("channel") or "chat"
            queries_by_channel[ch] = queries_by_channel.get(ch, 0) + 1
    return {
        "channels": {
            "slack": {"connected": slack_connected, "queries_today": queries_by_channel.get("slack", 0)},
            "widget": {"connected": True, "queries_today": queries_by_channel.get("widget", 0)},
            "api": {"connected": True, "queries_today": queries_by_channel.get("api", 0)},
            "whatsapp": {"connected": False, "queries_today": 0},
            "teams": {"connected": False, "queries_today": 0},
        },
    }


# ---------- 7. Analytics & dashboards ----------
@app.get("/api/analytics/activity")
async def analytics_activity(tenant_id: str | None = None, limit: int = 100):
    """Agent activity log — real-time feed of every action."""
    return {"events": get_recent(limit=limit, tenant_id=tenant_id)}


@app.get("/api/health/scores")
async def health_scores(
    tenant_id: str = Query("default"),
    namespace: str = Query("main"),
):
    """Four health scores for Health Monitor: knowledge_health, average_freshness, answer_accuracy, pii_shield."""
    try:
        records = await app.state.vector_store.scroll(namespace, limit=50_000)
        total_chunks = len(records)
    except Exception:
        total_chunks = 0
    docs = await app.state.registry.list_by_tenant(tenant_id)
    docs_in_ns = [d for d in docs if _doc_namespace_match(d, namespace)]
    freshness_scores = [d.freshness_score for d in docs_in_ns if d.freshness_score is not None]
    average_freshness = (sum(freshness_scores) / len(freshness_scores) * 100) if freshness_scores else 0
    # Completeness from gaps: answered / (answered + unanswered)
    gap_items = await get_unanswered_for_report(tenant_id=tenant_id, namespace=namespace, limit=5000)
    events = get_recent(limit=5000, tenant_id=tenant_id)
    answered = sum(1 for e in events if (e.get("action") if isinstance(e, dict) else "") == "READY")
    total_q = answered + len(gap_items)
    completeness = (answered / total_q * 100) if total_q > 0 else 100.0
    volume_score = min(100.0, total_chunks / 50.0) if total_chunks else 0.0
    knowledge_health = round(0.4 * average_freshness + 0.4 * (completeness / 100.0 * 100) + 0.2 * volume_score, 1)
    # Answer accuracy and PII shield from DB
    answer_accuracy = 100.0
    pii_shield = 100.0
    pool = await get_pool()
    if pool:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """SELECT COUNT(*) FILTER (WHERE helpful = true) AS helpful, COUNT(*) AS total
                   FROM answer_feedback WHERE tenant_id = $1 AND namespace = $2""",
                tenant_id,
                namespace,
            )
            if row and row["total"] and int(row["total"]) > 0:
                answer_accuracy = round(int(row["helpful"] or 0) / int(row["total"]) * 100, 1)
            r = await conn.fetchrow(
                """SELECT COUNT(*) FILTER (WHERE kind = 'pii_scan' AND (payload->>'total_count')::int > 0) AS with_pii, COUNT(*) FILTER (WHERE kind = 'pii_scan') AS total
                   FROM compliance_audit WHERE tenant_id = $1""",
                tenant_id,
            )
            if r and r["total"] and int(r["total"]) > 0 and int(r["with_pii"] or 0) > 0:
                pii_shield = max(0, round(100 - (int(r["with_pii"]) / int(r["total"]) * 100), 1))
    return {
        "knowledge_health": knowledge_health,
        "average_freshness": round(average_freshness, 1),
        "answer_accuracy": answer_accuracy,
        "pii_shield": pii_shield,
    }


def _doc_namespace_match(doc: Any, namespace: str | None) -> bool:
    """True if doc belongs to the given namespace (metadata.namespace; missing = main)."""
    if not namespace:
        return True
    doc_ns = (doc.metadata or {}).get("namespace") if hasattr(doc, "metadata") else (doc.get("metadata") or {}).get("namespace")
    if doc_ns is None:
        doc_ns = "main"
    return doc_ns == namespace


def _doc_lifecycle(meta: dict | None) -> tuple[str, str | None, str | None]:
    """Return (lifecycle_status, review_by, expires_at) from metadata. Status: ok | needs_review | expired."""
    from datetime import datetime, timezone
    meta = meta or {}
    review_by_s = meta.get("review_by")
    expires_at_s = meta.get("expires_at")
    now = datetime.now(timezone.utc)
    status = "ok"
    if expires_at_s:
        try:
            exp = datetime.fromisoformat(expires_at_s.replace("Z", "+00:00"))
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            if now > exp:
                status = "expired"
        except (ValueError, TypeError):
            pass
    if status == "ok" and review_by_s:
        try:
            rev = datetime.fromisoformat(review_by_s.replace("Z", "+00:00"))
            if rev.tzinfo is None:
                rev = rev.replace(tzinfo=timezone.utc)
            if now > rev:
                status = "needs_review"
        except (ValueError, TypeError):
            pass
    return status, review_by_s, expires_at_s


@app.get("/api/documents")
async def list_documents(tenant_id: str, namespace: str | None = Query(None)):
    """Document registry for dashboard. Optional namespace filters to current brain (my | main)."""
    docs = await app.state.registry.list_by_tenant(tenant_id)
    if namespace:
        docs = [d for d in docs if _doc_namespace_match(d, namespace)]
    out = []
    for d in docs:
        row = d.model_dump()
        life, review_by, expires_at = _doc_lifecycle(d.metadata)
        row["lifecycle_status"] = life
        row["review_by"] = review_by
        row["expires_at"] = expires_at
        out.append(row)
    return {"documents": out}


@app.get("/api/documents/source-health")
async def source_health(
    tenant_id: str = Query("default"),
    namespace: str | None = Query(None),
):
    """Source health for dashboard: healthy / stale / need_review counts and per-doc status. Optional namespace filter. decay_rate by source_type (url/crawl higher, file/paste lower)."""
    # Decay rate per source type: how fast freshness drops if not re-verified (e.g. 0.1 = 10% per day)
    DECAY_BY_TYPE = {"url": 0.1, "crawl": 0.1, "file": 0.05, "paste": 0.02}
    docs = await app.state.registry.list_by_tenant(tenant_id)
    if namespace:
        docs = [d for d in docs if _doc_namespace_match(d, namespace)]
    healthy = 0
    stale = 0
    need_review = 0
    expired_count = 0
    needs_review_lifecycle = 0
    items = []
    for d in docs:
        score = d.freshness_score
        if score is not None:
            if score >= 0.8:
                healthy += 1
                status = "healthy"
            elif score >= 0.5:
                stale += 1
                status = "stale"
            else:
                need_review += 1
                status = "need_review"
        else:
            need_review += 1
            status = "need_review"
        life, review_by, expires_at = _doc_lifecycle(d.metadata)
        if life == "expired":
            expired_count += 1
        elif life == "needs_review":
            needs_review_lifecycle += 1
        items.append({
            "id": d.id,
            "name": d.name,
            "source_type": d.source_type,
            "status": status,
            "freshness_score": score,
            "decay_rate": DECAY_BY_TYPE.get((d.source_type or "").lower(), 0.05),
            "last_verified_at": d.last_verified_at.isoformat() if d.last_verified_at else None,
            "lifecycle_status": life,
            "review_by": review_by,
            "expires_at": expires_at,
        })
    return {
        "healthy": healthy,
        "stale": stale,
        "need_review": need_review,
        "expired": expired_count,
        "needs_review_lifecycle": needs_review_lifecycle,
        "documents": items,
    }


class DocumentLifecycleBody(BaseModel):
    review_by: str | None = None  # ISO date e.g. 2025-04-01
    expires_at: str | None = None  # ISO date
    watchdog_schedule: str | None = None  # off | daily | weekly
    sync_mode: str | None = None  # batch | live


@app.patch("/api/documents/{document_id}")
async def update_document_lifecycle(document_id: str, body: DocumentLifecycleBody):
    """Set review_by, expires_at, watchdog_schedule, and/or sync_mode on a document. Stored in metadata."""
    doc = await app.state.registry.get(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    meta = dict(doc.metadata or {})
    if body.review_by is not None:
        meta["review_by"] = body.review_by.strip()[:30]
    if body.expires_at is not None:
        meta["expires_at"] = body.expires_at.strip()[:30]
    if body.watchdog_schedule is not None:
        v = (body.watchdog_schedule or "").strip().lower()
        meta["watchdog_schedule"] = v if v in ("off", "daily", "weekly") else "off"
    if body.sync_mode is not None:
        v = (body.sync_mode or "").strip().lower()
        meta["sync_mode"] = v if v in ("batch", "live") else "batch"
    await app.state.registry.update(document_id, metadata=meta)
    return {
        "document_id": document_id,
        "review_by": meta.get("review_by"),
        "expires_at": meta.get("expires_at"),
        "watchdog_schedule": meta.get("watchdog_schedule", "off"),
        "sync_mode": meta.get("sync_mode", "batch"),
    }


# ---------- Sources: OAuth tool connections (Gmail, Slack, Drive) ----------
@app.get("/api/sources/connections")
async def list_connections(tenant_id: str = Query("default")):
    """List connected OAuth tools for the tenant (Gmail, Slack, Google Drive)."""
    pool = await get_pool()
    if not pool:
        return {"connections": []}
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT provider, status, metadata, connected_at FROM connected_tools WHERE tenant_id = $1",
            tenant_id,
        )
    return {
        "connections": [
            {
                "provider": r["provider"],
                "status": r["status"],
                "metadata": dict(r["metadata"]) if r.get("metadata") else {},
                "connected_at": r["connected_at"].isoformat() if r.get("connected_at") else None,
            }
            for r in rows
        ],
    }


def _oauth_auth_url(provider: str) -> str | None:
    """Return configured OAuth auth URL for provider (gmail, slack, drive) from env."""
    key = f"OAUTH_{provider.upper()}_AUTH_URL"
    return os.environ.get(key) or os.environ.get("OAUTH_AUTH_URL")


def _slack_oauth_redirect_uri() -> str | None:
    """Backend base URL + Slack OAuth callback path."""
    base = os.environ.get("BACKEND_URL", os.environ.get("PUBLIC_URL", "http://localhost:8000"))
    return (base.rstrip("/") + "/api/sources/connections/slack/callback") if base else None


@app.post("/api/sources/connections/{provider}/connect")
async def start_connection_connect(provider: str, tenant_id: str = Query("default")):
    """Start OAuth flow for a tool. Returns auth_url to redirect user, or configured: false if not set."""
    provider = (provider or "").strip().lower()
    if provider not in ("gmail", "slack", "drive"):
        raise HTTPException(status_code=400, detail="Provider must be gmail, slack, or drive")
    if provider == "slack":
        client_id = (os.environ.get("SLACK_CLIENT_ID") or "").strip()
        if client_id:
            redirect_uri = _slack_oauth_redirect_uri()
            if not redirect_uri:
                return {"configured": False, "message": "Set BACKEND_URL or PUBLIC_URL for Slack OAuth callback."}
            from urllib.parse import urlencode
            scope = "app_mentions:read,chat:write,channels:read"
            state = tenant_id
            auth_url = f"https://slack.com/oauth/v2/authorize?{urlencode({'client_id': client_id, 'scope': scope, 'redirect_uri': redirect_uri, 'state': state})}"
            return {"configured": True, "auth_url": auth_url}
    auth_url = _oauth_auth_url(provider)
    if not auth_url:
        return {"configured": False, "message": f"OAuth for {provider} is not configured. Set OAUTH_{provider.upper()}_AUTH_URL or SLACK_CLIENT_ID for Slack."}
    return {"configured": True, "auth_url": auth_url}


@app.get("/api/sources/connections/{provider}/callback")
async def connection_callback(
    provider: str,
    code: str | None = Query(None),
    state: str | None = Query(None),
    tenant_id: str = Query("default"),
):
    """OAuth callback: exchange code for token (Slack: exchange for bot token and store). Redirects to frontend on success."""
    from urllib.parse import urlencode
    from fastapi.responses import RedirectResponse
    provider = (provider or "").strip().lower()
    if provider not in ("gmail", "slack", "drive"):
        raise HTTPException(status_code=400, detail="Provider must be gmail, slack, or drive")
    tid = (state or tenant_id or "default").strip() or "default"
    pool = await get_pool()
    if provider == "slack" and code and pool:
        client_id = (os.environ.get("SLACK_CLIENT_ID") or "").strip()
        client_secret = (os.environ.get("SLACK_CLIENT_SECRET") or "").strip()
        redirect_uri = _slack_oauth_redirect_uri()
        if client_id and client_secret and redirect_uri:
            import httpx
            async with httpx.AsyncClient() as client:
                r = await client.post(
                    "https://slack.com/api/oauth.v2.access",
                    data={
                        "client_id": client_id,
                        "client_secret": client_secret,
                        "code": code,
                        "redirect_uri": redirect_uri,
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
            data = r.json() if r.status_code == 200 else {}
            if data.get("ok") and data.get("access_token"):
                team = data.get("team") or {}
                metadata = {
                    "access_token": data["access_token"],
                    "team_id": team.get("id", ""),
                    "team_name": team.get("name", ""),
                }
                async with pool.acquire() as conn:
                    await conn.execute(
                        """INSERT INTO connected_tools (tenant_id, provider, status, metadata, connected_at)
                           VALUES ($1, $2, 'connected', $3::jsonb, NOW())
                           ON CONFLICT (tenant_id, provider) DO UPDATE SET status = 'connected', metadata = $3::jsonb""",
                        tid,
                        "slack",
                        json.dumps(metadata),
                    )
                frontend_base = os.environ.get("FRONTEND_URL", "http://localhost:3000")
                params = urlencode({"connected": "slack", "tenant_id": tid})
                return RedirectResponse(url=f"{frontend_base}/deploy?{params}", status_code=302)
    if pool and code:
        async with pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO connected_tools (tenant_id, provider, status, metadata, connected_at)
                   VALUES ($1, $2, 'connected', $3::jsonb, NOW())
                   ON CONFLICT (tenant_id, provider) DO UPDATE SET status = 'connected', metadata = $3::jsonb""",
                tid,
                provider,
                json.dumps({"code_received": True}),
            )
    frontend_base = os.environ.get("FRONTEND_URL", "http://localhost:3000")
    params = urlencode({"connected": provider, "tenant_id": tid})
    return RedirectResponse(url=f"{frontend_base}/sources?{params}", status_code=302)


@app.get("/api/documents/{document_id}/changes")
async def document_changes(document_id: str):
    """What changed in this doc since last sync? (for URL sources: re-fetch and semantic diff)."""
    from app.services.fetch_url import fetch_url_content
    doc = await app.state.registry.get(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    meta = doc.metadata or {}
    old_content = (meta.get("last_content") or "")[:50000]
    external = doc.external_id or ""
    if not external.startswith(("http://", "https://")):
        return {"document_id": document_id, "document_name": doc.name, "changed": None, "message": "Not a URL source; cannot re-fetch for changes."}
    try:
        new_content = await fetch_url_content(external, timeout=15.0)
    except Exception as e:
        return {"document_id": document_id, "document_name": doc.name, "changed": None, "error": str(e)[:200]}
    if not old_content.strip():
        out = {"document_id": document_id, "document_name": doc.name, "changed": True, "semantic_summary": "First fetch; no previous content to compare."}
        pool = await get_pool()
        if pool:
            async with pool.acquire() as conn:
                await conn.execute(
                    "INSERT INTO document_changes_log (document_id, tenant_id, semantic_summary) VALUES ($1, $2, $3)",
                    document_id, doc.tenant_id, "First fetch; no previous content to compare.",
                )
        return out
    summary = await semantic_diff(old_content[:50000], new_content[:50000], getattr(app.state, "config", None) or load_config())
    changed = old_content != new_content
    if changed:
        pool = await get_pool()
        if pool:
            async with pool.acquire() as conn:
                await conn.execute(
                    "INSERT INTO document_changes_log (document_id, tenant_id, semantic_summary) VALUES ($1, $2, $3)",
                    document_id, doc.tenant_id, (summary or "")[:2000],
                )
    return {"document_id": document_id, "document_name": doc.name, "changed": changed, "semantic_summary": summary}


@app.get("/api/documents/{document_id}/changes/history")
async def document_changes_history(document_id: str, limit: int = Query(50, ge=1, le=200)):
    """Change log timeline for this document (when URL was re-fetched and what changed)."""
    doc = await app.state.registry.get(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    pool = await get_pool()
    if not pool:
        return {"document_id": document_id, "document_name": doc.name, "history": []}
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, changed_at, semantic_summary, created_at FROM document_changes_log WHERE document_id = $1 ORDER BY changed_at DESC LIMIT $2",
            document_id,
            limit,
        )
    return {
        "document_id": document_id,
        "document_name": doc.name,
        "history": [
            {"id": r["id"], "changed_at": r["changed_at"].isoformat() if r.get("changed_at") else None, "semantic_summary": r.get("semantic_summary"), "created_at": r["created_at"].isoformat() if r.get("created_at") else None}
            for r in rows
        ],
    }


@app.get("/api/documents/changes/timeline")
async def document_changes_timeline(
    tenant_id: str = Query("default"),
    limit: int = Query(30, ge=1, le=100),
):
    """Recent change log across all documents (for Freshness change log timeline UI)."""
    pool = await get_pool()
    if not pool:
        return {"entries": []}
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT l.id, l.document_id, l.changed_at, l.semantic_summary, l.created_at, d.name AS document_name
               FROM document_changes_log l
               LEFT JOIN documents d ON d.id = l.document_id AND d.tenant_id = l.tenant_id
               WHERE l.tenant_id = $1 ORDER BY l.changed_at DESC LIMIT $2""",
            tenant_id,
            limit,
        )
    return {
        "entries": [
            {
                "id": r["id"],
                "document_id": r["document_id"],
                "document_name": r.get("document_name") or r["document_id"],
                "changed_at": r["changed_at"].isoformat() if r.get("changed_at") else None,
                "semantic_summary": r.get("semantic_summary"),
                "created_at": r["created_at"].isoformat() if r.get("created_at") else None,
            }
            for r in rows
        ],
    }


@app.get("/api/documents/{document_id}/chunks")
async def document_chunks(
    document_id: str,
    namespace: str = Query(..., description="Namespace (e.g. main, my) to scope vector store"),
    limit: int = Query(2000, ge=1, le=10000),
):
    """List chunks for a document (for View chunks in Sources). Filtered by document_id in vector store."""
    doc = await app.state.registry.get(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    try:
        chunks = await app.state.vector_store.scroll(
            namespace,
            limit=limit,
            filter_meta={"document_id": document_id},
        )
    except NotImplementedError:
        return {"chunks": [], "document_name": doc.name}
    # Sort by chunk_index for stable order
    chunks = sorted(chunks, key=lambda c: (c.get("chunk_index") or 0, c.get("id", "")))
    return {"chunks": chunks, "document_name": doc.name, "count": len(chunks)}


@app.get("/api/documents/recent-updates")
async def recent_updates(
    tenant_id: str = Query("default"),
    within_minutes: int = Query(60, ge=1, le=10080),
    namespace: str | None = Query(None),
):
    """Documents updated or re-verified in the last N minutes (for live knowledge pulse). Optional namespace filter."""
    from datetime import datetime, timezone, timedelta
    docs = await app.state.registry.list_by_tenant(tenant_id)
    if namespace:
        docs = [d for d in docs if _doc_namespace_match(d, namespace)]
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(minutes=within_minutes)
    recent = []
    for d in docs:
        dt = d.last_verified_at or d.updated_at
        if dt is None:
            continue
        # Make naive datetimes timezone-aware for comparison if needed
        if getattr(dt, "tzinfo", None) is None:
            dt = dt.replace(tzinfo=timezone.utc)
        if dt >= cutoff:
            recent.append({
                "id": d.id,
                "name": d.name,
                "updated_at": d.updated_at.isoformat() if d.updated_at else None,
                "last_verified_at": d.last_verified_at.isoformat() if d.last_verified_at else None,
            })
    recent.sort(key=lambda x: (x["last_verified_at"] or x["updated_at"] or ""), reverse=True)
    return {"documents": recent[:20], "count": len(recent)}


@app.post("/api/citations/verify")
async def verify_citations(body: VerifyCitationsBody):
    """Verify cited sources: re-check URL docs for changes; return per-doc status and summary."""
    results, summary = await verify_documents(body.document_ids, app.state.registry)
    return {"results": results, "summary": summary}


@app.get("/api/stats")
async def dashboard_stats(
    tenant_id: str = Query("default"),
    namespace: str = Query("main"),
):
    """Dashboard stats: total_chunks, average_freshness, queries_answered_this_month, knowledge_gaps_count. Optional previous_* for trend (vs last fetch)."""
    try:
        records = await app.state.vector_store.scroll(namespace, limit=50_000)
        total_chunks = len(records)
    except Exception:
        total_chunks = 0
    docs = await app.state.registry.list_by_tenant(tenant_id)
    freshness_scores = [d.freshness_score for d in docs if d.freshness_score is not None]
    average_freshness = round(sum(freshness_scores) / len(freshness_scores) * 100, 1) if freshness_scores else 0
    events = get_recent(limit=5000, tenant_id=tenant_id)
    queries_answered = sum(1 for e in events if (e.get("action") if isinstance(e, dict) else "") == "READY")
    gap_items = await get_unanswered_for_report(tenant_id=tenant_id, namespace=namespace, limit=1000)
    knowledge_gaps_count = len(gap_items)
    current = {
        "total_chunks": total_chunks,
        "average_freshness": average_freshness,
        "queries_answered_this_month": queries_answered,
        "knowledge_gaps_count": knowledge_gaps_count,
    }
    # Store previous snapshot for trend (vs last week would need date-scoped storage)
    prev = getattr(dashboard_stats, "_prev", {}).get(f"{tenant_id}:{namespace}")
    if prev:
        current["previous_total_chunks"] = prev.get("total_chunks")
        current["previous_average_freshness"] = prev.get("average_freshness")
        current["previous_queries_answered_this_month"] = prev.get("queries_answered_this_month")
        current["previous_knowledge_gaps_count"] = prev.get("knowledge_gaps_count")
    if not hasattr(dashboard_stats, "_prev"):
        dashboard_stats._prev = {}
    dashboard_stats._prev[f"{tenant_id}:{namespace}"] = dict(current)
    return current


# ---------- Brain settings (name, domain) ----------
class BrainSettingsBody(BaseModel):
    tenant_id: str = "default"
    brain_name: str | None = None
    domain: str | None = None


async def _get_brain_settings(tenant_id: str) -> dict:
    pool = await get_pool()
    if not pool:
        return {"brain_name": "My Brain", "domain": "custom"}
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT brain_name, domain FROM brain_settings WHERE tenant_id = $1", tenant_id)
    if not row:
        return {"brain_name": "My Brain", "domain": "custom"}
    return {"brain_name": row["brain_name"], "domain": row["domain"]}


@app.get("/api/brain/settings")
async def get_brain_settings(tenant_id: str = Query("default")):
    """Get brain name and domain for tenant."""
    return await _get_brain_settings(tenant_id)


@app.get("/api/brain/context")
async def get_brain_context(
    brain: str = Query("team", description="my | team"),
):
    """Return current brain context for UI: namespace, label, description. Use when you need 'team brain details'."""
    if brain == "my":
        return {
            "brain": "my",
            "namespace": "my",
            "label": "My brain",
            "description": "Your private workspace. Sources and answers here are only in your personal space.",
        }
    return {
        "brain": "team",
        "namespace": "main",
        "label": "Team brain",
        "description": "Shared workspace. Add sources here for the whole team; everyone using Team brain sees the same knowledge.",
    }


@app.put("/api/brain/settings")
async def put_brain_settings(body: BrainSettingsBody):
    """Update brain name and/or domain (partial update; only provided fields change)."""
    pool = await get_pool()
    if not pool:
        return {"brain_name": body.brain_name or "My Brain", "domain": body.domain or "custom"}
    async with pool.acquire() as conn:
        existing = await conn.fetchrow("SELECT brain_name, domain FROM brain_settings WHERE tenant_id = $1", body.tenant_id)
        name = body.brain_name if body.brain_name is not None and body.brain_name.strip() else (existing["brain_name"] if existing else "My Brain")
        domain = body.domain if body.domain is not None and body.domain.strip() else (existing["domain"] if existing else "custom")
        await conn.execute(
            """INSERT INTO brain_settings (tenant_id, brain_name, domain, updated_at)
               VALUES ($1, $2, $3, NOW())
               ON CONFLICT (tenant_id) DO UPDATE SET
                 brain_name = $2,
                 domain = $3,
                 updated_at = NOW()""",
            body.tenant_id,
            name,
            domain,
        )
    return await _get_brain_settings(body.tenant_id)


class ValidateNameBody(BaseModel):
    name: str


# ---------- Saved questions (one-click answers) ----------
class SavedQuestionBody(BaseModel):
    tenant_id: str = "default"
    question: str
    label: str | None = None


class SavedQuestionIdBody(BaseModel):
    id: str


@app.get("/api/saved-questions")
async def list_saved_questions(tenant_id: str = Query("default")):
    """List saved questions for one-click answers."""
    pool = await get_pool()
    if pool:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, question, label, created_at FROM saved_questions WHERE tenant_id = $1 ORDER BY created_at DESC",
                tenant_id,
            )
            return {"items": [{"id": r["id"], "question": r["question"], "label": r["label"], "created_at": r["created_at"].isoformat() if r["created_at"] else None} for r in rows]}
    # In-memory fallback
    store = getattr(app.state, "_saved_questions", None)
    if store is None:
        app.state._saved_questions = {}
        store = app.state._saved_questions
    items = [v for v in store.values() if v.get("tenant_id") == tenant_id]
    items.sort(key=lambda x: x.get("created_at") or "", reverse=True)
    return {"items": [{"id": x["id"], "question": x["question"], "label": x.get("label"), "created_at": x.get("created_at")} for x in items]}


@app.post("/api/saved-questions")
async def add_saved_question(body: SavedQuestionBody):
    """Save a question for one-click answer."""
    import uuid
    qid = str(uuid.uuid4())[:12]
    pool = await get_pool()
    if pool:
        async with pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO saved_questions (id, tenant_id, question, label) VALUES ($1, $2, $3, $4)",
                qid,
                body.tenant_id,
                body.question.strip()[:2000],
                body.label.strip()[:200] if body.label and body.label.strip() else None,
            )
        return {"id": qid, "question": body.question, "label": body.label}
    store = getattr(app.state, "_saved_questions", None)
    if store is None:
        app.state._saved_questions = {}
        store = app.state._saved_questions
    from datetime import datetime, timezone
    store[qid] = {"id": qid, "tenant_id": body.tenant_id, "question": body.question, "label": body.label, "created_at": datetime.now(timezone.utc).isoformat()}
    return {"id": qid, "question": body.question, "label": body.label}


@app.delete("/api/saved-questions/{question_id}")
async def delete_saved_question(question_id: str, tenant_id: str = Query("default")):
    """Remove a saved question."""
    pool = await get_pool()
    if pool:
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM saved_questions WHERE id = $1 AND tenant_id = $2", question_id, tenant_id)
        return {"deleted": True}
    store = getattr(app.state, "_saved_questions", None)
    if store and question_id in store and store[question_id].get("tenant_id") == tenant_id:
        del store[question_id]
    return {"deleted": True}


# ---------- Add to brain (from chat) + Suggest edit ----------
class AddToBrainBody(BaseModel):
    tenant_id: str = "default"
    namespace: str = "main"
    title: str  # document name
    content: str  # text to add as knowledge


class SuggestEditBody(BaseModel):
    tenant_id: str = "default"
    namespace: str = "main"
    question: str
    original_answer: str | None = None
    user_edit: str


@app.post("/api/knowledge/add-from-chat")
async def add_to_brain(body: AddToBrainBody):
    """Add an answer or pasted content to the knowledge base (brain grows from use)."""
    rec = await app.state.registry.create(
        body.tenant_id,
        (body.title or "From chat").strip()[:500],
        "from_chat",
        external_id=None,
    )
    await log_activity("ADD_TO_BRAIN", body.tenant_id, {"document": rec.name})
    result = await ingest_document(
        body.tenant_id,
        body.namespace,
        rec.id,
        rec.name,
        (body.content or "").strip()[:100_000],
        config=app.state.config,
        registry=app.state.registry,
        vector_store=app.state.vector_store,
        extract_with_llm=False,
    )
    return {"document_id": rec.id, "document_name": rec.name, "chunks_created": result.get("chunks_created", 0), "indexed": result.get("indexed", False)}


class KnowledgeCaptureCandidate(BaseModel):
    tenant_id: str = "default"
    namespace: str = "main"
    source_type: str = "slack"
    source_id: str | None = None
    question: str
    answer_text: str
    quality_score: float = 0.5
    sensitivity_score: float = 0.0


@app.get("/api/knowledge/capture")
async def list_knowledge_capture(
    tenant_id: str = Query("default"),
    status: str = Query("pending"),
    limit: int = Query(50, ge=1, le=200),
):
    """List knowledge capture queue (for Export Studio / review)."""
    pool = await get_pool()
    if not pool:
        return {"items": [], "total": 0}
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT id, tenant_id, namespace, source_type, source_id, question, answer_text, quality_score, sensitivity_score, status, created_at
               FROM knowledge_capture_queue WHERE tenant_id = $1 AND status = $2 ORDER BY created_at DESC LIMIT $3""",
            tenant_id,
            status,
            limit,
        )
    return {
        "items": [
            {
                "id": r["id"],
                "tenant_id": r["tenant_id"],
                "namespace": r["namespace"],
                "source_type": r["source_type"],
                "source_id": r["source_id"],
                "question": r["question"],
                "answer_text": r["answer_text"],
                "quality_score": r["quality_score"],
                "sensitivity_score": r["sensitivity_score"],
                "status": r["status"],
                "created_at": r["created_at"].isoformat() if r.get("created_at") else None,
            }
            for r in rows
        ],
        "total": len(rows),
    }


@app.post("/api/knowledge/capture")
async def add_knowledge_capture(body: KnowledgeCaptureCandidate):
    """Add a knowledge capture candidate (e.g. from Slack conversation classifier)."""
    pool = await get_pool()
    if not pool:
        return {"id": None, "message": "Database not configured."}
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """INSERT INTO knowledge_capture_queue (tenant_id, namespace, source_type, source_id, question, answer_text, quality_score, sensitivity_score, status)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 'pending') RETURNING id""",
            body.tenant_id,
            body.namespace,
            (body.source_type or "slack")[:50],
            (body.source_id or "")[:500],
            body.question.strip()[:10000],
            body.answer_text.strip()[:100000],
            max(0, min(1, body.quality_score)),
            max(0, min(1, body.sensitivity_score)),
        )
    return {"id": row["id"], "message": "Added to capture queue for review."}


@app.post("/api/knowledge/capture/{capture_id:int}/approve")
async def approve_knowledge_capture(
    capture_id: int,
    tenant_id: str = Query("default"),
):
    """Approve a capture: ingest Q&A into the knowledge base and mark approved."""
    pool = await get_pool()
    if not pool:
        raise HTTPException(status_code=503, detail="Database not configured.")
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, tenant_id, namespace, question, answer_text, status FROM knowledge_capture_queue WHERE id = $1 AND tenant_id = $2",
            capture_id,
            tenant_id,
        )
    if not row or row["status"] != "pending":
        raise HTTPException(status_code=404, detail="Capture not found or already processed.")
    doc_name = f"Captured Q&A ({capture_id})"
    content = f"Question: {row['question']}\n\nAnswer: {row['answer_text']}"
    rec = await app.state.registry.create(
        row["tenant_id"],
        doc_name,
        "capture",
        external_id=f"capture:{capture_id}",
    )
    result = await ingest_document(
        row["tenant_id"],
        row["namespace"],
        rec.id,
        rec.name,
        content[:100_000],
        config=app.state.config,
        registry=app.state.registry,
        vector_store=app.state.vector_store,
        extract_with_llm=False,
    )
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE knowledge_capture_queue SET status = 'approved', approved_at = NOW() WHERE id = $1",
            capture_id,
        )
    return {"document_id": rec.id, "document_name": rec.name, "chunks_created": result.get("chunks_created", 0), "approved": True}


# ---------- Personal profiles (preferences used at query time) ----------
@app.get("/api/profile")
async def get_profile(
    tenant_id: str = Query("default"),
    namespace: str = Query("main"),
    user_key: str = Query(..., description="User identifier (e.g. Slack user ID)"),
):
    """Get personal profile preferences for a user."""
    pool = await get_pool()
    if not pool:
        return {"preferences": {}}
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT preferences, updated_at FROM personal_profiles WHERE tenant_id = $1 AND namespace = $2 AND user_key = $3",
            tenant_id,
            namespace,
            user_key.strip()[:500],
        )
    if not row:
        return {"preferences": {}, "updated_at": None}
    return {
        "preferences": dict(row["preferences"]) if row.get("preferences") else {},
        "updated_at": row["updated_at"].isoformat() if row.get("updated_at") else None,
    }


class ProfileUpdateBody(BaseModel):
    tenant_id: str = "default"
    namespace: str = "main"
    user_key: str
    preferences: dict[str, Any] = {}


@app.put("/api/profile")
async def update_profile(body: ProfileUpdateBody):
    """Update personal profile preferences (inferred from feedback or set by user)."""
    pool = await get_pool()
    if not pool:
        return {"saved": False}
    prefs = {k: v for k, v in (body.preferences or {}).items() if isinstance(k, str) and len(k) < 200}
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO personal_profiles (tenant_id, namespace, user_key, preferences, updated_at)
               VALUES ($1, $2, $3, $4::jsonb, NOW())
               ON CONFLICT (tenant_id, namespace, user_key) DO UPDATE SET preferences = $4::jsonb, updated_at = NOW()""",
            body.tenant_id,
            body.namespace,
            body.user_key.strip()[:500],
            json.dumps(prefs),
        )
    return {"saved": True}


# ---------- Meeting summary (transcript -> summary, decisions, action items) ----------
class MeetingSummarizeBody(BaseModel):
    transcript: str
    title: str = "Meeting"


@app.post("/api/meetings/summarize")
async def meeting_summarize(body: MeetingSummarizeBody):
    """Generate meeting summary from transcript (decisions, action items, open questions). API for Zoom/Meet bot or manual paste."""
    config = getattr(app.state, "config", None) or load_config()
    llm = get_llm_provider(config)
    prompt = f"""You are a meeting notes assistant. Given the following transcript, produce a structured summary in JSON with these keys:
- summary: string (2-4 sentences overall)
- decisions: list of strings (each a clear decision made)
- action_items: list of {{"owner": string, "task": string, "due": string or null}}
- open_questions: list of strings (raised but not resolved)

Transcript:
{body.transcript[:50000]}

Title: {body.title}

Reply with only valid JSON, no markdown."""
    try:
        out = await llm.complete([{"role": "user", "content": prompt}], stream=False, max_tokens=1500)
        text = (out or "").strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0]
        data = json.loads(text)
        return {"ok": True, "title": body.title, **data}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200], "title": body.title}


# ---------- Ingest from email thread or web page (API for extension) ----------
class IngestEmailThreadBody(BaseModel):
    tenant_id: str = "default"
    namespace: str = "main"
    subject: str = ""
    messages: list[dict[str, Any]]  # [{ from, to, body, date }]


@app.post("/api/ingest/email-thread")
async def ingest_email_thread(body: IngestEmailThreadBody):
    """Ingest an email thread into the knowledge base (for Gmail/Outlook extension)."""
    parts = []
    for m in (body.messages or [])[:50]:
        f = (m.get("from") or m.get("sender") or "")
        t = (m.get("to") or m.get("recipient") or "")
        b = (m.get("body") or m.get("text") or m.get("content") or "")[:50000]
        parts.append(f"From: {f}\nTo: {t}\n{b}")
    content = (body.subject or "Email thread") + "\n\n" + "\n\n---\n\n".join(parts)
    content = content[:200000]
    rec = await app.state.registry.create(
        body.tenant_id,
        (body.subject or "Email thread")[:500],
        "email",
        external_id=None,
    )
    result = await ingest_document(
        body.tenant_id,
        body.namespace,
        rec.id,
        rec.name,
        content,
        config=app.state.config,
        registry=app.state.registry,
        vector_store=app.state.vector_store,
        extract_with_llm=False,
    )
    return {"document_id": rec.id, "document_name": rec.name, "chunks_created": result.get("chunks_created", 0)}


class IngestWebPageBody(BaseModel):
    tenant_id: str = "default"
    namespace: str = "main"
    url: str
    title: str = ""
    content: str  # HTML or plain text from extension


@app.post("/api/ingest/web-page")
async def ingest_web_page(body: IngestWebPageBody):
    """Ingest a web page into the knowledge base (for browser extension). Runs legal check if URL provided."""
    if body.url:
        verdict = await legal_verdict(body.url, config=getattr(app.state, "config", None) or load_config())
        if verdict.get("verdict") == "BLOCK":
            raise HTTPException(status_code=400, detail=verdict.get("evidence", "URL not allowed for scraping."))
    text = (body.content or "").strip()[:500000]
    if not text:
        raise HTTPException(status_code=400, detail="content is required.")
    title = (body.title or body.url or "Web page")[:500]
    rec = await app.state.registry.create(body.tenant_id, title, "url", external_id=body.url or None)
    result = await ingest_document(
        body.tenant_id,
        body.namespace,
        rec.id,
        rec.name,
        text,
        config=app.state.config,
        registry=app.state.registry,
        vector_store=app.state.vector_store,
        extract_with_llm=False,
    )
    return {"document_id": rec.id, "document_name": rec.name, "chunks_created": result.get("chunks_created", 0)}


@app.post("/api/feedback/suggest-edit")
async def suggest_edit(body: SuggestEditBody):
    """Store user correction when confidence is low (human-in-the-loop)."""
    pool = await get_pool()
    if pool:
        async with pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO suggested_edits (tenant_id, namespace, question, original_answer, user_edit)
                   VALUES ($1, $2, $3, $4, $5)""",
                body.tenant_id,
                body.namespace,
                body.question.strip()[:2000],
                (body.original_answer or "")[:50000],
                body.user_edit.strip()[:50000],
            )
        return {"saved": True, "message": "Thank you. Your edit will help improve the brain."}
    store = getattr(app.state, "_suggested_edits", None)
    if store is None:
        app.state._suggested_edits = []
        store = app.state._suggested_edits
    store.append({"tenant_id": body.tenant_id, "question": body.question, "user_edit": body.user_edit, "original_answer": body.original_answer})
    return {"saved": True, "message": "Thank you. Your edit will help improve the brain."}


@app.post("/api/brain/validate-name")
async def validate_brain_name(body: ValidateNameBody):
    """LLM check: name not offensive or too generic. Returns valid, message."""
    name = (body.name or "").strip()[:100]
    if not name:
        return {"valid": False, "message": "Name cannot be empty"}
    from app.core.config import get_intent_prompt
    cfg = get_intent_prompt(getattr(app.state, "config", None) or load_config(), "query") or {}
    system = "You are a validator. Reply only with JSON: {\"valid\": true} or {\"valid\": false, \"message\": \"reason\"}. Check if the given name is appropriate for a business AI assistant: not offensive, not empty, not too generic (e.g. 'AI' or 'Bot' alone)."
    user = f"Name to validate: {name}"
    try:
        llm = get_llm_provider(getattr(app.state, "config", None) or load_config())
        out = await llm.complete([{"role": "system", "content": system}, {"role": "user", "content": user}], stream=False, max_tokens=100)
        import json
        data = json.loads(out.strip().split("\n")[0] if out else "{}")
        return {"valid": data.get("valid", True), "message": data.get("message", "")}
    except Exception:
        return {"valid": True, "message": ""}


# ---------- 8. Compliance & audit ----------
async def _log_compliance_audit(tenant_id: str, kind: str, payload: dict):
    """Append an entry to compliance_audit for Compliance tab."""
    pool = await get_pool()
    if not pool:
        return
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO compliance_audit (tenant_id, kind, payload) VALUES ($1, $2, $3::jsonb)",
            tenant_id,
            kind,
            json.dumps(payload),
        )


@app.get("/api/compliance/audit")
async def get_compliance_audit(
    tenant_id: str = Query("default"),
    kind: str | None = Query(None, description="Filter by kind: pii_scan, url_verdict"),
    limit: int = Query(100, ge=1, le=500),
):
    """List compliance audit entries (PII scans, URL verdicts) for the Compliance tab."""
    pool = await get_pool()
    if not pool:
        return {"entries": [], "total": 0}
    async with pool.acquire() as conn:
        if kind:
            rows = await conn.fetch(
                "SELECT id, tenant_id, kind, payload, created_at FROM compliance_audit WHERE tenant_id = $1 AND kind = $2 ORDER BY created_at DESC LIMIT $3",
                tenant_id,
                kind,
                limit,
            )
        else:
            rows = await conn.fetch(
                "SELECT id, tenant_id, kind, payload, created_at FROM compliance_audit WHERE tenant_id = $1 ORDER BY created_at DESC LIMIT $2",
                tenant_id,
                limit,
            )
    return {
        "entries": [
            {
                "id": r["id"],
                "tenant_id": r["tenant_id"],
                "kind": r["kind"],
                "payload": dict(r["payload"]) if r.get("payload") else {},
                "created_at": r["created_at"].isoformat() if r.get("created_at") else None,
            }
            for r in rows
        ],
        "total": len(rows),
    }


@app.post("/api/compliance/pii-scan")
async def pii_scan(body: PIIScanBody):
    """PII scan report: every detection, type, action. Logged to compliance audit."""
    tenant_id = getattr(body, "tenant_id", None) or "default"
    result = await full_pii_report(body.text, app.state.config)
    await _log_compliance_audit(
        tenant_id,
        "pii_scan",
        {"total_count": result.get("total_count", 0), "summary": str(result.get("actions_taken", ""))[:200]},
    )
    return result


# ---------- 9. Web intelligence (scraper legal) ----------
@app.post("/api/web/verdict")
async def web_verdict(body: LegalVerdictBody):
    """Legal compliance verdict for URL: ALLOWED/WARN/DENIED + evidence. Logged to compliance audit."""
    tenant_id = getattr(body, "tenant_id", None) or "default"
    result = await legal_verdict(
        body.url,
        tos_excerpt=body.tos_excerpt,
        robots_excerpt=body.robots_excerpt,
        config=app.state.config,
    )
    await _log_compliance_audit(
        tenant_id,
        "url_verdict",
        {"url": body.url[:500], "verdict": result.get("verdict"), "evidence": result.get("evidence", "")[:500]},
    )
    return result


# ---------- 10. Domain expert ----------
@app.get("/api/domain-expert/persona")
async def domain_expert_persona(domain: str = "general"):
    """Persona system prompt for domain (from config prompts)."""
    from app.core.config import get_intent_prompt
    cfg = get_intent_prompt(app.state.config, "domain_expert")
    if not cfg:
        return {"persona": "Answer from the provided context. Cite sources."}
    return {"persona": cfg.get("system", "")}


# ---------- 11. Export formats ----------
async def _get_export_state(namespace: str) -> set[str]:
    """Return set of content_hashes already exported for this namespace (for incremental export)."""
    pool = await get_pool()
    if pool:
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT exported_hashes FROM export_state WHERE namespace = $1", namespace)
            if row and row["exported_hashes"]:
                return set(row["exported_hashes"])
    store = getattr(app.state, "_export_state", None)
    if store is not None and namespace in store:
        return set(store[namespace])
    return set()


async def _save_export_state(namespace: str, content_hashes: list[str]) -> None:
    """Persist exported content_hashes for this namespace (called after successful export)."""
    pool = await get_pool()
    if pool:
        import json
        async with pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO export_state (namespace, exported_hashes, updated_at)
                   VALUES ($1, $2::jsonb, NOW())
                   ON CONFLICT (namespace) DO UPDATE SET exported_hashes = $2::jsonb, updated_at = NOW()""",
                namespace,
                json.dumps(list(content_hashes)[:50000]),
            )
        return
    if getattr(app.state, "_export_state", None) is None:
        app.state._export_state = {}
    app.state._export_state[namespace] = list(content_hashes)[:50000]


@app.post("/api/export/state")
async def save_export_state(namespace: str = Query("main"), body: list[dict] | None = None):
    """Save export state (content_hashes from last export) for incremental export. Body: list of records with content_hash."""
    hashes = []
    if body:
        for r in body:
            h = (r.get("content_hash") or "").strip()
            if h:
                hashes.append(h)
    await _save_export_state(namespace, hashes)
    return {"saved": len(hashes)}


@app.get("/api/export/state")
async def get_export_state(namespace: str = Query("main")):
    """Get last incremental export state: count and updated_at for UI."""
    pool = await get_pool()
    if pool:
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT exported_hashes, updated_at FROM export_state WHERE namespace = $1", namespace)
            if row and row.get("exported_hashes"):
                hashes = row["exported_hashes"]
                count = len(hashes) if isinstance(hashes, list) else 0
                return {"namespace": namespace, "exported_count": count, "updated_at": row["updated_at"].isoformat() if row.get("updated_at") else None}
    return {"namespace": namespace, "exported_count": 0, "updated_at": None}


async def _get_filtered_chunks(
    namespace: str,
    limit: int,
    min_quality: float = 0,
    dedup: bool = False,
) -> list[dict]:
    """Shared helper: scroll and apply quality/dedup for export and generate."""
    try:
        raw = await app.state.vector_store.scroll(namespace, limit=limit * 3)
    except NotImplementedError:
        return []
    out = []
    seen_hashes: set[str] = set()
    for r in raw:
        content = r.get("content", "")
        ch = (r.get("content_hash") or "").strip() or None
        quality = r.get("quality_score")
        if quality is None:
            quality = 1.0
        if (float(quality) * 100) < min_quality:
            continue
        if dedup and ch:
            if ch in seen_hashes:
                continue
            seen_hashes.add(ch)
        out.append({"content": content, "document_name": r.get("document_name", ""), "document_id": r.get("document_id", ""), "content_hash": ch})
        if len(out) >= limit:
            break
    return out


@app.get("/api/export/generate/alpaca")
async def export_generate_alpaca(
    namespace: str = Query("main"),
    limit: int = Query(50, ge=1, le=200),
    min_quality: float = Query(0, ge=0, le=100),
    dedup: bool = Query(False),
):
    """Use LLM to generate industry Alpaca SFT (instruction, output) pairs from knowledge chunks."""
    from app.services.export_generator import generate_alpaca_from_chunks
    chunks = await _get_filtered_chunks(namespace, limit, min_quality, dedup)
    if not chunks:
        return {"records": [], "count": 0}
    records = await generate_alpaca_from_chunks(chunks, config=app.state.config, max_pairs=limit)
    return {"records": records, "count": len(records)}


@app.get("/api/export/generate/sharegpt")
async def export_generate_sharegpt(
    namespace: str = Query("main"),
    limit: int = Query(30, ge=1, le=100),
    min_quality: float = Query(0, ge=0, le=100),
    dedup: bool = Query(False),
):
    """Generate ShareGPT multi-turn conversations from knowledge chunks (LLM)."""
    from app.services.export_generator import generate_sharegpt_from_chunks
    chunks = await _get_filtered_chunks(namespace, limit, min_quality, dedup)
    if not chunks:
        return {"records": [], "count": 0}
    records = await generate_sharegpt_from_chunks(chunks, config=app.state.config, max_pairs=limit)
    return {"records": records, "count": len(records)}


@app.get("/api/export/generate/dpo")
async def export_generate_dpo(
    namespace: str = Query("main"),
    limit: int = Query(30, ge=1, le=100),
    min_quality: float = Query(0, ge=0, le=100),
    dedup: bool = Query(False),
):
    """Generate DPO (prompt, chosen, rejected) pairs from knowledge chunks (LLM)."""
    from app.services.export_generator import generate_dpo_from_chunks
    chunks = await _get_filtered_chunks(namespace, limit, min_quality, dedup)
    if not chunks:
        return {"records": [], "count": 0}
    records = await generate_dpo_from_chunks(chunks, config=app.state.config, max_pairs=limit)
    return {"records": records, "count": len(records)}


@app.get("/api/export/generate/pretrain")
async def export_generate_pretrain(
    namespace: str = Query("main"),
    limit: int = Query(50, ge=1, le=200),
    min_quality: float = Query(0, ge=0, le=100),
    dedup: bool = Query(False),
):
    """Generate pre-training format records (id, text, domain, language, quality_score) from chunks using LLM."""
    from app.services.export_generator import generate_pretrain_from_chunks
    chunks = await _get_filtered_chunks(namespace, limit, min_quality, dedup)
    if not chunks:
        return {"records": [], "count": 0}
    records = await generate_pretrain_from_chunks(chunks, config=app.state.config, max_records=limit)
    return {"records": records, "count": len(records)}


class ABTestBody(BaseModel):
    namespace: str = "main"
    variant_a_label: str = "Variant A"
    variant_b_label: str = "Variant B"
    variant_a_instruction: str = "Answer in 1-2 sentences only. Be concise."
    variant_b_instruction: str = "Answer in detail with examples. Be comprehensive."
    num_test_questions: int = 20


@app.post("/api/export/ab-test")
async def export_ab_test(body: ABTestBody):
    """A/B Dataset Tester: generate test questions, simulate answers in each variant style, score, return comparison."""
    from app.services.export_ab_test import run_ab_test
    result = await run_ab_test(
        body.namespace,
        app.state.vector_store,
        variant_a_label=body.variant_a_label,
        variant_b_label=body.variant_b_label,
        variant_a_instruction=body.variant_a_instruction,
        variant_b_instruction=body.variant_b_instruction,
        num_test_questions=min(20, max(5, body.num_test_questions)),
        config=app.state.config,
    )
    return result


class TransformPersonaBody(BaseModel):
    records: list[dict]
    persona: str  # customer_support | legal | sales | internal_expert
    format_hint: str | None = None  # alpaca | sharegpt | dpo | pretrain — so persona keeps correct schema


@app.post("/api/export/transform-persona")
async def export_transform_persona(body: TransformPersonaBody):
    """Persona Transformer: rewrite records in selected persona; format_hint keeps output in correct schema (Alpaca, DPO, ShareGPT, Pre-training)."""
    from app.services.export_generator import transform_records_persona
    out = await transform_records_persona(
        body.records, body.persona, format_hint=body.format_hint, config=app.state.config
    )
    return {"records": out, "count": len(out)}


class ScoreQualityBody(BaseModel):
    records: list[dict]
    max_records: int = 200


@app.post("/api/export/score-quality")
async def export_score_quality(body: ScoreQualityBody):
    """Batch LLM quality scoring: add quality_score (0-1) to each record. Caps at max_records for latency."""
    from app.services.export_generator import score_records_quality
    records = body.records[: body.max_records]
    out = await score_records_quality(records, config=app.state.config)
    return {"records": out, "count": len(out)}


class ExportSheetsBody(BaseModel):
    records: list[dict]
    format_hint: str = "alpaca"


@app.post("/api/export/sheets")
async def export_sheets(body: ExportSheetsBody):
    """Export for Google Sheets: returns ZIP with 8 CSV files (Raw, Pre-training, Alpaca, ShareGPT, DPO, RAG chunks, QA queue, Dashboard)."""
    import zipfile
    import io
    from fastapi.responses import Response
    records = body.records[:10000]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # Tab 1: Raw
        raw_lines = ["id,content,source,document_id,chunk_index,content_hash"]
        for i, r in enumerate(records):
            raw_lines.append(",".join([
                str(i + 1),
                f'"{str(r.get("output", r.get("content", ""))).replace(chr(34), chr(34)+chr(34))}"',
                f'"{str(r.get("source", "")).replace(chr(34), chr(34)+chr(34))}"',
                str(r.get("document_id", "")),
                str(r.get("chunk_index", 0)),
                str(r.get("content_hash", "")),
            ]))
        zf.writestr("1_raw.csv", "\n".join(raw_lines))
        # Tab 2: Pre-training ready
        zf.writestr("2_pretrain_ready.csv", "\n".join(list(to_csv_rows(records, columns=["instruction", "output", "source", "quality_score"]))) if records else "instruction,output,source,quality_score\n")
        # Tab 3: Alpaca SFT
        zf.writestr("3_alpaca_sft.csv", "\n".join(list(to_csv_rows(records, columns=["instruction", "input", "output", "source"]))) if records else "instruction,input,output,source\n")
        # Tab 4: ShareGPT (simplified: one row per convo)
        sharegpt = ["id,conversations,source_docs"]
        for i, r in enumerate(records):
            conv = r.get("conversations") or [{"from": "human", "value": r.get("instruction", "")}, {"from": "gpt", "value": r.get("output", "")}]
            sharegpt.append(f'{i+1},"{json.dumps(conv).replace(chr(34), chr(34)+chr(34))}","{str(r.get("source_docs", [])).replace(chr(34), chr(34)+chr(34))}"')
        zf.writestr("4_sharegpt.csv", "\n".join(sharegpt))
        # Tab 5: DPO
        dpo_cols = ["prompt", "chosen", "rejected", "score_gap", "rejection_type"]
        dpo_recs = [r for r in records if "prompt" in r and "chosen" in r] or records[:1]
        zf.writestr("5_dpo.csv", "\n".join(list(to_csv_rows(dpo_recs, columns=dpo_cols))) if dpo_recs else "prompt,chosen,rejected,score_gap,rejection_type\n")
        # Tab 6: RAG chunks
        rag_cols = ["document_id", "content", "source", "chunk_index", "content_hash"]
        rag_recs = [{**r, "content": r.get("output", r.get("content", ""))} for r in records]
        zf.writestr("6_rag_chunks.csv", "\n".join(list(to_csv_rows(rag_recs, columns=["document_id", "content", "source", "chunk_index", "content_hash"]))) if rag_recs else "document_id,content,source,chunk_index,content_hash\n")
        # Tab 7: QA review queue (records with low quality or flagged)
        qa = ["record_id,source_tab,issue_type,human_review,reviewer_notes"]
        for i, r in enumerate(records):
            q = (r.get("quality_score") or 1) * 100
            if q < 70 or not r.get("output"):
                qa.append(f"{i+1},alpaca,quality_low,pending,")
        zf.writestr("7_qa_review_queue.csv", "\n".join(qa) if qa else "record_id,source_tab,issue_type,human_review,reviewer_notes\n")
        # Tab 8: Dashboard summary
        dash = [
            "metric,value",
            f"total_records,{len(records)}",
            "approved,0",
            "rejected,0",
            "pending,0",
            "needs_edit,0",
        ]
        zf.writestr("8_dashboard.csv", "\n".join(dash))
    buf.seek(0)
    return Response(content=buf.getvalue(), media_type="application/zip", headers={"Content-Disposition": "attachment; filename=brainos_sheets_export.zip"})


@app.get("/api/export/records")
async def export_records(
    namespace: str = Query("main", description="Namespace to export"),
    limit: int = Query(5000, ge=1, le=50000),
    min_quality: float = Query(0, ge=0, le=100, description="Min quality score 0-100; only chunks with quality_score*100 >= this"),
    dedup: bool = Query(False, description="Deduplicate by content_hash"),
    incremental: bool = Query(False, description="Only records not in last export state for this namespace"),
):
    """Return knowledge base chunks for export. Quality filter and dedup applied in backend."""
    try:
        raw = await app.state.vector_store.scroll(namespace, limit=limit * 2 if dedup or incremental else limit)
    except NotImplementedError:
        return {"records": [], "count": 0, "message": "Vector store does not support scroll"}
    out = []
    seen_hashes: set[str] = set()
    last_export_hashes = set()
    if incremental:
        last_export_hashes = await _get_export_state(namespace)
    for r in raw:
        content = r.get("content", "")
        ch = (r.get("content_hash") or "").strip() or None
        quality = r.get("quality_score")
        if quality is None:
            quality = 1.0
        if isinstance(quality, (int, float)) and (quality * 100) < min_quality:
            continue
        if incremental and ch and ch in last_export_hashes:
            continue
        if dedup and ch:
            if ch in seen_hashes:
                continue
            seen_hashes.add(ch)
        rec = {
            "instruction": content[:500],
            "input": "",
            "output": content,
            "source": r.get("document_name", ""),
            "document_id": r.get("document_id", ""),
            "chunk_index": r.get("chunk_index", 0),
            "content_hash": ch or "",
            "quality_score": quality,
        }
        out.append(rec)
        if len(out) >= limit:
            break
    return {"records": out, "count": len(out)}


@app.post("/api/export/jsonl")
async def export_jsonl(records: list[dict], format_hint: str = "alpaca"):
    """Export as JSONL (Alpaca, ShareGPT, OpenAI Chat, DPO, etc.)."""
    def gen():
        for line in to_jsonl(records, format_hint=format_hint):
            yield line
    return StreamingResponse(gen(), media_type="application/x-ndjson", headers={"Content-Disposition": "attachment; filename=export.jsonl"})


@app.get("/api/export/schema")
async def export_schema():
    """JSON Schema inferred from sample export record."""
    sample = {"instruction": "", "input": "", "output": "", "source": "", "document_id": "", "chunk_index": 0}
    return to_json_schema(sample)


@app.get("/api/export/training-estimate")
async def export_training_estimate(
    record_count: int = Query(..., ge=0),
    format_hint: str = Query("alpaca"),
    avg_tokens_per_record: float = Query(300, ge=50, le=2000),
    duplicate_pct: float = Query(0, ge=0, le=100),
):
    """Training cost estimator: total tokens, recommended approach, GPU, cost ranges, readiness score."""
    total_tokens = int(record_count * avg_tokens_per_record)
    # LoRA 7B, 2 epochs heuristic
    gpu_hours = max(0.1, (total_tokens / 1_000_000) * 3.2)
    gpu_memory_gb = 24
    cost_ranges = [
        {"provider": "RunPod (A100 spot)", "range_usd": f"${max(4, int(gpu_hours * 2.5))}–{max(6, int(gpu_hours * 4))}", "gpu_hours": round(gpu_hours, 1)},
        {"provider": "Lambda Labs (A100 on-demand)", "range_usd": f"${max(8, int(gpu_hours * 4.5))}–{max(12, int(gpu_hours * 6))}", "gpu_hours": round(gpu_hours, 1)},
        {"provider": "AWS p4d.24xl (spot)", "range_usd": f"${max(10, int(gpu_hours * 5))}–{max(18, int(gpu_hours * 8))}", "gpu_hours": round(gpu_hours, 1)},
        {"provider": "Google Cloud (A100)", "range_usd": f"${max(10, int(gpu_hours * 5))}–{max(16, int(gpu_hours * 7))}", "gpu_hours": round(gpu_hours, 1)},
    ]
    checks = []
    if record_count >= 100:
        checks.append({"ok": True, "label": "Size adequate"})
    else:
        checks.append({"ok": False, "label": "Consider 100+ records for fine-tuning"})
    checks.append({"ok": True, "label": "Format valid"})
    if duplicate_pct > 20:
        checks.append({"ok": False, "label": f"{duplicate_pct:.0f}% duplicate rate — run dedup"})
    else:
        checks.append({"ok": True, "label": f"Duplicate rate {duplicate_pct:.0f}%"})
    readiness = sum(1 for c in checks if c["ok"]) * 33
    readiness = min(100, readiness)
    return {
        "record_count": record_count,
        "total_tokens": total_tokens,
        "avg_tokens_per_record": avg_tokens_per_record,
        "format": format_hint,
        "recommended_approach": "LoRA fine-tune · 7B parameter model · 2 epochs",
        "gpu_memory_gb": gpu_memory_gb,
        "gpu_hours": round(gpu_hours, 1),
        "cost_ranges": cost_ranges,
        "readiness": {"score": readiness, "checks": checks},
    }


@app.post("/api/export/parquet")
async def export_parquet(records: list[dict]):
    """Export records as Parquet (Hugging Face / pandas compatible)."""
    from fastapi.responses import Response
    try:
        data = to_parquet_bytes(records)
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    return Response(content=data, media_type="application/octet-stream", headers={"Content-Disposition": "attachment; filename=export.parquet"})


class PushHFBody(BaseModel):
    token: str
    repo_id: str  # e.g. "username/dataset-name"
    records: list[dict]
    format_hint: str = "alpaca"
    private: bool = True


@app.post("/api/export/push/hf")
async def export_push_hf(body: PushHFBody):
    """One-click push to Hugging Face: create repo, upload Parquet/JSONL, optional dataset card."""
    try:
        from huggingface_hub import HfApi
        import tempfile
        import os
    except ImportError:
        raise HTTPException(status_code=501, detail="Install huggingface_hub: pip install huggingface_hub")
    api = HfApi(token=body.token)
    try:
        api.create_repo(repo_id=body.repo_id, private=body.private, repo_type="dataset", exist_ok=True)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Create repo failed: {str(e)[:200]}")
    parquet_path = tempfile.mktemp(suffix=".parquet")
    try:
        data = to_parquet_bytes(body.records)
        with open(parquet_path, "wb") as f:
            f.write(data)
        api.upload_file(path_or_fileobj=parquet_path, path_in_repo="data/train.parquet", repo_id=body.repo_id, repo_type="dataset")
    finally:
        try:
            os.unlink(parquet_path)
        except Exception:
            pass
    jsonl_path = tempfile.mktemp(suffix=".jsonl")
    try:
        with open(jsonl_path, "w", encoding="utf-8") as f:
            for line in to_jsonl(body.records, format_hint=body.format_hint):
                f.write(line)
        api.upload_file(path_or_fileobj=jsonl_path, path_in_repo="data/train.jsonl", repo_id=body.repo_id, repo_type="dataset")
    finally:
        try:
            os.unlink(jsonl_path)
        except Exception:
            pass
    return {"ok": True, "repo_id": body.repo_id, "url": f"https://huggingface.co/datasets/{body.repo_id}"}


@app.post("/api/export/csv")
async def export_csv(records: list[dict], columns: str | None = None):
    """Export records as CSV (Google Sheets, human review)."""
    from fastapi.responses import Response
    cols = columns.split(",") if columns else (list(records[0].keys()) if records else [])
    lines = list(to_csv_rows(records, columns=cols))
    body = "\n".join(lines)
    return Response(content=body, media_type="text/csv", headers={"Content-Disposition": "attachment; filename=export.csv"})


@app.get("/health")
async def health():
    return {"status": "ok", "service": "BrainOS"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
