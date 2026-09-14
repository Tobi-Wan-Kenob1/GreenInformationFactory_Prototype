"""Snapshot fetcher for the Policy & Grant Finder (``docs/finder/``).

The finder web app prefers live browser calls to the EU endpoints, but falls
back to JSON snapshots under ``docs/finder/data/``. This module writes those
snapshots: it queries

* the EU Funding & Tenders search API (SEDIA) for Horizon Europe call topics,
* the Publications Office CELLAR SPARQL endpoint for EU acts (EUR-Lex),

normalises both into the document shape the app expects, and writes
``grants.json`` / ``policies.json``. Run via ``gif finder-data`` (locally or
from the ``finder-data`` GitHub Action).

Normalised document shape (kept in sync with docs/finder/api.js):
    {id, kind: 'policy'|'grant', title, summary, date, url,
     budgetEUR | None, doctype, source: 'cache'}
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import requests

from helper.utils import find_repo_root

SEDIA_URL = "https://api.tech.ec.europa.eu/search-api/prod/rest/search"
CELLAR_URL = "https://publications.europa.eu/webapi/rdf/sparql"
TIMEOUT = 60

#: Largest page the SEDIA search API will serve. Anything above this comes
#: back as ``400 … Result size limit 100mb has been reached``. The limit is on
#: the whole matched result set, not just the page, so broad multi-keyword
#: queries trip it even at this size — hence one request per keyword below.
MAX_PAGE_SIZE = 50
DEFAULT_PAGE_SIZE = 25

#: SEDIA status codes for call topics.
STATUS_FORTHCOMING, STATUS_OPEN, STATUS_CLOSED = "31094501", "31094502", "31094503"

DEFAULT_KEYWORDS = [
    "bioeconomy", "circular economy", "biomass", "just transition",
    "carbon farming", "renewable energy", "carbon capture", "soil",
]

_TAG_RE = re.compile(r"<[^>]*>")
_WS_RE = re.compile(r"\s+")


def _clean(text: Any) -> str:
    """Strip HTML tags and collapse whitespace."""
    return _WS_RE.sub(" ", _TAG_RE.sub(" ", str(text or ""))).strip()


def _first(value: Any) -> Any:
    if isinstance(value, list):
        return value[0] if value else None
    return value


# ---------------------------------------------------------------------------
# Grants (SEDIA / Funding & Tenders)
# ---------------------------------------------------------------------------

_NUM_RE = re.compile(r'"(?:budget|totalBudget|plannedOpeningBudget)"\s*:\s*"?([\d.,\s]+)"?')


def extract_budget_eur(meta: Dict[str, Any]) -> Optional[int]:
    """Best-effort numeric EUR budget from SEDIA's assorted metadata fields."""
    candidates: List[Any] = []
    for key in ("budget", "cftEstimatedTotalProcedureValue"):
        v = _first(meta.get(key))
        if v is not None:
            candidates.append(v)
    overview = _first(meta.get("budgetOverview")) or _first(meta.get("budgetOverviewJSONItem"))
    if isinstance(overview, str) and "{" in overview:
        candidates.extend(_NUM_RE.findall(overview))
    for cand in candidates:
        digits = re.sub(r"[^\d.]", "", str(cand))
        try:
            value = float(digits)
        except ValueError:
            continue
        if value > 1000:
            return int(round(value))
    return None


def normalize_grant(result: Dict[str, Any]) -> Dict[str, Any]:
    """SEDIA search result → finder document."""
    meta = result.get("metadata") or {}
    identifier = _first(meta.get("identifier")) or result.get("reference") or result.get("url") or ""
    date_raw = str(_first(meta.get("startDate")) or _first(meta.get("publicationDateLong")) or "")
    return {
        "id": f"g:{identifier}",
        "kind": "grant",
        "title": _clean(_first(meta.get("title")) or result.get("title") or identifier),
        "summary": _clean(_first(meta.get("description")) or result.get("summary")
                          or result.get("content") or "")[:600],
        "date": date_raw[:10] or None,
        "url": ("https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/"
                f"opportunities/topic-details/{str(identifier).lower()}"),
        "budgetEUR": extract_budget_eur(meta),
        "doctype": "Tender" if _first(meta.get("type")) == "2" else "Call topic",
        "source": "cache",
    }


