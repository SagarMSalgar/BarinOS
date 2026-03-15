"""Extract text from PDF, DOCX, images, URLs, and voice for proactive flows (project planner, meeting summary, requirements)."""
from __future__ import annotations

import base64
import io
import logging
from typing import Any

log = logging.getLogger(__name__)


async def extract_text_from_pdf(data: bytes) -> str:
    """Extract text from PDF bytes. Returns concatenated text or empty string on failure."""
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(data))
        parts = []
        for page in reader.pages:
            t = page.extract_text()
            if t:
                parts.append(t)
        return "\n\n".join(parts) if parts else ""
    except Exception as e:
        log.warning("PDF extraction failed: %s", e)
        return ""


async def extract_text_from_docx(data: bytes) -> str:
    """Extract text from DOCX bytes."""
    try:
        from docx import Document
        doc = Document(io.BytesIO(data))
        return "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())
    except Exception as e:
        log.warning("DOCX extraction failed: %s", e)
        return ""


async def extract_text_from_image(data: bytes, config: dict[str, Any] | None = None) -> str:
    """Extract text/description from image using vision. Prefer OpenAI if available."""
    import os
    b64 = base64.standard_b64encode(data).decode("ascii")
    mime = "image/png"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        mime = "image/png"
    elif data[:2] in (b"\xff\xd8", b"\xff\xd9"):
        mime = "image/jpeg"
    elif data[:6] in (b"GIF87a", b"GIF89a"):
        mime = "image/gif"
    elif data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        mime = "image/webp"

    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        r = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Extract all text and describe the content relevant to planning, tasks, or requirements. Be concise."},
                        {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
                    ],
                }
            ],
            max_tokens=2000,
        )
        return (r.choices[0].message.content or "").strip()
    except Exception as e:
        log.warning("Image vision extraction failed: %s", e)
        return ""


async def fetch_url_content(url: str, timeout: float = 30.0) -> str:
    """Fetch URL and return text. Re-export of fetch_url.fetch_url_content."""
    from app.services.fetch_url import fetch_url_content as _fetch
    return await _fetch(url, timeout=timeout)


async def transcribe_audio(data: bytes, filename: str | None = None) -> str:
    """Transcribe audio using OpenAI Whisper. filename hint (e.g. .mp4, .webm) can help."""
    import os
    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        f = io.BytesIO(data)
        f.name = filename or "audio.webm"
        r = await client.audio.transcriptions.create(model="whisper-1", file=f)
        return (r.text or "").strip()
    except Exception as e:
        log.warning("Whisper transcription failed: %s", e)
        return ""


async def extract_from_slack_file(
    file_url: str,
    file_type: str,
    bot_token: str,
    config: dict[str, Any] | None = None,
) -> str:
    """Download a Slack file and extract text. file_type: pdf, doc, docx, image (png/jpg/gif/webp), or audio."""
    import httpx
    async with httpx.AsyncClient() as client:
        r = await client.get(file_url, headers={"Authorization": f"Bearer {bot_token}"}, timeout=60.0)
        r.raise_for_status()
        data = r.content

    kind = (file_type or "").lower()
    if "pdf" in kind:
        return await extract_text_from_pdf(data)
    if "docx" in kind or "document" in kind and "docx" in (file_url or "").lower():
        return await extract_text_from_docx(data)
    if "doc" in kind and "docx" not in kind:
        return await extract_text_from_docx(data)  # try anyway
    if kind in ("png", "jpg", "jpeg", "gif", "webp") or "image" in kind:
        return await extract_text_from_image(data, config)
    if kind in ("mp3", "mp4", "webm", "m4a", "ogg", "wav") or "audio" in kind:
        return await transcribe_audio(data, filename=f"audio.{kind.split('/')[-1] if '/' in kind else kind}")
    # Plain text
    try:
        return data.decode("utf-8", errors="replace").strip()
    except Exception:
        return ""
