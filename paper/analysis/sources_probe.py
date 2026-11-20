#!/usr/bin/env python3
"""Two checks that both need the open internet.

A. What the routine-act filter does to the real policy corpus — counts with it
   off and on, and what requiring EuroVoc descriptors would additionally cost.
   The filter is a judgement about what counts as policy, so its effect belongs
   in the record as a measured number rather than an assurance.

B. Whether a list of candidate data sources is actually reachable and in a
   usable shape. "Available" here means an HTTP request succeeds and returns
   something machine-readable; it does not mean the licence permits reuse, which
   no request can tell us.

Usage:  python3 sources_probe.py [A|B]
"""
from __future__ import annotations

import csv
import io
import json
import sys
from typing import Any, Dict, List, Optional, Tuple

import requests

TIMEOUT = 90
UA = {"User-Agent": "GreenInformationFactory-source-probe/1.0 (research)"}

# --- B: the candidate list -------------------------------------------------
# Each entry is (theme, name, url, kind). `kind` says what a successful answer
# should look like, so a 200 serving a JavaScript shell is not mistaken for data:
#   api   — expected to return JSON/CSV/XML directly
#   bulk  — a file download (csv, xlsx, zip, parquet)
#   page  — a human page; data may exist behind it but not at this URL
SOURCES: List[Tuple[str, str, str, str]] = [
    ("policy", "OECD PINE", "https://www.oecd.org/en/data/datasets/policy-instruments-for-the-environment-pine-database.html", "page"),
    ("policy", "OECD CAPMF (SDMX)", "https://sdmx.oecd.org/public/rest/data/OECD.ENV.EPI,DSD_CAPMF@DF_CAPMF,1.0/all?format=csvfile&lastNObservations=1", "api"),
    ("policy", "OECD EPS (SDMX)", "https://sdmx.oecd.org/public/rest/data/OECD.ECO.MAD,DSD_EPS@DF_EPS,1.0/all?format=csvfile&lastNObservations=1", "api"),
    ("policy", "Climate Policy Database", "https://www.climatepolicydatabase.org/", "page"),
    ("policy", "Climate Policy Radar (HF)", "https://huggingface.co/api/datasets/ClimatePolicyRadar/all-document-text-data", "api"),
    ("policy", "Climate Policy Radar API", "https://app.climatepolicyradar.org/api/v1/searches", "api"),
    ("policy", "Climate Change Laws of the World", "https://www.climate-laws.org/", "page"),
    ("policy", "IEA policies", "https://www.iea.org/policies", "page"),
    ("policy", "IEA Global Energy Policies Hub", "https://www.iea.org/data-and-statistics/data-tools/global-energy-policies-hub", "page"),
    ("policy", "EEA PaMs", "https://pam.apps.eea.europa.eu/", "page"),
    ("policy", "Climate Policy Atlas", "https://climatepolicyatlas.org/data.html", "page"),
    ("policy", "World Bank Carbon Pricing", "https://datacatalogapi.worldbank.org/ddhxext/DatasetDownload?dataset_unique_id=0042051", "api"),
    ("policy", "UNEP Plastics Legislation Explorer", "https://leap.unep.org/knowledge/toolkits/plastic/legislation-explorer", "page"),
    ("policy", "EEA circular economy country profiles", "https://www.eea.europa.eu/en/topics/in-depth/circular-economy/country-profiles-on-circular-economy/circular-economy-country-profiles-2024", "page"),
    ("policy", "EEA national CE policies metric", "https://www.eea.europa.eu/en/circularity/thematic-metrics/enabling/national-circular-economy-policies", "page"),
    ("policy", "UNFCCC NDC registry", "https://unfccc.int/NDCREG", "page"),
    ("policy", "Climate Watch NDC content API", "https://www.climatewatchdata.org/api/v1/data/ndc_content?page=1&per_page=5", "api"),
    ("policy", "IEA Climate Pledges Explorer", "https://www.iea.org/data-and-statistics/data-tools/climate-pledges-explorer", "page"),
    ("policy", "CBD Online Reporting Tool", "https://ort.cbd.int/", "page"),
    ("policy", "CBD developer API", "https://api.cbd.int/api/v2013/documents?limit=3", "api"),
    ("policy", "JRC bioeconomy country dashboard", "https://knowledge-for-policy.ec.europa.eu/visualisation/bioeconomy-different-countries_en", "page"),
    ("policy", "FAO bioeconomy dashboards", "https://www.fao.org/bioeconomy/dashboards/en", "page"),
    ("policy", "EUR-Lex reuse terms", "https://eur-lex.europa.eu/content/help/content/help/data-reuse/reuse-contents-eurlex-details.html?locale=en", "page"),
    ("policy", "UNEP LEAP", "https://leap.unep.org/", "page"),
    ("policy", "InforMEA", "https://www.informea.org/", "page"),

    # Eurostat: one shape for all, so a single success proves the family.
    ("circular", "Eurostat env_ac_cur", "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/env_ac_cur?format=JSON&lang=EN&lastTimePeriod=1", "api"),
    ("circular", "Eurostat env_ac_mfa", "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/env_ac_mfa?format=JSON&lang=EN&lastTimePeriod=1&geo=DE", "api"),
    ("circular", "Eurostat env_ac_rme", "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/env_ac_rme?format=JSON&lang=EN&lastTimePeriod=1&geo=DE", "api"),
    ("circular", "Eurostat env_ac_rp", "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/env_ac_rp?format=JSON&lang=EN&lastTimePeriod=1&geo=DE", "api"),
    ("circular", "Eurostat env_wasmun", "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/env_wasmun?format=JSON&lang=EN&lastTimePeriod=1&geo=DE", "api"),
    ("circular", "Eurostat env_wasgen", "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/env_wasgen?format=JSON&lang=EN&lastTimePeriod=1&geo=DE", "api"),
    ("circular", "Eurostat env_wastrt", "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/env_wastrt?format=JSON&lang=EN&lastTimePeriod=1&geo=DE", "api"),
    ("circular", "Eurostat env_waspac", "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/env_waspac?format=JSON&lang=EN&lastTimePeriod=1&geo=DE", "api"),
    ("circular", "Eurostat env_waspacr", "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/env_waspacr?format=JSON&lang=EN&lastTimePeriod=1&geo=DE", "api"),
    ("circular", "Eurostat env_waselee", "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/env_waselee?format=JSON&lang=EN&lastTimePeriod=1&geo=DE", "api"),
    ("circular", "Eurostat cei_cie011", "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/cei_cie011?format=JSON&lang=EN&lastTimePeriod=1&geo=DE", "api"),
    ("circular", "Eurostat env_egss_emp", "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/env_egss_emp?format=JSON&lang=EN&lastTimePeriod=1&geo=DE", "api"),
    ("circular", "Eurostat env_egss_mon", "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/env_egss_mon?format=JSON&lang=EN&lastTimePeriod=1&geo=DE", "api"),
    ("circular", "UNEP CE indicators workbook", "https://wedocs.unep.org/items/119697bc-0a4e-48d3-937d-5b6843b6cee1", "page"),
    ("circular", "UN IRP material flows", "https://www.resourcepanel.org/global-material-flows-database", "page"),
    ("circular", "EEA circularity metrics lab", "https://www.eea.europa.eu/en/circularity", "page"),

    ("bioeconomy", "EU Bioeconomy Monitoring System", "https://knowledge-for-policy.ec.europa.eu/bioeconomy/monitoring_en", "page"),
    ("bioeconomy", "JRC jobs and wealth dataset", "https://data.jrc.ec.europa.eu/dataset/7d7d5481-2d02-4b36-8e79-697b04fa4278", "page"),
    ("bioeconomy", "JRC DataM bioeconomy area", "https://datam.jrc.ec.europa.eu/datam/area/BIOECONOMY", "page"),
    ("bioeconomy", "JRC national strategies dataset", "https://data.europa.eu/data/datasets/990dcbce-11c8-44f4-a6f4-af7339c9b4ae", "page"),
    ("bioeconomy", "FAOSTAT bulk (QCL)", "https://bulks-faostat.fao.org/production/Production_Crops_Livestock_E_All_Data_(Normalized).zip", "bulk"),
    ("bioeconomy", "FAO FRA data", "https://fra-data.fao.org/", "page"),
    ("bioeconomy", "Eurostat apro_cpsh1", "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/apro_cpsh1?format=JSON&lang=EN&lastTimePeriod=1&geo=DE", "api"),
    ("bioeconomy", "UNCTAD biotrade", "https://unctadstat.unctad.org/EN/Biotrade.html", "page"),
    ("bioeconomy", "UN Comtrade", "https://comtradeplus.un.org/", "page"),
]


