# -*- coding:utf-8 -*-
# ! usr/bin/env python3
"""AD-Alterome web QA orchestration and evidence selection."""

import asyncio
import hashlib
import json
import re
import shutil
import time
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from django.conf import settings
from django.core.cache import cache
from openai import OpenAI, DefaultHttpxClient

from .mcp_client import McpRetrievalError, call_mcp_tool
from .codex_llm import CodexCompletionError, codex_json_completion

_LLM_TRACE_SINK = ContextVar("adalterome_llm_trace", default=None)

ROUTE_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "mode": {"type": "string", "enum": ["gene", "hypothesis", "term", "compare"]},
        **{field: {"type": ["string", "null"]}
           for field in ("gene", "hypothesis", "term", "gene_a", "gene_b")},
    },
    "required": ["mode", "gene", "hypothesis", "term", "gene_a", "gene_b"],
}
SUMMARY_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "claims": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "properties": {"heading": {"type": "string"}, "text": {"type": "string"},
                           "refs": {"type": "array", "items": {"type": "integer"}}},
            "required": ["heading", "text", "refs"],
        }},
        "limitations": {"type": "string"},
    },
    "required": ["claims", "limitations"],
}

MCP_CACHE_TIMEOUT = int(getattr(settings, "ADALTEROME_MCP_CACHE_TIMEOUT", 300))
SUPPORTED_MODES = {"auto", "gene", "hypothesis", "term", "compare"}
GENE_TOKEN_STOPWORDS = {
    "AD",
    "ALTEROME",
    "AND",
    "COMPARE",
    "GENE",
    "MCP",
    "PMID",
    "PMIDS",
    "QA",
}


def _cache_key(name: str, args: Dict[str, Any]) -> str:
    raw_key = json.dumps(args, ensure_ascii=False, sort_keys=True).encode("utf-8")
    digest = hashlib.sha256(raw_key).hexdigest()
    return f"adalterome:mcp-qa:mcp-v1:{settings.ADALTEROME_MCP_URL}:{name}:{digest}"


def _llm_client(
    api_key: Optional[str] = None,
    allow_server_key: bool = True,
    provider: str = "deepseek",
) -> OpenAI:
    resolved_provider = _resolve_llm_provider(api_key, allow_server_key, provider)
    server_key = ""
    if allow_server_key:
        server_key = (getattr(settings, "ADALTEROME_OPENAI_API_KEY", "")
                      if resolved_provider == "openai" else settings.ADALTEROME_DEEPSEEK_API_KEY)
    resolved_api_key = (api_key or server_key or "").strip()
    if not resolved_api_key:
        raise RuntimeError("AD-Alterome AI summarization service is not configured")
    provider_config = _llm_provider_config(resolved_provider)
    if not provider_config:
        raise ValueError("Unsupported AI provider")
    client_options = {}
    if resolved_provider == "openai":
        client_options["max_retries"] = 0
    if getattr(settings, "ADALTEROME_USE_SYSTEM_TRUST", False):
        import ssl
        import truststore
        client_options["http_client"] = DefaultHttpxClient(
            verify=truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        )
    return OpenAI(
        api_key=resolved_api_key,
        base_url=provider_config["base_url"],
        **client_options,
    )


def _llm_provider_config(provider: str) -> Dict[str, Any]:
    configured = getattr(settings, "ADALTEROME_BYOK_PROVIDERS", {}).get(provider)
    if not configured:
        raise ValueError("Unsupported AI provider")
    provider_config = dict(configured)
    if provider == "deepseek":
        provider_config["base_url"] = settings.ADALTEROME_DEEPSEEK_BASE_URL.rstrip("/")
    return provider_config


def _resolve_llm_model(
    api_key: Optional[str] = None,
    allow_server_key: bool = True,
    provider: str = "deepseek",
    model: Optional[str] = None,
) -> str:
    if allow_server_key and not api_key:
        if _resolve_llm_provider(api_key, allow_server_key, provider) in {"openai", "codex"}:
            return settings.ADALTEROME_OPENAI_MODEL
        return settings.ADALTEROME_DEEPSEEK_MODEL
    provider_config = _llm_provider_config(provider)
    allowed_models = tuple(provider_config.get("models") or ())
    resolved_model = (model or (allowed_models[0] if allowed_models else "")).strip()
    if not resolved_model or resolved_model not in allowed_models:
        raise ValueError("Unsupported AI model")
    return resolved_model


