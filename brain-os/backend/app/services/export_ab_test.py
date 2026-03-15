"""A/B Dataset Tester: compare two format variants (e.g. short vs long instructions) via simulated answers and LLM scoring."""
from __future__ import annotations

import json
import re
from typing import Any

from app.core.config import load_config
from app.providers import get_embedding_provider, get_llm_provider
from app.store.vector import VectorStore, SearchHit


def _build_context(hits: list[SearchHit]) -> str:
    return "\n\n---\n\n".join(
        f"[{i}] {h.meta.document_name}\n{h.content}"
        for i, h in enumerate(hits, 1)
    )


async def run_ab_test(
    namespace: str,
    vector_store: VectorStore,
    variant_a_label: str,
    variant_b_label: str,
    variant_a_instruction: str,
    variant_b_instruction: str,
    num_test_questions: int = 20,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Generate test questions from KB, simulate answers in each variant style, score both, return comparison.
    variant_a_instruction / variant_b_instruction: e.g. "Answer in 1-2 sentences only." vs "Answer in detail with examples."
    """
    config = config or load_config()
    llm = get_llm_provider(config)
    emb = get_embedding_provider(config)

    # 1. Get chunks and generate test questions
    try:
        raw = await vector_store.scroll(namespace, limit=200)
    except NotImplementedError:
        return {"error": "Vector store does not support scroll", "winner": None}
    if not raw:
        return {"error": "No chunks in namespace", "winner": None}

    sample = "\n\n".join((r.get("content") or "")[:500] for r in raw[:30])
    questions_prompt = f"""Based on the following knowledge base snippets, generate exactly {min(num_test_questions, 20)} short questions that this knowledge can answer.
One question per line. No numbering. Questions should be diverse (different topics). Only output the questions.

Snippets:
{sample[:8000]}

Questions:"""
    try:
        q_out = await llm.complete([{"role": "user", "content": questions_prompt}], stream=False, max_tokens=800)
        questions = [q.strip() for q in (q_out or "").strip().split("\n") if q.strip()][:num_test_questions]
    except Exception as e:
        return {"error": f"Failed to generate questions: {e}", "winner": None}
    if not questions:
        return {"error": "No questions generated", "winner": None}

    # 2. For each question: retrieve context, then generate answer in style A and style B
    results_a: list[dict[str, Any]] = []
    results_b: list[dict[str, Any]] = []

    for q in questions:
        try:
            q_vec = (await emb.embed([q]))[0]
            hits = await vector_store.search(namespace, q_vec, top_k=5)
            context = _build_context(hits)
        except Exception:
            context = ""
        if not context.strip():
            continue
        system_base = "Answer ONLY from the provided context. Do not use outside knowledge. Be accurate and grounded."
        # Variant A answer
        try:
            ans_a = await llm.complete(
                [
                    {"role": "system", "content": f"{system_base} {variant_a_instruction}"},
                    {"role": "user", "content": f"Context:\n{context[:6000]}\n\nQuestion: {q}\n\nAnswer:"},
                ],
                stream=False,
                max_tokens=400,
            )
            results_a.append({"question": q, "answer": (ans_a or "").strip()})
        except Exception:
            results_a.append({"question": q, "answer": ""})
        # Variant B answer
        try:
            ans_b = await llm.complete(
                [
                    {"role": "system", "content": f"{system_base} {variant_b_instruction}"},
                    {"role": "user", "content": f"Context:\n{context[:6000]}\n\nQuestion: {q}\n\nAnswer:"},
                ],
                stream=False,
                max_tokens=400,
            )
            results_b.append({"question": q, "answer": (ans_b or "").strip()})
        except Exception:
            results_b.append({"question": q, "answer": ""})

    # 3. Score each (question, answer) pair: accuracy, groundedness, clarity, format (1-5)
    async def score_answer(question: str, answer: str, style_instruction: str) -> dict[str, float]:
        if not answer:
            return {"accuracy": 0, "groundedness": 0, "clarity": 0, "format": 0}
        try:
            judge = await llm.complete(
                [
                    {"role": "system", "content": "You score an answer 1-5 on four dimensions. Reply with JSON only: {\"accuracy\": N, \"groundedness\": N, \"clarity\": N, \"format\": N}. Accuracy: factually correct from context. Groundedness: stays in context. Clarity: easy to understand. Format: follows the requested style."},
                    {"role": "user", "content": f"Question: {question}\nRequested style: {style_instruction}\nAnswer: {answer}\n\nJSON scores (1-5 each):"},
                ],
                stream=False,
                max_tokens=150,
            )
            m = re.search(r"\{[^{}]*\}", judge or "")
            if m:
                d = json.loads(m.group(0))
                return {k: float(d.get(k, 3)) for k in ("accuracy", "groundedness", "clarity", "format")}
        except Exception:
            pass
        return {"accuracy": 3, "groundedness": 3, "clarity": 3, "format": 3}

    scores_a: list[dict[str, float]] = []
    scores_b: list[dict[str, float]] = []
    for i, (ra, rb) in enumerate(zip(results_a, results_b)):
        scores_a.append(await score_answer(ra["question"], ra["answer"], variant_a_instruction))
        scores_b.append(await score_answer(rb["question"], rb["answer"], variant_b_instruction))

    def avg_scores(scores: list[dict[str, float]]) -> dict[str, float]:
        if not scores:
            return {"accuracy": 0, "groundedness": 0, "clarity": 0, "format": 0, "overall": 0}
        n = len(scores)
        out = {}
        for k in ("accuracy", "groundedness", "clarity", "format"):
            out[k] = round(sum(s[k] for s in scores) / n, 1)
        out["overall"] = round(sum(out.values()) / 4, 1)
        return out

    avg_a = avg_scores(scores_a)
    avg_b = avg_scores(scores_b)
    winner = variant_a_label if avg_a["overall"] >= avg_b["overall"] else variant_b_label
    diff = round(avg_a["overall"] - avg_b["overall"], 1)
    recommendation = f"{winner} scores {'higher' if diff != 0 else 'the same'} (Δ {abs(diff)}). Use {winner} for this knowledge base." if diff != 0 else "Both variants score similarly. Choose by preference."

    return {
        "variant_a": {"label": variant_a_label, "scores": avg_a, "sample_qa": results_a[:3] if results_a else []},
        "variant_b": {"label": variant_b_label, "scores": avg_b, "sample_qa": results_b[:3] if results_b else []},
        "winner": winner,
        "recommendation": recommendation,
        "num_questions": len(questions),
    }