def _sedia_search(text: str, page_size: int, page: int,
                  statuses: List[str]) -> List[Dict[str, Any]]:
    """One SEDIA search request. Raises with the API's own message on error.

    The payload must be form-urlencoded — multipart bodies make the API answer
    ``500 An internal error occurred``.
    """
    query = {"bool": {"must": [
        {"terms": {"type": ["1"]}},
        {"terms": {"status": statuses}},
    ]}}
    resp = requests.post(
        SEDIA_URL,
        params={"apiKey": "SEDIA", "text": text,
                "pageSize": str(page_size), "pageNumber": str(page)},
        data={"query": json.dumps(query),
              "languages": json.dumps(["en"]),
              "sort": json.dumps({"field": "sortStatus", "order": "DESC"})},
        timeout=TIMEOUT,
    )
    if resp.status_code >= 400:
        # Surface the API's explanation, not just the status code.
        raise RuntimeError(f"SEDIA HTTP {resp.status_code}: {resp.text[:200]}")
    return resp.json().get("results") or []


def fetch_grants(keywords: Iterable[str], page_size: int = DEFAULT_PAGE_SIZE,
                 pages: int = 1, include_closed: bool = True) -> List[Dict[str, Any]]:
    """Query SEDIA for grant call topics matching the keywords.

    One request **per keyword** rather than a single ``OR`` query: the API
    enforces a 100 MB limit on the whole matched result set, and a broad
    multi-keyword query exceeds it (``400 … Result size limit 100mb has been
    reached``) regardless of page size. Per-keyword queries stay well inside
    the limit and let one bad keyword fail without losing the rest.
    """
    page_size = min(page_size, MAX_PAGE_SIZE)
    statuses = [STATUS_FORTHCOMING, STATUS_OPEN]
    if include_closed:
        statuses.append(STATUS_CLOSED)

    docs: List[Dict[str, Any]] = []
    seen: set = set()
    failures: List[str] = []
    keywords = list(keywords)

    for keyword in keywords:
        for page in range(1, pages + 1):
            try:
                results = _sedia_search(f'"{keyword}"', page_size, page, statuses)
            except Exception as exc:                  # noqa: BLE001 - collected below
                failures.append(f"{keyword}: {exc}")
                break
            for r in results:
                doc = normalize_grant(r)
                if doc["id"] not in seen:
                    seen.add(doc["id"])
                    doc["matchedKeyword"] = keyword
                    docs.append(doc)
            if len(results) < page_size:
                break

    if failures and not docs:
        raise RuntimeError("every keyword query failed — " + "; ".join(failures))
    if failures:
        print(f"  warning: {len(failures)}/{len(keywords)} keyword queries failed: "
              + "; ".join(failures))
    return docs


# ---------------------------------------------------------------------------
# Policies (EUR-Lex via CELLAR SPARQL)
# ---------------------------------------------------------------------------

def sparql_query(keywords: Iterable[str], since: str = "2015-01-01",
                 until: Optional[str] = None, limit: int = 150) -> str:
    filters = " || ".join(
        f'CONTAINS(LCASE(STR(?title)), "{k.lower()}")'
        for k in (re.sub(r'["\\\\]', "", k) for k in keywords)
    )
    until_filter = f'\n  FILTER(?date <= "{until}"^^xsd:date)' if until else ""
    return f"""
PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
SELECT DISTINCT ?work ?title ?date ?type ?celex WHERE {{
  ?work cdm:work_date_document ?date .
  ?work cdm:work_has_resource-type ?type .
  FILTER(?type IN (
    <http://publications.europa.eu/resource/authority/resource-type/REG>,
    <http://publications.europa.eu/resource/authority/resource-type/DIR>,
    <http://publications.europa.eu/resource/authority/resource-type/DEC>,
    <http://publications.europa.eu/resource/authority/resource-type/COM>))
  OPTIONAL {{ ?work cdm:resource_legal_id_celex ?celex . }}
  ?exp cdm:expression_belongs_to_work ?work .
  ?exp cdm:expression_uses_language <http://publications.europa.eu/resource/authority/language/ENG> .
  ?exp cdm:expression_title ?title .
  FILTER({filters})
  FILTER(?date >= "{since}"^^xsd:date){until_filter}
}} ORDER BY DESC(?date) LIMIT {limit}"""


