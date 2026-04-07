from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from extractor.enrichment import (
    CANONICAL_FIELDS,
    _candidate_in_text,
    _clean_value,
    _field_from_key,
    _iter_pairs,
    _valid_for_field,
)

ROOT = Path(__file__).resolve().parent
FRIEND_DIR = ROOT / "anonyme" / "2004"
CONSTITUTION_ROOT = ROOT / "constitution" / "anonyme" / "2004"
PIPELINE_JSON = ROOT / "output" / "extracted_notices.json"

CORE_ORDER = [
    "company_name",
    "capital",
    "address",
    "corporate_purpose",
    "duration",
    "manager",
    "president_directeur_general",
    "president",
    "directeur_general",
    "auditor",
]


def load_pipeline_records() -> Dict[str, Dict[str, Any]]:
    data = json.loads(PIPELINE_JSON.read_text(encoding="utf-8"))
    mapping: Dict[str, Dict[str, Any]] = {}
    for row in data:
        if row.get("legal_form") != "anonyme":
            continue
        if row.get("year") != 2004:
            continue

        source_file = str(row.get("source_file") or "")
        if not source_file:
            continue
        mapping[Path(source_file).stem] = row
    return mapping


def list_friend_json_files() -> List[Path]:
    files = []
    for path in sorted(FRIEND_DIR.rglob("*.json")):
        if ":Zone.Identifier" in path.name:
            continue
        if path.is_file():
            files.append(path)
    return files


def candidate_status_for_field(
    field: str,
    candidates_raw: List[str],
    pipeline_value: Any,
    source_text: str,
) -> Tuple[str, Optional[str], List[str]]:
    reasons: List[str] = []

    if pipeline_value is not None:
        return "blocked_already_present", None, ["pipeline already has value"]

    if not candidates_raw:
        return "blocked_no_friend_candidate", None, ["friend JSON has no matching key for field"]

    valid_candidates: List[str] = []
    for raw in candidates_raw:
        cleaned = _clean_value(raw)
        if cleaned is None:
            reasons.append("empty_after_clean")
            continue
        if not _valid_for_field(field, cleaned):
            reasons.append("failed_quality_gate")
            continue
        valid_candidates.append(cleaned)

    if not valid_candidates:
        if not reasons:
            reasons.append("no_valid_candidate")
        return "blocked_no_valid_candidate", None, sorted(set(reasons))

    best = min(valid_candidates, key=len)
    if not _candidate_in_text(best, source_text):
        return "blocked_not_in_source_text", best, ["candidate not aligned with source notice text"]

    return "eligible_for_fallback", best, []


def collect_field_candidates(payload: Dict[str, Any]) -> Dict[str, List[str]]:
    out: Dict[str, List[str]] = defaultdict(list)
    for key, raw_value in _iter_pairs(payload):
        field = _field_from_key(key)
        if field is None or field not in CANONICAL_FIELDS:
            continue
        out[field].append(raw_value)
    return out


def main() -> None:
    pipeline_map = load_pipeline_records()
    friend_files = list_friend_json_files()

    friend_map: Dict[str, Path] = {}
    for path in friend_files:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        reference = payload.get("_reference") if isinstance(payload.get("_reference"), str) else path.stem
        reference = str(reference).strip()
        if reference:
            friend_map[reference] = path

    shared_refs = sorted(set(friend_map) & set(pipeline_map))

    details: List[Dict[str, Any]] = []
    reason_counts: Dict[str, Counter] = {field: Counter() for field in CORE_ORDER}
    status_counts: Dict[str, Counter] = {field: Counter() for field in CORE_ORDER}

    for reference in shared_refs:
        friend_path = friend_map[reference]
        payload = json.loads(friend_path.read_text(encoding="utf-8"))
        pipeline_record = pipeline_map[reference]

        relative = friend_path.relative_to(FRIEND_DIR)
        source_txt = CONSTITUTION_ROOT / relative.parent / f"{reference}.txt"
        source_text = source_txt.read_text(encoding="utf-8", errors="replace") if source_txt.exists() else ""

        field_candidates = collect_field_candidates(payload)

        field_report: Dict[str, Any] = {}
        for field in CORE_ORDER:
            status, candidate, reasons = candidate_status_for_field(
                field=field,
                candidates_raw=field_candidates.get(field, []),
                pipeline_value=pipeline_record.get(field),
                source_text=source_text,
            )

            field_report[field] = {
                "pipeline_value": pipeline_record.get(field),
                "friend_candidate": candidate,
                "status": status,
                "reasons": reasons,
                "friend_candidate_count": len(field_candidates.get(field, [])),
            }
            status_counts[field][status] += 1
            for reason in reasons:
                reason_counts[field][reason] += 1

        details.append(
            {
                "reference": reference,
                "friend_json": str(friend_path.relative_to(ROOT)),
                "source_txt": str(source_txt.relative_to(ROOT)) if source_txt.exists() else None,
                "fields": field_report,
            }
        )

    summary = {
        "friend_refs_total": len(friend_map),
        "pipeline_refs_2004_anonyme": len(pipeline_map),
        "shared_refs": len(shared_refs),
        "by_field_status": {field: dict(status_counts[field]) for field in CORE_ORDER},
        "by_field_reasons": {field: dict(reason_counts[field]) for field in CORE_ORDER},
    }

    out_detail = ROOT / "output" / "friend_2004_side_by_side_diff.json"
    out_summary = ROOT / "output" / "friend_2004_side_by_side_summary.json"
    out_detail.write_text(json.dumps(details, ensure_ascii=False, indent=2), encoding="utf-8")
    out_summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"\nWrote detail report: {out_detail}")
    print(f"Wrote summary report: {out_summary}")


if __name__ == "__main__":
    main()
