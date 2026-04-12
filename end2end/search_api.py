from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from elasticsearch import Elasticsearch, helpers
from elasticsearch.exceptions import ConnectionError as ESConnectionError
from elasticsearch.exceptions import NotFoundError as ESNotFoundError
from elasticsearch.exceptions import TransportError
from fastapi import FastAPI, HTTPException, Query

ES_URL = os.environ.get("ELASTICSEARCH_URL", "http://localhost:9200")
INDEX_NAME = "jort_events"
STRUCTURED_INDEX_NAME = "jort_events_structured"
PROFILE_INDEX_NAME = "jort_company_profile"
STRUCTURE_PIPELINE_ID = "jort_events_structuring_pipeline"
PROFILE_TRANSFORM_ID = "jort_company_profile_transform"
DEFAULT_JSON_PATH = Path("end2end/output/extracted_events_end2end.json")

logger = logging.getLogger("jort-search-api")
logging.basicConfig(level=logging.INFO)

es = Elasticsearch(
    ES_URL,
    request_timeout=10,
    retry_on_timeout=True,
    max_retries=3,
)

app = FastAPI(title="JORT Search API", version="1.0.0")


INDEX_MAPPING = {
    "settings": {
        "number_of_shards": 1,
        "number_of_replicas": 0,
        "refresh_interval": "1s",
    },
    "mappings": {
        "properties": {
            "company_id": {"type": "keyword"},
            "canonical_company_name": {
                "type": "text",
                "analyzer": "standard",
                "fields": {"keyword": {"type": "keyword", "ignore_above": 512}},
            },
            "event_type": {"type": "keyword"},
            "event_subtype": {"type": "keyword"},
            "date": {"type": "integer"},
            "tax_id": {"type": "keyword"},
            "capital": {"type": "text", "analyzer": "standard"},
            "address": {"type": "text", "analyzer": "standard"},
            "activity": {"type": "text", "analyzer": "standard"},
        }
    },
}


STRUCTURED_INDEX_MAPPING = {
    "settings": {
        "number_of_shards": 1,
        "number_of_replicas": 0,
        "refresh_interval": "1s",
    },
    "mappings": {
        "properties": {
            "company_id": {"type": "keyword"},
            "canonical_company_name": {
                "type": "text",
                "analyzer": "standard",
                "fields": {
                    "keyword": {"type": "keyword", "ignore_above": 512},
                    "suggest": {"type": "search_as_you_type"},
                },
            },
            "company_name_normalized": {"type": "keyword"},
            "event_type": {"type": "keyword"},
            "event_subtype": {"type": "keyword"},
            "date": {"type": "integer"},
            "event_year": {"type": "integer"},
            "tax_id": {"type": "keyword"},
                "tax_id_raw": {"type": "keyword", "ignore_above": 256},
                "tax_id_clean": {"type": "keyword"},
                "tax_id_valid": {"type": "boolean"},
                "tax_id_reject_reason": {"type": "keyword"},
            "capital": {
                "type": "text",
                "analyzer": "standard",
                "fields": {"keyword": {"type": "keyword", "ignore_above": 256}},
            },
            "capital_amount": {"type": "double"},
            "address": {
                "type": "text",
                "analyzer": "standard",
                "fields": {"keyword": {"type": "keyword", "ignore_above": 512}},
            },
            "activity": {
                "type": "text",
                "analyzer": "standard",
                "fields": {"keyword": {"type": "keyword", "ignore_above": 512}},
            },
            "has_tax_id": {"type": "boolean"},
            "has_address": {"type": "boolean"},
            "has_activity": {"type": "boolean"},
            "parse_confidence": {"type": "float"},
        }
    },
}


