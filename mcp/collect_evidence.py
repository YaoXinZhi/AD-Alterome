"""Portable entry point for the frozen web QA retrieval functions; no LLM calls."""
import argparse
import asyncio
import json
import os


def configure():
    from django.conf import settings
    if not settings.configured:
        settings.configure(
            SECRET_KEY="local-retrieval-only",
            CACHES={"default": {"BACKEND": "django.core.cache.backends.dummy.DummyCache"}},
            ADALTEROME_MCP_URL=os.getenv("ADALTEROME_MCP_URL", "http://127.0.0.1:8000/mcp"),
            ADALTEROME_MCP_TIMEOUT=180,
            ADALTEROME_MCP_EVIDENCE_LIMIT=30,
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", choices=["gene", "term", "hypothesis"])
    parser.add_argument("query")
    args = parser.parse_args()
    configure()
    from web_qa import mcp_qa_service as qa
    functions = {"gene": qa.fetch_gene_context, "term": qa.fetch_term_context,
                 "hypothesis": qa.fetch_hypothesis_context}
    result = asyncio.run(functions[args.kind](args.query))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
