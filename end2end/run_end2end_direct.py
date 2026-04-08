#!/usr/bin/env python3
from __future__ import annotations

import argparse
import concurrent.futures
from collections import Counter
import json
import os
import re
import sys
import unicodedata
from pathlib import Path
from typing import Dict, List, Optional

import pdfplumber

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from OCR_Extraction.extraction import organize_text
from extractor.cleaner import clean_text
from extractor.parser import parse_notice

FOOTER_CROP_HEIGHT = 84  # points
GENERIC_COMPANY_ID_BLACKLIST = {
    "au",
    "matricule fiscal",
    "siege social",
    "adresse",
    "objet",
}

STRICT_TAX_ID_NUMERIC_REGEX = re.compile(r"^\d{8}$")
STRICT_TAX_ID_MF_REGEX = re.compile(r"^\d{7,8}[A-Z]/[A-Z]/[A-Z]/\d{3}$")
STRICT_TAX_ID_MF_ALT_REGEX = re.compile(r"^\d{7,8}/[A-Z]/[A-Z]/[A-Z]/\d{3}$")

DATA_DICT_PATH = Path(__file__).resolve().parent / "data_dict.json"
ENABLE_SECTION_FILTER = os.getenv("JORT_ENABLE_SECTION_FILTER", "0").strip().lower() in {"1", "true", "yes"}
TAX_ID_STOPWORDS = {
    "fiscale": "ocr_header_fiscale",
    "fiscal": "ocr_header_fiscale",
    "societes": "ocr_header_societes",
    "societe": "ocr_header_societes",
    "poursuivant": "ocr_column_break",
    "demande": "ocr_footer_noise",
    "au": "ocr_stopword_au",
}


