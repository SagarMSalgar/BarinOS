# Export Studio — How it works

Export Studio lets you export your BrainOS knowledge base (indexed chunks) in several formats for training, analysis, or compliance.

## Data flow

1. **Source**: The backend reads chunks from the vector store (Qdrant) for the selected namespace via a scroll API. Each record typically includes: `id`, `content`, `document_id`, `document_name`, `chunk_index`, `content_hash`, and any custom metadata.

2. **UI**: The Export Studio page (sidebar → Export Studio) loads:
   - **Records**: from `GET /api/export/records?namespace=main&limit=...`
   - **Schema**: from `GET /api/export/schema` (inferred JSON Schema for the records)

3. **Three columns**:
   - **Dataset Builder (left)**: Pick export format (Alpaca SFT, ShareGPT, OpenAI Chat, DPO pairs, Pre-training), quality filter, and deduplication. These control how the same rows are written to the file.
   - **Live Preview (center)**: Table of the first 20 rows so you can verify content before downloading.
   - **Quality Dashboard (right)**: Total record count and the JSON Schema.

4. **Download**: When you click Download JSONL / CSV / Parquet:
   - A **compliance gate** modal opens. You must check “PII scan passed” and “Legal re-check acknowledged”. This ensures exports are intentional and auditable.
   - After you click **Allow download**, the frontend sends the current records to the backend:
     - **JSONL**: `POST /api/export/jsonl` with body = records array and `format_hint` (alpaca, sharegpt, etc.). Backend serializes each record as one JSON line.
     - **CSV**: `POST /api/export/csv` with body = records. Backend flattens to CSV and returns the file.
     - **Parquet**: `POST /api/export/parquet` with body = records. Backend writes Parquet (Hugging Face–compatible) and streams it back.
   - The response is a blob; the browser triggers a file download (e.g. `brainos_export.jsonl`).

## Formats in short

- **JSONL**: One JSON object per line. Used for LLM fine-tuning (Alpaca, ShareGPT, etc.) and pre-training.
- **CSV**: Flat table for Google Sheets, Excel, or human review.
- **Parquet**: Columnar format for big data and Hugging Face Hub uploads.

## Compliance gate

Before any export, you must confirm:

- PII scan passed (no sensitive data in the export set).
- Legal / terms re-check acknowledged.

Exports are intended to be logged for audit (backend can record export events). The gate prevents accidental bulk export without compliance checks.

## Backend endpoints

| Endpoint | Purpose |
|----------|---------|
| `GET /api/export/records?namespace=&limit=` | Fetch chunk records from vector store for preview and export. |
| `GET /api/export/schema` | Return inferred JSON Schema for the record shape. |
| `POST /api/export/jsonl` | Body: list of records. Returns JSONL file (format_hint in query or body). |
| `POST /api/export/csv` | Body: list of records. Returns CSV file. |
| `POST /api/export/parquet` | Body: list of records. Returns Parquet file. |

All download responses use `Content-Disposition: attachment` so the browser offers a file save.
