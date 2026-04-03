import argparse
import json
import os
import re
import unicodedata
from pathlib import Path
from typing import Dict, List, Optional, Tuple


REFERENCE_REGEX = re.compile(r"^20\d{2}[A-Z0-9\-/\s]{4,}$")


def read_text(path: Path) -> str:
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        return handle.read()


def normalize_lines(text: str) -> List[str]:
    return text.replace("\r\n", "\n").replace("\r", "\n").split("\n")


def normalize_for_match(text: str) -> str:
    text = text.lower()
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def extract_summary_sections(lines: List[str]) -> Tuple[List[str], int]:
    sections: List[str] = []
    in_summary = False
    summary_end_idx = 0

    for i, line in enumerate(lines):
        stripped = line.strip()

        if normalize_for_match(stripped) == "sommaire":
            in_summary = True
            continue

        if not in_summary:
            continue

        if not stripped and sections:
            summary_end_idx = i
            break

        if stripped and len(stripped) > 3 and not re.search(r"\s\d+$", stripped):
            if not line.startswith(" " * 4):
                sections.append(stripped)

    return sections, summary_end_idx


def find_block1_start(lines: List[str], sections: List[str], summary_end_idx: int) -> int:
    if not sections or summary_end_idx == 0:
        return max(summary_end_idx, 0)

    section_norms = [normalize_for_match(s) for s in sections]
    for i in range(summary_end_idx, len(lines)):
        stripped = lines[i].strip()
        if not stripped:
            continue

        if stripped.isupper() or (len(stripped.split()) > 1 and stripped[0].isupper()):
            line_norm = normalize_for_match(stripped)
            for section_norm in section_norms:
                if section_norm in line_norm or line_norm in section_norm:
                    return i

    return summary_end_idx


def find_reference_indices(lines: List[str]) -> List[int]:
    refs = []
    for i, line in enumerate(lines):
        candidate = re.sub(r"\s+", "", line.strip())
        if REFERENCE_REGEX.match(candidate):
            refs.append(i)
    return refs


def split_notices(block1_lines: List[str]) -> List[dict]:
    notices: List[dict] = []
    current_lines: List[str] = []

    for line in block1_lines:
        stripped = line.strip()
        candidate = re.sub(r"\s+", "", stripped)

        if REFERENCE_REGEX.match(candidate):
            content = "\n".join(current_lines).strip()
            notices.append({"reference_code": candidate, "content": content})
            current_lines = []
        else:
            current_lines.append(line)

    if current_lines:
        content = "\n".join(current_lines).strip()
        if content:
            notices.append({"reference_code": "", "content": content})

    return notices


def split_blocks(lines: List[str]) -> Tuple[str, List[str], str]:
    sections, summary_end_idx = extract_summary_sections(lines)
    block1_start = find_block1_start(lines, sections, summary_end_idx)
    ref_indices = find_reference_indices(lines)

    if not ref_indices:
        return "\n".join(lines).strip(), [], ""

    last_ref_index = ref_indices[-1]

    block0 = "\n".join(lines[:block1_start]).strip()
    block1_lines = lines[block1_start : last_ref_index + 1]
    block2 = "\n".join(lines[last_ref_index + 1 :]).strip()
    return block0, block1_lines, block2


def organize_text(text: str) -> Dict[str, dict]:
    lines = normalize_lines(text)
    block0, block1_lines, block2 = split_blocks(lines)
    notices = split_notices(block1_lines) if block1_lines else []

    return {
        "block0": {"raw_text": block0},
        "block1": {"notices": notices},
        "block2": {"raw_text": block2},
    }


