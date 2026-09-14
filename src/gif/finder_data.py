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
#: "Indicative budget: 188.65 Million Euros" in the free-text additionalInfos.
_INDICATIVE_RE = re.compile(
    r"budget[^0-9]{0,40}([\d]+(?:[.,][\d]+)?)\s*(million|m\b|bn|billion)?", re.I)


def _budget_year_totals(node: Any) -> List[float]:
    """Collect one total per ``budgetYearMap`` found anywhere in the structure.

    SEDIA nests the money as ``budgetOverview.budgetTopicActionMap.<id>[].
    budgetYearMap = {"2016": 188650000}``. Each map is summed over its years;
    the caller takes the largest rather than the sum of all maps, since the
    same call budget is repeated per action and would otherwise double-count.
    """
    totals: List[float] = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "budgetYearMap" and isinstance(value, dict):
                years = [v for v in value.values() if isinstance(v, (int, float))]
                if years:
                    totals.append(float(sum(years)))
            else:
                totals.extend(_budget_year_totals(value))
    elif isinstance(node, list):
        for item in node:
            totals.extend(_budget_year_totals(item))
    return totals


def extract_budget_eur(meta: Dict[str, Any]) -> Optional[int]:
    """Best-effort numeric EUR budget from SEDIA's assorted metadata fields."""
    overview = _first(meta.get("budgetOverview")) or _first(meta.get("budgetOverviewJSONItem"))
    if isinstance(overview, str) and "{" in overview:
        try:
            totals = _budget_year_totals(json.loads(overview))
        except (ValueError, TypeError):
            totals = []
        if totals:
            return int(round(max(totals)))

    candidates: List[Any] = []
    for key in ("budget", "cftEstimatedTotalProcedureValue"):
        v = _first(meta.get(key))
        if v is not None:
            candidates.append(v)
    if isinstance(overview, str):
        candidates.extend(_NUM_RE.findall(overview))
    for cand in candidates:
        digits = re.sub(r"[^\d.]", "", str(cand))
        try:
            value = float(digits)
        except ValueError:
            continue
        if value > 1000:
            return int(round(value))

    # Last resort: the free-text "Indicative budget: 188.65 Million Euros".
    infos = _clean(_first(meta.get("additionalInfos")) or "")
    match = _INDICATIVE_RE.search(infos)
    if match:
        try:
            amount = float(match.group(1).replace(",", "."))
        except ValueError:
            return None
        unit = (match.group(2) or "").lower()
        if unit.startswith(("m",)):
            amount *= 1e6
        elif unit.startswith(("b", "bn")):
            amount *= 1e9
        if amount > 1000:
            return int(round(amount))
    return None


def is_call_topic(result: Dict[str, Any]) -> bool:
    """True for grant call topics.

    The API ignores the ``type`` filter we send in the query body, so support
    FAQs and tenders arrive mixed into the results. Type 1 alone is not enough:
    some FAQ entries are indexed as type 1 too. Real call topics always carry a
    topic ``identifier`` (e.g. ``BBI-2016-S04``) and never an FAQ question.
    """
    meta = result.get("metadata") or {}
    if str(_first(meta.get("type")) or "") != "1":
        return False
    if not _first(meta.get("identifier")):
        return False
    return not _first(meta.get("esST_question"))


