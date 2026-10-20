# -*- coding:utf-8 -*-
# ! usr/bin/env python3
"""AD-Alterome MCP adapter for the retrieval REST API."""

from mcp.server.fastmcp import FastMCP
from backend.config import MCP_TRANSPORT, MCP_HOST, MCP_PORT, MCP_PATH
from backend.api_client import (
    compare_genes,
    curate_compound_evidence,
    curate_gene_evidence,
    curate_hypothesis_evidence,
    curate_term_evidence,
    get_gene_overview,
    get_hypothesis_overview,
    get_schema,
    get_term_overview,
    list_hypotheses,
    query_gene_events,
    query_hypothesis_support,
    query_term_events,
)
from urllib.parse import unquote

mcp = FastMCP(
    "AD-Alterome MCP Server",
    host=MCP_HOST,
    port=MCP_PORT,
    streamable_http_path=MCP_PATH,
)


# ----------------------------
# Tools
# ----------------------------

@mcp.tool()
def mcp_query_gene_events(gene: str, top_k: int = 10):
    """查询某个基因在 AD-Alterome 中的事件证据。"""
    return query_gene_events(gene, top_k)


@mcp.tool()
def mcp_query_term_events(term: str, top_k: int = 10):
    """查询某个表型、术语或病理现象相关的事件证据。"""
    return query_term_events(term, top_k)


@mcp.tool()
def mcp_query_hypothesis_support(hypothesis: str, top_k: int = 10):
    """查询某个 AD 假说相关的支持证据。"""
    return query_hypothesis_support(hypothesis, top_k)


@mcp.tool()
def mcp_curate_gene_evidence(gene: str, selected_limit: int = 30):
    """从离线 curated gene pool 读取报告级证据，使用 final expert annotation 重排后返回 curation 包。"""
    return curate_gene_evidence(gene, selected_limit)


@mcp.tool()
def mcp_curate_term_evidence(term: str, selected_limit: int = 30):
    """从离线 curated term pool 读取报告级证据，使用 final expert annotation 重排后返回 curation 包。"""
    return curate_term_evidence(term, selected_limit)


@mcp.tool()
def mcp_curate_hypothesis_evidence(hypothesis: str, selected_limit: int = 30):
    """从离线 curated hypothesis pool 读取报告级证据，使用 final expert annotation 重排后返回 curation 包。"""
    return curate_hypothesis_evidence(hypothesis, selected_limit)


@mcp.tool()
def mcp_curate_compound_evidence(
    gene: str | None = None,
    term: str | None = None,
    hypothesis: str | None = None,
    selected_limit: int = 30,
    fallback: str = "axis_merge",
):
    """组合查询基因、表型/过程、AD假说中的至少两项，优先按 raw_event_id 做 curated pool 交集。"""
    return curate_compound_evidence(gene, term, hypothesis, selected_limit, fallback)


@mcp.tool()
def mcp_get_gene_overview(gene: str):
    """获取某个基因的聚合统计信息。"""
    return get_gene_overview(gene)

@mcp.tool()
def mcp_get_hypothesis_overview(hypothesis: str):
    """获取某个 AD 假说的聚合统计信息。"""
    return get_hypothesis_overview(hypothesis)


@mcp.tool()
def mcp_get_term_overview(term: str):
    """获取某个表型/术语的聚合统计信息。"""
    return get_term_overview(term)

@mcp.tool()
def mcp_compare_genes(gene_a: str, gene_b: str):
    """比较两个基因在 AD-Alterome 中的共性与差异。"""
    return compare_genes(gene_a, gene_b)

# ----------------------------
# Resources
# ----------------------------

@mcp.resource("ad-alterome://schema")
def ad_alterome_schema() -> str:
    """AD-Alterome数据库核心表结构说明。"""
    info = get_schema()

    lines = [
        "AD-Alterome MCP Resource: schema",
        "",
        f"table_name: {info['table_name']}",
        f"table_exists: {info['table_exists']}",
        f"row_count: {info['row_count']}",
        "",
        "columns:",
    ]
    lines.extend([f"- {col}" for col in info["columns"]])

    lines.extend([
        "",
        "query guide:",
        "- use mcp_curate_gene_evidence for gene-centered report curation from the offline full-pool curated evidence database",
        "- use mcp_curate_term_evidence for phenotype / term-centered report curation from the offline full-pool curated evidence database",
        "- use mcp_curate_hypothesis_evidence for AD hypothesis-centered report curation from the offline full-pool curated evidence database",
        "- use mcp_curate_compound_evidence for true gene / phenotype-process / hypothesis combination queries from curated pools",
        "- use mcp_query_* event tools for lightweight top-k sentence retrieval",
        "- use mcp_get_gene_overview for aggregated gene statistics",
    ])

    return "\n".join(lines)