def _resolve_llm_provider(api_key=None, allow_server_key=True, provider="deepseek"):
    server_mode = allow_server_key and not api_key
    backend = (getattr(settings, "ADALTEROME_MCP_LLM_BACKEND", "deepseek")
               if server_mode else provider)
    allowed = {"deepseek", "openai", "codex"} if server_mode else {"deepseek", "openai", "qwen"}
    if backend not in allowed:
        raise ValueError("Unsupported AI backend")
    return backend


def server_llm_available():
    backend = _resolve_llm_provider()
    if backend == "codex":
        return bool(shutil.which(getattr(settings, "ADALTEROME_CODEX_EXECUTABLE", "codex")))
    if backend == "openai":
        return bool(getattr(settings, "ADALTEROME_OPENAI_API_KEY", ""))
    return bool(settings.ADALTEROME_DEEPSEEK_API_KEY)


def _response_dict(response):
    value = response.model_dump(mode="json")
    return value if isinstance(value, dict) else {}


def _usage_counts(usage):
    usage = usage if isinstance(usage, dict) else {}
    result = {
        "input_tokens": usage.get("input_tokens", usage.get("prompt_tokens")),
        "output_tokens": usage.get("output_tokens", usage.get("completion_tokens")),
        "cached_input_tokens": usage.get("cached_input_tokens"),
        "reasoning_output_tokens": usage.get("reasoning_output_tokens"),
        "total_tokens": usage.get("total_tokens"),
    }
    if result["total_tokens"] is None and all(
        isinstance(result[key], int) for key in ("input_tokens", "output_tokens")
    ):
        result["total_tokens"] = result["input_tokens"] + result["output_tokens"]
    for field, source, key in (
        ("cached_input_tokens", "input_tokens_details", "cached_tokens"),
        ("reasoning_output_tokens", "output_tokens_details", "reasoning_tokens"),
    ):
        details = usage.get(source) or {}
        if isinstance(details, dict) and key in details:
            result[field] = details[key]
    return result


