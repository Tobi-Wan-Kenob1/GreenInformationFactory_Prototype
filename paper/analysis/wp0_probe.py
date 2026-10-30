#!/usr/bin/env python3
"""WP0 — data availability probe for the validation study.

Protocol §7 WP0: confirm, before anything is pre-registered, that the four
outcome data sources actually exist, are reachable without credentials, and
carry the fields the design depends on. Running this from a GitHub Actions
runner rather than a dev sandbox is deliberate — EU hosts are unreachable from
the sandbox, and a runner is an ordinary internet client.

The probe only reads. It prints a report; it writes nothing to the repo.

What each source is needed for (protocol §6):
  CORDIS    outcome uptake per topic + the Tier B sampling frame
  Eurostat  sector/region economic and social context (no ORBIS licence)
  GLEIF     entity status, i.e. survival/dissolution for Tier B attrition
  EUTL/EEA  verified installation CO2 for the environmental dimension

Usage:  python3 paper/analysis/wp0_probe.py
"""
from __future__ import annotations

import csv
import io
import json
import sys
import zipfile
from typing import Any, Dict, Iterable, List, Optional

import requests

TIMEOUT = 120
UA = {"User-Agent": "GreenInformationFactory-WP0-probe/1.0 (research; +github.com/Tobi-Wan-Kenob1)"}

# Fields the design depends on. Absence is a finding, not an error.
CORDIS_PROJECT_FIELDS = ["id", "startDate", "endDate", "ecMaxContribution",
                         "totalCost", "title", "objective"]
CORDIS_ORG_FIELDS = ["projectID", "name", "country", "activityType",
                     "ecContribution", "organisationID", "vatNumber", "SME"]


def rule(title: str) -> None:
    print(f"\n{'=' * 78}\n{title}\n{'=' * 78}")


def get(url: str, **kw) -> Optional[requests.Response]:
    headers = {**UA, **kw.pop("headers", {})}
    try:
        r = requests.get(url, headers=headers, timeout=TIMEOUT, **kw)
        print(f"  GET {url[:110]}\n      -> HTTP {r.status_code}, "
              f"{r.headers.get('content-type', '?')}, "
              f"{r.headers.get('content-length', '?')} bytes")
        return r
    except Exception as exc:                                  # noqa: BLE001
        print(f"  GET {url[:110]}\n      -> EXCEPTION {type(exc).__name__}: {exc}")
        return None


def head(url: str) -> Optional[requests.Response]:
    try:
        r = requests.head(url, headers=UA, timeout=TIMEOUT, allow_redirects=True)
        size = r.headers.get("content-length")
        mb = f"{int(size) / 1e6:.1f} MB" if size and size.isdigit() else "size unknown"
        print(f"  HEAD {url[:105]}\n       -> HTTP {r.status_code}, "
              f"{r.headers.get('content-type', '?')}, {mb}")
        return r
    except Exception as exc:                                  # noqa: BLE001
        print(f"  HEAD {url[:105]}\n       -> EXCEPTION {type(exc).__name__}: {exc}")
        return None


def report_fill(label: str, header: List[str], rows: List[List[str]],
                fields: List[str]) -> None:
    """How often a field is actually populated — a column can exist and be empty.

    This matters for the oldest programmes: the available-at-*T* rule of §4.2
    rests on `ecSignatureDate`, and a present-but-blank column would silently
    turn that rule into a guess.
    """
    idx = {c.lower(): i for i, c in enumerate(header)}
    print(f"    {label}: fill rate over {len(rows)} rows")
    for field in fields:
        i = idx.get(field.lower())
        if i is None:
            print(f"      —    {field} (absent)")
            continue
        vals = [r[i].strip() for r in rows if len(r) > i and r[i].strip()]
        pct = 100.0 * len(vals) / len(rows) if rows else 0.0
        extra = ""
        if vals and "date" in field.lower():
            extra = f", range {min(vals)[:10]} … {max(vals)[:10]}"
        print(f"      {pct:5.1f}%  {field}{extra}")


