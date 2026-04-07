import argparse
import os
import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

import cv2
import fitz  # PyMuPDF
import numpy as np
import pytesseract
from pytesseract import Output


@dataclass
class Column:
    x0: int
    x1: int


@dataclass
class PageLayout:
    page_index: int
    columns: Optional[List[Column]]


def render_page(page: fitz.Page, dpi: int) -> np.ndarray:
    mat = fitz.Matrix(dpi / 72.0, dpi / 72.0)
    pix = page.get_pixmap(matrix=mat, alpha=False)
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3)
    return img


def crop_footer(image: np.ndarray, footer_px: int) -> np.ndarray:
    if footer_px <= 0:
        return image
    h, w = image.shape[:2]
    if h <= footer_px:
        return image
    return image[: h - footer_px, :]


def preprocess_for_layout(image: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    binary = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 31, 15
    )
    return binary


def find_column_boundaries(binary: np.ndarray) -> Optional[List[Column]]:
    h, w = binary.shape
    projection = binary.sum(axis=0).astype(np.float32)
    if projection.max() == 0:
        return None

    projection /= projection.max()
    kernel = np.ones(21, dtype=np.float32) / 21.0
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

    col0 = Column(0, max(left_gap[0] - 1, 0))
    col1 = Column(left_gap[1] + 1, max(right_gap[0] - 1, left_gap[1] + 1))
    col2 = Column(right_gap[1] + 1, w - 1)

    min_col_width = int(w * 0.15)
    for col in (col0, col1, col2):
        if (col.x1 - col.x0 + 1) < min_col_width:
            return None

    return [col0, col1, col2]


def extract_lines(
    image: np.ndarray, lang: str, psm: int, timeout: Optional[int]
) -> List[Tuple[int, str]]:
    config = f"--oem 1 --psm {psm}"
    data = pytesseract.image_to_data(
        image, lang=lang, config=config, output_type=Output.DICT, timeout=timeout
    )

    lines = {}
    for i, text in enumerate(data["text"]):
        if not text or int(data["conf"][i]) < 0:
            continue
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        x = data["left"][i]
        y = data["top"][i]
        lines.setdefault(key, {"y": y, "words": []})
        lines[key]["words"].append((x, text))

    ordered = []
    for key, info in lines.items():
        words = " ".join([w for _, w in sorted(info["words"], key=lambda w: w[0])]).strip()
        if words:
            ordered.append((info["y"], words))

    ordered.sort(key=lambda item: item[0])
    return ordered


def ocr_full_page(image: np.ndarray, lang: str, timeout: Optional[int]) -> str:
    lines = extract_lines(image, lang=lang, psm=4, timeout=timeout)
    return "\n".join([line for _, line in lines]).strip()


def ocr_columns(
    image: np.ndarray, columns: List[Column], lang: str, timeout: Optional[int]
) -> str:
    texts = []
    for col in columns:
        crop = image[:, col.x0 : col.x1 + 1]
        lines = extract_lines(crop, lang=lang, psm=6, timeout=timeout)
        text = "\n".join([line for _, line in lines]).strip()
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


def process_pdf(
    pdf_path: str,
    output_path: str,
    dpi: int,
    footer_px: int,
    lang: str,
    end_pattern: str,
    page_start: int,
    page_end: Optional[int],
    max_pages: Optional[int],
    timeout: Optional[int],
) -> None:
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
        image = render_page(page, dpi=dpi)
        image = crop_footer(image, footer_px=footer_px)

        binary = preprocess_for_layout(image)
        columns = find_column_boundaries(binary)
        layout = PageLayout(page_index=page_index, columns=columns)

        total_pages = last_page - page_start + 1
        print(
            f"Processing page {page_index + 1}/{len(doc)} "
            f"(batch {page_index - page_start + 1}/{total_pages})"
        )

        if layout.columns is None:
            page_text = ocr_full_page(image, lang=lang, timeout=timeout)
        else:
            page_text = ocr_columns(image, layout.columns, lang=lang, timeout=timeout)

        if page_text:
            combined = merge_pages(combined, page_text)

        last_line = last_non_empty_line(page_text)
        if last_line and pattern.search(last_line):
            break

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(combined)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="OCR pipeline with dynamic 3-column ordering.")
    parser.add_argument("pdf_path", help="Path to a single PDF file.")
    parser.add_argument("--out-dir", default="/home/iyedpc1/Technokutha/JORT/OUTPUT", help="Output directory.")
    parser.add_argument("--dpi", type=int, default=300, help="Render DPI for PDF pages.")
    parser.add_argument("--footer-px", type=int, default=350, help="Footer height to crop in pixels.")
    parser.add_argument("--lang", default="fra", help="Tesseract language code.")
    parser.add_argument("--page-start", type=int, default=0, help="Zero-based start page index.")
    parser.add_argument("--page-end", type=int, default=None, help="Zero-based end page index (inclusive).")
    parser.add_argument("--max-pages", type=int, default=None, help="Maximum number of pages to process.")
    parser.add_argument(
        "--timeout",
        type=int,
        default=120,
        help="Per-page OCR timeout in seconds (set 0 to disable).",
    )
    parser.add_argument(
        "--end-pattern",
        default=r"\b[0-9]{4}[A-Z]{1,4}[0-9]{2,}\b$",
        help="Regex used to detect the final reference number line.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    pdf_path = args.pdf_path
    if pdf_path.endswith(")"):
        pdf_path = pdf_path[:-1]

    base = os.path.splitext(os.path.basename(pdf_path))[0]
    output_path = os.path.join(args.out_dir, f"{base}.txt")

    process_pdf(
        pdf_path=pdf_path,
        output_path=output_path,
        dpi=args.dpi,
        footer_px=args.footer_px,
        lang=args.lang,
        end_pattern=args.end_pattern,
        page_start=max(0, args.page_start),
        page_end=args.page_end,
        max_pages=args.max_pages,
        timeout=None if args.timeout == 0 else args.timeout,
    )


if __name__ == "__main__":
    main()
