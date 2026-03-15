"""Agent executor: run task graph with tool registry (search, summarize, report). Evaluator loop + outcome memory."""
from __future__ import annotations

import json
import uuid
from typing import Any, AsyncIterator

from app.core.config import load_config
from app.providers import get_llm_provider
from app.store import VectorStore


async def _tool_search(
    tenant_id: str,
    namespace: str,
    query: str,
    vector_store: VectorStore,
    top_k: int = 8,
) -> dict[str, Any]:
    """Search knowledge base (RAG retrieval). Returns { success, content, doc_names, error }. """
    try:
        from app.providers import get_embedding_provider
        config = load_config()
        emb = get_embedding_provider(config)
        q_vec = (await emb.embed([query]))[0]
        hits = await vector_store.search(namespace, q_vec, top_k=top_k)
        content = "\n\n".join(h.content for h in hits[:top_k])
        doc_names = list({h.meta.document_name for h in hits if h.meta.document_name})
        return {"success": True, "content": content[:12000], "doc_names": doc_names, "hit_count": len(hits)}
    except Exception as e:
        return {"success": False, "content": "", "doc_names": [], "error": str(e)}


async def _tool_summarize(text: str, config: dict[str, Any], llm) -> dict[str, Any]:
    """Summarize text via LLM. Returns { success, content, error }. """
    if not text or not text.strip():
        return {"success": True, "content": "", "error": None}
    try:
        out = await llm.complete(
            [{"role": "user", "content": f"Summarize the following concisely, preserving key facts and numbers.\n\n{text[:8000]}"}],
            stream=False,
            max_tokens=1500,
        )
        return {"success": True, "content": (out or "").strip()[:6000], "error": None}
    except Exception as e:
        return {"success": False, "content": "", "error": str(e)}


async def _tool_report(goal: str, context: str, config: dict[str, Any], llm) -> dict[str, Any]:
    """Generate final report from goal and context. Returns { success, content, error }. """
    try:
        out = await llm.complete(
            [
                {"role": "system", "content": "You produce a clear, structured report. Use bullet points or short sections. Base everything on the context provided."},
                {"role": "user", "content": f"Goal: {goal}\n\nContext:\n{context[:10000]}\n\nProduce the report:"},
            ],
            stream=False,
            max_tokens=2000,
        )
        return {"success": True, "content": (out or "").strip()[:8000], "error": None}
    except Exception as e:
        return {"success": False, "content": "", "error": str(e)}


def _select_tool(action: str) -> str:
    """Map task action to tool name: search, summarize, report."""
    a = (action or "").lower()
    if "search" in a or "find" in a or "query" in a or "look up" in a or "knowledge" in a:
        return "search"
    if "summar" in a or "summary" in a:
        return "summarize"
    if "report" in a or "generat" in a or "write" in a or "analys" in a:
        return "report"
    return "search"