def report_fields(label: str, present: Iterable[str], wanted: List[str]) -> None:
    have = {c.lower(): c for c in present}
    print(f"    {label}: required-field check")
    for field in wanted:
        hit = have.get(field.lower())
        # tolerate near-misses like ecMaxContribution vs ec_max_contribution
        if not hit:
            squashed = field.lower().replace("_", "")
            hit = next((orig for low, orig in have.items()
                        if low.replace("_", "") == squashed), None)
        print(f"      {'OK  ' if hit else 'MISS'} {field}"
              + (f"  (as {hit!r})" if hit and hit != field else ""))


# ---------------------------------------------------------------------------
# A. discover CORDIS datasets through the official catalogue
# ---------------------------------------------------------------------------

def probe_catalogue() -> List[Dict[str, Any]]:
    """Search data.europa.eu for CORDIS datasets and list their resources."""
    rule("A. data.europa.eu catalogue — discover CORDIS datasets")
    found: List[Dict[str, Any]] = []
    url = "https://data.europa.eu/api/hub/search/search"
    r = get(url, params={"q": "CORDIS projects", "limit": 10,
                         "filter": "dataset", "showScore": "false"})
    if not r or r.status_code != 200:
        print("    catalogue search unavailable — falling back to known URL patterns")
        return found
    try:
        payload = r.json()
    except ValueError:
        print(f"    non-JSON response: {r.text[:200]!r}")
        return found

    results = (payload.get("result") or {}).get("results") or []
    print(f"    {len(results)} dataset(s) returned")
    for ds in results:
        title = ds.get("title")
        if isinstance(title, dict):
            title = title.get("en") or next(iter(title.values()), "?")
        print(f"\n    • {str(title)[:90]}")
        print(f"      id: {ds.get('id')}")
        for res in (ds.get("distributions") or [])[:6]:
            fmt = res.get("format")
            fmt = (fmt or {}).get("label") if isinstance(fmt, dict) else fmt
            access = res.get("access_url") or res.get("accessUrl") or []
            access = access[0] if isinstance(access, list) and access else access
            dl = res.get("download_url") or res.get("downloadUrl") or []
            dl = dl[0] if isinstance(dl, list) and dl else dl
            print(f"        - {str(fmt)[:12]:12s} {str(dl or access)[:95]}")
            if dl:
                found.append({"dataset": title, "format": fmt, "url": dl})
    return found


# ---------------------------------------------------------------------------
# B. CORDIS bulk files — the fields the study needs
# ---------------------------------------------------------------------------

CORDIS_BASE = "https://cordis.europa.eu/data"

# Round 1 established that CORDIS publishes every framework programme back to
# FP1 (1984), not just FP7 onward. That matters for the design: the pre-2010
# arm can be built from grant data that genuinely existed at T, instead of
# being policy-only. So FP6 is downloaded and checked in full alongside FP7 —
# it is the programme that supplies arm A1's grant corpus.
CORDIS_FULL = [                        # downloaded and read column by column
    ("FP7 projects (2007-2013)", f"{CORDIS_BASE}/cordis-fp7projects-csv.zip"),
    ("FP6 projects (2002-2006)", f"{CORDIS_BASE}/cordis-fp6projects-csv.zip"),
]
CORDIS_EXISTS = [                      # existence and size only
    ("FP5 projects (1998-2002)", f"{CORDIS_BASE}/cordis-fp5projects-csv.zip"),
    ("H2020 projects (2014-2020)", f"{CORDIS_BASE}/cordis-h2020projects-csv.zip"),
    ("Horizon Europe projects (2021-)",
     f"{CORDIS_BASE}/cordis-HORIZONprojects-csv.zip"),
]

# The field that makes the available-at-T rule of §4.2 enforceable: a project
# is known at T only once its grant agreement is signed.
CORDIS_TIMING_FIELDS = ["ecSignatureDate", "startDate", "frameworkProgramme"]