def _complete_json(stage, system_prompt, user_prompt, schema, *, api_key=None,
                   allow_server_key=True, provider="deepseek", model=None,
                   temperature=0.1):
    backend = _resolve_llm_provider(api_key, allow_server_key, provider)
    resolved_model = _resolve_llm_model(api_key, allow_server_key, backend, model)
    effort = getattr(settings, "ADALTEROME_OPENAI_REASONING_EFFORT", "high")
    timeout = float(getattr(settings, "ADALTEROME_MCP_LLM_TIMEOUT", 300))
    messages = [{"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}]
    trace = {"stage": stage, "backend": backend, "requested_model": resolved_model,
             "response_model": None, "reasoning_effort": effort if backend in {"openai", "codex"} else None,
             "started_at": datetime.now(timezone.utc).isoformat(), "success": False,
             "request": {"messages": messages, "model": resolved_model}, "usage": {}}
    started = time.perf_counter()
    try:
        if backend == "codex":
            trace["request"].update({"schema": schema, "reasoning_effort": effort})
            text, raw_response = codex_json_completion(
                system_prompt, user_prompt, schema, model=resolved_model,
                reasoning_effort=effort, timeout=timeout,
                executable=getattr(settings, "ADALTEROME_CODEX_EXECUTABLE", "codex"),
            )
        elif backend == "openai":
            request = {
                "model": resolved_model, "instructions": system_prompt,
                "input": user_prompt, "reasoning": {"effort": effort},
                "text": {"format": {"type": "json_schema", "name": stage,
                                     "strict": True, "schema": schema}},
                "tools": [], "tool_choice": "none", "store": False,
                "timeout": timeout,
            }
            trace["request"] = request
            response = _llm_client(api_key, allow_server_key, backend).responses.create(**request)
            raw_response = _response_dict(response)
            text = response.output_text
            if raw_response.get("status") not in {None, "completed"}:
                trace["response"] = raw_response
                raise RuntimeError("OpenAI response was incomplete")
        else:
            request = {"model": resolved_model, "messages": messages,
                       "temperature": temperature}
            trace["request"] = request
            response = _llm_client(api_key, allow_server_key, backend).chat.completions.create(**request)
            raw_response = _response_dict(response)
            text = response.choices[0].message.content or ""
        trace["response"] = raw_response
        trace["response_model"] = raw_response.get("response_model", raw_response.get("model"))
        trace["usage"] = _usage_counts(raw_response.get("usage"))
        trace["output_text"] = text
        payload = _parse_json_response(text)
        if not payload or (stage == "summary" and not isinstance(payload.get("claims"), list)):
            raise RuntimeError("AI response did not match the expected JSON object")
        trace["success"] = True
        return text
    except Exception as exc:
        trace["error_type"] = type(exc).__name__
        if isinstance(exc, CodexCompletionError):
            trace["response"] = exc.trace
        raise
    finally:
        trace["duration_seconds"] = time.perf_counter() - started
        sink = _LLM_TRACE_SINK.get()
        if sink is not None:
            sink.append(trace)


def evidence_sample_limit():
    return max(1, min(int(getattr(settings, "ADALTEROME_MCP_EVIDENCE_LIMIT", 30)), 30))


def evidence_candidate_limit(limit):
    return min(50, limit * 3)


def pick_evidence_rows(rows, limit=3):
    if limit <= 0:
        return []
    candidates = []
    seen_records = set()
    for row in rows:
        evidence = row.get("Evidence") or {}
        source = row.get("source") or {}
        article = evidence.get("article") or {}
        interpretation = evidence.get("ad_interpretation") or {}
        pmid = source.get("pmid") or row.get("PMID")
        evidence_text = evidence.get("sentence") or row.get("Sentence")
        if str(evidence_text or "").strip() in {"", "-"} or str(pmid or "").strip() in {"", "-"}:
            continue
        record_key = " ".join(str(evidence_text).split())
        if record_key in seen_records:
            continue
        seen_records.add(record_key)

        candidates.append(
            {
                "Gene": row.get("Gene"),
                "TermName": row.get("TermName"),
                "Hypothesis": row.get("Hypothesis"),
                "PMID": pmid,
                "PubMedURL": source.get("pubmed_url") or row.get("PubMedURL"),
                "RetrievalSource": row.get("RetrievalSource", "ranked_events"),
                "EvidenceText": evidence_text,
                "RichSentenceHTML": evidence.get("rich_sentence_html") or row.get("RichSentence"),
                "Journal": article.get("journal") or row.get("Journal"),
                "Year": article.get("year") or row.get("Year"),
                "MajorMeSH": article.get("major_mesh_index", []),
                "PubTypes": article.get("pubtypes", []),
                "Event": evidence.get("event") or row.get("Event"),
                "Definition": interpretation.get("definition") or row.get("Definition"),
                "ExtendedExplanation": interpretation.get("extended_explanation") or row.get("ExtendedExplanation"),
            }
        )
    # Preserve upstream relevance order while preferring distinct publications.
    picked, remaining, seen_pmids = [], [], set()
    for candidate in candidates:
        pmid = str(candidate["PMID"])
        if pmid in seen_pmids:
            remaining.append(candidate)
        else:
            picked.append(candidate)
            seen_pmids.add(pmid)
    return (picked + remaining)[:limit]


def build_evidence_traces(items, label=None, limit=4, start_index=1):
    traces = []
    for offset, item in enumerate((items or [])[:limit]):
        pmid = item.get("PMID")
        pubmed_url = item.get("PubMedURL")
        if not pubmed_url and pmid:
            pubmed_url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"

        traces.append(
            {
                "RefID": start_index + offset,
                "label": label,
                "Gene": item.get("Gene"),
                "TermName": item.get("TermName"),
                "Hypothesis": item.get("Hypothesis"),
                "PMID": pmid,
                "PubMedURL": pubmed_url,
                "Journal": item.get("Journal"),
                "Year": item.get("Year"),
                "Sentence": item.get("EvidenceText"),
                "RichSentenceHTML": item.get("RichSentenceHTML"),
                "RetrievalSource": item.get("RetrievalSource"),
            }
        )
    return traces


def without_internal_scores(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        key: value
        for key, value in (payload or {}).items()
        if "evidence_score" not in key.lower()
        and "quality_score" not in key.lower()
    }


def guess_compare_by_regex(question: str) -> Optional[Dict[str, Any]]:
    q = question.strip()
    if not any(x in q.lower() for x in ["compare", "vs"]) and "比较" not in q:
        return None

    genes = extract_gene_symbols(q)
    if len(genes) >= 2:
        return {
            "mode": "compare",
            "gene_a": genes[0],
            "gene_b": genes[1],
        }
    return None


def extract_gene_symbols(question: str):
    tokens = [
        token.strip("-")
        for token in re.findall(r"\b[A-Z][A-Z0-9\-]{1,14}\b", question)
    ]
    return [
        token
        for token in dict.fromkeys(tokens)
        if token not in GENE_TOKEN_STOPWORDS
    ]


def extract_hypothesis(question: str) -> Optional[str]:
    matches = re.findall(
        r"\b([A-Z][A-Za-z0-9-]*(?:\s+[A-Z][A-Za-z0-9-]*){0,4}\s+Hypothesis)\b",
        question,
    )
    return max(matches, key=len) if matches else None


def extract_term(question: str) -> str:
    patterns = (
        r"associated with\s+(.+?)(?:\?|$)",
        r"evidence (?:for|about)\s+(.+?)(?:\?|$)",
        r"(?:term|phenotype)\s+(.+?)(?:\?|$)",
    )
    for pattern in patterns:
        match = re.search(pattern, question, flags=re.IGNORECASE)
        if match:
            term = re.sub(
                r"\s+in\s+AD-Alterome\.?$",
                "",
                match.group(1).strip(),
                flags=re.IGNORECASE,
            )
            if term:
                return term
    return question.strip().rstrip("?.")


def deterministic_route(question: str, requested_mode: str) -> Dict[str, Any]:
    compare_route = guess_compare_by_regex(question)
    hypothesis = extract_hypothesis(question)
    genes = extract_gene_symbols(question)

    if requested_mode == "compare":
        if compare_route:
            return compare_route
        raise ValueError("Compare mode requires two gene symbols")
    if requested_mode == "gene":
        if genes:
            return {"mode": "gene", "gene": genes[0]}
        raise ValueError("Gene mode requires a gene symbol")
    if requested_mode == "hypothesis":
        if hypothesis:
            return {"mode": "hypothesis", "hypothesis": hypothesis}
        return {"mode": "hypothesis", "hypothesis": question.strip().rstrip("?.")}
    if requested_mode == "term":
        return {"mode": "term", "term": extract_term(question)}

    if compare_route:
        return compare_route
    if hypothesis:
        return {"mode": "hypothesis", "hypothesis": hypothesis}
    if genes:
        return {"mode": "gene", "gene": genes[0]}
    return {"mode": "term", "term": extract_term(question)}


def route_question_with_llm(
    question: str,
    requested_mode: str = "auto",
    api_key: Optional[str] = None,
    allow_server_key: bool = True,
    provider: str = "deepseek",
    model: Optional[str] = None,
) -> Dict[str, Any]:
    if requested_mode not in SUPPORTED_MODES:
        raise ValueError("Unsupported MCP QA mode")

    cache_key = _cache_key(
        "route",
        {
            "question": question,
            "requested_mode": requested_mode,
            "llm_enabled": bool(api_key or allow_server_key),
            "provider": _resolve_llm_provider(api_key, allow_server_key, provider),
            "model": _resolve_llm_model(api_key, allow_server_key, provider, model),
        },
    )
    cached_route = cache.get(cache_key)
    if cached_route is not None:
        return cached_route

    if requested_mode != "auto":
        route = deterministic_route(question, requested_mode)
        cache.set(cache_key, route, MCP_CACHE_TIMEOUT)
        return route

    deterministic = deterministic_route(question, "auto")
    if deterministic["mode"] != "term":
        cache.set(cache_key, deterministic, MCP_CACHE_TIMEOUT)
        return deterministic

    system_prompt = """
You are a routing assistant for AD-Alterome.
Classify the user question into exactly one mode:
- gene
- hypothesis
- term
- compare

Return strict JSON only.

Schemas:
1) {"mode":"gene","gene":"MAPT"}
2) {"mode":"hypothesis","hypothesis":"Tau Protein Hypothesis"}
3) {"mode":"term","term":"mitochondrial dysfunction"}
4) {"mode":"compare","gene_a":"APOE","gene_b":"APP"}

Rules:
- The requested mode is supplied with the question.
- When it is not "auto", the returned mode MUST exactly match it.
- Use compare when the user asks to compare two genes.
- Use hypothesis when the user explicitly asks about a hypothesis or contains the word hypothesis / 假说.
- Use gene when a specific gene symbol is central.
- Otherwise use term.
- Do not output markdown.
""".strip()

    try:
        text = _complete_json(
            "routing", system_prompt,
            f"Requested mode: {requested_mode}\nQuestion: {question}", ROUTE_SCHEMA,
            api_key=api_key, allow_server_key=allow_server_key,
            provider=provider, model=model, temperature=0,
        )
        route = _parse_json_response(text)
    except Exception:
        route = deterministic

    resolved_mode = requested_mode if requested_mode != "auto" else route.get("mode")
    if resolved_mode not in SUPPORTED_MODES - {"auto"}:
        resolved_mode = "term"
    route["mode"] = resolved_mode

    required_fields = {
        "gene": ("gene",),
        "hypothesis": ("hypothesis",),
        "term": ("term",),
        "compare": ("gene_a", "gene_b"),
    }[resolved_mode]
    if any(not str(route.get(field) or "").strip() for field in required_fields):
        if resolved_mode == "term":
            route["term"] = question
        else:
            raise ValueError(f"Could not identify the target for {resolved_mode} mode")

    cache.set(cache_key, route, MCP_CACHE_TIMEOUT)
    return route


async def call_tool_cached(tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    key = _cache_key(tool_name, arguments)
    cached_payload = cache.get(key)
    if cached_payload is not None:
        return cached_payload

    payload = await call_mcp_tool(tool_name, arguments)
    cache.set(key, payload, MCP_CACHE_TIMEOUT)
    return payload


async def select_diverse_evidence(rows, limit, curation_tool, arguments, exclude_sentences=()):
    excluded = set(exclude_sentences)

    def select(candidates):
        return [
            item for item in pick_evidence_rows(candidates, limit=len(candidates))
            if " ".join(item["EvidenceText"].split()) not in excluded
        ][:limit]

    picked = select(rows)
    if len(picked) >= limit:
        return picked
    # Top-ranked event rows often repeat one sentence for many annotations.
    # Supplement once through the existing MCP curation tool, with a hard bound.
    try:
        result = await asyncio.wait_for(
            call_tool_cached(curation_tool, {**arguments, "selected_limit": 50}),
            timeout=30,
        )
    except (McpRetrievalError, TimeoutError):
        return picked
    data = result.get("data", {}).get("curation", {})
    source = result.get("meta", {}).get("curation_source", "curation")
    supplemental = [
        {**row, "RetrievalSource": source}
        for row in data.get("selected_evidence", []) if isinstance(row, dict)
    ][:50]
    return select(list(rows) + supplemental)


async def fetch_gene_context(gene: str) -> dict:
    limit = evidence_sample_limit()
    overview, events = await asyncio.gather(
        call_tool_cached("mcp_get_gene_overview", {"gene": gene}),
        call_tool_cached("mcp_query_gene_events", {"gene": gene, "top_k": evidence_candidate_limit(limit)}),
    )
    evidence_examples = await select_diverse_evidence(
        events.get("data", {}).get("results", []), limit,
        "mcp_curate_gene_evidence", {"gene": gene},
    )

    return {
        "mode": "gene",
        "target": gene,
        "overview_summary": without_internal_scores(
            overview.get("data", {}).get("summary", {})
        ),
        "top_terms": overview.get("data", {}).get("top_terms", [])[:5],
        "top_hypotheses": overview.get("data", {}).get("top_hypotheses", [])[:5],
        "evidence_examples": evidence_examples,
        "evidence_traces": build_evidence_traces(evidence_examples, label=gene, limit=limit),
    }


async def fetch_hypothesis_context(hypothesis: str) -> dict:
    limit = evidence_sample_limit()
    overview, support = await asyncio.gather(
        call_tool_cached(
            "mcp_get_hypothesis_overview",
            {"hypothesis": hypothesis},
        ),
        call_tool_cached(
            "mcp_query_hypothesis_support",
            {"hypothesis": hypothesis, "top_k": evidence_candidate_limit(limit)},
        ),
    )
    evidence_examples = await select_diverse_evidence(
        support.get("data", {}).get("results", []), limit,
        "mcp_curate_hypothesis_evidence", {"hypothesis": hypothesis},
    )

    return {
        "mode": "hypothesis",
        "target": hypothesis,
        "overview_summary": without_internal_scores(
            overview.get("data", {}).get("summary", {})
        ),
        "top_genes": overview.get("data", {}).get("top_genes", [])[:5],
        "top_terms": overview.get("data", {}).get("top_terms", [])[:5],
        "evidence_examples": evidence_examples,
        "evidence_traces": build_evidence_traces(evidence_examples, label=hypothesis, limit=limit),
    }


async def fetch_term_context(term: str) -> dict:
    limit = evidence_sample_limit()
    overview, events = await asyncio.gather(
        call_tool_cached("mcp_get_term_overview", {"term": term}),
        call_tool_cached("mcp_query_term_events", {"term": term, "top_k": evidence_candidate_limit(limit)}),
    )
    evidence_examples = await select_diverse_evidence(
        events.get("data", {}).get("results", []), limit,
        "mcp_curate_term_evidence", {"term": term},
    )

    return {
        "mode": "term",
        "target": term,
        "overview_summary": without_internal_scores(
            overview.get("data", {}).get("summary", {})
        ),
        "top_genes": overview.get("data", {}).get("top_genes", [])[:5],
        "top_hypotheses": overview.get("data", {}).get("top_hypotheses", [])[:5],
        "evidence_examples": evidence_examples,
        "evidence_traces": build_evidence_traces(evidence_examples, label=term, limit=limit),
    }


async def fetch_compare_context(gene_a: str, gene_b: str) -> dict:
    limit = max(2, evidence_sample_limit())
    limit_a, limit_b = (limit + 1) // 2, limit // 2
    compare, events_a, events_b = await asyncio.gather(
        call_tool_cached(
            "mcp_compare_genes",
            {"gene_a": gene_a, "gene_b": gene_b},
        ),
        call_tool_cached(
            "mcp_query_gene_events",
            {"gene": gene_a, "top_k": evidence_candidate_limit(limit_a)},
        ),
        call_tool_cached(
            "mcp_query_gene_events",
            {"gene": gene_b, "top_k": evidence_candidate_limit(limit_b)},
        ),
    )
    payload = compare.get("data", {})
    evidence_examples_a = await select_diverse_evidence(
        events_a.get("data", {}).get("results", []), limit_a,
        "mcp_curate_gene_evidence", {"gene": gene_a},
    )
    sentences_a = {" ".join(item["EvidenceText"].split()) for item in evidence_examples_a}
    evidence_examples_b = await select_diverse_evidence(
        events_b.get("data", {}).get("results", []), limit_b,
        "mcp_curate_gene_evidence", {"gene": gene_b}, exclude_sentences=sentences_a,
    )

    return {
        "mode": "compare",
        "target": {"gene_a": gene_a, "gene_b": gene_b},
        "gene_a_overview": without_internal_scores(
            payload.get("gene_a_overview", {})
        ),
        "gene_b_overview": without_internal_scores(
            payload.get("gene_b_overview", {})
        ),
        "shared_terms": payload.get("shared_terms", [])[:5],
        "unique_terms_a": payload.get("unique_terms_a", [])[:5],
        "unique_terms_b": payload.get("unique_terms_b", [])[:5],
        "shared_hypotheses": payload.get("shared_hypotheses", [])[:5],
        "unique_hypotheses_a": payload.get("unique_hypotheses_a", [])[:5],
        "unique_hypotheses_b": payload.get("unique_hypotheses_b", [])[:5],
        "evidence_examples_a": evidence_examples_a,
        "evidence_examples_b": evidence_examples_b,
        "evidence_traces": (
            build_evidence_traces(evidence_examples_a, label=gene_a, limit=limit_a)
            + build_evidence_traces(
                evidence_examples_b,
                label=gene_b,
                limit=limit_b,
                start_index=len(evidence_examples_a) + 1,
            )
        ),
    }


def _parse_json_response(text: str) -> Dict[str, Any]:
    cleaned = (text or "{}").strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()
    try:
        payload = json.loads(cleaned)
    except (TypeError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def fallback_grounded_summary(traces) -> Dict[str, Any]:
    claims = []
    for trace in (traces or [])[:4]:
        ref_id = trace.get("RefID")
        gene = str(trace.get("Gene") or "").strip()
        term = str(trace.get("TermName") or "").strip()
        hypothesis = str(trace.get("Hypothesis") or "").strip()
        hypothesis = re.sub(r",\s*", ", ", hypothesis)
        label = str(trace.get("label") or "the query target").strip()
        if not isinstance(ref_id, int):
            continue
        if gene and term:
            text = f"The retrieved literature evidence links {gene} with {term}."
        elif gene and hypothesis:
            text = f"The retrieved literature evidence associates {gene} with {hypothesis}."
        elif term and hypothesis:
            text = f"The retrieved literature evidence connects {term} with {hypothesis}."
        else:
            text = f"A traceable literature record was retrieved for {label}."
        claims.append({
            "heading": f"A retrieved record concerns {gene or label}.",
            "text": text,
            "refs": [ref_id],
        })

    answer_lines = ["## Evidence Summary"]
    for claim in claims:
        answer_lines.append(f"- **{claim['heading']}** {claim['text']} [Ref {claim['refs'][0]}]")
    limitations = (
        "AI synthesis was unavailable, so this fallback reports only direct "
        "relationships from the retrieved records."
    )
    if not claims:
        answer_lines.append("No traceable literature evidence was returned for this query.")
    answer_lines.extend(["", "## Evidence Limitations", limitations])
    return {
        "answer": "\n".join(answer_lines),
        "claims": claims,
        "limitations": limitations,
        "llm_used": False,
    }


def summarize_with_llm(
    user_question: str,
    context: dict,
    api_key: Optional[str] = None,
    allow_server_key: bool = True,
    provider: str = "deepseek",
    model: Optional[str] = None,
) -> Dict[str, Any]:
    traces = context.get("evidence_traces", [])
    valid_ref_ids = {
        trace.get("RefID")
        for trace in traces
        if isinstance(trace.get("RefID"), int)
    }
    if not valid_ref_ids:
        return {
            "answer": (
                "## Evidence Summary\n"
                "No traceable literature evidence was returned for this query."
            ),
            "claims": [],
            "limitations": "Review the query target or try a broader term.",
            "llm_used": False,
        }

    system_prompt = """
You are an AD-Alterome assistant.
Return strict JSON only using this schema:
{
  "claims": [
    {"heading": "One short takeaway sentence in English.", "text": "One or two sentences explaining the finding and its study context.", "refs": [1, 2]}
  ],
  "limitations": "One brief, plain-English sentence describing the evidence scope."
}

Rules:
- Always answer in concise English, regardless of the language of the question.
- Produce 2-6 thematic paragraphs when supported; group related findings rather than repeat a paragraph per sentence.
- Each heading must be a concise takeaway sentence (about 8-16 words). Its text must add concrete detail, not simply repeat the heading.
- Every claim must cite at least one RefID from evidence_traces.
- Use only RefIDs present in evidence_traces; never invent a reference.
- Ground both the heading and its explanation in the cited original evidence sentences.
- Do not infer prevalence, predominant mechanisms, or additional phenotypes from these representative sentences.
- Hypothesis and TermName fields are database annotations, not findings stated by the paper. Label them explicitly as AD-Alterome annotations if mentioned.
- Preserve the cited study's scope and uncertainty; describe experimental effects as findings reported by that study, not established human disease causality.
- Do not include EvidenceScore, causal claims, markdown, PMID links, or full evidence sentences.
- In limitations, state the sampled evidence scope and any material study limitation in one short sentence (at most 35 words). Avoid internal field names such as TermName and Hypothesis, HTML entities, and boilerplate lists of disclaimers.
""".strip()

    # Aggregate counts remain available in the response/UI. They cannot justify
    # sentence-level citations. Omit duplicate HTML and URLs from the LLM input.
    citation_fields = ("RefID", "Gene", "TermName", "Hypothesis", "PMID", "Journal", "Year", "Sentence")
    citation_context = {
        "mode": context.get("mode"),
        "target": context.get("target"),
        "evidence_traces": [
            {key: trace[key] for key in citation_fields if key in trace}
            for trace in traces
        ],
    }
    user_prompt = f"""
User question:
{user_question}

Citation evidence from AD-Alterome MCP (JSON):
{json.dumps(citation_context, ensure_ascii=False, indent=2)}

Return the required JSON only.
""".strip()

    try:
        text = _complete_json(
            "summary", system_prompt, user_prompt, SUMMARY_SCHEMA,
            api_key=api_key, allow_server_key=allow_server_key,
            provider=provider, model=model, temperature=0.1,
        )
    except Exception:
        return fallback_grounded_summary(traces)
    payload = _parse_json_response(text)
    if not isinstance(payload, dict) or not isinstance(payload.get("claims"), list):
        return fallback_grounded_summary(traces)
    claims = []
    for raw_claim in payload.get("claims", []):
        if not isinstance(raw_claim, dict):
            continue
        text = str(raw_claim.get("text") or "").strip()
        refs = []
        raw_refs = raw_claim.get("refs")
        if not isinstance(raw_refs, list):
            continue
        for raw_ref in raw_refs:
            try:
                ref_id = int(raw_ref)
            except (TypeError, ValueError):
                continue
            if ref_id in valid_ref_ids and ref_id not in refs:
                refs.append(ref_id)
        if text and refs:
            claim = {"text": text, "refs": refs}
            heading = raw_claim.get("heading")
            if isinstance(heading, str) and heading.strip():
                claim["heading"] = heading.strip()
            claims.append(claim)

    limitations = str(payload.get("limitations") or "").strip()
    if not claims:
        return fallback_grounded_summary(traces)

    answer_lines = ["## Evidence Summary"]
    for claim in claims:
        references = " ".join(f"[Ref {ref_id}]" for ref_id in claim["refs"])
        lead = f"**{claim['heading']}** " if claim.get("heading") else ""
        answer_lines.append(f"- {lead}{claim['text']} {references}")
    if limitations:
        answer_lines.extend(["", "## Evidence Limitations", limitations])
    return {
        "answer": "\n".join(answer_lines),
        "claims": claims,
        "limitations": limitations,
        "llm_used": True,
    }


def build_result_metadata(context: Dict[str, Any]) -> Dict[str, Any]:
    mode = context.get("mode")
    metadata = {
        "mode": mode,
        "target": context.get("target"),
        "evidence_shown": len(context.get("evidence_traces", [])),
        "evidence_pmid_count": len({
            str(trace["PMID"]) for trace in context.get("evidence_traces", [])
            if trace.get("PMID")
        }),
        "retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    if mode == "compare":
        metadata["comparison_counts"] = [
            {
                "gene": overview.get("Gene"),
                "event_count": overview.get("event_count"),
                "pmid_count": overview.get("pmid_count"),
            }
            for overview in (
                context.get("gene_a_overview", {}),
                context.get("gene_b_overview", {}),
            )
        ]
    else:
        summary = context.get("overview_summary", {})
        metadata["event_count"] = summary.get("event_count")
        metadata["pmid_count"] = summary.get("pmid_count")
    return metadata


async def _answer_question_async(
    question: str,
    requested_mode: str = "auto",
    api_key: Optional[str] = None,
    allow_server_key: bool = True,
    provider: str = "deepseek",
    model: Optional[str] = None,
    access_mode: str = "server",
) -> Dict[str, Any]:
    resolved_provider = _resolve_llm_provider(api_key, allow_server_key, provider)
    resolved_model = _resolve_llm_model(
        api_key, allow_server_key, resolved_provider, model
    )
    route = route_question_with_llm(
        question,
        requested_mode=requested_mode,
        api_key=api_key,
        allow_server_key=allow_server_key,
        provider=resolved_provider,
        model=resolved_model,
    )

    mode = route.get("mode")
    if mode == "gene":
        context = await fetch_gene_context(route["gene"])
    elif mode == "hypothesis":
        context = await fetch_hypothesis_context(route["hypothesis"])
    elif mode == "term":
        context = await fetch_term_context(route["term"])
    elif mode == "compare":
        context = await fetch_compare_context(route["gene_a"], route["gene_b"])
    else:
        raise ValueError("Unsupported route")

    summary = summarize_with_llm(
        question,
        context,
        api_key=api_key,
        allow_server_key=allow_server_key,
        provider=resolved_provider,
        model=resolved_model,
    )
    metadata = build_result_metadata(context)
    metadata.update({
        "llm_access": access_mode,
        "llm_provider": resolved_provider,
        "llm_model": resolved_model,
        "llm_used": bool(summary.get("llm_used")),
        "retrieval_transport": "mcp",
    })
    return {
        "question": question,
        "route": route,
        "context": context,
        "evidence_traces": context.get("evidence_traces", []),
        "answer": summary["answer"],
        "claims": summary["claims"],
        "limitations": summary["limitations"],
        "metadata": metadata,
    }


async def answer_question_async(
    question: str, requested_mode: str = "auto", api_key=None,
    allow_server_key=True, provider="deepseek", model=None, access_mode="server",
    llm_trace=None,
):
    """Collect full calls only in the optional server-owned list, never the UI."""
    records = []
    token = _LLM_TRACE_SINK.set(records)
    try:
        result = await _answer_question_async(
            question, requested_mode=requested_mode, api_key=api_key,
            allow_server_key=allow_server_key, provider=provider,
            model=model, access_mode=access_mode,
        )
        safe_fields = ("stage", "backend", "requested_model", "response_model",
                       "reasoning_effort", "started_at", "duration_seconds",
                       "usage", "success", "error_type")
        result["metadata"]["llm_calls"] = [
            {key: record[key] for key in safe_fields if key in record}
            for record in records
        ]
        return result
    finally:
        _LLM_TRACE_SINK.reset(token)
        if llm_trace is not None:
            llm_trace.extend(records)


def answer_question(
    question: str,
    requested_mode: str = "auto",
    api_key: Optional[str] = None,
    allow_server_key: bool = True,
    provider: str = "deepseek",
    model: Optional[str] = None,
    access_mode: str = "server",
    llm_trace=None,
) -> Dict[str, Any]:
    return asyncio.run(
        answer_question_async(
            question,
            requested_mode=requested_mode,
            api_key=api_key,
            allow_server_key=allow_server_key,
            provider=provider,
            model=model,
            access_mode=access_mode,
            llm_trace=llm_trace,
        )
    )
