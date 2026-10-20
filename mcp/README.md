# AD-Alterome MCP and QA retrieval source

This directory supplies the FastMCP adapter, REST client, and native web QA
retrieval code used by the question-answering workflow. The REST service,
database, and Skills implementation are maintained separately and are not
vendored here.

## Source layout

- `server/mcp_server.py`: MCP tools, resources, and prompt registrations backed
  by the REST service; no direct database access.
- `server/backend/api_client.py`: REST transport used by the MCP tools.
- `server/backend/config.py`: environment-based configuration.
- `web_qa/mcp_client.py`: MCP ClientSession transport and result validation.
- `web_qa/mcp_qa_service.py`: routing, native retrieval, sentence deduplication
  and PMID diversity, structured webpage summaries, and citation filtering.
- `web_qa/codex_llm.py`: optional transport dependency for the separate Codex
  configuration; not used in the DeepSeek evaluation.
- `collect_evidence.py`: portable retrieval entry point with minimal Django
  settings and caching disabled; does not run an LLM.
- `prompts/`: exact webpage routing and summary system prompts, also embedded in
  the QA service. Registered MCP prompt templates are in `mcp_server.py`.

The server, REST client/configuration, and QA client/service are the frozen
October 2026 experiment sources. Personal author/date headers were removed
from the server and QA service. [source-manifest.json](source-manifest.json) records source and
published hashes. The portable entry point and packaging files were added for
this release; retrieval and selection algorithms were not changed.

## Run the MCP server

Python 3.11 is recommended. Run from the repository root:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r mcp/requirements.txt
export ADALTEROME_API_BASE_URL="http://127.0.0.1:8010"
export MCP_HOST="127.0.0.1"
export MCP_PORT="8000"
export MCP_PATH="/mcp"
export MCP_TRANSPORT="streamable-http"
export NO_PROXY="127.0.0.1,localhost"
python mcp/server/mcp_server.py
```

Set `ADALTEROME_API_BASE_URL` to the base of an available AD-Alterome REST
deployment, including its proxy prefix if applicable. It must expose the
documented gene, term, hypothesis, and curation endpoints. The localhost value
above assumes a separately running API. See the
[external API documentation](https://github.com/YaoXinZhi/adalterome-skills/blob/79359ca5ee83fbac45e00199903c44b97c587d9c/skills/adalterome-api/references/api_docs.md)
for the service interface and published endpoint. No database files or service
credentials are distributed here. Server startup and evidence collection do not
need a model API key. The adapter is intended for local use; binding it to a
public interface requires deployment-specific access controls.

In another terminal, from the repository root using the same environment:

```bash
export ADALTEROME_MCP_URL="http://127.0.0.1:8000/mcp"
export NO_PROXY="127.0.0.1,localhost"
python mcp/collect_evidence.py gene PINK1 > evidence.json
python qa_evaluation/prompt_templates.py mcp G4 --evidence evidence.json > request.json
```

`term` and `hypothesis` are also supported. Native retrieval uses overview and
event tools, then a bounded curation supplement when required, selecting up to
30 distinct sentences while favoring different PMIDs. The 15-question
evaluation calls these retrieval branches with fixed targets, then submits the
selected evidence to the common evaluation prompt. Its final answer does not
use the webpage summary generator, auto-routing, or fallback summary. See
[evaluation settings](../qa_evaluation/) for permissions, limits, and provenance.

This release is not a standalone copy of the Django website. The complete QA
service is retained for method inspection and integration; calling its optional
web summary/auto-routing functions additionally requires appropriate Django
provider settings and credentials. The supplied portable collector calls only
retrieval functions. A current live API run is a new retrieval, not an exact
replay of the historical experiment.

## Related projects

- [AD-Alterome Skills](https://github.com/YaoXinZhi/adalterome-skills/tree/79359ca5ee83fbac45e00199903c44b97c587d9c):
  evaluated knowledge-synthesis workflow and instructions.
- [API documentation](https://github.com/YaoXinZhi/adalterome-skills/blob/79359ca5ee83fbac45e00199903c44b97c587d9c/skills/adalterome-api/references/api_docs.md):
  separately maintained REST interface.

Check syntax and prompt assembly without network access or a model key:

```bash
python3 -m unittest discover -s qa_evaluation/tests -v
```

[requirements-validated.txt](requirements-validated.txt) records direct dependency
versions checked for this publication. It is not a complete historical lock.
See [validation notes](../qa_evaluation/VALIDATION.md) for source and payload checks.
