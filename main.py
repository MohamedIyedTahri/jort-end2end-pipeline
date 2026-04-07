from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Dict, List

from extractor.cleaner import clean_text
from extractor.enrichment import apply_friend_fallback, load_friend_index
from extractor.parser import is_constitution_notice, parse_notice
from utils.filesystem import extract_metadata_from_path, iter_notice_files


def _read_notice_text(file_path: Path) -> str:
    raw_bytes = file_path.read_bytes()

    for encoding in ("utf-8", "cp1252", "latin-1"):
        try:
            return raw_bytes.decode(encoding)
        except UnicodeDecodeError:
            continue

    # Last-resort decode so one bad file does not stop the full dataset run.
    return raw_bytes.decode("utf-8", errors="replace")


def run_pipeline(
    dataset_dir: Path,
    output_dir: Path,
    friend_data_dir: Path | None = None,
) -> Dict[str, int]:
    records: List[Dict[str, object]] = []

    friend_index: Dict[str, Dict[str, str]] = {}
    if friend_data_dir is not None:
        friend_index = load_friend_index(friend_data_dir)
        logging.info(
            "Loaded friend enrichment index: references=%s from %s",
            len(friend_index),
            friend_data_dir,
        )

    scanned = 0
    parsed = 0
    skipped = 0
    skipped_non_constitution = 0
    errors = 0
    enriched_fields = 0
    enriched_records = 0

    for file_path in iter_notice_files(dataset_dir):
        scanned += 1

        metadata = extract_metadata_from_path(file_path, dataset_dir)
        if metadata is None:
            skipped += 1
            continue

        try:
            raw_text = _read_notice_text(file_path)
            cleaned_text = clean_text(raw_text)

            if not is_constitution_notice(cleaned_text):
                skipped += 1
                skipped_non_constitution += 1
                continue

            record = parse_notice(cleaned_text, metadata)

            if friend_index:
                reference = Path(str(metadata.get("source_file") or "")).stem
                added = apply_friend_fallback(record, cleaned_text, reference, friend_index)
                if added > 0:
                    enriched_records += 1
                    enriched_fields += added

            records.append(record)
            parsed += 1
        except Exception as exc:  # pylint: disable=broad-except
            errors += 1
            logging.warning("Failed to parse '%s': %s", file_path, exc)

        if scanned % 5000 == 0:
            logging.info(
                "Progress: scanned=%s parsed=%s skipped=%s skipped_non_constitution=%s errors=%s",
                scanned,
                parsed,
                skipped,
                skipped_non_constitution,
                errors,
            )

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "extracted_notices.json"
    with output_path.open("w", encoding="utf-8") as output_file:
        json.dump(records, output_file, ensure_ascii=False, indent=2)

    return {
        "scanned": scanned,
        "parsed": parsed,
        "skipped": skipped,
        "skipped_non_constitution": skipped_non_constitution,
        "errors": errors,
        "enriched_records": enriched_records,
        "enriched_fields": enriched_fields,
        "written": len(records),
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Extract structured company-constitution notices from JORT text files."
    )
    parser.add_argument(
        "--dataset",
        required=True,
        help="Path to dataset root (example: constitution)",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Path to output directory (example: output/)",
    )
    parser.add_argument(
        "--friend-data",
        default="anonyme/2004",
        help=(
            "Optional path to friend JSON extraction folder used as fallback enrichment "
            "(default: anonyme/2004)."
        ),
    )
    return parser


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    args = build_arg_parser().parse_args()
    dataset_dir = Path(args.dataset)
    output_dir = Path(args.output)
    friend_data_dir = Path(args.friend_data) if args.friend_data else None
    if friend_data_dir is not None and not friend_data_dir.exists():
        logging.warning("Friend data directory not found, fallback enrichment disabled: %s", friend_data_dir)
        friend_data_dir = None

    summary = run_pipeline(dataset_dir, output_dir, friend_data_dir=friend_data_dir)
    print(
        "Extraction complete. "
        f"scanned={summary['scanned']} "
        f"parsed={summary['parsed']} "
        f"skipped={summary['skipped']} "
        f"skipped_non_constitution={summary['skipped_non_constitution']} "
        f"errors={summary['errors']} "
        f"enriched_records={summary['enriched_records']} "
        f"enriched_fields={summary['enriched_fields']} "
        f"written={summary['written']}"
    )


if __name__ == "__main__":
    main()