def classify(resp: Optional[requests.Response], kind: str) -> str:
    """What the answer is actually worth, beyond the status code."""
    if resp is None:
        return "unreachable"
    if resp.status_code >= 400:
        return f"http_{resp.status_code}"
    ctype = (resp.headers.get("content-type") or "").split(";")[0].lower()
    machine = ("json" in ctype or "csv" in ctype or "xml" in ctype
               or "sdmx" in ctype or "zip" in ctype or "excel" in ctype
               or "spreadsheet" in ctype or "octet-stream" in ctype
               or "parquet" in ctype)
    if kind in ("api", "bulk"):
        return f"ok ({ctype})" if machine else f"HTML not data ({ctype})"
    return f"page ok ({ctype})" if "html" in ctype else f"ok ({ctype})"


def probe_sources() -> None:
    print(f"\n{'=' * 78}\nB. candidate sources: reachable, and in a usable shape?\n{'=' * 78}")
    by_theme: Dict[str, List[str]] = {}
    for theme, name, url, kind in SOURCES:
        try:
            resp = requests.get(url, headers=UA, timeout=TIMEOUT,
                                stream=True, allow_redirects=True)
            # Read a little, so a streaming endpoint is not judged on headers
            # alone, then close without pulling a whole bulk file.
            head = resp.raw.read(2048, decode_content=True) or b""
            verdict = classify(resp, kind)
            size = resp.headers.get("content-length") or "?"
            resp.close()
        except Exception as exc:                  # noqa: BLE001 - reported
            head, verdict, size = b"", f"unreachable ({type(exc).__name__})", "?"

        note = ""
        text = head.decode("utf-8", errors="replace")
        if "login" in text.lower()[:400] or "sign in" in text.lower()[:400]:
            note = "  [looks like a login wall]"
        if kind == "api" and verdict.startswith("ok") and text.strip().startswith("<"):
            note = "  [markup where data expected]"
        print(f"  {name[:38]:40s} {kind:5s} {verdict[:38]:40s} {size:>10s}{note}")
        by_theme.setdefault(theme, []).append(verdict)

    print("\n  summary by theme:")
    for theme, verdicts in by_theme.items():
        ok = sum(1 for v in verdicts if v.startswith(("ok", "page ok")))
        print(f"    {theme:12s} {ok}/{len(verdicts)} answered usefully")


