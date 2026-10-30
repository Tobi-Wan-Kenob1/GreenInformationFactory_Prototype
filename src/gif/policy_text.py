"""Give EU acts some text to search.

A policy document in the finder carries its title and its EuroVoc descriptors
and nothing else — a few dozen words. A funded project carries its objective.
That asymmetry is not cosmetic: when the benchmark corpus was first frozen,
ten query terms drawn from the project's own literature codebook matched 679
projects and essentially no acts, because there was almost no act text for them
to match. Anything that compares the two corpora — which is the whole point of
a tool about bridging policy and funding — is measuring the metadata, not the
policy.

CELLAR serves the act itself by CELEX, so this fetches it and keeps an excerpt.
The excerpt is deliberately short: the opening recitals say what an act is for,
and the operative articles that follow are long, repetitive and far less
discriminating.

Enrichment is best-effort by design. Old acts exist only as scanned PDFs, some
have no English expression, and CELLAR answers 404 for a few CELEX numbers that
SPARQL hands out. A document that cannot be enriched keeps the summary it had,
and the caller is told how many were enriched — a corpus silently enriched for
a third of its documents would be worse than one not enriched at all, because
the thin third would look like an absence of topic rather than an absence of
text.
"""
from __future__ import annotations

import html
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests

CELLAR_CELEX = "http://publications.europa.eu/resource/celex/{celex}"

#: Characters of act text kept per document.
DEFAULT_EXCERPT = 600

#: Stop reading a response after this much. Some acts run to megabytes and the
#: excerpt comes from the opening, so the rest is downloaded for nothing.
MAX_BYTES = 2_000_000

TIMEOUT = 60

_SCRIPTISH = re.compile(r"<(script|style|head)\b.*?</\1>", re.I | re.S)
_COMMENT = re.compile(r"<!--.*?-->", re.S)
_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")

#: Boilerplate that opens many EUR-Lex HTML renderings and says nothing about
#: the act's subject. Removed from the front of the excerpt only.
_PREAMBLE = re.compile(
    r"^\s*(avis\s+juridique\s+important|important\s+legal\s+notice)\b.*?(?=\b(commission|council|"
    r"regulation|directive|decision|the\s+european)\b)", re.I | re.S)


def extract_text(markup: str, limit: int = DEFAULT_EXCERPT) -> str:
    """Readable text from an HTML/XML act, trimmed to ``limit`` characters."""
    text = _SCRIPTISH.sub(" ", markup)
    text = _COMMENT.sub(" ", text)
    text = _TAG.sub(" ", text)
    text = html.unescape(text)
    text = _WS.sub(" ", text).strip()
    text = _PREAMBLE.sub("", text).strip()
    return text[:limit]


def fetch_text(celex: str, excerpt: int = DEFAULT_EXCERPT,
               timeout: int = TIMEOUT) -> Tuple[Optional[str], str]:
    """Fetch one act's text by CELEX. Returns ``(excerpt, status)``.

    Status is one of ``ok``, ``empty`` (served, but no readable text — typically
    a scanned PDF), ``http_<code>`` or ``error_<type>``. It is reported rather
    than raised because a handful of unavailable acts is normal and must not
    stop a corpus being built.
    """
    url = CELLAR_CELEX.format(celex=celex)
    try:
        resp = requests.get(
            url, timeout=timeout, stream=True,
            headers={"Accept": "text/html, application/xhtml+xml, text/plain",
                     "Accept-Language": "eng"})
    except Exception as exc:                      # noqa: BLE001 - reported
        return None, f"error_{type(exc).__name__}"

    try:
        if resp.status_code >= 400:
            return None, f"http_{resp.status_code}"
        ctype = (resp.headers.get("content-type") or "").lower()
        if "pdf" in ctype or "image" in ctype:
            # Nothing to read without OCR, which is out of scope here.
            return None, "empty"
        raw = resp.raw.read(MAX_BYTES, decode_content=True) or b""
        markup = raw.decode(resp.encoding or "utf-8", errors="replace")
    except Exception as exc:                      # noqa: BLE001 - reported
        return None, f"error_{type(exc).__name__}"
    finally:
        resp.close()

    text = extract_text(markup, excerpt)
    return (text, "ok") if text else (None, "empty")


def enrich_policies(docs: Iterable[Dict[str, Any]],
                    excerpt: int = DEFAULT_EXCERPT,
                    limit: Optional[int] = None,
                    timeout: int = TIMEOUT) -> Dict[str, Any]:
    """Add an act-text excerpt to each policy document, in place.

    The EuroVoc descriptors are kept and the excerpt appended, so enrichment
    only ever adds searchable text. Each document records what happened, so a
    corpus can say how much of its policy side is actually readable.
    """
    docs = list(docs)
    statuses: Dict[str, int] = {}
    enriched = 0
    for index, doc in enumerate(docs):
        if limit is not None and index >= limit:
            doc["textStatus"] = "skipped"
            statuses["skipped"] = statuses.get("skipped", 0) + 1
            continue
        celex = str(doc.get("id") or "").removeprefix("p:")
        if not celex or celex.startswith("http"):
            doc["textStatus"] = "no_celex"
            statuses["no_celex"] = statuses.get("no_celex", 0) + 1
            continue
        text, status = fetch_text(celex, excerpt=excerpt, timeout=timeout)
        doc["textStatus"] = status
        statuses[status] = statuses.get(status, 0) + 1
        if text:
            subjects = str(doc.get("summary") or "").strip()
            doc["summary"] = f"{subjects} · {text}".strip(" ·") if subjects else text
            doc["textChars"] = len(text)
            enriched += 1
    return {"documents": len(docs), "enriched": enriched, "statuses": statuses}
