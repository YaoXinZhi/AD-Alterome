# Publication validation

Validation was performed on 20 October 2026, without new generation-model calls.

| Check | Result |
|---|---|
| Published prompt renderer versus recorded API payloads | All 45 initial requests and all 15 revised Skills final requests match exactly as JSON objects |
| Published MCP server and QA retrieval versus frozen query-response replay | All 15 complete retrieved contexts match the recorded contexts |
| Gene-batch versus phenotype/hypothesis-batch MCP source | Five frozen modules are identical across both batches |
| Published executable Python syntax trees versus frozen MCP modules | Unchanged; personal header docstrings excluded from comparison |
| Network-free prompt tests | Four tests pass, covering source permissions, shared settings, forced query parameters, and selected-only Skills results |

The request comparisons include the actual externally maintained, pinned Skill
instructions and original packet text; neither is replaced by a shorter prompt.
MCP replay used the published FastMCP server and ClientSession against local
frozen REST responses. These checks confirm packaging fidelity, not scientific
correctness or an improvement in answer quality.

The historical captures and request logs used for these comparisons are not
distributed in this release. Users can run the portable prompt tests directly;
an exact historical replay additionally requires those archived inputs. Current
API retrieval can differ. The public review responses were not edited by these
checks, and collected ratings were not included.
