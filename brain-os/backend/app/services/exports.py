"""Export formats: JSONL (Alpaca, ShareGPT, etc.), Parquet, CSV, JSON Schema. Config-driven."""
from __future__ import annotations

import json
from typing import Any, Iterator

from pydantic import BaseModel


class ExportRecord(BaseModel):
    """Single record for pre-training / SFT formats."""
    instruction: str | None = None
    input: str | None = None
    output: str | None = None
    source: str | None = None
    metadata: dict[str, Any] = {}


def to_jsonl(records: list[dict[str, Any]], format_hint: str = "alpaca") -> Iterator[str]:
    """Yield JSONL lines. format_hint: alpaca | sharegpt | openai_chat | dpo | pretrain."""
    for r in records:
        if format_hint == "alpaca":
            line = {"instruction": r.get("instruction", r.get("input", "")), "input": r.get("input", ""), "output": r.get("output", "")}
        elif format_hint == "sharegpt":
            if "conversations" in r and isinstance(r["conversations"], list):
                line = {"id": r.get("id", ""), "conversations": r["conversations"], "source_docs": r.get("source_docs", [])}
            else:
                line = {"conversations": [{"from": "human", "value": r.get("input", "")}, {"from": "gpt", "value": r.get("output", "")}]}
        elif format_hint == "openai_chat":
            line = {"messages": [{"role": "user", "content": r.get("input", "")}, {"role": "assistant", "content": r.get("output", "")}]}
        elif format_hint == "dpo":
            if "prompt" in r and "chosen" in r and "rejected" in r:
                line = {k: r[k] for k in ("prompt", "chosen", "rejected", "chosen_score", "rejected_score", "score_gap", "rejection_type", "source_url") if k in r}
            else:
                line = r
        elif format_hint == "pretrain":
            line = {
                "id": r.get("id", r.get("document_id", "")),
                "text": r.get("text", r.get("output", r.get("content", ""))),
                "source_url": r.get("source_url", r.get("source", "")),
                "domain": r.get("domain", ""),
                "language": r.get("language", "en"),
                "quality_score": r.get("quality_score"),
                "token_count": r.get("token_count"),
                "content_hash": r.get("content_hash", ""),
            }
            line = {k: v for k, v in line.items() if v is not None and (not isinstance(v, str) or v != "")}
        else:
            line = r
        yield json.dumps(line, ensure_ascii=False) + "\n"


def to_csv_rows(records: list[dict[str, Any]], columns: list[str] | None = None) -> Iterator[str]:
    cols = columns or (list(records[0].keys()) if records else [])
    yield ",".join(f'"{c}"' for c in cols) + "\n"
    for r in records:
        yield ",".join(f'"{str(r.get(c, "")).replace(chr(34), chr(34)+chr(34))}"' for c in cols) + "\n"


def to_parquet_bytes(records: list[dict[str, Any]]) -> bytes:
    """Export records as Parquet bytes (Hugging Face / pandas compatible)."""
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError:
        raise RuntimeError("Install pyarrow: pip install pyarrow")
    if not records:
        table = pa.table({})
    else:
        columns = list(records[0].keys())
        arrays = []
        for col in columns:
            values = [r.get(col) for r in records]
            arrays.append(pa.array(values))
        table = pa.table(arrays, names=columns)
    buf = pa.BufferOutputStream()
    pq.write_table(table, buf)
    return buf.getvalue().to_pybytes()


def to_json_schema(record_sample: dict[str, Any]) -> dict[str, Any]:
    """Infer a minimal JSON schema from a sample record."""
    def infer_type(v: Any) -> str:
        if v is None: return "null"
        if isinstance(v, bool): return "boolean"
        if isinstance(v, int): return "integer"
        if isinstance(v, float): return "number"
        if isinstance(v, str): return "string"
        if isinstance(v, list): return "array"
        if isinstance(v, dict): return "object"
        return "string"
    props = {}
    for k, v in record_sample.items():
        t = infer_type(v)
        props[k] = {"type": t}
        if t == "array" and v and isinstance(v, list):
            props[k]["items"] = {"type": infer_type(v[0]) if v else "string"}
    return {"type": "object", "properties": props}