STRUCTURE_PIPELINE = {
    "description": "Enrich JORT events into BI-friendly structured fields",
    "processors": [
        {"set": {"field": "event_year", "copy_from": "date", "ignore_failure": True}},
        {
            "script": {
                "lang": "painless",
                                "source": r"""
if (ctx.containsKey('canonical_company_name') && ctx.canonical_company_name != null) {
  ctx.company_name_normalized = ctx.canonical_company_name.toLowerCase(Locale.ROOT).trim();
}

String rawTaxId = null;
if (ctx.containsKey('tax_id') && ctx.tax_id != null) {
    rawTaxId = ctx.tax_id.toString().trim().toUpperCase(Locale.ROOT).replace('-', '/').replace(' ', '');
}

ctx.tax_id_raw = rawTaxId;
ctx.tax_id_clean = null;
ctx.tax_id_valid = false;
ctx.tax_id_reject_reason = null;

if (rawTaxId == null || rawTaxId.length() == 0) {
    ctx.tax_id_reject_reason = "missing";
    ctx.tax_id = null;
} else {
    String upperTaxId = rawTaxId;
    boolean isNumeric8 = /^[0-9]{8}$/.matcher(rawTaxId).matches();
    boolean isMf = /^[0-9]{7,8}[A-Z]\/[A-Z]\/[A-Z]\/[0-9]{3}$/.matcher(rawTaxId).matches();
    boolean isMfAlt = /^[0-9]{7,8}\/[A-Z]\/[A-Z]\/[A-Z]\/[0-9]{3}$/.matcher(rawTaxId).matches();
    if (isNumeric8 || isMf || isMfAlt) {
        ctx.tax_id_clean = rawTaxId;
        ctx.tax_id = rawTaxId;
        ctx.tax_id_valid = true;
        ctx.tax_id_reject_reason = null;
    } else {
        ctx.tax_id = null;
        if (upperTaxId.contains("FISCALE") || upperTaxId.contains("FISCAL")) {
            ctx.tax_id_reject_reason = "ocr_header_fiscale";
        } else if (upperTaxId.contains("SOCIETE") || upperTaxId.contains("SOCIETES")) {
            ctx.tax_id_reject_reason = "ocr_header_societes";
        } else if (upperTaxId.contains("POURSUIVANT") || upperTaxId.contains("PARTIE")) {
            ctx.tax_id_reject_reason = "ocr_column_break";
        } else if (upperTaxId.contains("DEMANDE")) {
            ctx.tax_id_reject_reason = "ocr_footer_noise";
        } else {
            ctx.tax_id_reject_reason = "invalid_format";
        }
    }
}

ctx.has_tax_id = ctx.tax_id_valid;
ctx.has_address = ctx.containsKey('address') && ctx.address != null && ctx.address.toString().trim().length() > 0;
ctx.has_activity = ctx.containsKey('activity') && ctx.activity != null && ctx.activity.toString().trim().length() > 0;

double score = 0.2;
if (ctx.company_name_normalized != null && ctx.company_name_normalized.length() > 0) score += 0.3;
if (ctx.tax_id_valid) score += 0.3;
if (ctx.has_address) score += 0.1;
if (ctx.has_activity) score += 0.1;
ctx.parse_confidence = score;

if (ctx.containsKey('capital') && ctx.capital != null) {
    String c = ctx.capital.toString().replace(',', '.');
  def m = /([0-9]+(?:\\.[0-9]+)?)/.matcher(c);
  if (m.find()) {
    try {
      ctx.capital_amount = Double.parseDouble(m.group(1));
    } catch (Exception ignored) {
      // Keep null when value cannot be parsed cleanly.
    }
  }
}
"""
            }
        },
    ],
}


def create_index_if_needed() -> None:
    try:
        if not es.indices.exists(index=INDEX_NAME):
            es.indices.create(index=INDEX_NAME, body=INDEX_MAPPING)
            logger.info("Created index %s", INDEX_NAME)
    except ESConnectionError as exc:
        raise RuntimeError("Cannot connect to Elasticsearch at http://localhost:9200") from exc
    except TransportError as exc:
        raise RuntimeError(f"Failed to create index: {exc}") from exc


def _active_search_index() -> str:
    try:
        if es.indices.exists(index=STRUCTURED_INDEX_NAME):
            return STRUCTURED_INDEX_NAME
    except Exception:  # pylint: disable=broad-except
        pass
    return INDEX_NAME