def probe_cordis_archive(label: str, url: str) -> None:
    """Download one CORDIS CSV archive and report every CSV's schema."""
    print(f"\n  --- {label} ---")
    h = head(url)
    if not h or h.status_code >= 400:
        print("      unavailable at this URL")
        return
    r = get(url)
    if not r or r.status_code != 200:
        return
    try:
        zf = zipfile.ZipFile(io.BytesIO(r.content))
    except zipfile.BadZipFile:
        print(f"      not a zip: first bytes {r.content[:60]!r}")
        return
    names = zf.namelist()
    print(f"    archive members ({len(names)}): {', '.join(names[:12])}")
    for member in names:
        low = member.lower()
        if not low.endswith(".csv"):
            continue
        if not any(k in low for k in ("project", "organization", "organisation",
                                      "euroscivoc", "topic", "legalbasis")):
            continue
        with zf.open(member) as fh:
            text = io.TextIOWrapper(fh, encoding="utf-8", errors="replace")
            reader = csv.reader(text, delimiter=";")
            try:
                header = next(reader)
            except StopIteration:
                print(f"\n    {member}: empty")
                continue
            if len(header) == 1:        # wrong delimiter guess
                text.seek(0)
                reader = csv.reader(text, delimiter=",")
                header = next(reader)
            body = list(reader)
            rows = len(body)
        print(f"\n    {member}: {rows} rows, {len(header)} columns")
        print(f"      columns: {', '.join(header[:22])}"
              + (" …" if len(header) > 22 else ""))
        if "project" in low and "organi" not in low:
            report_fields(member, header, CORDIS_PROJECT_FIELDS)
            report_fields(member, header, CORDIS_TIMING_FIELDS)
            report_fill(member, header, body,
                        CORDIS_TIMING_FIELDS + ["ecMaxContribution", "objective",
                                                "endDate"])
        if "organi" in low:
            report_fields(member, header, CORDIS_ORG_FIELDS)
            report_fill(member, header, body,
                        ["organisationID", "vatNumber", "SME", "activityType",
                         "country", "ecContribution", "nutsCode"])
        if "euroscivoc" in low:
            print("      → euroSciVoc classification IS present for this programme")


def probe_cordis_bulk() -> None:
    rule("B. CORDIS bulk downloads — availability and schema")
    for label, url in CORDIS_FULL:
        probe_cordis_archive(label, url)
    for label, url in CORDIS_EXISTS:
        print(f"\n  --- {label} ---")
        head(url)


# ---------------------------------------------------------------------------
# C. Eurostat — sector/region indicators (the ORBIS substitute)
# ---------------------------------------------------------------------------