def write_json(data: Dict[str, dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)


def _import_pdf_dependencies():
    try:
        import cv2  # type: ignore
        import fitz  # type: ignore
        import numpy as np  # type: ignore
        import pytesseract  # type: ignore
        from pytesseract import Output  # type: ignore

        return cv2, fitz, np, pytesseract, Output
    except Exception as exc:
        raise RuntimeError(
            "PDF mode requires cv2, pymupdf (fitz), numpy and pytesseract. "
            "Install them in your active environment before using --mode pdf/auto with PDFs."
        ) from exc


def process_pdf_to_text(
    pdf_path: Path,
    txt_output_path: Path,
    dpi: int,
    footer_px: int,
    lang: str,
    end_pattern: str,
    page_start: int,
    page_end: Optional[int],
    max_pages: Optional[int],
    timeout: Optional[int],
) -> None:
    cv2, fitz, np, pytesseract, Output = _import_pdf_dependencies()

    def render_page(page, page_dpi: int):
        mat = fitz.Matrix(page_dpi / 72.0, page_dpi / 72.0)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        return np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3)

    def crop_footer(image, footer_pixels: int):
        if footer_pixels <= 0:
            return image
        h, _ = image.shape[:2]
        if h <= footer_pixels:
            return image
        return image[: h - footer_pixels, :]

    def preprocess_for_layout(image):
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (3, 3), 0)
        return cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 31, 15
        )

    def find_column_boundaries(binary) -> Optional[List[Tuple[int, int]]]:
        h, w = binary.shape
        _ = h
        projection = binary.sum(axis=0).astype("float32")
        if projection.max() == 0:
            return None

        projection /= projection.max()
        kernel = np.ones(21, dtype="float32") / 21.0
        smooth = np.convolve(projection, kernel, mode="same")

        whitespace = smooth < 0.05
        gaps = []
        start = None
        for i, is_gap in enumerate(whitespace):
            if is_gap and start is None:
                start = i
            if not is_gap and start is not None:
                gaps.append((start, i - 1))
                start = None
        if start is not None:
            gaps.append((start, w - 1))

        min_gap_width = max(12, int(w * 0.02))
        gaps = [g for g in gaps if (g[1] - g[0] + 1) >= min_gap_width]
        if len(gaps) < 2:
            return None

        gaps = sorted(gaps, key=lambda g: (g[1] - g[0]), reverse=True)
        chosen = []
        for g in gaps:
            mid = (g[0] + g[1]) / 2.0
            if 0.15 * w < mid < 0.85 * w:
                chosen.append(g)
            if len(chosen) == 2:
                break

        if len(chosen) < 2:
            return None

        chosen = sorted(chosen, key=lambda g: g[0])
        left_gap, right_gap = chosen
        cols = [
            (0, max(left_gap[0] - 1, 0)),
            (left_gap[1] + 1, max(right_gap[0] - 1, left_gap[1] + 1)),
            (right_gap[1] + 1, w - 1),
        ]

        min_col_width = int(w * 0.15)
        for x0, x1 in cols:
            if (x1 - x0 + 1) < min_col_width:
                return None

        return cols

    def extract_lines(image, psm: int) -> List[Tuple[int, str]]:
        config = f"--oem 1 --psm {psm}"
        data = pytesseract.image_to_data(
            image,
            lang=lang,
            config=config,
            output_type=Output.DICT,
            timeout=timeout,
        )
        lines: Dict[Tuple[int, int, int], Dict[str, object]] = {}
        for i, txt in enumerate(data["text"]):
            if not txt:
                continue
            conf = int(float(data["conf"][i])) if data["conf"][i] else -1
            if conf < 0:
                continue
            key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
            x, y = data["left"][i], data["top"][i]
            if key not in lines:
                lines[key] = {"y": y, "words": []}
            lines[key]["words"].append((x, txt))

        ordered = []
        for info in lines.values():
            words = " ".join(w for _, w in sorted(info["words"], key=lambda it: it[0])).strip()
            if words:
                ordered.append((int(info["y"]), words))
        ordered.sort(key=lambda item: item[0])
        return ordered

    def ocr_page(image, columns: Optional[List[Tuple[int, int]]]) -> str:
        if not columns:
            return "\n".join(line for _, line in extract_lines(image, psm=4)).strip()

        texts = []
        for x0, x1 in columns:
            crop = image[:, x0 : x1 + 1]
            text = "\n".join(line for _, line in extract_lines(crop, psm=6)).strip()
            if text:
                texts.append(text)
        return "\n\n".join(texts).strip()

    def merge_pages(prev_text: str, next_text: str) -> str:
        if not prev_text:
            return next_text
        prev = prev_text.rstrip()
        nxt = next_text.lstrip()
        if prev.endswith("-") and nxt[:1].islower():
            return prev[:-1] + nxt
        return prev + "\n\n" + nxt

    def last_non_empty_line(text: str) -> str:
        for line in reversed(text.splitlines()):
            if line.strip():
                return line.strip()
        return ""

    pattern = re.compile(end_pattern)
    doc = fitz.open(pdf_path)

    combined = ""
    last_page = len(doc) - 1
    if page_end is not None:
        last_page = min(last_page, page_end)
    if max_pages is not None:
        last_page = min(last_page, page_start + max_pages - 1)

    for page_index in range(page_start, last_page + 1):
        page = doc.load_page(page_index)
        image = render_page(page, page_dpi=dpi)
        image = crop_footer(image, footer_pixels=footer_px)
        binary = preprocess_for_layout(image)
        columns = find_column_boundaries(binary)

        print(f"Processing {pdf_path.name}: page {page_index + 1}/{len(doc)}")
        page_text = ocr_page(image, columns)
        if page_text:
            combined = merge_pages(combined, page_text)

        if pattern.search(last_non_empty_line(page_text)):
            break

    txt_output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(txt_output_path, "w", encoding="utf-8") as handle:
        handle.write(combined)


