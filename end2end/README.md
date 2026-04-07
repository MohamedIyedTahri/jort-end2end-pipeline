# End-to-End Direct Pipeline

This folder contains a standalone end-to-end pipeline:

1. Direct extraction from PDF (`pdfplumber`, 3-column + footer crop)
2. Notice splitting (`organize_text` from `OCR_Extraction/extraction.py`)
3. Constitution filtering + structured field extraction (`extractor/parser.py`)
4. Final JSON records + summary

## Event Layer (Prototype)

- Every notice is classified into one of 3 event types: constitution, modification, liquidation.
- Modification notices may receive a lightweight `event_subtype` (for example: `capital_increase`, `capital_decrease`, `transfer_head_office`, `management_change`).
- If parsing yields no structured fields, an event is still emitted with an empty `data` object to preserve timeline continuity.

## Run

```bash
cd /home/iyedpc1/jort
source .venv/bin/activate

# Quick validation on one year and limited files
python end2end/run_end2end_direct.py --pdf-root doc --year 2014 --limit 5

# Full run on all available years
python end2end/run_end2end_direct.py --pdf-root doc
```

## Outputs

- `end2end/output/direct_text/**.txt`: direct extracted text per PDF
- `end2end/output/notices_json/**_result.json`: organized block output per PDF
- `end2end/output/extracted_notices_end2end.json`: parsed constitution records
- `end2end/output/extracted_events_end2end.json`: event-layer records for all classified notices
- `end2end/output/company_timelines.json`: events grouped by company_id and sorted by date
- `end2end/output/summary_end2end.json`: execution summary

## Search API (FastAPI + Elasticsearch)

This repository includes an API service at `end2end/search_api.py` that indexes
`end2end/output/extracted_events_end2end.json` into Elasticsearch and exposes
search endpoints.

### Install

```bash
cd /home/iyedpc1/jort
source .venv/bin/activate
pip install -r end2end/requirements_search_api.txt
```

### Start Elasticsearch

The API expects a local Elasticsearch node at `http://localhost:9200`.

### Run API

```bash
cd /home/iyedpc1/jort
source .venv/bin/activate
uvicorn end2end.search_api:app --host 0.0.0.0 --port 8000 --reload
```

### Index events

```bash
curl -X POST "http://localhost:8000/index"
```

Optional custom path:

```bash
curl -X POST "http://localhost:8000/index?json_path=end2end/output/extracted_events_end2end.json"
```

### Query examples

```bash
# Fuzzy text search (company name, activity, address)
curl "http://localhost:8000/search?q=transport"

# Filter by event type and date range
curl "http://localhost:8000/search?q=parfum&event_type=constitution&start_year=2018&end_year=2024"

# Filter by tax ID
curl "http://localhost:8000/search?tax_id=1369632C/A/M/000"

# Full company timeline
curl "http://localhost:8000/company/1369632C/A/M/000"
```