def probe_eurostat() -> None:
    rule("C. Eurostat REST API — sector/region economic and social indicators")
    base = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data"
    checks = [
        ("regional GVA by NACE (nama_10r_3gva)", "nama_10r_3gva",
         {"format": "JSON", "lang": "EN", "geo": "DE21", "time": "2015"}),
        ("regional employment (nama_10r_3empers)", "nama_10r_3empers",
         {"format": "JSON", "lang": "EN", "geo": "DE21", "time": "2015"}),
        # Round 1 returned a well-formed envelope with zero values for
        # sbs_ovw_act at time=2020, which means the filter missed, not that the
        # dataset is empty. SBS needs an indicator and a NACE activity, and the
        # mining/agriculture activities are the ones the study uses, so ask for
        # exactly those.
        ("SBS: enterprises in mining of other minerals (sbs_ovw_act, B08)",
         "sbs_ovw_act",
         {"format": "JSON", "lang": "EN", "geo": "DE", "nace_r2": "B08",
          "indic_sbs": "ENT", "lastTimePeriod": "3"}),
        ("SBS: turnover in mining of other minerals (sbs_ovw_act, B08)",
         "sbs_ovw_act",
         {"format": "JSON", "lang": "EN", "geo": "DE", "nace_r2": "B08",
          "indic_sbs": "NETTUR", "lastTimePeriod": "3"}),
        ("SBS unfiltered, most recent period only (shape check)", "sbs_ovw_act",
         {"format": "JSON", "lang": "EN", "geo": "DE", "lastTimePeriod": "1"}),
        # Round 2 showed sbs_ovw_act carries 2022 onward only, which is no use
        # for a 2009 or 2013 baseline. The discontinued NACE Rev.2 series are
        # the ones that reach back that far; find which of them still answers.
        ("SBS historical, NACE Rev.2 national (sbs_na_sca_r2, 2009)",
         "sbs_na_sca_r2",
         {"format": "JSON", "lang": "EN", "geo": "DE", "nace_r2": "B08",
          "indic_sb": "V11110", "time": "2009"}),
        ("SBS historical, industry detail (sbs_na_ind_r2, 2009)",
         "sbs_na_ind_r2",
         {"format": "JSON", "lang": "EN", "geo": "DE", "nace_r2": "B08",
          "indic_sb": "V11110", "time": "2009"}),
        ("SBS historical, regional (sbs_r_nuts06_r2, 2009)", "sbs_r_nuts06_r2",
         {"format": "JSON", "lang": "EN", "geo": "DE2", "nace_r2": "B",
          "indic_sb": "V11110", "time": "2009"}),
        # Agriculture is outside SBS entirely (NACE A is excluded), so the
        # agricultural half of the sector scope needs its own series.
        ("Agriculture: economic accounts (aact_eaa01, 2009)", "aact_eaa01",
         {"format": "JSON", "lang": "EN", "geo": "DE", "time": "2009",
          "indic_ag": "01000", "itm_newa": "01000"}),
        ("Agriculture: farm labour force (aact_ali01, 2009)", "aact_ali01",
         {"format": "JSON", "lang": "EN", "geo": "DE", "time": "2009"}),
    ]
    for label, dataset, params in checks:
        print(f"\n  --- {label} ---")
        r = get(f"{base}/{dataset}", params=params)
        if not r or r.status_code != 200:
            if r is not None:
                print(f"      body: {r.text[:300]!r}")
            continue
        try:
            payload = r.json()
        except ValueError:
            print(f"      non-JSON: {r.text[:160]!r}")
            continue
        dims = payload.get("dimension") or {}
        values = payload.get("value") or {}
        print(f"      JSON-stat OK: {len(values)} value(s), "
              f"dimensions: {', '.join(dims.keys())}")
        if not values:
            # A zero-value envelope still carries the category lists, which say
            # what the dataset would accept. Print them so the filter can be
            # fixed rather than guessed at again.
            print("      zero values — the dataset's own categories are:")
            for name, dim in dims.items():
                cats = list(((dim.get("category") or {}).get("index") or {}).keys())
                if cats:
                    print(f"        {name}: {', '.join(cats[:14])}"
                          + (f" … ({len(cats)} total)" if len(cats) > 14 else ""))
        else:
            sample = list(values.items())[:3]
            print(f"      sample values: {sample}")


# ---------------------------------------------------------------------------
# D. GLEIF — entity status for Tier B attrition
# ---------------------------------------------------------------------------

