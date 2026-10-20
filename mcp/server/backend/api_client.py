# -*- coding:utf-8 -*-
# ! usr/bin/env python3
"""
HTTP client for the AD-Alterome Retrieval API.

The MCP server uses this module so MCP tools no longer query SQLite directly.
SQLite access is centralized behind api_server.py.
"""

import json
from typing import Any, Dict
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .config import ADALTEROME_API_BASE_URL, ADALTEROME_API_TIMEOUT


def _api_error(tool: str, query: Dict[str, Any], message: str) -> Dict[str, Any]:
    return {
        "tool": tool,
        "status": "error",
        "query": query,
        "count": 0,
        "data": {},
        "meta": {
            "message": message,
            "api_base_url": ADALTEROME_API_BASE_URL,
        },
    }


def _get_json(path: str, params: Dict[str, Any] | None = None) -> Dict[str, Any]:
    query = urlencode(params or {}, doseq=True)
    url = f"{ADALTEROME_API_BASE_URL}{path}"
    if query:
        url = f"{url}?{query}"

    request = Request(url, headers={"Accept": "application/json"})
    with urlopen(request, timeout=ADALTEROME_API_TIMEOUT) as response:
        raw = response.read().decode("utf-8")
    return json.loads(raw)


def _call_tool_api(path: str, tool: str, query: Dict[str, Any]) -> Dict[str, Any]:
    try:
        return _get_json(path, query)
    except HTTPError as exc:
        return _api_error(tool, query, f"API HTTP error {exc.code}: {exc.reason}")
    except URLError as exc:
        return _api_error(tool, query, f"API connection error: {exc.reason}")
    except Exception as exc:
        return _api_error(tool, query, f"API request failed: {exc}")


def get_schema() -> Dict[str, Any]:
    try:
        return _get_json("/schema")
    except Exception as exc:
        return {
            "table_exists": False,
            "table_name": "ADAlteromeModel",
            "columns": [],
            "row_count": 0,
            "error": f"API request failed: {exc}",
            "api_base_url": ADALTEROME_API_BASE_URL,
        }


def list_hypotheses() -> Dict[str, Any]:
    return _call_tool_api("/hypotheses", "list_hypotheses", {})


def query_gene_events(gene: str, top_k: int = 10) -> Dict[str, Any]:
    query = {"gene": gene, "top_k": top_k}
    return _call_tool_api("/gene/events", "query_gene_events", query)


def query_term_events(term: str, top_k: int = 10) -> Dict[str, Any]:
    query = {"term": term, "top_k": top_k}
    return _call_tool_api("/term/events", "query_term_events", query)


def query_hypothesis_support(hypothesis: str, top_k: int = 10) -> Dict[str, Any]:
    query = {"hypothesis": hypothesis, "top_k": top_k}
    return _call_tool_api("/hypothesis/support", "query_hypothesis_support", query)


def curate_gene_evidence(gene: str, selected_limit: int = 30) -> Dict[str, Any]:
    query = {"gene": gene, "selected_limit": selected_limit}
    return _call_tool_api("/gene/curation", "curate_gene_evidence", query)


def curate_term_evidence(term: str, selected_limit: int = 30) -> Dict[str, Any]:
    query = {"term": term, "selected_limit": selected_limit}
    return _call_tool_api("/term/curation", "curate_term_evidence", query)


def curate_hypothesis_evidence(hypothesis: str, selected_limit: int = 30) -> Dict[str, Any]:
    query = {"hypothesis": hypothesis, "selected_limit": selected_limit}
    return _call_tool_api("/hypothesis/curation", "curate_hypothesis_evidence", query)


def curate_compound_evidence(
    gene: str | None = None,
    term: str | None = None,
    hypothesis: str | None = None,
    selected_limit: int = 30,
    fallback: str = "axis_merge",
) -> Dict[str, Any]:
    query: Dict[str, Any] = {"selected_limit": selected_limit, "fallback": fallback}
    if gene:
        query["gene"] = gene
    if term:
        query["term"] = term
    if hypothesis:
        query["hypothesis"] = hypothesis
    return _call_tool_api("/compound/curation", "curate_compound_evidence", query)


def get_gene_overview(gene: str) -> Dict[str, Any]:
    query = {"gene": gene}
    return _call_tool_api("/gene/overview", "get_gene_overview", query)


def get_hypothesis_overview(hypothesis: str) -> Dict[str, Any]:
    query = {"hypothesis": hypothesis}
    return _call_tool_api("/hypothesis/overview", "get_hypothesis_overview", query)


def get_term_overview(term: str) -> Dict[str, Any]:
    query = {"term": term}
    return _call_tool_api("/term/overview", "get_term_overview", query)


def compare_genes(gene_a: str, gene_b: str) -> Dict[str, Any]:
    query = {"gene_a": gene_a, "gene_b": gene_b}
    return _call_tool_api("/compare/genes", "compare_genes", query)