def probe_filter() -> None:
    print(f"\n{'=' * 78}\nA. what the routine-act filter does to the policy corpus\n{'=' * 78}")
    from gif import finder_data as fd

    keywords = fd.load_snapshot_keywords()
    print(f"  keywords: {', '.join(keywords)}")
    window = ("1990-01-01", "2009-12-31")

    for label, kwargs in (
        ("unfiltered (as first frozen)", {"exclude_routine": False}),
        ("routine acts excluded", {"exclude_routine": True}),
        ("routine excluded + >=2 EuroVoc descriptors",
         {"exclude_routine": True, "min_subjects": 2}),
        ("routine excluded + >=4 EuroVoc descriptors",
         {"exclude_routine": True, "min_subjects": 4}),
    ):
        report: Dict[str, Any] = {}
        docs = fd.fetch_policies(keywords, since=window[0], until=window[1],
                                 report_out=report, **kwargs)
        dates = sorted(d["date"] for d in docs if d.get("date"))
        routine_left = sum(1 for d in docs if fd.is_routine_act(d.get("title")))
        subj = sorted(len(d.get("subjects") or []) for d in docs)
        median = subj[len(subj) // 2] if subj else 0
        print(f"\n  {label}")
        print(f"    {len(docs)} acts, {dates[0] if dates else '?'} .. "
              f"{dates[-1] if dates else '?'}")
        print(f"    routine titles still present: {routine_left}")
        print(f"    EuroVoc descriptors per act: median {median}, "
              f"none on {sum(1 for s in subj if s == 0)}")
        print(f"    dropped as thinly described: {report.get('dropped_thin', 0)}")
        for doc in docs[:6]:
            print(f"      - {doc.get('date')} {str(doc.get('title'))[:88]}")


def main() -> int:
    which = (sys.argv[1].upper() if len(sys.argv) > 1 else "AB")
    if "A" in which:
        probe_filter()
    if "B" in which:
        probe_sources()
    return 0


if __name__ == "__main__":
    sys.exit(main())
