#!/usr/bin/env python3
"""Run the TEST workflow end-to-end.

Usage examples:
  python Start_pipeline.py
  python Start_pipeline.py --pdf-dir /home/iyedpc1/Technokutha/RAW/doc
  python Start_pipeline.py --pdf-dir /home/iyedpc1/Technokutha/RAW/doc --max-pages 5

Behavior:
- If --pdf-dir is provided, OCR+structuring is executed first to generate *_result.json
  in workflow/INPUT.
- Then the full workflow pipeline (steps 0-9) is run from workflow/WORK_FLOW.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Iterable, List


ROOT_DIR = Path(__file__).resolve().parent
DEFAULT_WORKFLOW_DIR = ROOT_DIR / "workflow" / "WORK_FLOW"


def run(cmd: List[str], cwd: Path, label: str) -> None:
    print(f"\n{'=' * 72}\n{label}\n{'=' * 72}")
    print("$", " ".join(cmd))
    result = subprocess.run(cmd, cwd=str(cwd))
    if result.returncode != 0:
        raise RuntimeError(f"Command failed ({result.returncode}): {' '.join(cmd)}")


def discover_pdf_batches(pdf_dir: Path) -> Iterable[Path]:
    """Yield PDF batch directories.

    If direct PDFs exist in `pdf_dir`, process that directory as one batch.
    Also process immediate subfolders that contain PDFs (e.g. yearly folders).
    """
    direct_pdfs = list(pdf_dir.glob("*.pdf"))
    if direct_pdfs:
        yield pdf_dir

    for child in sorted(p for p in pdf_dir.iterdir() if p.is_dir()):
        if any(child.glob("*.pdf")):
            yield child


def run_pdf_ingestion(
    workflow_dir: Path,
    input_dir: Path,
    pdf_root: Path,
    lang: str,
    max_pages: int | None,
    page_start: int,
    timeout: int,
) -> None:
    extraction_script = workflow_dir / "extraction.py"
    py = sys.executable

    batches = list(discover_pdf_batches(pdf_root))
    if not batches:
        raise RuntimeError(f"No PDFs found in {pdf_root} (or its immediate subfolders).")

    print(f"Found {len(batches)} PDF batch folder(s) under {pdf_root}")
    for batch_dir in batches:
        txt_dir = input_dir / "ocr_txt" / batch_dir.name
        cmd = [
            py,
            str(extraction_script),
            "--mode",
            "pdf",
            "--input-dir",
            str(batch_dir),
            "--output-dir",
            str(input_dir),
            "--txt-dir",
            str(txt_dir),
            "--lang",
            lang,
            "--page-start",
            str(page_start),
            "--timeout",
            str(timeout),
        ]
        if max_pages is not None:
            cmd += ["--max-pages", str(max_pages)]

        run(cmd, workflow_dir, f"PDF ingestion from: {batch_dir}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run TEST workflow end-to-end")
    parser.add_argument(
        "--workflow-dir",
        default=str(DEFAULT_WORKFLOW_DIR),
        help="Path to workflow/WORK_FLOW directory.",
    )
    parser.add_argument(
        "--pdf-dir",
        default=None,
        help=(
            "Optional PDF source directory. Can point to a folder containing PDFs "
            "or year subfolders (2014, 2015, ...)."
        ),
    )
    parser.add_argument("--lang", default="fra", help="Tesseract OCR language code.")
    parser.add_argument("--max-pages", type=int, default=None, help="Limit pages per PDF for fast tests.")
    parser.add_argument("--page-start", type=int, default=0, help="Start page index for OCR.")
    parser.add_argument("--timeout", type=int, default=120, help="Per-page OCR timeout (seconds).")
    args = parser.parse_args()

    workflow_dir = Path(args.workflow_dir).expanduser().resolve()
    if not workflow_dir.exists():
        print(f"workflow-dir not found: {workflow_dir}")
        return 2

    input_dir = (workflow_dir / ".." / "INPUT").resolve()
    input_dir.mkdir(parents=True, exist_ok=True)

    try:
        if args.pdf_dir:
            pdf_root = Path(args.pdf_dir).expanduser().resolve()
            if not pdf_root.exists() or not pdf_root.is_dir():
                print(f"pdf-dir not found: {pdf_root}")
                return 2
            run_pdf_ingestion(
                workflow_dir=workflow_dir,
                input_dir=input_dir,
                pdf_root=pdf_root,
                lang=args.lang,
                max_pages=args.max_pages,
                page_start=max(0, args.page_start),
                timeout=args.timeout,
            )

        run(
            [sys.executable, str(workflow_dir / "run_clean_and_extract.py")],
            workflow_dir,
            "Run full WORK_FLOW pipeline (steps 0-9)",
        )

        print("\nPipeline finished successfully.")
        print(f"Outputs: {(workflow_dir / '..').resolve()}")
        return 0

    except RuntimeError as exc:
        print(f"\nERROR: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