def normalize_policy(binding: Dict[str, Any]) -> Dict[str, Any]:
    """SPARQL result binding → finder document."""
    uri = (binding.get("work") or {}).get("value", "")
    celex = (binding.get("celex") or {}).get("value")
    rtype = (binding.get("type") or {}).get("value", "")
    date_raw = str((binding.get("date") or {}).get("value", ""))
    return {
        "id": f"p:{celex or uri}",
        "kind": "policy",
        "title": _clean((binding.get("title") or {}).get("value") or uri),
        "summary": "",
        "date": date_raw[:10] or None,
        "url": (f"https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:{celex}"
                if celex else uri),
        "budgetEUR": None,
        "doctype": rtype.rsplit("/", 1)[-1] or "Act",
        "source": "cache",
    }


def fetch_policies(keywords: Iterable[str], since: str = "2015-01-01",
                   until: Optional[str] = None,
                   limit: int = 150) -> List[Dict[str, Any]]:
    """Query CELLAR for EU acts whose English title matches any keyword."""
    resp = requests.get(
        CELLAR_URL,
        params={"query": sparql_query(keywords, since=since, until=until, limit=limit),
                "format": "application/sparql-results+json"},
        headers={"Accept": "application/sparql-results+json"},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    bindings = (resp.json().get("results") or {}).get("bindings") or []
    docs: List[Dict[str, Any]] = []
    seen: set = set()
    for b in bindings:
        doc = normalize_policy(b)
        if doc["id"] not in seen:
            seen.add(doc["id"])
            docs.append(doc)
    return docs


# ---------------------------------------------------------------------------
# Snapshot writing
# ---------------------------------------------------------------------------

def load_snapshot_keywords(repo_root: Optional[Path] = None) -> List[str]:
    """Keywords from docs/finder/data/snapshot_config.json, or the defaults."""
    root = repo_root or find_repo_root()
    cfg_path = root / "docs" / "finder" / "data" / "snapshot_config.json"
    if cfg_path.exists():
        keywords = json.loads(cfg_path.read_text(encoding="utf-8")).get("keywords") or []
        if keywords:
            return [str(k) for k in keywords]
    return list(DEFAULT_KEYWORDS)


def write_snapshot(out_dir: Path, keywords: List[str],
                   grants: List[Dict[str, Any]],
                   policies: List[Dict[str, Any]],
                   skip: Optional[Iterable[str]] = None) -> Dict[str, Path]:
    """Write grants.json / policies.json in the shape the web app expects.

    Names listed in ``skip`` are left untouched, so a failed fetch cannot
    replace an existing good snapshot with an empty file.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    skip = set(skip or ())
    written: Dict[str, Path] = {}
    for name, items in (("grants", grants), ("policies", policies)):
        if name in skip:
            continue
        path = out_dir / f"{name}.json"
        payload = {"generated": stamp, "keywords": keywords, "items": items}
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n",
                        encoding="utf-8")
        written[name] = path
    return written


def build_snapshot(keywords: Optional[List[str]] = None,
                   out_dir: Optional[Path] = None,
                   since: str = "2015-01-01",
                   until: Optional[str] = None) -> Dict[str, Any]:
    """Fetch both sources and write the snapshot files. Returns a report.

    Each source is fetched independently: if one endpoint fails, the other is
    still written and the failure is reported in ``errors`` rather than
    aborting the run (a single 400 used to lose the whole snapshot).
    """
    root = find_repo_root()
    keywords = keywords or load_snapshot_keywords(root)
    out = out_dir or (root / "docs" / "finder" / "data")

    errors: Dict[str, str] = {}
    try:
        grants = fetch_grants(keywords)
    except Exception as exc:                      # noqa: BLE001 - reported, not raised
        grants, errors["grants"] = [], f"{type(exc).__name__}: {exc}"
    try:
        policies = fetch_policies(keywords, since=since, until=until)
    except Exception as exc:                      # noqa: BLE001 - reported, not raised
        policies, errors["policies"] = [], f"{type(exc).__name__}: {exc}"

    # Never overwrite a good snapshot with an empty one from a failed fetch.
    skipped = [name for name, items in (("grants", grants), ("policies", policies))
               if name in errors and (out / f"{name}.json").exists()]
    written = write_snapshot(out, keywords, grants, policies, skip=skipped)

    return {
        "keywords": keywords,
        "grants": len(grants),
        "policies": len(policies),
        "errors": errors,
        "skipped": skipped,
        "files": {k: str(v) for k, v in written.items()},
        "generated": date.today().isoformat(),
    }
