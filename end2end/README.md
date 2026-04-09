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

### NLP Enrichment (Current)

The parser now enriches events with:

- Governance propagation in `data`: `manager`, `president`, `directeur_general`, `president_directeur_general`, `administrators`, `auditor`
- Activity taxonomy normalization:
	- `activity_category`
	- `activity_category_confidence`
	- `activity_category_keywords`
- Confidence scoring:
	- per-field `field_confidence`
	- global `parse_confidence`

## Run

```bash
cd /home/iyedpc1/jort
source .venv/bin/activate

# Quick validation on one year and limited files
python end2end/run_end2end_direct.py --pdf-root doc --year 2014 --limit 5

# Full run on all available years
python end2end/run_end2end_direct.py --pdf-root doc

# Full run with parallel workers and resumable processing
python end2end/run_end2end_direct.py \
	--pdf-root doc \
	--output-root end2end/output_all_years_dict \
	--workers 4 \
	--resume
```

## Outputs

- `end2end/output/direct_text/**.txt`: direct extracted text per PDF
- `end2end/output/notices_json/**_result.json`: organized block output per PDF
- `end2end/output/extracted_notices_end2end.json`: parsed constitution records
- `end2end/output/extracted_events_end2end.json`: event-layer records for all classified notices
- `end2end/output/company_timelines.json`: events grouped by company_id and sorted by date
- `end2end/output/summary_end2end.json`: execution summary

For the full multi-year run, use:

- `end2end/output_all_years_dict/extracted_notices_end2end.json`
- `end2end/output_all_years_dict/extracted_events_end2end.json`
- `end2end/output_all_years_dict/company_timelines.json`
- `end2end/output_all_years_dict/summary_end2end.json`

Latest validated all-years snapshot:

- PDFs processed: 1568
- Notices processed: 250008
- Events generated: 249927
- Constitution records: 67932
- Events with `activity_category`: 50314
- Events with `parse_confidence`: 206045
- Events with `manager`: 69374

## Post-OCR Company ID Cleanup

Script: `end2end/run_after_ocr.py`

Purpose:

- normalize `company_id` format (spacing/slash/casing)
- detect OCR leakage and suspicious IDs (for example: `column break`, legal phrase fragments)
- keep tax-like IDs unchanged
- flag suspicious IDs as `__suspicious__` while preserving original value
- produce before/after quality metrics and top suspicious IDs

Run:

```bash
cd /home/iyedpc1/jort
source .venv/bin/activate
python end2end/run_after_ocr.py
```

Outputs:

- `end2end/output_all_years_dict/extracted_events_end2end_cleaned.json`
- `end2end/output_all_years_dict/post_ocr_quality_report.json`

Latest post-OCR quality metrics:

- suspicious company_id instances: 1386
- suspicious unique values: 106

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

## Advanced Structuring for BI

The API now supports a silver/gold modeling flow in Elasticsearch:

- `jort_events` (raw searchable events)
- `jort_events_structured` (enriched events with analytics fields)
- `jort_company_profile` (company-level aggregate index)

### Step 1: Build structured event index

```bash
curl -X POST "http://localhost:8000/structure/rebuild"
```

This creates and uses ingest pipeline `jort_events_structuring_pipeline` to enrich:

- `event_year`
- `company_name_normalized`
- `capital_amount`
- quality flags (`has_tax_id`, `has_address`, `has_activity`)
- `parse_confidence`

Tax ID quality model (strict):

- `tax_id_raw`: preserved raw extracted value (audit/debug)
- `tax_id_clean`: only valid 8-digit tax IDs
- `tax_id_valid`: true only when `tax_id_clean` is valid
- `tax_id_reject_reason`: one of `missing`, `invalid_format`,
	`ocr_header_fiscale`, `ocr_header_societes`, `ocr_column_break`,
	`ocr_footer_noise`

Search/filter field `tax_id` is now the clean value (invalid values are nulled).

Example quality aggregation:

```bash
curl -sS 'http://localhost:9200/jort_events_structured/_search?pretty' \
	-H 'Content-Type: application/json' \
	-d '{
		"size": 0,
		"aggs": {
			"invalid_tax_ids": {
				"terms": {"field": "tax_id_reject_reason", "size": 10}
			}
		}
	}'
```

### Step 2: Build company profile index (transform)

```bash
curl -X POST "http://localhost:8000/structure/transform"
```

This creates transform `jort_company_profile_transform` and writes company-level metrics to:

- `jort_company_profile`

### Search behavior

When `jort_events_structured` exists, `/search` and `/company/{company_id}` automatically use it.

## Company 360 Executive Dashboard

Provision a company-centric dashboard with lifecycle timeline, quality diagnostics,
and dashboard-level controls:

```bash
cd /home/iyedpc1/jort
source .venv/bin/activate
python end2end/provision_company360_dashboard.py
```

Dashboard ID:

- `jort-company-360-dashboard`

Includes:

- Controls panel (dashboard-level filtering):
	- `event_type`
	- `event_year` range slider
	- `parse_confidence` threshold slider
- Company Selector table (click a company to filter all panels)
- Lifecycle timeline by year and event type
- Quality diagnostics (tax ID/address/activity coverage + high-confidence ratio)
- KPI cards for event volume and confidence
- Tax ID quality diagnostics:
	- Valid vs invalid trend by year
	- Reject reason distribution
	- Top offending raw tax ID patterns
