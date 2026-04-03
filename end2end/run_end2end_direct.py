#!/usr/bin/env python3
from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional

import pdfplumber

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from OCR_Extraction.extraction import organize_text
from extractor.cleaner import clean_text
from extractor.parser import is_constitution_notice, parse_notice

FOOTER_CROP_HEIGHT = 84  # points


def find_pdfs(pdf_root: Path, year: Optional[str], limit: Optional[int]) -> List[Path]:
    search_root = pdf_root / year if year else pdf_root
    pdfs = sorted(search_root.rglob("*.pdf"))
    if limit is not None:
        return pdfs[:limit]
    return pdfs


def infer_legal_form(text: str) -> str:
    upper = text.upper()
    if re.search(r"\bSUARL\b", upper):
        return "suarl"
    if re.search(r"\bSARL\b", upper):
        return "sarl"
    if re.search(r"\bS\.?\s*A\.?\b|SOCIETE\s+ANONYME|SOCIÉTÉ\s+ANONYME|\bANONYME\b", upper):
        return "anonyme"
    return "autre"


def extract_issue_number(pdf_name: str) -> int:
    match = re.search(r"(\d+)Journal", pdf_name)
    if match:
        return int(match.group(1))
    return 0


def extract_year_from_path(pdf_path: Path) -> int:
    for part in reversed(pdf_path.parts):
        if re.fullmatch(r"20\d{2}", part):
            return int(part)
    return 0


def extract_direct_text(pdf_path: Path) -> str:
    chunks: List[str] = []
    with pdfplumber.open(pdf_path) as pdf:
        for idx, page in enumerate(pdf.pages, 1):
            width = page.width
            height = page.height
            cropped = page.crop((0, 0, width, height - FOOTER_CROP_HEIGHT))
            col_width = width / 3

            columns: List[str] = []
            for i in range(3):
                x0 = i * col_width
                x1 = (i + 1) * col_width
                col_text = cropped.crop((x0, 0, x1, cropped.height)).extract_text()
                if col_text:
                    columns.append(col_text.strip())

            if any(columns):
                page_text = "\n\n[COLUMN BREAK]\n\n".join(columns)
            else:
                page_text = cropped.extract_text() or ""

            chunks.append(f"\n--- Page {idx} ---\n{page_text}")

    return "\n".join(chunks).strip()


def process_pdf(
    pdf_path: Path,
    pdf_root: Path,
    direct_txt_root: Path,
    notices_json_root: Path,
    resume: bool,
) -> Dict[str, object]:
    year_value = extract_year_from_path(pdf_path)
    issue_number = extract_issue_number(pdf_path.name)

    relative = pdf_path.relative_to(pdf_root)
    txt_out = (direct_txt_root / relative).with_suffix(".txt")
    json_base = notices_json_root / relative
    json_out = json_base.with_name(f"{json_base.stem}_result.json")

    txt_out.parent.mkdir(parents=True, exist_ok=True)
    json_out.parent.mkdir(parents=True, exist_ok=True)

    if resume and txt_out.exists() and json_out.exists():
        organized = json.loads(json_out.read_text(encoding="utf-8"))
    else:
        extracted_text = extract_direct_text(pdf_path)
        txt_out.write_text(extracted_text, encoding="utf-8")
        organized = organize_text(extracted_text)
        json_out.write_text(json.dumps(organized, ensure_ascii=False, indent=2), encoding="utf-8")

    notices = organized.get("block1", {}).get("notices", [])
    records: List[Dict[str, object]] = []
    notices_total = 0
    notices_constitution = 0

    for idx, notice in enumerate(notices, 1):
        notices_total += 1
        raw_notice = str(notice.get("content") or "").strip()
        if not raw_notice:
            continue

        cleaned = clean_text(raw_notice)
        if not is_constitution_notice(cleaned):
            continue

        notices_constitution += 1
        legal_form = infer_legal_form(cleaned)
        ref = str(notice.get("reference_code") or f"N{idx}")

        metadata = {
            "legal_form": legal_form,
            "year": year_value,
            "issue_number": issue_number,
            "source_file": f"{pdf_path.stem}__{ref}.txt",
        }

        record = parse_notice(cleaned, metadata)
        record["journal_reference"] = ref
        record["pdf_source"] = str(relative)
        records.append(record)

    return {
        "ok": True,
        "records": records,
        "notices_total": notices_total,
        "notices_constitution": notices_constitution,
    }