def convert_txt_to_result_json(input_txt: Path, output_json: Path) -> None:
    text = read_text(input_txt)
    data = organize_text(text)
    write_json(data, output_json)


def run_legacy_mode(input_path: Optional[Path], input_dir: Path, output_dir: Path) -> int:
    if input_path:
        txt_files = [input_path]
    else:
        txt_files = sorted(input_dir.glob("*.txt"))

    if not txt_files:
        print("Legacy mode: no .txt files found.")
        return 0

    for txt_path in txt_files:
        out_name = f"{txt_path.stem}_result.json"
        output_json = output_dir / out_name
        convert_txt_to_result_json(txt_path, output_json)
        print(f"Legacy mode: {txt_path.name} -> {output_json.name}")
    return 0


def run_pdf_mode(
    pdf_path: Optional[Path],
    input_dir: Path,
    output_dir: Path,
    txt_dir: Path,
    dpi: int,
    footer_px: int,
    lang: str,
    end_pattern: str,
    page_start: int,
    page_end: Optional[int],
    max_pages: Optional[int],
    timeout: Optional[int],
) -> int:
    if pdf_path:
        pdf_files = [pdf_path]
    else:
        pdf_files = sorted(input_dir.glob("*.pdf"))

    if not pdf_files:
        print("PDF mode: no .pdf files found.")
        return 0

    for pdf_file in pdf_files:
        txt_path = txt_dir / f"{pdf_file.stem}.txt"
        out_json = output_dir / f"{pdf_file.stem}_result.json"
        process_pdf_to_text(
            pdf_path=pdf_file,
            txt_output_path=txt_path,
            dpi=dpi,
            footer_px=footer_px,
            lang=lang,
            end_pattern=end_pattern,
            page_start=page_start,
            page_end=page_end,
            max_pages=max_pages,
            timeout=timeout,
        )
        convert_txt_to_result_json(txt_path, out_json)
        print(f"PDF mode: {pdf_file.name} -> {out_json.name}")

    return 0


