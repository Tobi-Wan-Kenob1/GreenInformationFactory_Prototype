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
    try:
        r = requests.get(url, headers=UA, timeout=TIMEOUT, **kw)
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

CORDIS_CANDIDATES = [
    ("FP7 projects", "https://cordis.europa.eu/data/cordis-fp7projects-csv.zip"),
    ("H2020 projects", "https://cordis.europa.eu/data/cordis-h2020projects-csv.zip"),
    ("Horizon Europe projects",
     "https://cordis.europa.eu/data/cordis-HORIZONprojects-csv.zip"),
]


def probe_cordis_bulk() -> None:
    rule("B. CORDIS bulk downloads — availability and schema")
    for label, url in CORDIS_CANDIDATES:
        print(f"\n  --- {label} ---")
        h = head(url)
        if not h or h.status_code >= 400:
            print("      unavailable at this URL")
            continue
        if label != "FP7 projects":
            # One full download is enough to establish the schema; the others
            # are only checked for existence and size.
            continue
        r = get(url)
        if not r or r.status_code != 200:
            continue
        try:
            zf = zipfile.ZipFile(io.BytesIO(r.content))
        except zipfile.BadZipFile:
            print(f"      not a zip: first bytes {r.content[:60]!r}")
            continue
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
                rows = sum(1 for _ in reader)
            print(f"\n    {member}: {rows} rows, {len(header)} columns")
            print(f"      columns: {', '.join(header[:22])}"
                  + (" …" if len(header) > 22 else ""))
            if "project" in low and "organi" not in low:
                report_fields(member, header, CORDIS_PROJECT_FIELDS)
            if "organi" in low:
                report_fields(member, header, CORDIS_ORG_FIELDS)
            if "euroscivoc" in low:
                print("      → euroSciVoc classification IS present for this programme")


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
        ("structural business statistics (sbs_ovw_act)", "sbs_ovw_act",
         {"format": "JSON", "lang": "EN", "time": "2020"}),
    ]
    for label, dataset, params in checks:
        print(f"\n  --- {label} ---")
        r = get(f"{base}/{dataset}", params=params)
        if not r or r.status_code != 200:
            continue
        try:
            payload = r.json()
        except ValueError:
            print(f"      non-JSON: {r.text[:160]!r}")
            continue
        dims = list((payload.get("dimension") or {}).keys())
        values = payload.get("value") or {}
        print(f"      JSON-stat OK: {len(values)} value(s), dimensions: {', '.join(dims)}")


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
    print("  searching the catalogue for an ETS/EUTL dataset…")
    r = get("https://data.europa.eu/api/hub/search/search",
            params={"q": "EU Emissions Trading System EUTL verified emissions",
                    "limit": 5, "filter": "dataset"})
    if r and r.status_code == 200:
        try:
            results = (r.json().get("result") or {}).get("results") or []
        except ValueError:
            results = []
        for ds in results:
            title = ds.get("title")
            if isinstance(title, dict):
                title = title.get("en") or next(iter(title.values()), "?")
            print(f"    • {str(title)[:88]}")
            for res in (ds.get("distributions") or [])[:3]:
                dl = res.get("download_url") or res.get("downloadUrl") or []
                dl = dl[0] if isinstance(dl, list) and dl else dl
                if dl:
                    print(f"        {str(dl)[:100]}")
    for label, url in [
        ("EEA datahub (ETS)", "https://www.eea.europa.eu/en/datahub/datahubitem-view/"
                              "98f04097-26de-4fca-83ee-5d6a4b1e5c6a"),
        ("EUTL public site", "https://ec.europa.eu/clima/ets/"),
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
