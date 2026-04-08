from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List

KIBANA_URL = "http://localhost:5601"
STRUCTURED_PATTERN_ID = "jort-structured-pattern"


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
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Kibana API error {exc.code} on {path}: {detail}") from exc


def _create_saved_object(
    object_type: str,
    object_id: str,
    attributes: Dict[str, Any],
    references: List[Dict[str, str]] | None = None,
) -> Dict[str, Any]:
    path = f"/api/saved_objects/{object_type}/{urllib.parse.quote(object_id)}?overwrite=true"
    payload: Dict[str, Any] = {"attributes": attributes}
    if references:
        payload["references"] = references
    return _request("POST", path, payload)


def _search_source(index_ref_name: str) -> str:
    return json.dumps(
        {
            "query": {"query": "", "language": "kuery"},
            "filter": [],
            "indexRefName": index_ref_name,
        }
    )


def ensure_data_view() -> None:
    _create_saved_object(
        "index-pattern",
        STRUCTURED_PATTERN_ID,
        {"title": "jort_events_structured", "name": "JORT Events Structured"},
    )


def create_controls_visualization() -> None:
    controls_vis = {
        "title": "Dashboard Controls",
        "type": "input_control_vis",
        "params": {
            "controls": [
                {
                    "id": "1",
                    "indexPattern": STRUCTURED_PATTERN_ID,
                    "fieldName": "event_type",
                    "label": "Event Type",
                    "type": "list",
                    "options": {
                        "type": "terms",
                        "multiselect": True,
                        "dynamicOptions": True,
                        "size": 20,
                        "order": "desc",
                    },
                },
                {
                    "id": "2",
                    "indexPattern": STRUCTURED_PATTERN_ID,
                    "fieldName": "event_year",
                    "label": "Year Range",
                    "type": "range",
                    "options": {"decimalPlaces": 0, "step": 1},
                },
                {
                    "id": "3",
                    "indexPattern": STRUCTURED_PATTERN_ID,
                    "fieldName": "parse_confidence",
                    "label": "Confidence Threshold",
                    "type": "range",
                    "options": {"decimalPlaces": 2, "step": 0.05},
                },
            ],
            "updateFiltersOnChange": True,
            "useTimeFilter": False,
            "pinFilters": True,
        },
    }

    _create_saved_object(
        "visualization",
        "jort-company360-controls",
        {
            "title": "Company 360 Controls",
            "visState": json.dumps(controls_vis),
            "uiStateJSON": "{}",
            "description": "Global dashboard controls for event type, year, and confidence.",
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


def create_company_360_visuals() -> None:
    _create_saved_object(
        "visualization",
        "jort-company360-kpi-events",
        {
            "title": "Company Events",
            "visState": json.dumps(
                {
                    "title": "Company Events",
                    "type": "metric",
                    "aggs": [{"id": "1", "enabled": True, "type": "count", "schema": "metric", "params": {}}],
                    "params": {"fontSize": 52},
                }
            ),
            "uiStateJSON": "{}",
            "description": "Event count for current company/filter scope.",
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
        "jort-company360-kpi-confidence",
        {
            "title": "Avg Confidence",
            "visState": json.dumps(
                {
                    "title": "Avg Confidence",
                    "type": "metric",
                    "aggs": [{"id": "1", "enabled": True, "type": "avg", "schema": "metric", "params": {"field": "parse_confidence"}}],
                    "params": {"fontSize": 52},
                }
            ),
            "uiStateJSON": "{}",
            "description": "Average extraction confidence under active filters.",
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
        "jort-company360-lifecycle",
        {
            "title": "Lifecycle Timeline (By Event Type)",
            "visState": json.dumps(
                {
                    "title": "Lifecycle Timeline (By Event Type)",
                    "type": "line",
                    "aggs": [
                        {"id": "1", "enabled": True, "type": "count", "schema": "metric", "params": {}},
                        {
                            "id": "2",
                            "enabled": True,
                            "type": "histogram",
                            "schema": "segment",
                            "params": {"field": "event_year", "interval": 1, "min_doc_count": 1},
                        },
                        {
                            "id": "3",
                            "enabled": True,
                            "type": "terms",
                            "schema": "group",
                            "params": {"field": "event_type", "size": 10, "order": "desc", "orderBy": "1"},
                        },
                    ],
                    "params": {"addTooltip": True, "addLegend": True, "legendPosition": "right"},
                }
            ),
            "uiStateJSON": "{}",
            "description": "Company lifecycle over time; click legend/items to focus type.",
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
        "jort-company360-quality",
        {
            "title": "Quality Diagnostics",
            "visState": json.dumps(
                {
                    "title": "Quality Diagnostics",
                    "type": "horizontal_bar",
                    "aggs": [
                        {"id": "1", "enabled": True, "type": "count", "schema": "metric", "params": {}},
                        {
                            "id": "2",
                            "enabled": True,
                            "type": "filters",
                            "schema": "segment",
                            "params": {
                                "filters": [
                                    {"input": {"query": "has_tax_id:true", "language": "kuery"}, "label": "Has Tax ID"},
                                    {"input": {"query": "has_address:true", "language": "kuery"}, "label": "Has Address"},
                                    {"input": {"query": "has_activity:true", "language": "kuery"}, "label": "Has Activity"},
                                    {"input": {"query": "parse_confidence >= 0.8", "language": "kuery"}, "label": "High Confidence >= 0.8"},
                                ]
                            },
                        },
                    ],
                    "params": {"addTooltip": True, "addLegend": False, "legendPosition": "right"},
                }
            ),
            "uiStateJSON": "{}",
            "description": "Coverage and confidence quality diagnostics for current selection.",
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
        "jort-company360-selector",
        {
            "title": "Company Selector",
            "visState": json.dumps(
                {
                    "title": "Company Selector",
                    "type": "table",
                    "aggs": [
                        {
                            "id": "1",
                            "enabled": True,
                            "type": "terms",
                            "schema": "bucket",
                            "params": {"field": "company_id", "size": 25, "order": "desc", "orderBy": "2"},
                        },
                        {"id": "2", "enabled": True, "type": "count", "schema": "metric", "params": {}},
                        {"id": "3", "enabled": True, "type": "max", "schema": "metric", "params": {"field": "event_year"}},
                    ],
                    "params": {"perPage": 10, "showPartialRows": False, "showMetricsAtAllLevels": False},
                }
            ),
            "uiStateJSON": "{}",
            "description": "Click any company row to filter all dashboard panels to that company.",
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
        "jort-company360-event-subtypes",
        {
            "title": "Event Subtype Mix",
            "visState": json.dumps(
                {
                    "title": "Event Subtype Mix",
                    "type": "pie",
                    "aggs": [
                        {"id": "1", "enabled": True, "type": "count", "schema": "metric", "params": {}},
                        {
                            "id": "2",
                            "enabled": True,
                            "type": "terms",
                            "schema": "segment",
                            "params": {"field": "event_subtype", "size": 10, "order": "desc", "orderBy": "1"},
                        },
                    ],
                    "params": {"addTooltip": True, "addLegend": True, "legendPosition": "right", "isDonut": True},
                }
            ),
            "uiStateJSON": "{}",
            "description": "Subtype distribution for selected company/filters.",
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
        "jort-company360-taxid-validity-trend",
        {
            "title": "Tax ID Validity Trend",
            "visState": json.dumps(
                {
                    "title": "Tax ID Validity Trend",
                    "type": "line",
                    "aggs": [
                        {"id": "1", "enabled": True, "type": "count", "schema": "metric", "params": {}},
                        {
                            "id": "2",
                            "enabled": True,
                            "type": "histogram",
                            "schema": "segment",
                            "params": {"field": "event_year", "interval": 1, "min_doc_count": 1},
                        },
                        {
                            "id": "3",
                            "enabled": True,
                            "type": "filters",
                            "schema": "group",
                            "params": {
                                "filters": [
                                    {"input": {"query": "tax_id_valid:true", "language": "kuery"}, "label": "Valid"},
                                    {"input": {"query": "tax_id_valid:false", "language": "kuery"}, "label": "Invalid"},
                                ]
                            },
                        },
                    ],
                    "params": {"addTooltip": True, "addLegend": True, "legendPosition": "right"},
                }
            ),
            "uiStateJSON": "{}",
            "description": "Valid vs invalid tax ID volume over years.",
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
        "jort-company360-taxid-reject-reasons",
        {
            "title": "Tax ID Reject Reasons",
            "visState": json.dumps(
                {
                    "title": "Tax ID Reject Reasons",
                    "type": "horizontal_bar",
                    "aggs": [
                        {"id": "1", "enabled": True, "type": "count", "schema": "metric", "params": {}},
                        {
                            "id": "2",
                            "enabled": True,
                            "type": "terms",
                            "schema": "segment",
                            "params": {
                                "field": "tax_id_reject_reason",
                                "size": 10,
                                "order": "desc",
                                "orderBy": "1",
                            },
                        },
                    ],
                    "params": {"addTooltip": True, "addLegend": False, "legendPosition": "right"},
                }
            ),
            "uiStateJSON": "{}",
            "description": "Main causes of tax ID rejection under current filters.",
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
        "jort-company360-taxid-offenders",
        {
            "title": "Top Offending Raw Tax IDs",
            "visState": json.dumps(
                {
                    "title": "Top Offending Raw Tax IDs",
                    "type": "table",
                    "aggs": [
                        {
                            "id": "1",
                            "enabled": True,
                            "type": "terms",
                            "schema": "bucket",
                            "params": {
                                "field": "tax_id_raw",
                                "size": 20,
                                "order": "desc",
                                "orderBy": "2",
                                "exclude": "[0-9]{8}",
                            },
                        },
                        {"id": "2", "enabled": True, "type": "count", "schema": "metric", "params": {}},
                    ],
                    "params": {"perPage": 10, "showPartialRows": False, "showMetricsAtAllLevels": False},
                }
            ),
            "uiStateJSON": "{}",
            "description": "Most frequent invalid raw tax ID patterns (click to filter).",
            "version": 1,
            "kibanaSavedObjectMeta": {
                "searchSourceJSON": json.dumps(
                    {
                        "query": {"query": "tax_id_valid:false and tax_id_raw:*", "language": "kuery"},
                        "filter": [],
                        "indexRefName": "kibanaSavedObjectMeta.searchSourceJSON.index",
                    }
                )
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


def create_company_360_dashboard() -> Dict[str, Any]:
    panels = [
        {
            "version": "8.14.3",
            "type": "visualization",
            "panelIndex": "1",
            "gridData": {"x": 0, "y": 0, "w": 24, "h": 6, "i": "1"},
            "embeddableConfig": {},
            "panelRefName": "panel_0",
        },
        {
            "version": "8.14.3",
            "type": "visualization",
            "panelIndex": "2",
            "gridData": {"x": 0, "y": 6, "w": 8, "h": 7, "i": "2"},
            "embeddableConfig": {},
            "panelRefName": "panel_1",
        },
        {
            "version": "8.14.3",
            "type": "visualization",
            "panelIndex": "3",
            "gridData": {"x": 8, "y": 6, "w": 8, "h": 7, "i": "3"},
            "embeddableConfig": {},
            "panelRefName": "panel_2",
        },
        {
            "version": "8.14.3",
            "type": "visualization",
            "panelIndex": "4",
            "gridData": {"x": 16, "y": 6, "w": 8, "h": 13, "i": "4"},
            "embeddableConfig": {},
            "panelRefName": "panel_3",
        },
        {
            "version": "8.14.3",
            "type": "visualization",
            "panelIndex": "5",
            "gridData": {"x": 0, "y": 13, "w": 16, "h": 13, "i": "5"},
            "embeddableConfig": {},
            "panelRefName": "panel_4",
        },
        {
            "version": "8.14.3",
            "type": "visualization",
            "panelIndex": "6",
            "gridData": {"x": 0, "y": 26, "w": 12, "h": 12, "i": "6"},
            "embeddableConfig": {},
            "panelRefName": "panel_5",
        },
        {
            "version": "8.14.3",
            "type": "visualization",
            "panelIndex": "7",
            "gridData": {"x": 12, "y": 26, "w": 12, "h": 12, "i": "7"},
            "embeddableConfig": {},
            "panelRefName": "panel_6",
        },
        {
            "version": "8.14.3",
            "type": "visualization",
            "panelIndex": "8",
            "gridData": {"x": 0, "y": 38, "w": 8, "h": 12, "i": "8"},
            "embeddableConfig": {},
            "panelRefName": "panel_7",
        },
        {
            "version": "8.14.3",
            "type": "visualization",
            "panelIndex": "9",
            "gridData": {"x": 8, "y": 38, "w": 8, "h": 12, "i": "9"},
            "embeddableConfig": {},
            "panelRefName": "panel_8",
        },
        {
            "version": "8.14.3",
            "type": "visualization",
            "panelIndex": "10",
            "gridData": {"x": 16, "y": 38, "w": 8, "h": 12, "i": "10"},
            "embeddableConfig": {},
            "panelRefName": "panel_9",
        },
    ]

    attributes = {
        "title": "JORT Company 360 Dashboard",
        "description": "Company-centric lifecycle and quality diagnostics with executive controls. Click company rows/charts to inspect one company.",
        "hits": 0,
        "optionsJSON": json.dumps({"useMargins": True, "syncColors": True, "hidePanelTitles": False}),
        "panelsJSON": json.dumps(panels),
        "version": 1,
        "kibanaSavedObjectMeta": {
            "searchSourceJSON": json.dumps({"query": {"language": "kuery", "query": ""}, "filter": []})
        },
    }

    references = [
        {"name": "panel_0", "type": "visualization", "id": "jort-company360-controls"},
        {"name": "panel_1", "type": "visualization", "id": "jort-company360-kpi-events"},
        {"name": "panel_2", "type": "visualization", "id": "jort-company360-kpi-confidence"},
        {"name": "panel_3", "type": "visualization", "id": "jort-company360-selector"},
        {"name": "panel_4", "type": "visualization", "id": "jort-company360-lifecycle"},
        {"name": "panel_5", "type": "visualization", "id": "jort-company360-quality"},
        {"name": "panel_6", "type": "visualization", "id": "jort-company360-event-subtypes"},
        {"name": "panel_7", "type": "visualization", "id": "jort-company360-taxid-validity-trend"},
        {"name": "panel_8", "type": "visualization", "id": "jort-company360-taxid-reject-reasons"},
        {"name": "panel_9", "type": "visualization", "id": "jort-company360-taxid-offenders"},
    ]

    return _create_saved_object("dashboard", "jort-company-360-dashboard", attributes, references)


def main() -> None:
    ensure_data_view()
    create_controls_visualization()
    create_company_360_visuals()
    dashboard = create_company_360_dashboard()
    url = (
        f"{KIBANA_URL}/app/dashboards#/view/{dashboard['id']}"
        "?_g=(refreshInterval:(pause:!t,value:0),time:(from:now-15y,to:now))"
    )
    print(json.dumps({"status": "ok", "dashboard_id": dashboard["id"], "dashboard_url": url}, ensure_ascii=True))


if __name__ == "__main__":
    main()
