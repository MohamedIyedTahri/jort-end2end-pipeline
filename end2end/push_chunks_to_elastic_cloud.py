#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Iterable, List, Tuple

# Default configuration for your Elastic Cloud deployment.
DEFAULT_ES_HOST = "https://8007270842084ace97b12cc8261a9a4e.us-central1.gcp.cloud.es.io:443"
DEFAULT_BATCH_SIZE = 2000

# Data source: NDJSON files generated in upload_chunks.
DEFAULT_FILES = [
    "events_part_000",
    "events_part_001",
    "events_part_002",
    "events_part_003",
    "events_part_004",
    "timeline_events_part_000",
    "timeline_events_part_001",
    "timeline_events_part_002",
    "timeline_events_part_003",
    "timeline_events_part_004",
]


def chunked(items: List[dict], batch_size: int) -> Iterable[List[dict]]:
    for i in range(0, len(items), batch_size):
        yield items[i : i + batch_size]


def read_ndjson_docs(file_path: Path) -> List[dict]:
    docs: List[dict] = []
    with file_path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                docs.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON in {file_path.name} at line {line_no}: {exc}") from exc
    return docs


def build_bulk_payload(index_name: str, docs: List[dict]) -> bytes:
    lines: List[str] = []
    for doc in docs:
        lines.append(json.dumps({"index": {"_index": index_name}}, ensure_ascii=False))
        lines.append(json.dumps(doc, ensure_ascii=False))
    # Bulk endpoint requires newline at the end of payload.
    payload = "\n".join(lines) + "\n"
    return payload.encode("utf-8")


def post_bulk(
    es_host: str,
    api_key: str,
    payload: bytes,
    timeout: int,
    ssl_context: ssl.SSLContext,
) -> dict:
    url = f"{es_host.rstrip('/')}/_bulk"
    req = urllib.request.Request(
        url=url,
        data=payload,
        method="POST",
        headers={
            "Authorization": f"ApiKey {api_key}",
            "Content-Type": "application/x-ndjson",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout, context=ssl_context) as resp:
        body = resp.read().decode("utf-8")
        return json.loads(body)


def ingest_file(
    es_host: str,
    api_key: str,
    file_path: Path,
    index_name: str,
    batch_size: int,
    timeout: int,
    max_retries: int,
    dry_run: bool,
    ssl_context: ssl.SSLContext,
) -> Tuple[int, int]:
    docs = read_ndjson_docs(file_path)
    total_docs = len(docs)
    if total_docs == 0:
        print(f"[SKIP] {file_path.name}: no docs")
        return 0, 0

    print(f"[START] {file_path.name} -> {index_name} | docs={total_docs} | batch_size={batch_size}")

    success_docs = 0
    failed_docs = 0

    for batch_no, batch in enumerate(chunked(docs, batch_size), 1):
        if dry_run:
            success_docs += len(batch)
            if batch_no % 5 == 0 or success_docs == total_docs:
                print(f"[DRY-RUN] {file_path.name} batch={batch_no} processed={success_docs}/{total_docs}")
            continue

        payload = build_bulk_payload(index_name, batch)
        last_err: Exception | None = None

        for attempt in range(1, max_retries + 1):
            try:
                result = post_bulk(es_host, api_key, payload, timeout=timeout, ssl_context=ssl_context)
                if result.get("errors"):
                    items = result.get("items", [])
                    # Count per-item failures from bulk response.
                    batch_failures = 0
                    for item in items:
                        action = item.get("index", {})
                        status = int(action.get("status", 500))
                        if status >= 300:
                            batch_failures += 1
                    success_docs += len(batch) - batch_failures
                    failed_docs += batch_failures
                    print(
                        f"[WARN] {file_path.name} batch={batch_no} had {batch_failures} item failures "
                        f"(processed={success_docs + failed_docs}/{total_docs})"
                    )
                else:
                    success_docs += len(batch)
                    if batch_no % 5 == 0 or success_docs + failed_docs == total_docs:
                        print(f"[OK] {file_path.name} batch={batch_no} processed={success_docs + failed_docs}/{total_docs}")
                break
            except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as exc:
                last_err = exc
                if attempt == max_retries:
                    failed_docs += len(batch)
                    print(
                        f"[ERROR] {file_path.name} batch={batch_no} failed after {max_retries} attempts: {exc} "
                        f"(processed={success_docs + failed_docs}/{total_docs})"
                    )
                else:
                    backoff = min(2 ** (attempt - 1), 10)
                    print(
                        f"[RETRY] {file_path.name} batch={batch_no} attempt={attempt}/{max_retries} error={exc}; "
                        f"sleep={backoff}s"
                    )
                    time.sleep(backoff)
        if last_err is not None and success_docs + failed_docs >= total_docs:
            pass

    print(f"[DONE] {file_path.name} -> {index_name} | success={success_docs} failed={failed_docs}")
    return success_docs, failed_docs


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Bulk push NDJSON chunks to Elasticsearch Cloud")
    parser.add_argument(
        "--data-dir",
        default="end2end/output_all_years_dict/upload_chunks",
        help="Directory containing NDJSON chunk files",
    )
    parser.add_argument(
        "--host",
        default=os.getenv("ES_HOST", DEFAULT_ES_HOST),
        help="Elasticsearch host URL",
    )
    parser.add_argument(
        "--api-key",
        default=os.getenv("ES_API_KEY", ""),
        help="Elastic API key (or set ES_API_KEY env var)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=int(os.getenv("ES_BATCH_SIZE", str(DEFAULT_BATCH_SIZE))),
        help="Documents per bulk request",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=90,
        help="HTTP timeout per bulk request in seconds",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=4,
        help="Retries per batch when request fails",
    )
    parser.add_argument(
        "--insecure",
        action="store_true",
        help="Disable TLS certificate verification (only for troubleshooting)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse files and simulate batching without sending data",
    )
    parser.add_argument(
        "--files",
        nargs="*",
        default=DEFAULT_FILES,
        help="Chunk file names to ingest (index name is the same as file name)",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()

    data_dir = Path(args.data_dir)
    if not data_dir.exists() or not data_dir.is_dir():
        print(f"[FATAL] data dir not found: {data_dir}", file=sys.stderr)
        return 2

    if not args.dry_run and not args.api_key:
        print("[FATAL] Missing API key. Set ES_API_KEY or pass --api-key.", file=sys.stderr)
        return 2

    ssl_context = ssl.create_default_context()
    if args.insecure:
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

    total_success = 0
    total_failed = 0

    # Distribution logic: all documents in each file are indexed into one index
    # with the same name as that file (e.g., events_part_000 -> events_part_000).
    for file_name in args.files:
        file_path = data_dir / file_name
        if not file_path.exists():
            print(f"[WARN] file missing, skipping: {file_path}")
            continue

        success, failed = ingest_file(
            es_host=args.host,
            api_key=args.api_key,
            file_path=file_path,
            index_name=file_name,
            batch_size=args.batch_size,
            timeout=args.timeout,
            max_retries=args.max_retries,
            dry_run=args.dry_run,
            ssl_context=ssl_context,
        )
        total_success += success
        total_failed += failed

    print(f"[SUMMARY] success={total_success} failed={total_failed} dry_run={args.dry_run}")
    return 0 if total_failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