def run_auto_mode(
    input_dir: Path,
    output_dir: Path,
    txt_dir: Path,
    dpi: int,
    footer_px: int,
    lang: str,
    end_pattern: str,
    page_start: int,
    page_end: Optional[int],
    max_pages: Optional[int],
    timeout: Optional[int],
) -> int:
    existing_results = sorted(input_dir.glob("*_result.json"))
    pdf_files = sorted(input_dir.glob("*.pdf"))
    txt_files = sorted(input_dir.glob("*.txt"))

    if existing_results and not pdf_files and not txt_files:
        print("Auto mode: existing *_result.json found; using older workflow entry.")
        return 0

    if pdf_files:
        run_pdf_mode(
            pdf_path=None,
            input_dir=input_dir,
            output_dir=output_dir,
            txt_dir=txt_dir,
            dpi=dpi,
            footer_px=footer_px,
            lang=lang,
            end_pattern=end_pattern,
            page_start=page_start,
            page_end=page_end,
            max_pages=max_pages,
            timeout=timeout,
        )

    if txt_files:
        run_legacy_mode(input_path=None, input_dir=input_dir, output_dir=output_dir)

    generated = sorted(output_dir.glob("*_result.json"))
    if generated:
        print(f"Auto mode: ready with {len(generated)} result files.")
    else:
        print("Auto mode: nothing to process.")
    return 0


def parse_args() -> argparse.Namespace:
    workflow_dir = Path(__file__).resolve().parent
    default_input_dir = (workflow_dir / ".." / "INPUT").resolve()
    default_output_dir = default_input_dir
    default_txt_dir = (default_input_dir / "ocr_txt").resolve()

    parser = argparse.ArgumentParser(
        description=(
            "Unified extraction entrypoint: "
            "legacy OCR-text to *_result.json and PDF OCR to *_result.json."
        )
    )
    parser.add_argument(
        "--mode",
        choices=["auto", "pdf", "legacy"],
        default="auto",
        help="auto: detect available inputs, pdf: process PDFs, legacy: process .txt inputs.",
    )
    parser.add_argument("--input-path", default=None, help="Single input file (.pdf or .txt).")
    parser.add_argument("--input-dir", default=str(default_input_dir), help="Input directory.")
    parser.add_argument(
        "--output-dir",
        default=str(default_output_dir),
        help="Directory for generated *_result.json files.",
    )
    parser.add_argument(
        "--txt-dir",
        default=str(default_txt_dir),
        help="Directory to store OCR text generated from PDFs.",
    )
    parser.add_argument("--dpi", type=int, default=300, help="Render DPI for PDF pages.")
    parser.add_argument("--footer-px", type=int, default=350, help="Footer crop height in px.")
    parser.add_argument("--lang", default="fra", help="Tesseract language code.")
    parser.add_argument("--page-start", type=int, default=0, help="Zero-based start page index.")
    parser.add_argument("--page-end", type=int, default=None, help="Zero-based end page index.")
    parser.add_argument("--max-pages", type=int, default=None, help="Maximum pages to process.")
    parser.add_argument("--timeout", type=int, default=120, help="Per-page OCR timeout seconds; 0 disables.")
    parser.add_argument(
        "--end-pattern",
        default=r"\b[0-9]{4}[A-Z]{1,4}[0-9]{2,}\b$",
        help="Regex used to detect last reference line while OCRing PDFs.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_dir = Path(args.input_dir).resolve()
    output_dir = Path(args.output_dir).resolve()
    txt_dir = Path(args.txt_dir).resolve()
    input_path = Path(args.input_path).resolve() if args.input_path else None
    timeout = None if args.timeout == 0 else args.timeout

    input_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.mode == "legacy":
        rc = run_legacy_mode(input_path=input_path, input_dir=input_dir, output_dir=output_dir)
    elif args.mode == "pdf":
        rc = run_pdf_mode(
            pdf_path=input_path,
            input_dir=input_dir,
            output_dir=output_dir,
            txt_dir=txt_dir,
            dpi=args.dpi,
            footer_px=args.footer_px,
            lang=args.lang,
            end_pattern=args.end_pattern,
            page_start=max(0, args.page_start),
            page_end=args.page_end,
            max_pages=args.max_pages,
            timeout=timeout,
        )
    else:
        rc = run_auto_mode(
            input_dir=input_dir,
            output_dir=output_dir,
            txt_dir=txt_dir,
            dpi=args.dpi,
            footer_px=args.footer_px,
            lang=args.lang,
            end_pattern=args.end_pattern,
            page_start=max(0, args.page_start),
            page_end=args.page_end,
            max_pages=args.max_pages,
            timeout=timeout,
        )

    raise SystemExit(rc)


if __name__ == "__main__":
    main()