@mcp.resource("ad-alterome://hypotheses")
def ad_alterome_hypotheses() -> str:
    """AD-Alterome中出现的假说名称列表（去重后的简要版）。"""
    result = list_hypotheses()
    cleaned = result.get("data", {}).get("hypotheses", [])

    lines = [
        "AD-Alterome MCP Resource: hypotheses",
        "",
        f"count: {len(cleaned)}",
        "",
        "hypotheses:",
    ]
    lines.extend([f"- {x}" for x in cleaned])

    return "\n".join(lines)



@mcp.resource("ad-alterome://gene/{gene}/overview")
def ad_alterome_gene_overview_resource(gene: str) -> str:
    """返回指定基因的聚合统计概览。"""
    result = get_gene_overview(gene)

    if result.get("status") != "ok":
        return f"AD-Alterome MCP Resource: gene overview\ngene: {gene}\n\nNo summary found."

    payload = result.get("data", {})
    summary = payload.get("summary")
    top_terms = payload.get("top_terms", [])
    top_hypotheses = payload.get("top_hypotheses", [])

    lines = [
        "AD-Alterome MCP Resource: gene overview",
        f"gene: {gene}",
        "",
        "summary:",
        f"- event_count: {summary.get('event_count')}",
        f"- pmid_count: {summary.get('pmid_count')}",
        f"- term_count: {summary.get('term_count')}",
        f"- hypothesis_count: {summary.get('hypothesis_count')}",
        f"- avg_evidence_score: {summary.get('avg_evidence_score')}",
        "",
        "top_terms:",
    ]

    for item in top_terms:
        lines.append(f"- {item.get('TermName')} ({item.get('TermType')}): {item.get('freq')}")

    lines.append("")
    lines.append("top_hypotheses:")

    for item in top_hypotheses:
        lines.append(f"- {item.get('Hypothesis')}: {item.get('freq')}")

    return "\n".join(lines)


@mcp.resource("ad-alterome://hypothesis/{hypothesis}/overview")
def ad_alterome_hypothesis_overview_resource(hypothesis: str) -> str:
    """返回指定 AD 假说的聚合统计概览。"""
    hypothesis_decoded = unquote(hypothesis)
    result = get_hypothesis_overview(hypothesis_decoded)

    if result.get("status") != "ok":
        return f"AD-Alterome MCP Resource: hypothesis overview\nhypothesis: {hypothesis_decoded}\n\nNo summary found."

    payload = result.get("data", {})
    summary = payload.get("summary", {})
    top_genes = payload.get("top_genes", [])
    top_terms = payload.get("top_terms", [])

    lines = [
        "AD-Alterome MCP Resource: hypothesis overview",
        f"hypothesis: {hypothesis_decoded}",
        "",
        "summary:",
        f"- event_count: {summary.get('event_count')}",
        f"- pmid_count: {summary.get('pmid_count')}",
        f"- gene_count: {summary.get('gene_count')}",
        f"- term_count: {summary.get('term_count')}",
        "",
        "top_genes:",
    ]

    for item in top_genes:
        lines.append(f"- {item.get('Gene')}: {item.get('freq')}")

    lines.append("")
    lines.append("top_terms:")

    for item in top_terms:
        lines.append(f"- {item.get('TermName')} ({item.get('TermType')}): {item.get('freq')}")

    return "\n".join(lines)

@mcp.resource("ad-alterome://term/{term}/overview")
def ad_alterome_term_overview_resource(term: str) -> str:
    """返回指定 term/phenotype 的聚合统计概览。"""
    term_decoded = unquote(term)
    result = get_term_overview(term_decoded)

    if result.get("status") != "ok":
        return f"AD-Alterome MCP Resource: term overview\nterm: {term_decoded}\n\nNo summary found."

    payload = result.get("data", {})
    summary = payload.get("summary", {})
    top_genes = payload.get("top_genes", [])
    top_hypotheses = payload.get("top_hypotheses", [])

    lines = [
        "AD-Alterome MCP Resource: term overview",
        f"term: {term_decoded}",
        "",
        "summary:",
        f"- event_count: {summary.get('event_count')}",
        f"- pmid_count: {summary.get('pmid_count')}",
        f"- gene_count: {summary.get('gene_count')}",
        f"- hypothesis_count: {summary.get('hypothesis_count')}",
        "",
        "top_genes:",
    ]

    for item in top_genes:
        lines.append(f"- {item.get('Gene')}: {item.get('freq')}")

    lines.append("")
    lines.append("top_hypotheses:")

    for item in top_hypotheses:
        lines.append(f"- {item.get('Hypothesis')}: {item.get('freq')}")

    return "\n".join(lines)