def create_structured_index_if_needed() -> None:
    try:
        if not es.indices.exists(index=STRUCTURED_INDEX_NAME):
            es.indices.create(index=STRUCTURED_INDEX_NAME, body=STRUCTURED_INDEX_MAPPING)
            logger.info("Created structured index %s", STRUCTURED_INDEX_NAME)
    except ESConnectionError as exc:
        raise RuntimeError("Cannot connect to Elasticsearch at http://localhost:9200") from exc
    except TransportError as exc:
        raise RuntimeError(f"Failed to create structured index: {exc}") from exc


def create_structure_pipeline() -> None:
    try:
        es.ingest.put_pipeline(id=STRUCTURE_PIPELINE_ID, body=STRUCTURE_PIPELINE)
    except ESConnectionError as exc:
        raise RuntimeError("Cannot connect to Elasticsearch at http://localhost:9200") from exc
    except TransportError as exc:
        raise RuntimeError(f"Failed to create structure pipeline: {exc}") from exc


def rebuild_structured_index(source_index: str = INDEX_NAME) -> Dict[str, Any]:
    create_structure_pipeline()
    if es.indices.exists(index=STRUCTURED_INDEX_NAME):
        es.indices.delete(index=STRUCTURED_INDEX_NAME)
    create_structured_index_if_needed()

    try:
        reindex_response = es.reindex(
            body={
                "source": {"index": source_index},
                "dest": {
                    "index": STRUCTURED_INDEX_NAME,
                    "pipeline": STRUCTURE_PIPELINE_ID,
                    "op_type": "index",
                },
                "conflicts": "proceed",
            },
            refresh=True,
            wait_for_completion=True,
            request_timeout=3600,
        )
    except ESConnectionError as exc:
        raise RuntimeError("Elasticsearch connection failed during reindex") from exc
    except TransportError as exc:
        raise RuntimeError(f"Reindex failed: {exc}") from exc

    return {
        "source_index": source_index,
        "target_index": STRUCTURED_INDEX_NAME,
        "created": reindex_response.get("created", 0),
        "updated": reindex_response.get("updated", 0),
        "failures": len(reindex_response.get("failures", [])),
        "took_ms": reindex_response.get("took", 0),
    }


def build_company_profile_transform() -> Dict[str, Any]:
    transform_body = {
        "source": {"index": STRUCTURED_INDEX_NAME},
        "dest": {"index": PROFILE_INDEX_NAME},
        "pivot": {
            "group_by": {
                "company_id": {"terms": {"field": "company_id"}},
            },
            "aggregations": {
                "events_count": {"value_count": {"field": "event_type"}},
                "first_seen_year": {"min": {"field": "event_year"}},
                "last_seen_year": {"max": {"field": "event_year"}},
                "event_type_mix": {"terms": {"field": "event_type", "size": 10}},
                "latest_company_name": {
                    "top_metrics": {
                        "metrics": [{"field": "canonical_company_name.keyword"}],
                        "sort": {"event_year": "desc"},
                    }
                },
                "latest_tax_id": {
                    "top_metrics": {
                        "metrics": [{"field": "tax_id"}],
                        "sort": {"event_year": "desc"},
                    }
                },
                "latest_event_type": {
                    "top_metrics": {
                        "metrics": [{"field": "event_type"}],
                        "sort": {"event_year": "desc"},
                    }
                },
                "max_capital_amount": {"max": {"field": "capital_amount"}},
            },
        },
    }

    try:
        if es.transform.get_transform(transform_id=PROFILE_TRANSFORM_ID).get("transforms"):
            try:
                es.transform.stop_transform(transform_id=PROFILE_TRANSFORM_ID, force=True)
            except Exception:  # pylint: disable=broad-except
                pass
            es.transform.delete_transform(transform_id=PROFILE_TRANSFORM_ID, force=True)
    except ESNotFoundError:
        pass

    es.transform.put_transform(transform_id=PROFILE_TRANSFORM_ID, body=transform_body)
    start_response = es.transform.start_transform(transform_id=PROFILE_TRANSFORM_ID)

    return {
        "transform_id": PROFILE_TRANSFORM_ID,
        "profile_index": PROFILE_INDEX_NAME,
        "started": bool(start_response.get("acknowledged", False)),
    }


