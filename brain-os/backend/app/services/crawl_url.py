"""LLM-guided web crawler: intelligent link selection, sub-links, topic extraction, and content cleaning."""
from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import yaml

from app.core.config import load_config
from app.providers import get_llm_provider
from app.services.fetch_url import fetch_url_content


def _extract_text(html: str) -> str:
    """Strip HTML to plain text."""
    text = re.sub(r"<script[^>]*>[\s\S]*?</script>", " ", html, flags=re.I)
    text = re.sub(r"<style[^>]*>[\s\S]*?</style>", " ", text, flags=re.I)
    text = re.sub(r"<nav[^>]*>[\s\S]*?</nav>", " ", text, flags=re.I)
    text = re.sub(r"<footer[^>]*>[\s\S]*?</footer>", " ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()[:500000]


def _extract_links(html: str, base_url: str) -> list[str]:
    """Extract absolute same-origin links."""
    base = urlparse(base_url)
    netloc = base.netloc or ""
    scheme = base.scheme or "https"
    links = set()
    for m in re.finditer(r'<a\s+[^>]*href\s*=\s*["\']([^"\']+)["\']', html, re.I):
        href = m.group(1).strip().split("#")[0].strip()
        if not href or href.startswith(("mailto:", "javascript:", "data:", "tel:")):
            continue
        abs_url = urljoin(base_url, href)
        p = urlparse(abs_url)
        if p.netloc and p.netloc != netloc:
            continue
        if p.path.endswith((".pdf", ".png", ".jpg", ".jpeg", ".gif", ".zip", ".xml", ".rss")):
            continue
        links.add(abs_url)
    return list(links)


def _extract_title(html: str) -> str:
    m = re.search(r"<title[^>]*>([^<]+)</title>", html, re.I)
    return (m.group(1).strip() if m else "")[:500]


def _load_crawl_prompts(config: dict[str, Any]) -> dict[str, Any]:
    """Load crawl.yaml prompts (select_links, extract_topic, clean_content)."""
    config_dir = Path(config.get("_config_dir", Path(__file__).parent.parent.parent / "config"))
    path = config_dir / "prompts" / "crawl.yaml"
    if not path.exists():
        return {}
    with open(path) as f:
        return yaml.safe_load(f) or {}


async def _llm_select_links(
    url: str,
    title: str,
    candidate_links: list[str],
    config: dict[str, Any],
    max_pick: int = 15,
    crawl_goal: str | None = None,
) -> list[str]:
    """Use LLM to choose which links are worth crawling (content-rich, not nav/footer). Optionally prefer links matching crawl_goal."""
    if not candidate_links:
        return []
    prompts = _load_crawl_prompts(config)
    spec = prompts.get("select_links") or {}
    system = spec.get("system", "Pick URLs that have main content. One URL per line.")
    user_tpl = spec.get("user_template", "URL: {{ url }}\nLinks:\n{{ links }}\nReply with URLs only, one per line.")
    goal_hint = f"User's crawl goal (prefer links that match this): {crawl_goal}\n\n" if (crawl_goal and crawl_goal.strip()) else ""
    links_blob = "\n".join(candidate_links[:80])
    user_msg = user_tpl.replace("{{ url }}", url).replace("{{ title }}", title).replace("{{ links }}", links_blob).replace("{{ goal_hint }}", goal_hint)
    llm = get_llm_provider(config)
    try:
        out = await llm.complete(
            [{"role": "system", "content": system}, {"role": "user", "content": user_msg}],
            stream=False,
            max_tokens=800,
        )
    except Exception:
        return candidate_links[:max_pick]
    chosen = []
    candidate_set = {u.strip().lower(): u for u in candidate_links}
    for line in (out or "").strip().split("\n"):
        line = line.strip()
        u = None
        for part in line.split():
            if part.startswith("http://") or part.startswith("https://"):
                u = part.rstrip(".,)")
                break
        if not u:
            continue
        u_lower = u.lower()
        if u_lower in candidate_set and candidate_set[u_lower] not in chosen:
            chosen.append(candidate_set[u_lower])
        if len(chosen) >= max_pick:
            break
    return chosen or candidate_links[:max_pick]


async def _llm_extract_topic(title: str, snippet: str, config: dict[str, Any]) -> str:
    """Use LLM to get a short topic phrase for metadata."""
    prompts = _load_crawl_prompts(config)
    spec = prompts.get("extract_topic") or {}
    system = spec.get("system", "Extract a short topic phrase (3-8 words).")
    user_tpl = spec.get("user_template", "Title: {{ title }}\nSnippet: {{ snippet }}\nTopic:")
    user_msg = user_tpl.replace("{{ title }}", title).replace("{{ snippet }}", snippet[:1500])
    llm = get_llm_provider(config)
    try:
        out = await llm.complete(
            [{"role": "system", "content": system}, {"role": "user", "content": user_msg}],
            stream=False,
            max_tokens=50,
        )
        return (out or "").strip()[:200] or title
    except Exception:
        return title


async def _llm_worth_it(title: str, snippet: str, config: dict[str, Any]) -> tuple[int, str]:
    """Score 1-5: is this page substantive (5) or boilerplate (1)? Returns (score, reason)."""
    if len(snippet.strip()) < 100:
        return 1, "Too little text"
    prompts = _load_crawl_prompts(config)
    spec = prompts.get("worth_it") or {}
    system = spec.get("system", "Score 1-5: 1=nav/footer only, 5=substantive content. Reply: SCORE then reason.")
    user_tpl = spec.get("user_template", "Title: {{ title }}\nSnippet: {{ snippet }}\nReply: SCORE (1-5) then reason.")
    user_msg = user_tpl.replace("{{ title }}", title[:200]).replace("{{ snippet }}", snippet[:2000])
    llm = get_llm_provider(config)
    try:
        out = (await llm.complete(
            [{"role": "system", "content": system}, {"role": "user", "content": user_msg}],
            stream=False,
            max_tokens=80,
        ) or "").strip()
        score = 3
        reason = out[:100]
        for word in out.split():
            if word.isdigit() and 1 <= int(word) <= 5:
                score = int(word)
                break
        return score, reason or "No reason"
    except Exception:
        return 3, "Check skipped"


async def _llm_clean_content(raw_text: str, config: dict[str, Any]) -> str:
    """Use LLM to remove nav/boilerplate and keep main content."""
    if len(raw_text) < 500:
        return raw_text
    prompts = _load_crawl_prompts(config)
    spec = prompts.get("clean_content") or {}
    system = spec.get("system", "Output only the main article text, no nav or notices.")
    user_tpl = spec.get("user_template", "Raw text:\n{{ raw_text }}\nCleaned content:")
    user_msg = user_tpl.replace("{{ raw_text }}", raw_text[:12000])
    llm = get_llm_provider(config)
    try:
        out = await llm.complete(
            [{"role": "system", "content": system}, {"role": "user", "content": user_msg}],
            stream=False,
            max_tokens=4000,
        )
        return (out or "").strip() or raw_text
    except Exception:
        return raw_text


def _noop_progress(_msg: str) -> None:
    pass


async def crawl_url(
    seed_url: str,
    config: dict[str, Any] | None = None,
    max_depth: int = 2,
    max_pages: int = 40,
    timeout: float = 15.0,
    use_llm_links: bool = True,
    use_llm_topic: bool = True,
    use_llm_clean: bool = False,
    crawl_goal: str | None = None,
    filter_substantive: bool = True,
    progress_callback: Callable[[str], None] | None = None,
) -> list[dict[str, Any]]:
    """
    LLM-guided crawl from seed_url.
    - use_llm_links: LLM selects which sub-links to follow (content-rich, skip nav/footer).
    - use_llm_topic: LLM extracts a short topic per page for metadata.
    - use_llm_clean: LLM strips boilerplate from each page (slower).
    - progress_callback(message): optional; called with live status messages for UI.
    Returns list of {url, depth, text, title, topic, source_url} for ingestion and training.
    """
    config = config or load_config()
    report = progress_callback or _noop_progress
    parsed = urlparse(seed_url)
    base_netloc = parsed.netloc or ""
    seen: set[str] = set()
    results: list[dict[str, Any]] = []
    frontier: list[tuple[str, int]] = [(seed_url.strip(), 0)]

    while frontier and len(results) < max_pages:
        url, depth = frontier.pop(0)
        if url in seen:
            report("Skipping duplicate URL.")
            continue
        seen.add(url)
        report(f"Reading page {len(results) + 1} of up to {max_pages}… {url[:60]}{'…' if len(url) > 60 else ''}")
        try:
            html = await fetch_url_content(url, timeout=timeout)
        except Exception as e:
            report(f"Skipping (fetch failed): {url[:50]}…")
            continue
        title = _extract_title(html)
        raw_text = _extract_text(html)
        if len(raw_text) < 150:
            report("Skipping page (too little text).")
            continue
        if use_llm_clean:
            report("Extracting main content…")
            text = await _llm_clean_content(raw_text, config)
        else:
            text = raw_text
        if filter_substantive and len(text.strip()) >= 200:
            report("Checking if page is substantive…")
            score, reason = await _llm_worth_it(title, text[:2500], config)
            if score < 3:
                report(f"Skipped [{url[:50]}…]: LLM said '{reason[:80]}'.")
                continue
        topic = title
        if use_llm_topic:
            report("Extracting topic for metadata…")
            topic = await _llm_extract_topic(title, raw_text[:2000], config)
        results.append({
            "url": url,
            "depth": depth,
            "text": text,
            "title": title,
            "topic": topic,
            "source_url": url,
        })
        if depth < max_depth and len(results) + len(frontier) < max_pages:
            candidates = _extract_links(html, url)
            if candidates:
                report(f"Found {len(candidates)} child links.")
            if use_llm_links and candidates:
                report("Selecting content-rich links (LLM)…")
                next_urls = await _llm_select_links(url, title, candidates, config, max_pick=12, crawl_goal=crawl_goal)
            else:
                next_urls = candidates[:15]
            for link in next_urls:
                if link not in seen:
                    p = urlparse(link)
                    if (p.netloc or base_netloc) == base_netloc:
                        frontier.append((link, depth + 1))

    report(f"Crawl complete. {len(results)} pages ready for ingestion.")
    return results