def normalize_grant(result: Dict[str, Any]) -> Dict[str, Any]:
    """SEDIA search result → finder document."""
    meta = result.get("metadata") or {}
    identifier = _first(meta.get("identifier")) or result.get("reference") or result.get("url") or ""
    date_raw = str(_first(meta.get("startDate"))
                   or _first(meta.get("es_SortDate"))
                   or _first(meta.get("publicationDateLong")) or "")
    deadline_raw = str(_first(meta.get("deadlineDate")) or "")

    # The description is HTML in descriptionByte; the curated keywords/tags are
    # short and topical, so they materially improve the topic analytics.
    description = _clean(_first(meta.get("description"))
                         or _first(meta.get("descriptionByte"))
                         or result.get("summary") or result.get("content") or "")
    terms = [str(t) for t in (meta.get("keywords") or []) + (meta.get("tags") or [])]
    summary = (description[:600] + (" · " + ", ".join(dict.fromkeys(terms)) if terms else "")).strip()

    return {
        "id": f"g:{identifier}",
        "kind": "grant",
        "title": _clean(_first(meta.get("title")) or result.get("title") or identifier),
        "summary": summary,
        "date": date_raw[:10] or None,
        "deadline": deadline_raw[:10] or None,
        "status": str(_first(meta.get("status")) or "") or None,
        "callId": _clean(_first(meta.get("callIdentifier")) or "") or None,
        "programmePeriod": _clean(_first(meta.get("programmePeriod")) or "") or None,
        "url": ("https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/"
                f"opportunities/topic-details/{str(identifier).lower()}"),
        "budgetEUR": extract_budget_eur(meta),
        "doctype": "Call topic",
        # Governance level of the instrument. Only EU-level sources are wired
        # up today; national and regional sources will set "national"/"regional"
        # so the UI can group and compare across levels.
        "level": "EU",
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
                if not is_call_topic(r):          # drop FAQs / tenders
                    continue
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

#: Prefixes that EU documents write solid, hyphenated or split interchangeably.
COMPOUND_PREFIXES = ("bio", "agro", "eco", "geo", "micro", "nano", "multi")


def expand_keyword(keyword: str) -> List[str]:
    """Orthographic variants of a keyword, in the spellings EU texts use.

    EUR-Lex matching is a raw substring test, so "bioeconomy" alone misses
    "bio-economy" and "bio economy". Deliberately conservative: spelling
    variants and a naive plural only, never semantic synonyms — those would
    widen recall in ways the user did not ask for.

    Kept in sync with ``expandKeyword`` in ``docs/finder/api.js``.
    """
    base = str(keyword or "").strip().lower()
    if not base:
        return []
    out: List[str] = [base]

    def add(variant: str) -> None:
        if variant and variant not in out:
            out.append(variant)

    if "-" in base:
        add(base.replace("-", " "))
        add(base.replace("-", ""))
    if " " in base:
        add(base.replace(" ", "-"))
        add(base.replace(" ", ""))
    for prefix in COMPOUND_PREFIXES:
        if base.startswith(prefix) and len(base) > len(prefix) + 3:
            add(prefix + "-" + base[len(prefix):])
            add(prefix + " " + base[len(prefix):])
    if re.search(r"[^aeiours]s$", base):
        add(base[:-1])                      # biofuels → biofuel
    elif re.search(r"[^aeiou]y$", base):
        add(base[:-1] + "ies")              # slurry → slurries
    elif not base.endswith("s"):
        add(base + "s")
    return out


def load_thesaurus(path: Optional[Path] = None) -> Dict[str, List[str]]:
    """Index ``keyword_thesaurus.json`` as normalised term → group terms.

    Mirrors ``loadThesaurus`` in ``docs/finder/api.js``. Missing file → empty
    index, i.e. spelling-only expansion.
    """
    root = find_repo_root()
    path = path or (root / "docs" / "finder" / "data" / "keyword_thesaurus.json")
    if not Path(path).exists():
        return {}
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    index: Dict[str, List[str]] = {}
    for group in payload.get("groups", []):
        terms = group.get("terms") or []
        for term in terms:
            index[_norm_term(term)] = terms
    return index


def _norm_term(term: str) -> str:
    return re.sub(r"[\s\-_]+", " ", str(term or "").lower()).strip()


def synonyms_for(keyword: str, thesaurus: Optional[Dict[str, List[str]]] = None) -> List[str]:
    """Thesaurus group of a keyword, excluding the keyword itself."""
    thesaurus = thesaurus if thesaurus is not None else load_thesaurus()
    group = thesaurus.get(_norm_term(keyword))
    if not group:
        return []
    return [t for t in group if _norm_term(t) != _norm_term(keyword)]


def expand_keywords(keywords: Iterable[str],
                    thesaurus: Optional[Dict[str, List[str]]] = None,
                    use_synonyms: bool = False) -> List[str]:
    """Flatten expand_keyword over several keywords, preserving order.

    With ``use_synonyms`` the thesaurus groups are folded in first, so plain
    wording reaches the jargon EU titles actually use.
    """
    out: List[str] = []
    for keyword in keywords:
        bases = [keyword]
        if use_synonyms:
            bases += synonyms_for(keyword, thesaurus)
        for base in bases:
            for variant in expand_keyword(base):
                if variant not in out:
                    out.append(variant)
    return out


#: Each CONTAINS is a scan, so an over-expanded query can time the endpoint out.
MAX_SPARQL_TERMS = 40


def sparql_query(keywords: Iterable[str], since: str = "2015-01-01",
                 until: Optional[str] = None, limit: int = 150,
                 use_synonyms: bool = False,
                 thesaurus: Optional[Dict[str, List[str]]] = None) -> str:
    variants = expand_keywords((re.sub(r'["\\\\]', "", k) for k in keywords),
                               thesaurus=thesaurus,
                               use_synonyms=use_synonyms)[:MAX_SPARQL_TERMS]
    filters = " || ".join(
        f'CONTAINS(LCASE(STR(?title)), "{v}")' for v in variants
    )
    until_filter = f'\n  FILTER(?date <= "{until}"^^xsd:date)' if until else ""
    # EuroVoc descriptors are the only per-act subject text CELLAR exposes —
    # there is no abstract — so they become the document's summary and feed the
    # topic analytics, which would otherwise run on the title alone.
    return f"""
PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
SELECT ?work ?title ?date ?type ?celex ?force
       (GROUP_CONCAT(DISTINCT ?subject; separator=", ") AS ?subjects) WHERE {{
  ?work cdm:work_date_document ?date .
  ?work cdm:work_has_resource-type ?type .
  FILTER(?type IN (
    <http://publications.europa.eu/resource/authority/resource-type/REG>,
    <http://publications.europa.eu/resource/authority/resource-type/DIR>,
    <http://publications.europa.eu/resource/authority/resource-type/DEC>,
    <http://publications.europa.eu/resource/authority/resource-type/COM>))
  OPTIONAL {{ ?work cdm:resource_legal_id_celex ?celex . }}
  OPTIONAL {{ ?work cdm:resource_legal_in-force ?force . }}
  OPTIONAL {{
    ?work cdm:work_is_about_concept_eurovoc ?concept .
    ?concept skos:prefLabel ?subject .
    FILTER(LANG(?subject) = "en")
  }}
  ?exp cdm:expression_belongs_to_work ?work .
  ?exp cdm:expression_uses_language <http://publications.europa.eu/resource/authority/language/ENG> .
  ?exp cdm:expression_title ?title .
  FILTER({filters})
  FILTER(?date >= "{since}"^^xsd:date){until_filter}
}} GROUP BY ?work ?title ?date ?type ?celex ?force
ORDER BY DESC(?date) LIMIT {limit}"""


def normalize_policy(binding: Dict[str, Any]) -> Dict[str, Any]:
    """SPARQL result binding → finder document."""
    uri = (binding.get("work") or {}).get("value", "")
    celex = (binding.get("celex") or {}).get("value")
    rtype = (binding.get("type") or {}).get("value", "")
    date_raw = str((binding.get("date") or {}).get("value", ""))
    subjects = _clean((binding.get("subjects") or {}).get("value") or "")
    force = str((binding.get("force") or {}).get("value") or "").lower()
    return {
        "id": f"p:{celex or uri}",
        "kind": "policy",
        "title": _clean((binding.get("title") or {}).get("value") or uri),
        # CELLAR has no abstract; the EuroVoc descriptors are the subject text.
        "summary": subjects,
        "subjects": [s for s in (x.strip() for x in subjects.split(",")) if s],
        "inForce": True if force == "true" else False if force == "false" else None,
        "date": date_raw[:10] or None,
        "url": (f"https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:{celex}"
                if celex else uri),
        "budgetEUR": None,
        "doctype": rtype.rsplit("/", 1)[-1] or "Act",
        "level": "EU",
        "source": "cache",
    }


def _cellar_query(keywords: Iterable[str], since: str, until: Optional[str],
                  limit: int) -> List[Dict[str, Any]]:
    """One CELLAR request → normalised policy documents."""
    resp = requests.get(
        CELLAR_URL,
        params={"query": sparql_query(keywords, since=since, until=until, limit=limit),
                "format": "application/sparql-results+json"},
        headers={"Accept": "application/sparql-results+json"},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    bindings = (resp.json().get("results") or {}).get("bindings") or []
    return [normalize_policy(b) for b in bindings]


def date_buckets(since: str, until: Optional[str],
                 span_years: int = 5) -> List[tuple]:
    """Split a window into (since, until) slices of at most ``span_years``."""
    start = int(str(since)[:4])
    end = int(str(until)[:4]) if until else date.today().year
    if end < start:
        end = start
    out = []
    year = start
    while year <= end:
        last = min(year + span_years - 1, end)
        out.append((f"{year}-01-01", f"{last}-12-31"))
        year = last + 1
    return out


def fetch_policies(keywords: Iterable[str], since: str = "2015-01-01",
                   until: Optional[str] = None,
                   limit: int = 150,
                   span_years: int = 5) -> List[Dict[str, Any]]:
    """Query CELLAR for EU acts whose English title matches any keyword.

    The query is ``ORDER BY DESC(date) LIMIT n``, so for a broad keyword set a
    single request returns only the most recent slice — a snapshot covering
    2000-today came back starting in 2022, silently removing the historical
    depth the benchmark window needs. Query one slice of the window at a time
    instead, so every period gets its own share of the budget.
    """
    keywords = list(keywords)
    buckets = date_buckets(since, until, span_years)
    per_bucket = max(20, limit // max(len(buckets), 1))

    docs: List[Dict[str, Any]] = []
    seen: set = set()
    failures: List[str] = []
    for b_since, b_until in buckets:
        try:
            found = _cellar_query(keywords, b_since, b_until, per_bucket)
        except Exception as exc:                  # noqa: BLE001 - collected below
            failures.append(f"{b_since[:4]}-{b_until[:4]}: {exc}")
            continue
        for doc in found:
            if doc["id"] not in seen:
                seen.add(doc["id"])
                docs.append(doc)

    if failures and not docs:
        raise RuntimeError("every CELLAR slice failed — " + "; ".join(failures))
    if failures:
        print(f"  warning: {len(failures)}/{len(buckets)} CELLAR slices failed: "
              + "; ".join(failures))
    docs.sort(key=lambda d: d.get("date") or "", reverse=True)
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