def _to_int(value: Any) -> Optional[int]:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _flatten_event(event: Dict[str, Any]) -> Dict[str, Any]:
    data = event.get("data") or {}
    return {
        "company_id": event.get("company_id"),
        "canonical_company_name": event.get("canonical_company_name"),
        "event_type": event.get("event_type"),
        "event_subtype": event.get("event_subtype"),
        "date": _to_int(event.get("date")),
        "tax_id": data.get("tax_id"),
            "tax_id_raw": data.get("tax_id_raw") or data.get("tax_id"),
            "tax_id_clean": data.get("tax_id_clean"),
            "tax_id_valid": data.get("tax_id_valid"),
            "tax_id_reject_reason": data.get("tax_id_reject_reason"),
        "capital": data.get("capital"),
        "address": data.get("address"),
        "activity": data.get("activity"),
    }


def _build_bulk_actions(events: Iterable[Dict[str, Any]]) -> Iterable[Dict[str, Any]]:
    for i, event in enumerate(events):
        doc = _flatten_event(event)
        # Deterministic id keeps re-indexing idempotent.
        doc_id = f"{doc.get('company_id', 'unknown')}::{doc.get('date', '0')}::{doc.get('event_type', 'unknown')}::{i}"
        yield {
            "_op_type": "index",
            "_index": INDEX_NAME,
            "_id": doc_id,
            "_source": doc,
        }


def index_events(json_path: str) -> Dict[str, Any]:
    path = Path(json_path)
    if not path.exists():
        raise FileNotFoundError(f"Input JSON file not found: {path}")

    with path.open("r", encoding="utf-8") as f:
        events = json.load(f)

    if not isinstance(events, list):
        raise ValueError("Input JSON must contain a list of events")

    create_index_if_needed()

    try:
        indexed_count, errors = helpers.bulk(
            es,
            _build_bulk_actions(events),
            chunk_size=2000,
            request_timeout=60,
            raise_on_error=False,
            raise_on_exception=False,
            refresh="wait_for",
        )
    except ESConnectionError as exc:
        raise RuntimeError("Elasticsearch connection failed during bulk indexing") from exc
    except TransportError as exc:
        raise RuntimeError(f"Bulk indexing failed: {exc}") from exc

    return {
        "indexed": indexed_count,
        "errors_count": len(errors) if errors else 0,
    }


@app.on_event("startup")
def startup_event() -> None:
    try:
        create_index_if_needed()
    except Exception as exc:  # pylint: disable=broad-except
        logger.warning("Index check at startup failed: %s", exc)


@app.get("/health")
def health() -> Dict[str, Any]:
    try:
        connected = bool(es.ping())
        return {
            "status": "ok" if connected else "degraded",
            "elasticsearch": connected,
            "index": INDEX_NAME,
            "structured_index": STRUCTURED_INDEX_NAME,
            "profile_index": PROFILE_INDEX_NAME,
        }
    except Exception as exc:  # pylint: disable=broad-except
        return {
            "status": "degraded",
            "elasticsearch": False,
            "index": INDEX_NAME,
            "structured_index": STRUCTURED_INDEX_NAME,
            "profile_index": PROFILE_INDEX_NAME,
            "error": str(exc),
        }


@app.post("/index")
def trigger_index(json_path: str = str(DEFAULT_JSON_PATH)) -> Dict[str, Any]:
    try:
        result = index_events(json_path)
        return {
            "status": "ok",
            "index": INDEX_NAME,
            "source_file": json_path,
            **result,
        }
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:  # pylint: disable=broad-except
        raise HTTPException(status_code=500, detail=f"Unexpected indexing error: {exc}") from exc


@app.post("/structure/rebuild")
def trigger_structure_rebuild(source_index: str = INDEX_NAME) -> Dict[str, Any]:
    try:
        result = rebuild_structured_index(source_index=source_index)
        return {
            "status": "ok",
            "pipeline": STRUCTURE_PIPELINE_ID,
            **result,
        }
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:  # pylint: disable=broad-except
        raise HTTPException(status_code=500, detail=f"Structuring error: {exc}") from exc