async def run_plan(
    tenant_id: str,
    namespace: str,
    goal: str,
    tasks: list[dict[str, Any]],
    vector_store: VectorStore,
    config: dict[str, Any] | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """
    Execute task graph. Yields log events: log, task_start, task_done, task_fail, evaluator, done.
    Each event is a dict with type and payload for SSE.
    """
    config = config or load_config()
    llm = get_llm_provider(config)
    run_id = str(uuid.uuid4())[:12]
    results_by_index: dict[int, str] = {}
    steps_log: list[dict] = []
    tool = "search"
    content = ""

    yield {"type": "log", "payload": {"message": f"Starting run {run_id} for goal: {goal[:80]}…", "level": "info"}}

    for i, task in enumerate(tasks):
        action = (task.get("action") or "").strip() or f"Task {i+1}"
        deps = task.get("dependencies") or []
        yield {"type": "task_start", "payload": {"task_index": i, "action": action, "dependencies": deps}}
        steps_log.append({"task_index": i, "action": action, "status": "running", "result_excerpt": None})

        tool = _select_tool(action)
        success = False
        content = ""

        if tool == "search":
            # Use action or goal as query
            query = action if len(action) > 20 else f"{goal} {action}"
            yield {"type": "log", "payload": {"message": f"Searching knowledge base: «{query[:60]}…»", "level": "info"}}
            out = await _tool_search(tenant_id, namespace, query, vector_store)
            success = out.get("success", False)
            content = out.get("content", "") or out.get("error", "")
            if success:
                yield {"type": "log", "payload": {"message": f"Found {out.get('hit_count', 0)} chunks from {len(out.get('doc_names', []))} doc(s)", "level": "info"}}
        elif tool == "summarize":
            # Use previous step outputs as input
            input_text = " ".join(results_by_index.get(j, "") for j in range(i) if results_by_index.get(j))
            if not input_text.strip():
                input_text = content or "No prior context."
            yield {"type": "log", "payload": {"message": "Summarizing previous results…", "level": "info"}}
            out = await _tool_summarize(input_text, config, llm)
            success = out.get("success", False)
            content = out.get("content", "") or out.get("error", "")
        else:
            # report
            context = " ".join(results_by_index.get(j, "") for j in range(i) if results_by_index.get(j)) or content
            yield {"type": "log", "payload": {"message": "Generating report…", "level": "info"}}
            out = await _tool_report(goal, context, config, llm)
            success = out.get("success", False)
            content = out.get("content", "") or out.get("error", "")

        results_by_index[i] = content[:2000]
        steps_log[-1]["status"] = "completed" if success else "failed"
        steps_log[-1]["result_excerpt"] = (content or "")[:300]

        if success:
            yield {"type": "task_done", "payload": {"task_index": i, "action": action, "result_excerpt": (content or "")[:400]}}
        else:
            yield {"type": "task_fail", "payload": {"task_index": i, "action": action, "error": content or "Unknown error"}}

    # Build final output for the user (goal-based answer/report)
    all_context = "\n\n---\n\n".join(
        results_by_index.get(j, "") for j in range(len(tasks)) if results_by_index.get(j)
    ).strip()
    final_content = ""
    if all_context:
        if tool == "report" and content:
            final_content = content
        else:
            try:
                final_content = await llm.complete(
                    [
                        {"role": "system", "content": "You answer the user's goal using only the context below. Be clear, structured, and direct. Use bullet points or short paragraphs. If the context does not contain enough information, say so and summarize what is available."},
                        {"role": "user", "content": f"Goal: {goal}\n\nContext from knowledge base:\n\n{all_context[:12000]}\n\nProvide a direct answer or report addressing the goal:"},
                    ],
                    stream=False,
                    max_tokens=2500,
                )
                final_content = (final_content or "").strip()[:12000]
            except Exception:
                final_content = all_context[:4000] if all_context else "No content could be generated."
    else:
        final_content = "No relevant content was found in the knowledge base for this goal. Try adding more sources or rephrasing your goal."
    yield {"type": "result", "payload": {"content": final_content, "goal": goal}}

    # Evaluator: did we succeed overall?
    yield {"type": "log", "payload": {"message": "Evaluating run…", "level": "info"}}
    all_ok = all(s.get("status") == "completed" for s in steps_log)
    try:
        eval_prompt = f"Goal: {goal}\n\nSteps completed: {json.dumps([s.get('action') for s in steps_log])}. Outcomes: {json.dumps([s.get('status') for s in steps_log])}. Did we achieve the goal? Reply with one word: yes or no, then one short reason."
        eval_out = await llm.complete([{"role": "user", "content": eval_prompt}], stream=False, max_tokens=100)
        eval_reason = (eval_out or "").strip()[:200]
        eval_success = "yes" in (eval_out or "").lower()[:50]
    except Exception:
        eval_reason = "Evaluation skipped"
        eval_success = all_ok
    yield {"type": "evaluator", "payload": {"success": eval_success, "reason": eval_reason}}
    yield {"type": "done", "payload": {"run_id": run_id, "steps_log": steps_log, "outcome_success": eval_success}}
