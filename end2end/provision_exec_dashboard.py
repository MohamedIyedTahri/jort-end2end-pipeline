from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List

KIBANA_URL = "http://localhost:5601"

STRUCTURED_PATTERN_ID = "jort-structured-pattern"
PROFILE_PATTERN_ID = "jort-profile-pattern"


def _request(method: str, path: str, payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
    url = f"{KIBANA_URL}{path}"
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url=url,
        data=data,
        method=method,
        headers={
            "Content-Type": "application/json",
            "kbn-xsrf": "true",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8")
            if not body:
                return {}
            return json.loads(body)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Kibana API error {exc.code} on {path}: {detail}") from exc


def _create_saved_object(
    object_type: str,
    object_id: str,
    attributes: Dict[str, Any],
    references: List[Dict[str, str]] | None = None,
) -> Dict[str, Any]:
    suffix = f"/api/saved_objects/{object_type}/{urllib.parse.quote(object_id)}?overwrite=true"
    payload: Dict[str, Any] = {"attributes": attributes}
    if references:
        payload["references"] = references
    return _request("POST", suffix, payload)


def _search_source(index_ref_name: str) -> str:
    return json.dumps(
        {
            "query": {"query": "", "language": "kuery"},
            "filter": [],
            "indexRefName": index_ref_name,
        }
    )


def _create_data_views() -> None:
    _create_saved_object(
        "index-pattern",
        STRUCTURED_PATTERN_ID,
        {"title": "jort_events_structured", "name": "JORT Events Structured"},
    )
    _create_saved_object(
        "index-pattern",
        PROFILE_PATTERN_ID,
        {"title": "jort_company_profile", "name": "JORT Company Profile"},
    )


def _create_visualizations() -> None:
    _create_saved_object(
        "visualization",
        "jort-exec-kpi-events",
        {
            "title": "Total Events",
            "visState": json.dumps(
                {
                    "title": "Total Events",
                    "type": "metric",
                    "aggs": [
                        {
                            "id": "1",
                            "enabled": True,
                            "type": "count",
                            "schema": "metric",
                            "params": {},
                        }
                    ],
                    "params": {"fontSize": 56},
                }
            ),
            "uiStateJSON": "{}",
            "description": "Total number of structured events",
            "version": 1,
            "kibanaSavedObjectMeta": {
                "searchSourceJSON": _search_source("kibanaSavedObjectMeta.searchSourceJSON.index")
            },
        },
        references=[
            {
                "name": "kibanaSavedObjectMeta.searchSourceJSON.index",
                "type": "index-pattern",
                "id": STRUCTURED_PATTERN_ID,
            }
        ],
    )

    _create_saved_object(
        "visualization",
        "jort-exec-kpi-companies",
        {
            "title": "Total Companies",
            "visState": json.dumps(
                {
                    "title": "Total Companies",
                    "type": "metric",
                    "aggs": [
                        {
                            "id": "1",
                            "enabled": True,
                            "type": "cardinality",
                            "schema": "metric",
                            "params": {"field": "company_id"},
                        }
                    ],
                    "params": {"fontSize": 56},
                }
            ),
            "uiStateJSON": "{}",
            "description": "Distinct companies in structured events",
            "version": 1,
            "kibanaSavedObjectMeta": {
                "searchSourceJSON": _search_source("kibanaSavedObjectMeta.searchSourceJSON.index")
            },
        },
        references=[
            {
                "name": "kibanaSavedObjectMeta.searchSourceJSON.index",
                "type": "index-pattern",
                "id": STRUCTURED_PATTERN_ID,
            }
        ],
    )

    _create_saved_object(
        "visualization",
        "jort-exec-kpi-confidence",
        {
            "title": "Avg Parse Confidence",
            "visState": json.dumps(
                {
                    "title": "Avg Parse Confidence",
                    "type": "metric",
                    "aggs": [
                        {
                            "id": "1",
                            "enabled": True,
                            "type": "avg",
                            "schema": "metric",
                            "params": {"field": "parse_confidence"},
                        }
                    ],
                    "params": {"fontSize": 56},
                }
            ),
            "uiStateJSON": "{}",
            "description": "Average extraction confidence",
            "version": 1,
            "kibanaSavedObjectMeta": {
                "searchSourceJSON": _search_source("kibanaSavedObjectMeta.searchSourceJSON.index")
            },
        },
        references=[
            {
                "name": "kibanaSavedObjectMeta.searchSourceJSON.index",
                "type": "index-pattern",
                "id": STRUCTURED_PATTERN_ID,
            }
        ],
    )

    _create_saved_object(
        "visualization",
        "jort-exec-events-by-year",
        {
            "title": "Events Trend by Year",
            "visState": json.dumps(
                {
                    "title": "Events Trend by Year",
                    "type": "histogram",
                    "aggs": [
                        {
                            "id": "1",
                            "enabled": True,
                            "type": "count",
                            "schema": "metric",
                            "params": {},
                        },
                        {
                            "id": "2",
                            "enabled": True,
                            "type": "histogram",
                            "schema": "segment",
                            "params": {
                                "field": "event_year",
                                "interval": 1,
                                "min_doc_count": 1,
                            },
                        },
                    ],
                    "params": {
                        "addTooltip": True,
                        "addLegend": False,
                        "legendPosition": "right",
                    },
                }
            ),
            "uiStateJSON": "{}",
            "description": "Yearly trend of events",
            "version": 1,
            "kibanaSavedObjectMeta": {
                "searchSourceJSON": _search_source("kibanaSavedObjectMeta.searchSourceJSON.index")
            },
        },
        references=[
            {
                "name": "kibanaSavedObjectMeta.searchSourceJSON.index",
                "type": "index-pattern",
                "id": STRUCTURED_PATTERN_ID,
            }
        ],
    )

    _create_saved_object(
        "visualization",
        "jort-exec-events-by-type",
        {
            "title": "Events by Type",
            "visState": json.dumps(
                {
                    "title": "Events by Type",
                    "type": "pie",
                    "aggs": [
                        {
                            "id": "1",
                            "enabled": True,
                            "type": "count",
                            "schema": "metric",
                            "params": {},
                        },
                        {
                            "id": "2",
                            "enabled": True,
                            "type": "terms",
                            "schema": "segment",
                            "params": {
                                "field": "event_type",
                                "size": 10,
                                "order": "desc",
                                "orderBy": "1",
                            },
                        },
                    ],
                    "params": {
                        "addTooltip": True,
                        "addLegend": True,
                        "legendPosition": "right",
                        "isDonut": True,
                    },
                }
            ),
            "uiStateJSON": "{}",
            "description": "Distribution of event types",
            "version": 1,
            "kibanaSavedObjectMeta": {
                "searchSourceJSON": _search_source("kibanaSavedObjectMeta.searchSourceJSON.index")
            },
        },
        references=[
            {
                "name": "kibanaSavedObjectMeta.searchSourceJSON.index",
                "type": "index-pattern",
                "id": STRUCTURED_PATTERN_ID,
            }
        ],
    )

    _create_saved_object(
        "visualization",
        "jort-exec-top-companies",
        {
            "title": "Top Companies by Events",
            "visState": json.dumps(
                {
                    "title": "Top Companies by Events",
                    "type": "horizontal_bar",
                    "aggs": [
                        {
                            "id": "1",
                            "enabled": True,
                            "type": "max",
                            "schema": "metric",
                            "params": {"field": "events_count"},
                        },
                        {
                            "id": "2",
                            "enabled": True,
                            "type": "terms",
                            "schema": "segment",
                            "params": {
                                "field": "company_id",
                                "size": 15,
                                "order": "desc",
                                "orderBy": "1",
                            },
                        },
                    ],
                    "params": {
                        "addTooltip": True,
                        "addLegend": False,
                        "legendPosition": "right",
                    },
                }
            ),
            "uiStateJSON": "{}",
            "description": "Most active companies",
            "version": 1,
            "kibanaSavedObjectMeta": {
                "searchSourceJSON": _search_source("kibanaSavedObjectMeta.searchSourceJSON.index")
            },
        },
        references=[
            {
                "name": "kibanaSavedObjectMeta.searchSourceJSON.index",
                "type": "index-pattern",
                "id": PROFILE_PATTERN_ID,
            }
        ],
    )

    _create_saved_object(
        "visualization",
        "jort-exec-company-inspector",
        {
            "title": "Company Inspector",
            "visState": json.dumps(
                {
                    "title": "Company Inspector",
                    "type": "table",
                    "aggs": [
                        {
                            "id": "1",
                            "enabled": True,
                            "type": "terms",
                            "schema": "bucket",
                            "params": {
                                "field": "company_id",
                                "size": 20,
                                "order": "desc",
                                "orderBy": "2",
                            },
                        },
                        {
                            "id": "2",
                            "enabled": True,
                            "type": "max",
                            "schema": "metric",
                            "params": {"field": "events_count"},
                        },
                        {
                            "id": "3",
                            "enabled": True,
                            "type": "max",
                            "schema": "metric",
                            "params": {"field": "last_seen_year"},
                        },
                        {
                            "id": "4",
                            "enabled": True,
                            "type": "min",
                            "schema": "metric",
                            "params": {"field": "first_seen_year"},
                        },
                    ],
                    "params": {"perPage": 10, "showPartialRows": False, "showMetricsAtAllLevels": False},
                }
            ),
            "uiStateJSON": "{}",
            "description": "Click a company in this table to filter all dashboard panels",
            "version": 1,
            "kibanaSavedObjectMeta": {
                "searchSourceJSON": _search_source("kibanaSavedObjectMeta.searchSourceJSON.index")
            },
        },
        references=[
            {
                "name": "kibanaSavedObjectMeta.searchSourceJSON.index",
                "type": "index-pattern",
                "id": PROFILE_PATTERN_ID,
            }
        ],
    )


def _create_dashboard() -> Dict[str, Any]:
    panels = [
        {
            "version": "8.14.3",
            "type": "visualization",
            "panelIndex": "1",
            "gridData": {"x": 0, "y": 0, "w": 8, "h": 7, "i": "1"},
            "embeddableConfig": {},
            "panelRefName": "panel_0",
        },
        {
            "version": "8.14.3",
            "type": "visualization",
            "panelIndex": "2",
            "gridData": {"x": 8, "y": 0, "w": 8, "h": 7, "i": "2"},
            "embeddableConfig": {},
            "panelRefName": "panel_1",
        },
        {
            "version": "8.14.3",
            "type": "visualization",
            "panelIndex": "3",
            "gridData": {"x": 16, "y": 0, "w": 8, "h": 7, "i": "3"},
            "embeddableConfig": {},
            "panelRefName": "panel_2",
        },
        {
            "version": "8.14.3",
            "type": "visualization",
            "panelIndex": "4",
            "gridData": {"x": 0, "y": 7, "w": 12, "h": 11, "i": "4"},
            "embeddableConfig": {},
            "panelRefName": "panel_3",
        },
        {
            "version": "8.14.3",
            "type": "visualization",
            "panelIndex": "5",
            "gridData": {"x": 12, "y": 7, "w": 12, "h": 11, "i": "5"},
            "embeddableConfig": {},
            "panelRefName": "panel_4",
        },
        {
            "version": "8.14.3",
            "type": "visualization",
            "panelIndex": "6",
            "gridData": {"x": 0, "y": 18, "w": 12, "h": 12, "i": "6"},
            "embeddableConfig": {},
            "panelRefName": "panel_5",
        },
        {
            "version": "8.14.3",
            "type": "visualization",
            "panelIndex": "7",
            "gridData": {"x": 12, "y": 18, "w": 12, "h": 12, "i": "7"},
            "embeddableConfig": {},
            "panelRefName": "panel_6",
        },
    ]

    attributes = {
        "title": "JORT Executive Decision Dashboard",
        "description": "Executive BI dashboard for operational decision-making. Click a company in Top Companies or Company Inspector to filter all panels.",
        "hits": 0,
        "optionsJSON": json.dumps(
            {
                "useMargins": True,
                "syncColors": True,
                "hidePanelTitles": False,
            }
        ),
        "panelsJSON": json.dumps(panels),
        "version": 1,
        "kibanaSavedObjectMeta": {
            "searchSourceJSON": json.dumps(
                {
                    "query": {"language": "kuery", "query": ""},
                    "filter": [],
                }
            )
        },
    }

    references = [
        {"name": "panel_0", "type": "visualization", "id": "jort-exec-kpi-events"},
        {"name": "panel_1", "type": "visualization", "id": "jort-exec-kpi-companies"},
        {"name": "panel_2", "type": "visualization", "id": "jort-exec-kpi-confidence"},
        {"name": "panel_3", "type": "visualization", "id": "jort-exec-events-by-year"},
        {"name": "panel_4", "type": "visualization", "id": "jort-exec-events-by-type"},
        {"name": "panel_5", "type": "visualization", "id": "jort-exec-top-companies"},
        {"name": "panel_6", "type": "visualization", "id": "jort-exec-company-inspector"},
    ]

    return _create_saved_object("dashboard", "jort-executive-dashboard", attributes, references)


def main() -> None:
    _create_data_views()
    _create_visualizations()
    dashboard = _create_dashboard()

    dashboard_url = (
        f"{KIBANA_URL}/app/dashboards#/view/{dashboard['id']}"
        "?_g=(refreshInterval:(pause:!t,value:0),time:(from:now-15y,to:now))"
    )
    print(json.dumps({"status": "ok", "dashboard_id": dashboard["id"], "dashboard_url": dashboard_url}, ensure_ascii=True))


if __name__ == "__main__":
    main()