@app.post("/structure/transform")
def trigger_profile_transform() -> Dict[str, Any]:
    try:
        if not es.indices.exists(index=STRUCTURED_INDEX_NAME):
            raise HTTPException(
                status_code=400,
                detail=f"Structured index missing: {STRUCTURED_INDEX_NAME}. Run /structure/rebuild first.",
            )

        result = build_company_profile_transform()
        return {
            "status": "ok",
            **result,
        }
    except HTTPException:
        raise
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:  # pylint: disable=broad-except
        raise HTTPException(status_code=500, detail=f"Transform error: {exc}") from exc


@app.get("/search")
def search(
    q: str = "",
    event_type: Optional[str] = None,
    tax_id: Optional[str] = None,
    start_year: Optional[int] = Query(None, ge=1900, le=2100),
    end_year: Optional[int] = Query(None, ge=1900, le=2100),
    size: int = Query(20, ge=1, le=100),
) -> Dict[str, Any]:
    target_index = _active_search_index()
    must = []
    filters = []

    if q and q.strip():
        must.append(
            {
                "multi_match": {
                    "query": q.strip(),
                    "fields": [
                        "canonical_company_name^3",
                        "activity^2",
                        "address",
                    ],
                    "fuzziness": "AUTO",
                }
            }
        )
    else:
        must.append({"match_all": {}})

    if event_type:
        filters.append({"term": {"event_type": event_type}})

    if tax_id:
        filters.append({"term": {"tax_id": tax_id}})

    if start_year is not None or end_year is not None:
        date_range: Dict[str, int] = {}
        if start_year is not None:
            date_range["gte"] = start_year
        if end_year is not None:
            date_range["lte"] = end_year
        filters.append({"range": {"date": date_range}})

    query_body = {
        "query": {
            "bool": {
                "must": must,
                "filter": filters,
            }
        },
        "_source": [
            "company_id",
            "canonical_company_name",
            "event_type",
            "date",
            "tax_id",
            "tax_id_valid",
            "tax_id_reject_reason",
            "capital",
            "address",
            "activity",
        ],
        "size": size,
        "sort": [
            {"_score": "desc"},
            {"date": {"order": "desc"}},
        ],
    }

    try:
        response = es.search(index=target_index, body=query_body)
        hits = response.get("hits", {}).get("hits", [])
        total = response.get("hits", {}).get("total", {}).get("value", 0)
        return {
            "index": target_index,
            "total": total,
            "results": [hit.get("_source", {}) for hit in hits],
        }
    except ESNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Index not found: {INDEX_NAME}") from exc
    except ESConnectionError as exc:
        raise HTTPException(status_code=503, detail="Elasticsearch is unavailable") from exc
    except Exception as exc:  # pylint: disable=broad-except
        raise HTTPException(status_code=500, detail=f"Search error: {exc}") from exc


@app.get("/company/{company_id:path}")
def company_timeline(
    company_id: str,
    size: int = Query(1000, ge=1, le=5000),
) -> Dict[str, Any]:
    target_index = _active_search_index()
    query_body = {
        "query": {
            "term": {
                "company_id": company_id,
            }
        },
        "sort": [{"date": {"order": "asc"}}],
        "size": size,
    }

    try:
        response = es.search(index=target_index, body=query_body)
        timeline = [hit.get("_source", {}) for hit in response.get("hits", {}).get("hits", [])]
        return {
            "index": target_index,
            "company_id": company_id,
            "count": len(timeline),
            "timeline": timeline,
        }
    except ESNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Index not found: {INDEX_NAME}") from exc
    except ESConnectionError as exc:
        raise HTTPException(status_code=503, detail="Elasticsearch is unavailable") from exc
    except Exception as exc:  # pylint: disable=broad-except
        raise HTTPException(status_code=500, detail=f"Timeline retrieval error: {exc}") from exc
