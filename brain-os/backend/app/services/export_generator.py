"""LLM-generated training data in industry formats (Alpaca SFT, etc.) from knowledge chunks."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

from app.core.config import load_config
from app.providers import get_llm_provider


def _load_export_prompts(config: dict[str, Any]) -> dict[str, Any]:
    config_dir = Path(config.get("_config_dir", Path(__file__).parent.parent.parent / "config"))
    path = config_dir / "prompts" / "export_gen.yaml"
    if not path.exists():
        return {}
    with open(path) as f:
        return yaml.safe_load(f) or {}


async def generate_alpaca_from_chunks(
    chunks: list[dict[str, Any]],
    config: dict[str, Any] | None = None,
    max_pairs: int = 100,
) -> list[dict[str, Any]]:
    """
    Use LLM to generate Alpaca SFT (instruction, output) pairs from each chunk.
    Returns list of {instruction, input, output, source, document_name} for industry training format.
    """
    config = config or load_config()
    prompts = _load_export_prompts(config)
    spec = prompts.get("alpaca_from_chunk") or {}
    system = spec.get("system", "Generate one instruction and one output from the chunk. Reply JSON: {\"instruction\": \"...\", \"output\": \"...\"}")
    user_tpl = spec.get("user_template", "Chunk: {{ content }}\n\nJSON only.")
    llm = get_llm_provider(config)
    out_list = []
    for i, chunk in enumerate(chunks[:max_pairs]):
        content = (chunk.get("content") or "")[:4000]
        source = chunk.get("document_name") or chunk.get("source") or "document"
        if not content.strip():
            continue
        user_msg = user_tpl.replace("{{ content }}", content).replace("{{ source }}", source)
        try:
            raw = await llm.complete(
                [{"role": "system", "content": system}, {"role": "user", "content": user_msg}],
                stream=False,
                max_tokens=800,
            )
        except Exception:
            continue
        raw = (raw or "").strip()
        # Extract JSON from response (handle markdown code blocks)
        json_str = raw
        m = re.search(r"\{[\s\S]*\}", raw)
        if m:
            json_str = m.group(0)
        try:
            data = json.loads(json_str)
            inst = (data.get("instruction") or "").strip()
            output = (data.get("output") or "").strip()
            if inst and output:
                out_list.append({
                    "instruction": inst,
                    "input": "",
                    "output": output,
                    "source": source,
                    "document_name": source,
                    "document_id": chunk.get("document_id", ""),
                })
        except json.JSONDecodeError:
            continue
    return out_list


async def generate_sharegpt_from_chunks(
    chunks: list[dict[str, Any]],
    config: dict[str, Any] | None = None,
    max_pairs: int = 50,
) -> list[dict[str, Any]]:
    """Generate ShareGPT multi-turn conversations from chunks. Returns list of {id, conversations, source_docs}."""
    config = config or load_config()
    prompts = _load_export_prompts(config)
    spec = prompts.get("sharegpt_from_chunk") or {}
    system = spec.get("system", "Generate a short conversation (human/gpt turns) from the chunk. JSON: {\"conversations\": [{\"from\":\"human\",\"value\":\"...\"}, ...]}")
    user_tpl = spec.get("user_template", "Chunk: {{ content }}\n\nJSON only.")
    llm = get_llm_provider(config)
    out_list = []
    for i, chunk in enumerate(chunks[:max_pairs]):
        content = (chunk.get("content") or "")[:4000]
        source = chunk.get("document_name") or chunk.get("source") or "document"
        if not content.strip():
            continue
        user_msg = user_tpl.replace("{{ content }}", content).replace("{{ source }}", source)
        try:
            raw = await llm.complete(
                [{"role": "system", "content": system}, {"role": "user", "content": user_msg}],
                stream=False,
                max_tokens=600,
            )
        except Exception:
            continue
        raw = (raw or "").strip()
        m = re.search(r"\{[\s\S]*\}", raw)
        json_str = m.group(0) if m else raw
        try:
            data = json.loads(json_str)
            conv = data.get("conversations") or []
            if isinstance(conv, list) and len(conv) >= 2:
                out_list.append({
                    "id": f"conv_{i}",
                    "conversations": conv,
                    "source_docs": [source],
                })
        except json.JSONDecodeError:
            continue
    return out_list


async def generate_dpo_from_chunks(
    chunks: list[dict[str, Any]],
    config: dict[str, Any] | None = None,
    max_pairs: int = 50,
) -> list[dict[str, Any]]:
    """Generate DPO (prompt, chosen, rejected) pairs from chunks. Returns list with prompt, chosen, rejected, scores, rejection_type."""
    config = config or load_config()
    prompts = _load_export_prompts(config)
    spec = prompts.get("dpo_from_chunk") or {}
    system = spec.get("system", "Generate one DPO pair: prompt, chosen (good answer), rejected (bad answer). JSON only.")
    user_tpl = spec.get("user_template", "Chunk: {{ content }}\n\nJSON: {\"prompt\":\"...\",\"chosen\":\"...\",\"rejected\":\"...\",\"rejection_type\":\"...\"}")
    llm = get_llm_provider(config)
    out_list = []
    for i, chunk in enumerate(chunks[:max_pairs]):
        content = (chunk.get("content") or "")[:4000]
        source = chunk.get("document_name") or chunk.get("source") or "document"
        if not content.strip():
            continue
        user_msg = user_tpl.replace("{{ content }}", content).replace("{{ source }}", source)
        try:
            raw = await llm.complete(
                [{"role": "system", "content": system}, {"role": "user", "content": user_msg}],
                stream=False,
                max_tokens=500,
            )
        except Exception:
            continue
        raw = (raw or "").strip()
        m = re.search(r"\{[\s\S]*\}", raw)
        json_str = m.group(0) if m else raw
        try:
            data = json.loads(json_str)
            prompt = (data.get("prompt") or "").strip()
            chosen = (data.get("chosen") or "").strip()
            rejected = (data.get("rejected") or "").strip()
            if prompt and chosen and rejected:
                out_list.append({
                    "prompt": prompt,
                    "chosen": chosen,
                    "rejected": rejected,
                    "chosen_score": 0.9,
                    "rejected_score": 0.2,
                    "score_gap": 0.7,
                    "rejection_type": (data.get("rejection_type") or "vague")[:50],
                    "source_url": source,
                })
        except json.JSONDecodeError:
            continue
    return out_list


async def generate_pretrain_from_chunks(
    chunks: list[dict[str, Any]],
    config: dict[str, Any] | None = None,
    max_records: int = 100,
) -> list[dict[str, Any]]:
    """Generate pre-training format records from chunks using LLM. Returns list of {id, text, source_url, domain, language, quality_score, content_hash}."""
    config = config or load_config()
    prompts = _load_export_prompts(config)
    spec = prompts.get("pretrain_from_chunk") or {}
    system = spec.get(
        "system",
        "Produce one pre-training record: clean text, domain, language, quality_score. Reply JSON: {\"text\":\"...\",\"domain\":\"...\",\"language\":\"...\",\"quality_score\":0.9}",
    )
    user_tpl = spec.get("user_template", "Chunk: {{ content }}\n\nJSON only.")
    llm = get_llm_provider(config)
    out_list = []
    for i, chunk in enumerate(chunks[:max_records]):
        content = (chunk.get("content") or "")[:4000]
        source = chunk.get("document_name") or chunk.get("source") or "document"
        ch = chunk.get("content_hash") or ""
        if not content.strip():
            continue
        user_msg = user_tpl.replace("{{ content }}", content).replace("{{ source }}", source)
        try:
            raw = await llm.complete(
                [{"role": "system", "content": system}, {"role": "user", "content": user_msg}],
                stream=False,
                max_tokens=600,
            )
        except Exception:
            continue
        raw = (raw or "").strip()
        m = re.search(r"\{[\s\S]*\}", raw)
        json_str = m.group(0) if m else raw
        try:
            data = json.loads(json_str)
            text = (data.get("text") or content[:2000]).strip()
            domain = (data.get("domain") or "general")[:64]
            lang = (data.get("language") or "en")[:8]
            q = data.get("quality_score")
            quality_score = float(q) if isinstance(q, (int, float)) else 0.85
            quality_score = max(0, min(1, quality_score))
            out_list.append({
                "id": f"pretrain_{i}",
                "text": text,
                "source_url": source,
                "source": source,
                "domain": domain,
                "language": lang,
                "quality_score": round(quality_score, 2),
                "content_hash": ch or "",
            })
        except json.JSONDecodeError:
            continue
    return out_list


async def score_records_quality(
    records: list[dict[str, Any]],
    config: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Add quality_score (0-1) to each record using LLM. One sentence per record."""
    config = config or load_config()
    llm = get_llm_provider(config)
    out = []
    for r in records:
        text = (r.get("output") or r.get("content") or r.get("instruction") or "")[:1500]
        score = 0.8
        if text.strip():
            try:
                raw = await llm.complete(
                    [{"role": "user", "content": f"Rate this text for training data quality (substantive, clear, no junk). Reply with one number 0.0 to 1.0 only.\n\nText: {text}\n\nScore:"}],
                    stream=False,
                    max_tokens=10,
                )
                s = (raw or "").strip()
                for word in s.replace(",", ".").split():
                    try:
                        score = max(0, min(1, float(word)))
                        break
                    except ValueError:
                        continue
            except Exception:
                pass
        out.append({**r, "quality_score": round(score, 2)})
    return out


