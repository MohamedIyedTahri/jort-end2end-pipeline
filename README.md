# JORT End-to-End Constitution Extraction

Standalone repository for the constitution notice extraction pipeline.

## What This Repo Contains

- Direct PDF text extraction with 3-column reading and footer crop.
- Notice segmentation (`organize_text`).
- Constitution notice filtering.
- Structured field extraction with hardened normalization for sensitive fields.

Main entry point:

- `end2end/run_end2end_direct.py`

## Field Quality Hardening

The parser includes targeted safeguards for sensitive data quality:

- Corporate purpose extraction prioritizes explicit `Objet`/`Activite` labels and rejects company-name-like values.
- Company-name fallback rejects filing boilerplate and legal-form-only placeholders.
- Address normalization trims trailing legal/procedural text.
- Capital normalization keeps compact amount-and-currency values.

See implementation in:

- `extractor/parser.py`
- `extractor/patterns.py`
- `extractor/nlp_enrichment.py`

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m spacy download fr_core_news_sm
```

## Run

Quick check:

```bash
python end2end/run_end2end_direct.py --pdf-root doc --output-root end2end/output --limit 5 --workers 4 --resume
```

Full run:

```bash
python end2end/run_end2end_direct.py --pdf-root doc --output-root end2end/output --workers 8 --resume
```

## Outputs

- `end2end/output/direct_text/*.txt`
- `end2end/output/notices_json/*_result.json`
- `end2end/output/extracted_notices_end2end.json`
- `end2end/output/summary_end2end.json`

## Notes

- Keep raw PDFs outside the repository when possible (privacy and size).
- Prefer aggregated metrics for sharing results.