def probe_gleif() -> None:
    rule("D. GLEIF LEI API — entity status (survival / dissolution)")
    url = "https://api.gleif.org/api/v1/lei-records"
    r = get(url, params={"filter[entity.legalAddress.country]": "DE",
                         "page[size]": 2},
            headers={**UA, "Accept": "application/vnd.api+json"})
    if not r or r.status_code != 200:
        return
    try:
        payload = r.json()
    except ValueError:
        print(f"      non-JSON: {r.text[:160]!r}")
        return
    records = payload.get("data") or []
    print(f"      {len(records)} record(s) returned")
    for rec in records[:1]:
        attrs = rec.get("attributes") or {}
        entity = attrs.get("entity") or {}
        registration = attrs.get("registration") or {}
        print(f"      sample LEI: {attrs.get('lei')}")
        print(f"        entity.legalName:      {(entity.get('legalName') or {}).get('name')}")
        print(f"        entity.status:         {entity.get('status')}   <- active/inactive")
        print(f"        registration.status:   {registration.get('status')}")
        print(f"        entity.creationDate:   {entity.get('creationDate')}")
        print("      searchable by name? testing fulltext filter…")
    r2 = get(url, params={"filter[fulltext]": "Fraunhofer", "page[size]": 1},
             headers={**UA, "Accept": "application/vnd.api+json"})
    if r2 is not None and r2.status_code == 200:
        n = len((r2.json().get("data") or []))
        print(f"      fulltext name search works ({n} hit shown) — joinable to CORDIS by name")


# ---------------------------------------------------------------------------
# E. EU ETS verified emissions
# ---------------------------------------------------------------------------

def probe_ets() -> None:
    rule("E. EU ETS / EUTL — verified installation emissions")
    # Round 1 named two plausible datasets ("Verified ETS emissions" and the
    # Union Registry extract) but printed no URL for either, because their
    # distributions carry an access_url and no download_url. Print both, and
    # the dataset id, so the right one can be identified.
    ets_candidates: List[str] = []
    print("  searching the catalogue for an ETS/EUTL dataset…")
    r = get("https://data.europa.eu/api/hub/search/search",
            params={"q": "EU Emissions Trading System EUTL verified emissions",
                    "limit": 6, "filter": "dataset"})
    if r and r.status_code == 200:
        try:
            results = (r.json().get("result") or {}).get("results") or []
        except ValueError:
            results = []
        for ds in results:
            title = ds.get("title")
            if isinstance(title, dict):
                title = title.get("en") or next(iter(title.values()), "?")
            print(f"\n    • {str(title)[:88]}")
            print(f"      id: {ds.get('id')}")
            dists = ds.get("distributions") or []
            if not dists:
                print("      (no distributions listed in the search response)")
            for res in dists[:8]:
                fmt = res.get("format")
                fmt = (fmt or {}).get("label") if isinstance(fmt, dict) else fmt
                for key in ("download_url", "downloadUrl", "access_url", "accessUrl"):
                    val = res.get(key)
                    if isinstance(val, list):
                        val = val[0] if val else None
                    if val:
                        # Printed in full: round 2 truncated exactly the URL
                        # that turned out to be the useful one.
                        print(f"        {str(fmt)[:12]:12s} {key}: {val}")
                        if "sdi.eea.europa.eu/webdav" in str(val):
                            ets_candidates.append(str(val))
                        break
    print("\n  testing the EEA Union Registry distribution(s) found above…")
    for url in ets_candidates or ["(none found)"]:
        if url.startswith("("):
            print("    no webdav distribution was advertised this time")
            break
        head(url)
    for label, url in [
        # The datahub item id used in round 1 is dead; these are the entry
        # points that do not depend on a UUID staying valid.
        ("EEA datahub, ETS search", "https://www.eea.europa.eu/en/datahub?"
                                    "size=n_20_n&q=emissions%20trading"),
        ("EUTL public site", "https://ec.europa.eu/clima/ets/"),
        ("EEA ETS data viewer (legacy bulk)",
         "https://www.eea.europa.eu/data-and-maps/data/european-union-emissions-"
         "trading-scheme-eu-ets-data-from-citl-22"),
    ]:
        print(f"\n  --- {label} ---")
        head(url)


def main() -> int:
    print("WP0 data availability probe — validation study")
    print("protocol: paper/PROTOCOL.md §6, §7")
    probe_catalogue()
    probe_cordis_bulk()
    probe_eurostat()
    probe_gleif()
    probe_ets()
    print("\n\nProbe complete. Record the findings in paper/PROTOCOL.md §6 "
          "and resolve any MISS before WP2.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