_PERSONA_REWRITE = {
    "customer_support": "Rewrite in a warm, helpful, friendly customer-support tone. Concise and welcoming; light emoji OK. Keep the same facts.",
    "legal": "Rewrite in a formal, precise, citation-ready tone suitable for legal/compliance. Hedged language where appropriate. Same facts.",
    "sales": "Rewrite in a persuasive, benefit-focused tone for sales. Highlight value and outcomes. Same facts.",
    "internal_expert": "Rewrite as an internal domain expert: clear, direct, thorough. Technical accuracy. Same facts.",
}


def _detect_format(record: dict[str, Any]) -> str:
    """Infer format from record keys for persona transform."""
    if "conversations" in record and isinstance(record.get("conversations"), list):
        return "sharegpt"
    if "prompt" in record and "chosen" in record and "rejected" in record:
        return "dpo"
    if "text" in record and ("domain" in record or "content_hash" in record):
        return "pretrain"
    return "alpaca"


async def transform_records_persona(
    records: list[dict[str, Any]],
    persona: str,
    format_hint: str | None = None,
    config: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Rewrite records in the given persona. Format-aware: alpaca (instruction/output), dpo (prompt/chosen/rejected), sharegpt (conversations), pretrain (text)."""
    config = config or load_config()
    llm = get_llm_provider(config)
    instruction = _PERSONA_REWRITE.get(persona.strip().lower().replace(" ", "_")) or _PERSONA_REWRITE["internal_expert"]
    out = []
    for r in records[:200]:
        fmt = format_hint or _detect_format(r)
        if fmt == "alpaca":
            inst = (r.get("instruction") or "").strip()
            out_text = (r.get("output") or "").strip()
            if not inst and not out_text:
                out.append(dict(r))
                continue
            try:
                prompt = f"Instruction (user question): {inst[:1000]}\n\nOutput (answer): {out_text[:2000]}\n\n{instruction}\n\nReply with JSON only: {{\"instruction\": \"...\", \"output\": \"...\"}}"
                raw = await llm.complete([{"role": "user", "content": prompt}], stream=False, max_tokens=1500)
                raw = (raw or "").strip()
                m = re.search(r"\{[\s\S]*\}", raw)
                if m:
                    data = json.loads(m.group(0))
                    out.append({**r, "instruction": (data.get("instruction") or inst).strip(), "output": (data.get("output") or out_text).strip()})
                else:
                    out.append(dict(r))
            except Exception:
                out.append(dict(r))
        elif fmt == "dpo":
            prompt_t = (r.get("prompt") or "").strip()
            chosen = (r.get("chosen") or "").strip()
            rejected = (r.get("rejected") or "").strip()
            if not prompt_t and not chosen and not rejected:
                out.append(dict(r))
                continue
            try:
                prompt = f"DPO pair. Prompt (user question): {prompt_t[:800]}\nChosen (good answer): {chosen[:1500]}\nRejected (bad answer): {rejected[:800]}\n\n{instruction}\n\nRewrite all three in the new tone. Reply JSON only: {{\"prompt\": \"...\", \"chosen\": \"...\", \"rejected\": \"...\"}}"
                raw = await llm.complete([{"role": "user", "content": prompt}], stream=False, max_tokens=1200)
                raw = (raw or "").strip()
                m = re.search(r"\{[\s\S]*\}", raw)
                if m:
                    data = json.loads(m.group(0))
                    out.append({
                        **r,
                        "prompt": (data.get("prompt") or prompt_t).strip(),
                        "chosen": (data.get("chosen") or chosen).strip(),
                        "rejected": (data.get("rejected") or rejected).strip(),
                    })
                else:
                    out.append(dict(r))
            except Exception:
                out.append(dict(r))
        elif fmt == "sharegpt":
            conv = r.get("conversations") or []
            if not isinstance(conv, list) or len(conv) == 0:
                out.append(dict(r))
                continue
            try:
                values = [t.get("value", "") for t in conv if isinstance(t, dict)]
                combined = "\n---\n".join(f"Turn {i+1}: {v[:800]}" for i, v in enumerate(values))
                prompt = f"Multi-turn conversation (rewrite each turn in the new tone; keep same structure):\n{combined[:3000]}\n\n{instruction}\n\nReply with JSON only: {{\"conversations\": [{{\"from\": \"human\", \"value\": \"...\"}}, ...]}} Same number and order of turns; 'from' must match (human/gpt)."
                raw = await llm.complete([{"role": "user", "content": prompt}], stream=False, max_tokens=2000)
                raw = (raw or "").strip()
                m = re.search(r"\{[\s\S]*\}", raw)
                if m:
                    data = json.loads(m.group(0))
                    new_conv = data.get("conversations") or []
                    if isinstance(new_conv, list) and len(new_conv) == len(conv):
                        out.append({**r, "conversations": new_conv})
                    else:
                        out.append(dict(r))
                else:
                    out.append(dict(r))
            except Exception:
                out.append(dict(r))
        else:  # pretrain or unknown text
            text = (r.get("text") or r.get("output") or r.get("content") or "").strip()
            if not text:
                out.append(dict(r))
                continue
            try:
                prompt = f"Pre-training text (rewrite in the new tone; keep facts):\n{text[:2500]}\n\n{instruction}\n\nReply with JSON only: {{\"text\": \"...\"}}"
                raw = await llm.complete([{"role": "user", "content": prompt}], stream=False, max_tokens=1200)
                raw = (raw or "").strip()
                m = re.search(r"\{[\s\S]*\}", raw)
                if m:
                    data = json.loads(m.group(0))
                    new_text = (data.get("text") or text).strip()
                    out.append({**r, "text": new_text})
                else:
                    out.append(dict(r))
            except Exception:
                out.append(dict(r))
    return out