@mcp.resource("ad-alterome://index")
def ad_alterome_index() -> str:
    """AD-Alterome MCP 首页与导航说明。"""
    lines = [
        "AD-Alterome MCP Index",
        "",
        "available tools:",
        "- mcp_query_gene_events(gene, top_k=10)",
        "- mcp_query_term_events(term, top_k=10)",
        "- mcp_query_hypothesis_support(hypothesis, top_k=10)",
        "- mcp_curate_gene_evidence(gene, selected_limit=30)",
        "- mcp_curate_term_evidence(term, selected_limit=30)",
        "- mcp_curate_hypothesis_evidence(hypothesis, selected_limit=30)",
        "- mcp_curate_compound_evidence(gene=None, term=None, hypothesis=None, selected_limit=30)",
        "- mcp_get_gene_overview(gene)",
        "- mcp_get_hypothesis_overview(hypothesis)",
        "- mcp_get_term_overview(term)",
        "- mcp_compare_genes(gene_a, gene_b)",
        "",
        "available resources:",
        "- ad-alterome://schema",
        "- ad-alterome://hypotheses",
        "- ad-alterome://gene/{gene}/overview",
        "- ad-alterome://hypothesis/{hypothesis}/overview",
        "- ad-alterome://term/{term}/overview",
        "- ad-alterome://compare/gene/{gene_a}/{gene_b}",
        "",
        "available prompts:",
        "- gene_mechanism_prompt(gene)",
        "- hypothesis_summary_prompt(hypothesis)",
        "- term_summary_prompt(term)",
        "- compare_genes_prompt(gene_a, gene_b)",
        "",
        "recommended entry points:",
        "- gene analysis: start from ad-alterome://gene/{gene}/overview",
        "- hypothesis analysis: start from ad-alterome://hypothesis/{hypothesis}/overview",
        "- term analysis: start from ad-alterome://term/{term}/overview",
        "",
        "notes:",
        "- use tools for structured data retrieval",
        "- use resources for readable context and summaries",
        "- use prompts for guided LLM workflows",
    ]
    return "\n".join(lines)


@mcp.resource("ad-alterome://compare/gene/{gene_a}/{gene_b}")
def ad_alterome_compare_genes_resource(gene_a: str, gene_b: str) -> str:
    """返回两个基因在 AD-Alterome 中的比较摘要。"""
    gene_a_decoded = unquote(gene_a)
    gene_b_decoded = unquote(gene_b)

    result = compare_genes(gene_a_decoded, gene_b_decoded)

    if result.get("status") != "ok":
        return (
            "AD-Alterome MCP Resource: gene comparison\n"
            f"gene_a: {gene_a_decoded}\n"
            f"gene_b: {gene_b_decoded}\n\n"
            "Comparison not available."
        )

    payload = result.get("data", {})

    lines = [
        "AD-Alterome MCP Resource: gene comparison",
        f"gene_a: {gene_a_decoded}",
        f"gene_b: {gene_b_decoded}",
        "",
        "shared_terms:",
    ]

    for item in payload.get("shared_terms", []):
        lines.append(
            f"- {item.get('TermName')}: {gene_a_decoded}={item.get('freq_a')}, {gene_b_decoded}={item.get('freq_b')}"
        )

    lines.append("")
    lines.append(f"unique_terms_of_{gene_a_decoded}:")

    for item in payload.get("unique_terms_a", []):
        lines.append(f"- {item.get('TermName')}: {item.get('freq')}")

    lines.append("")
    lines.append(f"unique_terms_of_{gene_b_decoded}:")

    for item in payload.get("unique_terms_b", []):
        lines.append(f"- {item.get('TermName')}: {item.get('freq')}")

    lines.append("")
    lines.append("shared_hypotheses:")

    for item in payload.get("shared_hypotheses", []):
        lines.append(
            f"- {item.get('Hypothesis')}: {gene_a_decoded}={item.get('freq_a')}, {gene_b_decoded}={item.get('freq_b')}"
        )

    return "\n".join(lines)

