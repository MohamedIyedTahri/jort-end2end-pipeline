from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from elasticsearch import Elasticsearch, helpers
from elasticsearch.exceptions import ConnectionError as ESConnectionError
from elasticsearch.exceptions import NotFoundError as ESNotFoundError
from elasticsearch.exceptions import TransportError
from fastapi import FastAPI, HTTPException, Query

ES_URL = "http://localhost:9200"
INDEX_NAME = "jort_events"
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


def create_index_if_needed() -> None:
    try:
        if not es.indices.exists(index=INDEX_NAME):
            es.indices.create(index=INDEX_NAME, body=INDEX_MAPPING)
            logger.info("Created index %s", INDEX_NAME)
    except ESConnectionError as exc:
        raise RuntimeError("Cannot connect to Elasticsearch at http://localhost:9200") from exc
    except TransportError as exc:
        raise RuntimeError(f"Failed to create index: {exc}") from exc


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
        }
    except Exception as exc:  # pylint: disable=broad-except
        return {
            "status": "degraded",
            "elasticsearch": False,
            "index": INDEX_NAME,
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


@app.get("/search")
def search(
    q: str = "",
    event_type: Optional[str] = None,
    tax_id: Optional[str] = None,
    start_year: Optional[int] = Query(None, ge=1900, le=2100),
    end_year: Optional[int] = Query(None, ge=1900, le=2100),
    size: int = Query(20, ge=1, le=100),
) -> Dict[str, Any]:
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
        response = es.search(index=INDEX_NAME, body=query_body)
        hits = response.get("hits", {}).get("hits", [])
        total = response.get("hits", {}).get("total", {}).get("value", 0)
        return {
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
        response = es.search(index=INDEX_NAME, body=query_body)
        timeline = [hit.get("_source", {}) for hit in response.get("hits", {}).get("hits", [])]
        return {
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
