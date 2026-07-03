"""Zenodo REST-API client for FAIR ingestion.

Replaces the GitHub-Actions detour of notebook 01 with direct, scriptable
access to Zenodo: discover records in a community, resolve DOIs, and download
files with MD5 verification and a provenance run-log.

Typical use::

    from gif.zenodo import list_community_records, download_record

    for rec in list_community_records("biofairnet"):
        print(rec["doi"], rec["title"])

    download_record("10.5281/zenodo.20743706", "data/external")

or via the CLI::

    gif zenodo list --community biofairnet
    gif zenodo pull 10.5281/zenodo.20743706 --dest data/external
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

import requests

from helper.utils import find_repo_root, save_run_log

ZENODO_API = "https://zenodo.org/api"

#: Community used by the BioFairNet project.
DEFAULT_COMMUNITY = "biofairnet"

# Zenodo caps anonymous page size at 25.
_PAGE_SIZE = 25
_TIMEOUT = 60


def record_id_from_doi(doi_or_id: str) -> str:
    """Extract the numeric Zenodo record id from a DOI, URL, or bare id.

    Accepts ``10.5281/zenodo.12345``, ``https://zenodo.org/records/12345``,
    ``https://doi.org/10.5281/zenodo.12345`` or plain ``12345``.
    """
    s = str(doi_or_id).strip()
    if re.fullmatch(r"\d+", s):
        return s
    m = re.search(r"zenodo\D+(\d+)\s*$", s) or re.search(r"records?/(\d+)", s)
    if m:
        return m.group(1)
    raise ValueError(f"Cannot parse a Zenodo record id from: {doi_or_id!r}")


def get_record(doi_or_id: str, session: Optional[requests.Session] = None) -> Dict[str, Any]:
    """Fetch the full record JSON for a DOI / record id."""
    sess = session or requests.Session()
    rec_id = record_id_from_doi(doi_or_id)
    resp = sess.get(f"{ZENODO_API}/records/{rec_id}", timeout=_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def _iter_community_hits(
    community: str, session: requests.Session
) -> Iterator[Dict[str, Any]]:
    page = 1
    while True:
        resp = session.get(
            f"{ZENODO_API}/communities/{community}/records",
            params={"size": _PAGE_SIZE, "page": page, "sort": "newest"},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        hits = resp.json()["hits"]["hits"]
        if not hits:
            return
        yield from hits
        if len(hits) < _PAGE_SIZE:
            return
        page += 1


def record_summary(record: Dict[str, Any]) -> Dict[str, Any]:
    """Reduce a record JSON to the fields the pipeline cares about."""
    meta = record.get("metadata", {})
    return {
        "record_id": record.get("id"),
        "doi": record.get("doi"),
        "title": meta.get("title"),
        "publication_date": meta.get("publication_date"),
        "resource_type": (meta.get("resource_type") or {}).get("title"),
        "files": [
            {"key": f.get("key"), "size": f.get("size"), "checksum": f.get("checksum")}
            for f in record.get("files", [])
        ],
        "html": (record.get("links") or {}).get("self_html"),
    }


def list_community_records(
    community: str = DEFAULT_COMMUNITY,
    session: Optional[requests.Session] = None,
) -> List[Dict[str, Any]]:
    """List all records of a Zenodo community (newest first), summarized."""
    sess = session or requests.Session()
    return [record_summary(h) for h in _iter_community_hits(community, sess)]


def _md5(path: Path, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.md5()
    with path.open("rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def verify_checksum(path: Path, checksum: Optional[str]) -> bool:
    """Verify a file against a Zenodo checksum string (``"md5:<hex>"``).

    Returns True when the checksum matches or is absent/unsupported (in which
    case there is nothing to verify against).
    """
    if not checksum:
        return True
    algo, _, expected = checksum.partition(":")
    if algo.lower() != "md5" or not expected:
        return True  # unsupported scheme: skip rather than fail
    return _md5(Path(path)) == expected.lower()


def download_record(
    doi_or_id: str,
    dest_dir: Path | str,
    *,
    overwrite: bool = False,
    verify: bool = True,
    session: Optional[requests.Session] = None,
    log: bool = True,
) -> List[Path]:
    """Download all files of a record into ``dest_dir``.

    Skips files that already exist with a matching checksum (unless
    ``overwrite``). Verifies MD5 checksums after download and raises on
    mismatch so corrupted transfers never enter the pipeline silently.
    Writes a ``zenodo_download`` run-log for provenance when ``log`` is True.
    """
    sess = session or requests.Session()
    record = get_record(doi_or_id, session=sess)
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)

    downloaded: List[Path] = []
    skipped: List[str] = []
    for f in record.get("files", []):
        key, checksum = f["key"], f.get("checksum")
        out = dest / key
        if out.exists() and not overwrite and verify_checksum(out, checksum):
            skipped.append(key)
            downloaded.append(out)
            continue
        url = f"{ZENODO_API}/records/{record['id']}/files/{requests.utils.quote(key)}/content"
        with sess.get(url, stream=True, timeout=_TIMEOUT) as resp:
            resp.raise_for_status()
            with out.open("wb") as fh:
                for chunk in resp.iter_content(chunk_size=1024 * 256):
                    fh.write(chunk)
        if verify and not verify_checksum(out, checksum):
            out.unlink(missing_ok=True)
            raise IOError(f"Checksum mismatch for {key} from record {record['id']}")
        downloaded.append(out)

    if log:
        try:
            repo_root = find_repo_root()
            save_run_log(
                "zenodo_download",
                {
                    "doi": record.get("doi"),
                    "record_id": record.get("id"),
                    "title": record.get("metadata", {}).get("title"),
                    "dest_dir": str(dest),
                    "files": [p.name for p in downloaded],
                    "skipped_existing": skipped,
                },
                repo_root=repo_root,
            )
        except Exception as exc:  # provenance is best-effort outside a repo
            print(f"⚠️ Could not write run log: {exc}")

    return downloaded