def _load_data_dictionary() -> dict:
    try:
        return json.loads(DATA_DICT_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


DATA_DICT = _load_data_dictionary()
DICT_FIELDS = DATA_DICT.get("fields", {})
DICT_OCR_NORMALIZATION = {
    str(k): str(v) for k, v in (DATA_DICT.get("ocr_normalization", {}) or {}).items() if str(k).strip()
}
DICT_ALIAS_TO_CANONICAL = {
    str(k): str(v) for k, v in (DATA_DICT.get("flat_alias_to_canonical", {}) or {}).items() if str(k).strip()
}
DICT_SECTIONS = DATA_DICT.get("sections", {}) or {}
DICT_SECTION_ANCHORS: List[str] = [
    str(alias).strip()
    for aliases in DICT_SECTIONS.values()
    for alias in (aliases or [])
    if str(alias).strip()
]

TAX_LABEL_ALIASES: List[str] = [
    str(alias).strip()
    for alias in (DICT_FIELDS.get("matricule_fiscal", []) or [])
    if str(alias).strip()
]
if not TAX_LABEL_ALIASES:
    TAX_LABEL_ALIASES = ["Matricule fiscal", "Matricule fiscale", "MF", "M.F", "identifiant fiscal"]

_tax_alias_pattern = "|".join(re.escape(alias) for alias in sorted(TAX_LABEL_ALIASES, key=len, reverse=True))
TAX_LABEL_REGEX = re.compile(
    rf"(?P<label>{_tax_alias_pattern})\s*[:=\-]?\s*(?P<value>[^\n\r,;]+)",
    flags=re.IGNORECASE,
)

SECTION_ANCHOR_REGEX = (
    re.compile(
        "|".join(re.escape(anchor) for anchor in sorted(DICT_SECTION_ANCHORS, key=len, reverse=True)),
        flags=re.IGNORECASE,
    )
    if DICT_SECTION_ANCHORS
    else None
)


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


def normalize_name(name: str) -> Optional[str]:
    if not name:
        return None
    normalized = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode("ascii")
    normalized = re.sub(r"[^\w\s]", " ", normalized.lower())
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized or None


def is_blacklisted_company_name(name: Optional[str]) -> bool:
    normalized = normalize_name(name or "")
    if not normalized:
        return True
    return normalized in GENERIC_COMPANY_ID_BLACKLIST


def resolve_company_id(record: dict, raw_text: str) -> str:
    _ = raw_text  # Keep signature for compatibility with call site and future fallbacks.

    tax_id = _normalize_tax_id(str(record.get("tax_id") or ""))
    if tax_id:
        return tax_id

    normalized_name = normalize_name(str(record.get("company_name") or ""))
    if not normalized_name or is_blacklisted_company_name(normalized_name):
        return "__unknown_company__"

    return normalized_name


def resolve_canonical_company_name(record: dict) -> Optional[str]:
    canonical = normalize_name(str(record.get("company_name") or ""))
    if not canonical or is_blacklisted_company_name(canonical):
        return None
    return canonical


def classify_event(text: str) -> tuple[str, Optional[str]]:
    lower = (text or "").lower()

    if "liquidation" in lower:
        return "liquidation", None

    if "constitution" in lower or "creation" in lower or "création" in lower:
        return "constitution", None

    if "augmentation de capital" in lower:
        return "modification", "capital_increase"

    if "reduction de capital" in lower or "réduction de capital" in lower:
        return "modification", "capital_decrease"

    if "transfert de siege" in lower or "transfert de siège" in lower:
        return "modification", "transfer_head_office"

    if "changement de gerant" in lower or "changement de gérant" in lower:
        return "modification", "management_change"

    return "modification", None


def _extract_first_group(pattern: str, text: str) -> Optional[str]:
    match = re.search(pattern, text, re.IGNORECASE)
    if not match:
        return None
    value = re.sub(r"\s+", " ", match.group(1)).strip(" ,.;:-")
    return value or None


def _extract_capital_pair(text: str) -> tuple[Optional[str], Optional[str]]:
    old_capital = _extract_first_group(
        r"(?:ancien\s+capital|capital\s+ancien|capital\s+ant[ée]rieur)\s*(?:[:=]|est\s+de)?\s*([^\n,;]+)",
        text,
    )
    new_capital = _extract_first_group(
        r"(?:nouveau\s+capital|capital\s+nouveau|capital\s+social)\s*(?:[:=]|est\s+de)?\s*([^\n,;]+)",
        text,
    )

    if old_capital and new_capital:
        return old_capital, new_capital

    amounts = re.findall(r"\d[\d\s\.,]*\s*(?:dinars?|dt|tnd|d)\b", text, flags=re.IGNORECASE)
    cleaned = []
    for amount in amounts:
        normalized = re.sub(r"\s+", " ", amount).strip(" ,.;:-")
        if normalized and normalized not in cleaned:
            cleaned.append(normalized)

    if not old_capital and len(cleaned) >= 2:
        old_capital = cleaned[0]
    if not new_capital and len(cleaned) >= 2:
        new_capital = cleaned[1]

    return old_capital, new_capital


def _normalize_tax_id(value: str) -> Optional[str]:
    if not value:
        return None
    normalized = value.upper().strip(" ,.;:-")
    normalized = re.sub(r"\s+", "", normalized)
    normalized = re.sub(r"[^A-Z0-9/\-]", "", normalized)
    normalized = normalized.replace("-", "/")
    return normalized or None


def apply_ocr_normalization(text: str) -> str:
    if not text or not DICT_OCR_NORMALIZATION:
        return text

    normalized_text = text
    for source, target in sorted(DICT_OCR_NORMALIZATION.items(), key=lambda item: len(item[0]), reverse=True):
        pattern = re.compile(rf"(?<!\w){re.escape(source)}(?!\w)", flags=re.IGNORECASE)
        normalized_text = pattern.sub(target, normalized_text)
    return normalized_text


def canonicalize_alias(label: Optional[str]) -> Optional[str]:
    if not label:
        return None

    folded = unicodedata.normalize("NFKD", label).encode("ascii", "ignore").decode("ascii").lower().strip()
    for alias, canonical in DICT_ALIAS_TO_CANONICAL.items():
        alias_folded = unicodedata.normalize("NFKD", alias).encode("ascii", "ignore").decode("ascii").lower().strip()
        if folded == alias_folded:
            return canonical
    return None


def section_filtered_text(text: str) -> str:
    if not text or not ENABLE_SECTION_FILTER or SECTION_ANCHOR_REGEX is None:
        return text

    snippets: List[str] = []
    window = 700
    for match in SECTION_ANCHOR_REGEX.finditer(text):
        start = max(0, match.start() - window)
        end = min(len(text), match.end() + window)
        snippets.append(text[start:end])

    if not snippets:
        return text
    return "\n\n".join(snippets)


def _is_valid_tax_id_format(candidate: str) -> bool:
    if not candidate:
        return False
    return bool(
        STRICT_TAX_ID_NUMERIC_REGEX.match(candidate)
        or STRICT_TAX_ID_MF_REGEX.match(candidate)
        or STRICT_TAX_ID_MF_ALT_REGEX.match(candidate)
    )


def extract_tax_identifier_with_metadata(text: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
    if not text:
        return None, None, None

    scoped_text = section_filtered_text(text)

    # First: prefer tax IDs found near explicit labels.
    for match in TAX_LABEL_REGEX.finditer(scoped_text):
        candidate = re.split(
            r"\b(?:rc|registre|quittance|suivant|suivante|partie|demande|produisant|acte|adresse|capital|objet|g[ée]rant|d[ée]p[ôo]t|fiscale?|soci[ée]t[ée]s?)\b",
            match.group("value"),
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0]
        tax_id = _normalize_tax_id(candidate)
        if tax_id and _is_valid_tax_id_format(tax_id):
            label = re.sub(r"\s+", " ", match.group("label")).strip(" ,.;:-")
            return tax_id, label, canonicalize_alias(label)

    # Second: strict global fallback only for Tunisian MF-like patterns.
    strict_fallbacks = [
        r"\b(\d{7,8}\s*[A-Z]\s*/\s*[A-Z]\s*/\s*[A-Z]\s*/\s*\d{3})\b",
        r"\b(\d{7,8}\s*/\s*[A-Z]\s*/\s*[A-Z]\s*/\s*[A-Z]\s*/\s*\d{3})\b",
    ]
    for pattern in strict_fallbacks:
        match = re.search(pattern, scoped_text, re.IGNORECASE)
        if not match:
            continue
        tax_id = _normalize_tax_id(match.group(1))
        if tax_id and _is_valid_tax_id_format(tax_id):
            return tax_id, None, None

    return None, None, None


def extract_tax_identifier(text: str) -> Optional[str]:
    tax_id, _, _ = extract_tax_identifier_with_metadata(text)
    return tax_id


def validate_tax_id(raw_tax_id: Optional[str]) -> tuple[Optional[str], bool, Optional[str]]:
    if raw_tax_id is None:
        return None, False, "missing"

    candidate = str(raw_tax_id).strip()
    if not candidate:
        return None, False, "missing"

    normalized = _normalize_tax_id(candidate)
    if normalized and _is_valid_tax_id_format(normalized):
        return normalized, True, None

    folded = unicodedata.normalize("NFKD", candidate).encode("ascii", "ignore").decode("ascii").lower()
    for stopword, reason in TAX_ID_STOPWORDS.items():
        if re.search(rf"\b{re.escape(stopword)}\b", folded):
            return None, False, reason
    if "partie" in folded:
        return None, False, "ocr_column_break"
    return None, False, "invalid_format"


def enrich_event_data(event_type: str, event_subtype: Optional[str], raw_text: str) -> Dict[str, object]:
    extra: Dict[str, object] = {}

    if event_type == "modification":
        if event_subtype in {"capital_increase", "capital_decrease"}:
            old_capital, new_capital = _extract_capital_pair(raw_text)
            if old_capital:
                extra["old_capital"] = old_capital
            if new_capital:
                extra["new_capital"] = new_capital

        if event_subtype == "transfer_head_office":
            old_address = _extract_first_group(r"(?:ancien\s+si[èe]ge|ancien\s+adresse)\s*(?:[:=]|est\s+au)?\s*([^\n]+)", raw_text)
            new_address = _extract_first_group(r"(?:nouveau\s+si[èe]ge|nouvelle\s+adresse|transf[ée]r[ée]\s+au)\s*(?:[:=]|est\s+au)?\s*([^\n]+)", raw_text)
            if old_address:
                extra["old_address"] = old_address
            if new_address:
                extra["new_address"] = new_address

        if event_subtype == "management_change":
            old_manager = _extract_first_group(r"(?:ancien\s+g[ée]rant|g[ée]rant\s+sortant)\s*(?:[:=]|est)?\s*([^\n,;]+)", raw_text)
            new_manager = _extract_first_group(r"(?:nouveau\s+g[ée]rant|nomm[ée]\s+g[ée]rant|d[ée]sign[ée]\s+g[ée]rant)\s*(?:[:=]|est)?\s*([^\n,;]+)", raw_text)
            if old_manager:
                extra["old_manager"] = old_manager
            if new_manager:
                extra["new_manager"] = new_manager

    if event_type == "liquidation":
        if re.search(r"liquidation\s+(amiable|volontaire)", raw_text, re.IGNORECASE):
            extra["liquidation_type"] = "voluntary"
        elif re.search(r"liquidation\s+judiciaire|tribunal", raw_text, re.IGNORECASE):
            extra["liquidation_type"] = "court"

        liquidator = _extract_first_group(
            r"(?:nomm[ée]?|d[ée]sign[ée]?)\s+(?:comme\s+)?liquidateur(?:\s+de\s+la\s+soci[ée]t[ée])?\s*([^\n,;]+)",
            raw_text,
        )
        if not liquidator:
            liquidator = _extract_first_group(r"liquidateur\s*[:\-]?\s*([^\n,;]+)", raw_text)
        if liquidator:
            extra["liquidator"] = liquidator

        decision_date = _extract_first_group(
            r"(?:acte|proc[èe]s[-\s]?verbal|assembl[ée]e)\s+(?:en\s+date\s+du|du)\s*(\d{1,2}[\/-]\d{1,2}[\/-]\d{2,4})",
            raw_text,
        )
        if decision_date:
            extra["decision_date"] = decision_date

    return extra


def record_to_event(
    record: dict,
    raw_text: str,
    event_type: str,
    event_subtype: Optional[str] = None,
) -> dict:
    data: Dict[str, object] = {}
    for key, source in (
        ("capital", "capital"),
        ("address", "address"),
        ("activity", "corporate_purpose"),
    ):
        value = record.get(source)
        if value:
            data[key] = value

    data.update(enrich_event_data(event_type, event_subtype, raw_text))

    tax_id_raw, tax_id_label_raw, tax_id_label_canonical = extract_tax_identifier_with_metadata(raw_text)
    tax_id_clean, tax_id_valid, tax_id_reject_reason = validate_tax_id(tax_id_raw)
    data["tax_id_raw"] = tax_id_raw
    data["tax_id_clean"] = tax_id_clean
    data["tax_id_valid"] = tax_id_valid
    data["tax_id_reject_reason"] = tax_id_reject_reason
    data["tax_id_label_raw"] = tax_id_label_raw
    data["tax_id_label_canonical"] = tax_id_label_canonical
    data["has_tax_id"] = tax_id_valid
    if tax_id_clean:
        data["tax_id"] = tax_id_clean

    return {
        "company_id": record.get("company_id") or resolve_company_id(record, raw_text),
        "canonical_company_name": record.get("canonical_company_name"),
        "event_type": event_type,
        "event_subtype": event_subtype,
        "date": record.get("year"),
        "data": data,
        "source": "jort",
    }


def apply_tax_id_name_postpass(events: List[Dict[str, object]]) -> None:
    # Pick the most frequent canonical company name for each tax ID.
    tax_name_counts: Dict[str, Dict[str, int]] = {}
    for event in events:
        company_id = str(event.get("company_id") or "")
        tax_id = str((event.get("data") or {}).get("tax_id") or "")
        canonical_name = normalize_name(str(event.get("canonical_company_name") or ""))
        if not tax_id or company_id != tax_id or not canonical_name:
            continue

        bucket = tax_name_counts.setdefault(tax_id, {})
        bucket[canonical_name] = bucket.get(canonical_name, 0) + 1

    tax_best_name: Dict[str, str] = {}
    for tax_id, counts in tax_name_counts.items():
        best_name = max(counts.items(), key=lambda item: item[1])[0]
        tax_best_name[tax_id] = best_name

    for event in events:
        tax_id = str((event.get("data") or {}).get("tax_id") or "")
        if tax_id in tax_best_name:
            event["canonical_company_name"] = tax_best_name[tax_id]


def build_timelines(events: list[dict]) -> dict:
    timelines: Dict[str, List[dict]] = {}

    for event in events:
        company_id = (event or {}).get("company_id")
        if not company_id:
            company_id = "__unknown_company__"
        timelines.setdefault(company_id, []).append(event)

    def _date_sort_key(event: dict) -> tuple[int, int]:
        value = (event or {}).get("date")
        if value is None or value == "":
            return (1, 0)
        try:
            return (0, int(value))
        except (TypeError, ValueError):
            return (1, 0)

    for company_id in timelines:
        timelines[company_id].sort(key=_date_sort_key)

    return timelines


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
    events: List[Dict[str, object]] = []
    notices_total = 0
    notices_constitution = 0

    for idx, notice in enumerate(notices, 1):
        notices_total += 1
        raw_notice = str(notice.get("content") or "").strip()
        if not raw_notice:
            continue

        cleaned = apply_ocr_normalization(clean_text(raw_notice))
        event_type, event_subtype = classify_event(cleaned)
        if event_type == "constitution":
            notices_constitution += 1
        legal_form = infer_legal_form(cleaned)
        ref = str(notice.get("reference_code") or f"N{idx}")

        metadata = {
            "legal_form": legal_form,
            "year": year_value,
            "issue_number": issue_number,
            "source_file": f"{pdf_path.stem}__{ref}.txt",
        }

        try:
            record = parse_notice(cleaned, metadata)
        except Exception:
            record = dict(metadata)

        tax_id_raw, tax_id_label_raw, tax_id_label_canonical = extract_tax_identifier_with_metadata(cleaned)
        tax_id_clean, tax_id_valid, _ = validate_tax_id(tax_id_raw)
        record["tax_id_raw"] = tax_id_raw
        record["tax_id"] = tax_id_clean if tax_id_valid else None
        record["tax_id_label_raw"] = tax_id_label_raw
        record["tax_id_label_canonical"] = tax_id_label_canonical
        record["company_id"] = resolve_company_id(record, cleaned)
        record["canonical_company_name"] = resolve_canonical_company_name(record)
        record["journal_reference"] = ref
        record["pdf_source"] = str(relative)

        if event_type == "constitution":
            records.append(record)

        events.append(record_to_event(record, raw_text=cleaned, event_type=event_type, event_subtype=event_subtype))

    return {
        "ok": True,
        "records": records,
        "events": events,
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
    events: List[Dict[str, object]] = []

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
    print("[INFO] Progress will be reported for every completed PDF.")

    def _consume_result(result: Dict[str, object]) -> None:
        if not result.get("ok"):
            stats["errors"] += 1
            return
        stats["pdf_processed"] += 1
        stats["notices_total"] += int(result.get("notices_total", 0))
        stats["notices_constitution"] += int(result.get("notices_constitution", 0))
        records.extend(result.get("records", []))
        events.extend(result.get("events", []))

    if max_workers == 1:
        for idx, pdf_path in enumerate(pdfs, 1):
            stats["pdf_scanned"] += 1
            try:
                result = process_pdf(pdf_path, pdf_root, direct_txt_root, notices_json_root, resume)
            except Exception:
                result = {"ok": False}
            _consume_result(result)
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

            # Show immediate liveness to avoid appearing stuck while first PDFs are processing.
            print(f"[INFO] Submitted {len(futures)} PDF tasks to worker pool.")
            for idx, future in enumerate(concurrent.futures.as_completed(futures), 1):
                stats["pdf_scanned"] += 1
                try:
                    result = future.result()
                except Exception:
                    result = {"ok": False}
                _consume_result(result)
                pdf_path = futures.get(future)
                if pdf_path is not None:
                    print(f"[PROGRESS] {idx}/{total} PDFs processed (latest={pdf_path.name})")
                else:
                    print(f"[PROGRESS] {idx}/{total} PDFs processed")

    out_json = output_root / "extracted_notices_end2end.json"
    out_json.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")

    events_out_json = output_root / "extracted_events_end2end.json"
    apply_tax_id_name_postpass(events)
    events_out_json.write_text(json.dumps(events, ensure_ascii=False, indent=2), encoding="utf-8")

    timelines = build_timelines(events)
    timelines_out_json = output_root / "company_timelines.json"
    timelines_out_json.write_text(json.dumps(timelines, ensure_ascii=False, indent=2), encoding="utf-8")

    tax_reject_reasons: Counter[str] = Counter()
    tax_extracted = 0
    tax_valid = 0
    tax_invalid = 0
    for event in events:
        data = (event or {}).get("data") or {}
        if data.get("tax_id_raw"):
            tax_extracted += 1
        if data.get("tax_id_valid"):
            tax_valid += 1
        elif data.get("tax_id_raw"):
            tax_invalid += 1
            reason = str(data.get("tax_id_reject_reason") or "unknown")
            tax_reject_reasons[reason] += 1

    stats["records_written"] = len(records)
    stats["tax_extracted"] = tax_extracted
    stats["tax_valid"] = tax_valid
    stats["tax_invalid"] = tax_invalid
    stats["tax_reject_reasons_top"] = dict(tax_reject_reasons.most_common(10))

    print(
        "[TAX_QUALITY] "
        f"extracted={tax_extracted} valid={tax_valid} invalid={tax_invalid} "
        f"top_reasons={dict(tax_reject_reasons.most_common(5))}"
    )

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