# ----------------------------
# Prompts
# ----------------------------

@mcp.prompt()
def gene_mechanism_prompt(gene: str) -> str:
    """指导模型解释某个基因在 AD-Alterome 中的机制证据。"""
    return f"""
You are analyzing AD-Alterome evidence for the gene "{gene}".

Please follow this workflow:
1. Read the resource: ad-alterome://gene/{gene}/overview
2. Call the tool: mcp_curate_gene_evidence(gene="{gene}", selected_limit=30)
3. Summarize:
   - the main pathological mechanisms
   - the most relevant phenotypes/terms
   - the most supported AD hypotheses
   - 2-3 representative high-quality evidence records with PMID/PubMed links
4. If evidence is limited, explicitly say so.
5. Do not invent information outside AD-Alterome results.
Use `Evidence.sentence` as the original evidence sentence and `Evidence.pubmed_url`
as the PubMed hyperlink when available.
""".strip()


@mcp.prompt()
def hypothesis_summary_prompt(hypothesis: str) -> str:
    """指导模型总结某个 AD 假说的支持证据。"""
    return f"""
You are analyzing AD-Alterome evidence for the AD hypothesis "{hypothesis}".

Please follow this workflow:
1. Read the resource: ad-alterome://hypotheses
2. Call the tool: mcp_curate_hypothesis_evidence(hypothesis="{hypothesis}", selected_limit=30)
3. Summarize:
   - the main supported genes
   - the main related phenotypes/terms
   - the major mechanistic patterns
   - 2-3 representative high-quality evidence records with PMID/PubMed links
4. If evidence is weak or ambiguous, explicitly say so.
5. Do not invent information outside AD-Alterome results.
Use `Evidence.sentence` as the original evidence sentence and `Evidence.pubmed_url`
as the PubMed hyperlink when available.
""".strip()

@mcp.prompt()
def term_summary_prompt(term: str) -> str:
    """指导模型总结某个 term/phenotype 的相关机制证据。"""
    return f"""
You are analyzing AD-Alterome evidence for the term/phenotype "{term}".

Please follow this workflow:
1. Read the resource: ad-alterome://term/{term}/overview
2. Call the tool: mcp_get_term_overview(term="{term}")
3. Call the tool: mcp_curate_term_evidence(term="{term}", selected_limit=30)
4. Summarize:
   - the most relevant genes
   - the most supported AD hypotheses
   - the main mechanistic patterns
   - 2-3 representative high-quality evidence records with PMID/PubMed links
5. If evidence is weak or limited, explicitly say so.
6. Do not invent information outside AD-Alterome results.
Use `Evidence.sentence` as the original evidence sentence and `Evidence.pubmed_url`
as the PubMed hyperlink when available.
""".strip()


@mcp.prompt()
def compare_genes_prompt(gene_a: str, gene_b: str) -> str:
    """指导模型比较两个基因在 AD-Alterome 中的机制差异与共性。"""
    return f"""
You are comparing AD-Alterome evidence for two genes: "{gene_a}" and "{gene_b}".

Please follow this workflow:
1. Read the resource: ad-alterome://gene/{gene_a}/overview
2. Read the resource: ad-alterome://gene/{gene_b}/overview
3. Call the tool: mcp_get_gene_overview(gene="{gene_a}")
4. Call the tool: mcp_get_gene_overview(gene="{gene_b}")
5. Call the tool: mcp_curate_gene_evidence(gene="{gene_a}", selected_limit=24)
6. Call the tool: mcp_curate_gene_evidence(gene="{gene_b}", selected_limit=24)
7. Compare and summarize:
   - shared phenotypes/terms
   - distinct phenotypes/terms
   - shared AD hypotheses
   - distinct AD hypotheses
   - representative high-quality evidence records with PMID/PubMed links for each gene
8. Clearly separate:
   - common patterns
   - gene-specific mechanisms
9. If evidence is limited for one gene, explicitly say so.
10. Do not invent information outside AD-Alterome results.
Use `Evidence.sentence` as the original evidence sentence and `Evidence.pubmed_url`
as the PubMed hyperlink when available.
""".strip()

# if __name__ == "__main__":
#     mcp.run(transport="stdio")

if __name__ == "__main__":
    mcp.run(transport=MCP_TRANSPORT)