def run_pipeline(
    pdf_root: Path,
    output_root: Path,
    year: Optional[str] = None,
    limit: Optional[int] = None,
    workers: int = 1,
    resume: bool = False,
) -> Dict[str, int]:
    pdfs = find_pdfs(pdf_root, year=year, limit=limit)
    if not pdfs:
        raise RuntimeError(f"No PDFs found in {pdf_root} (year={year}).")

    direct_txt_root = output_root / "direct_text"
    notices_json_root = output_root / "notices_json"
    direct_txt_root.mkdir(parents=True, exist_ok=True)
    notices_json_root.mkdir(parents=True, exist_ok=True)

    records: List[Dict[str, object]] = []

    stats = {
        "pdf_scanned": 0,
        "pdf_processed": 0,
        "notices_total": 0,
        "notices_constitution": 0,
        "records_written": 0,
        "errors": 0,
    }

    total = len(pdfs)
    max_workers = max(1, workers)
    print(f"[INFO] Starting pipeline on {total} PDFs with workers={max_workers}, resume={resume}")

    def _consume_result(result: Dict[str, object]) -> None:
        if not result.get("ok"):
            stats["errors"] += 1
            return
        stats["pdf_processed"] += 1
        stats["notices_total"] += int(result.get("notices_total", 0))
        stats["notices_constitution"] += int(result.get("notices_constitution", 0))
        records.extend(result.get("records", []))

    if max_workers == 1:
        for idx, pdf_path in enumerate(pdfs, 1):
            stats["pdf_scanned"] += 1
            try:
                result = process_pdf(pdf_path, pdf_root, direct_txt_root, notices_json_root, resume)
            except Exception:
                result = {"ok": False}
            _consume_result(result)
            if idx % 10 == 0 or idx == total:
                print(f"[PROGRESS] {idx}/{total} PDFs processed")
    else:
        with concurrent.futures.ProcessPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(
                    process_pdf,
                    pdf_path,
                    pdf_root,
                    direct_txt_root,
                    notices_json_root,
                    resume,
                ): pdf_path
                for pdf_path in pdfs
            }
            for idx, future in enumerate(concurrent.futures.as_completed(futures), 1):
                stats["pdf_scanned"] += 1
                try:
                    result = future.result()
                except Exception:
                    result = {"ok": False}
                _consume_result(result)
                if idx % 10 == 0 or idx == total:
                    print(f"[PROGRESS] {idx}/{total} PDFs processed")

    out_json = output_root / "extracted_notices_end2end.json"
    out_json.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")

    stats["records_written"] = len(records)

    summary_path = output_root / "summary_end2end.json"
    summary_path.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")

    return stats


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="End-to-end: direct PDF extraction -> notice split -> constitution field extraction"
    )
    parser.add_argument("--pdf-root", default="doc", help="Root folder containing PDFs by year")
    parser.add_argument("--output-root", default="end2end/output", help="Output folder for end-to-end artifacts")
    parser.add_argument("--year", default=None, help="Optional year filter (e.g., 2014)")
    parser.add_argument("--limit", type=int, default=None, help="Optional max number of PDFs")
    parser.add_argument(
        "--workers",
        type=int,
        default=max(1, (os.cpu_count() or 2) - 1),
        help="Parallel worker processes (default: CPU count - 1)",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Reuse existing direct text and notice JSON outputs when available",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    stats = run_pipeline(
        pdf_root=Path(args.pdf_root),
        output_root=Path(args.output_root),
        year=args.year,
        limit=args.limit,
        workers=args.workers,
        resume=args.resume,
    )
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
