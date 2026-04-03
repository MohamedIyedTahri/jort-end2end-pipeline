# End-to-End Direct Pipeline

This folder contains a standalone end-to-end pipeline:

1. Direct extraction from PDF (`pdfplumber`, 3-column + footer crop)
2. Notice splitting (`organize_text` from `OCR_Extraction/extraction.py`)
3. Constitution filtering + structured field extraction (`extractor/parser.py`)
4. Final JSON records + summary

## Quality Controls

Field extraction includes hardening for sensitive data quality:

- Rejects company-name fallbacks that look like filing boilerplate.
- Preserves explicit `Objet`/`Activite` purpose values.
- Prevents company name from being copied into `corporate_purpose`.
- Trims procedural tails from `address` and `capital`.

## Run

```bash
cd /home/iyedpc1/jort
source .venv/bin/activate

# Quick validation on one year and limited files
python end2end/run_end2end_direct.py --pdf-root doc --year 2014 --limit 5 --workers 4 --resume

# Full run on all available years
python end2end/run_end2end_direct.py --pdf-root doc --workers 8 --resume
```

## Outputs

- `end2end/output/direct_text/**.txt`: direct extracted text per PDF
- `end2end/output/notices_json/**_result.json`: organized block output per PDF
- `end2end/output/extracted_notices_end2end.json`: parsed constitution records
- `end2end/output/summary_end2end.json`: execution summary
