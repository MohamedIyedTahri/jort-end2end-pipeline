#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Tuple

UNKNOWN_COMPANY_ID = "__unknown_company__"
SUSPICIOUS_COMPANY_ID = "__suspicious__"

TAX_ID_NUMERIC_REGEX = re.compile(r"^\d{8}$")
TAX_ID_MF_REGEX = re.compile(r"^\d{7,8}[A-Z]?/[A-Z]/[A-Z]/[A-Z]/\d{3}$")

LEGAL_LEAK_TERMS = {
    "column",
    "break",
    "produisant",
    "demande",
    "proces",
    "verbal",
    "assemblee",
    "articles",
    "article",
    "dispositions",
    "capital",
    "denomination",
    "present",
    "cause",
    "causes",
}

LEAK_TRIGGER_TERMS = {
    "column",
    "break",
    "produisant",
    "demande",
    "article",
    "articles",
    "dispositions",
    "proces",
    "verbal",
    "augmentation",
    "changement",
}

EXPLICIT_SUSPICIOUS_VALUES = {
    "column break",
    "societes",
    "pour le produisant cette demande",
    "le produisant cette demande",
    "cette demande enoncera les causes",
    "augmentation de capital",
    "changement de la denomination",
}


def normalize_spaces(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def normalize_company_id(value: object) -> str:
    if value is None:
        return UNKNOWN_COMPANY_ID

    raw = normalize_spaces(str(value))
    if not raw:
        return UNKNOWN_COMPANY_ID

    lowered = raw.lower()
    if lowered in {"none", "null", "nan", "n/a", "na", "unknown"}:
        return UNKNOWN_COMPANY_ID

    # Normalize separators and casing for stable matching/indexing.
    normalized = raw.replace("\\", "/")
    normalized = re.sub(r"\s*/\s*", "/", normalized)
    normalized = re.sub(r"/{2,}", "/", normalized)
    normalized = normalize_spaces(normalized)

    if not normalized:
        return UNKNOWN_COMPANY_ID

    if normalized == UNKNOWN_COMPANY_ID:
        return UNKNOWN_COMPANY_ID

    return normalized.upper()


def looks_like_tax_id(company_id: str) -> bool:
    if not company_id:
        return False
    return bool(TAX_ID_NUMERIC_REGEX.match(company_id) or TAX_ID_MF_REGEX.match(company_id))


def tokenized_lower(company_id: str) -> List[str]:
    return [token for token in re.split(r"[^a-z0-9]+", company_id.lower()) if token]


def is_suspicious_company_id(company_id: str) -> bool:
    if not company_id or company_id == UNKNOWN_COMPANY_ID:
        return False

    if looks_like_tax_id(company_id):
        return False

    lowered = company_id.lower()
    if lowered in EXPLICIT_SUSPICIOUS_VALUES:
        return True

    compact_alnum = re.sub(r"[^A-Z0-9]", "", company_id)
    if len(compact_alnum) < 3:
        return True

    words = tokenized_lower(company_id)
    if not words:
        return True

    legal_terms_hits = sum(1 for w in words if w in LEGAL_LEAK_TERMS)
    trigger_hits = sum(1 for w in words if w in LEAK_TRIGGER_TERMS)

    # Long phrase with legal/PDF vocabulary is likely OCR text leakage, not an identifier.
    if len(words) >= 4 and trigger_hits >= 1 and legal_terms_hits >= 2:
        return True

    # Very long non-tax IDs with multiple legal markers are typically noisy snippets.
    if len(company_id) >= 24 and trigger_hits >= 1 and legal_terms_hits >= 2:
        return True

    # Special case for broken OCR markers.
    if "column" in words and "break" in words:
        return True

    return False


def has_non_empty_field(event: dict, key: str) -> bool:
    data = event.get("data") or {}
    value = data.get(key)
    return value is not None and str(value).strip() != ""


def percent(n: int, d: int) -> float:
    return round((n / d) * 100.0, 2) if d else 0.0


def unknown_company_metrics_by_event_type(events: List[dict]) -> Dict[str, Dict[str, float]]:
    counts: Dict[str, Dict[str, int]] = defaultdict(lambda: {"total": 0, "unknown": 0})

    for event in events:
        event_type = str(event.get("event_type") or "unknown")
        company_id = str(event.get("company_id") or UNKNOWN_COMPANY_ID)
        counts[event_type]["total"] += 1
        if company_id == UNKNOWN_COMPANY_ID:
            counts[event_type]["unknown"] += 1

    out: Dict[str, Dict[str, float]] = {}
    for event_type, metric in counts.items():
        total = metric["total"]
        unknown = metric["unknown"]
        out[event_type] = {
            "total": total,
            "unknown_company": unknown,
            "unknown_company_pct": percent(unknown, total),
        }
    return out


def coverage_metrics(events: List[dict]) -> Dict[str, object]:
    total = len(events)
    tax_id_coverage = sum(1 for e in events if (e.get("data") or {}).get("tax_id_raw"))
    capital_coverage = sum(1 for e in events if has_non_empty_field(e, "capital"))
    address_coverage = sum(1 for e in events if has_non_empty_field(e, "address"))
    activity_coverage = sum(1 for e in events if has_non_empty_field(e, "activity"))

    return {
        "total_events": total,
        "tax_id_coverage": tax_id_coverage,
        "tax_id_coverage_pct": percent(tax_id_coverage, total),
        "capital_coverage": capital_coverage,
        "capital_coverage_pct": percent(capital_coverage, total),
        "address_coverage": address_coverage,
        "address_coverage_pct": percent(address_coverage, total),
        "activity_coverage": activity_coverage,
        "activity_coverage_pct": percent(activity_coverage, total),
    }


def clean_events(events: List[dict]) -> Tuple[List[dict], Counter]:
    cleaned: List[dict] = []
    suspicious_counter: Counter = Counter()

    for event in events:
        updated = dict(event)
        raw_company_id = event.get("company_id")
        normalized_company_id = normalize_company_id(raw_company_id)

        if is_suspicious_company_id(normalized_company_id):
            suspicious_counter[normalized_company_id] += 1
            updated["company_id_original"] = raw_company_id
            updated["company_id"] = SUSPICIOUS_COMPANY_ID
        else:
            updated["company_id"] = normalized_company_id

        cleaned.append(updated)

    return cleaned, suspicious_counter


def run(
    events_path: Path,
    notices_path: Path,
    timelines_path: Path,
    cleaned_events_path: Path,
    report_path: Path,
) -> dict:
    events = json.loads(events_path.read_text(encoding="utf-8"))

    # Load these to validate OCR outputs are present and readable.
    _ = json.loads(notices_path.read_text(encoding="utf-8"))
    _ = json.loads(timelines_path.read_text(encoding="utf-8"))

    before_unknown_by_type = unknown_company_metrics_by_event_type(events)
    before_coverage = coverage_metrics(events)

    cleaned_events, suspicious_counter = clean_events(events)

    after_unknown_by_type = unknown_company_metrics_by_event_type(cleaned_events)
    after_coverage = coverage_metrics(cleaned_events)

    cleaned_events_path.parent.mkdir(parents=True, exist_ok=True)
    cleaned_events_path.write_text(json.dumps(cleaned_events, ensure_ascii=False, indent=2), encoding="utf-8")

    report = {
        "input_files": {
            "events": str(events_path),
            "notices": str(notices_path),
            "timelines": str(timelines_path),
        },
        "output_files": {
            "cleaned_events": str(cleaned_events_path),
            "report": str(report_path),
        },
        "metrics": {
            "unknown_company_per_event_type_before": before_unknown_by_type,
            "unknown_company_per_event_type_after": after_unknown_by_type,
            "coverage_before": before_coverage,
            "coverage_after": after_coverage,
            "suspicious_company_ids_detected_total": int(sum(suspicious_counter.values())),
            "suspicious_company_ids_unique": int(len(suspicious_counter)),
        },
        "top_suspicious_company_ids": [
            {"company_id": company_id, "count": count}
            for company_id, count in suspicious_counter.most_common(20)
        ],
    }

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Post-OCR company_id cleaning and quality metrics")
    parser.add_argument(
        "--events",
        default="end2end/output_all_years_dict/extracted_events_end2end.json",
        help="Path to extracted_events_end2end.json",
    )
    parser.add_argument(
        "--notices",
        default="end2end/output_all_years_dict/extracted_notices_end2end.json",
        help="Path to extracted_notices_end2end.json",
    )
    parser.add_argument(
        "--timelines",
        default="end2end/output_all_years_dict/company_timelines.json",
        help="Path to company_timelines.json",
    )
    parser.add_argument(
        "--cleaned-events-out",
        default="end2end/output_all_years_dict/extracted_events_end2end_cleaned.json",
        help="Output path for cleaned events JSON",
    )
    parser.add_argument(
        "--report-out",
        default="end2end/output_all_years_dict/post_ocr_quality_report.json",
        help="Output path for metrics report JSON",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    report = run(
        events_path=Path(args.events),
        notices_path=Path(args.notices),
        timelines_path=Path(args.timelines),
        cleaned_events_path=Path(args.cleaned_events_out),
        report_path=Path(args.report_out),
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
