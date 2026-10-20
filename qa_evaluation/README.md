# Question-answering evaluation materials

This directory documents the 15-question, three-condition evaluation represented
in the [expert-review interfaces](../expert_review/). It provides the actual
common prompt, condition instructions, bilingual questions, generation settings,
and portable request construction. It is separate from the sentence-level
hypothesis-annotation experiment in `llm_hypothesis_annotation/`.

## Conditions and shared settings

| Condition | Information supplied | Model calls per question |
|---|---|---:|
| No knowledge base | Question and common requirements; no retrieval tools or source materials | 1 |
| MCP QA | Native MCP retrieval through the REST API; up to 30 deduplicated source sentences, favoring distinct PMIDs | 1 final generation call |
| Skills v2 | Prespecified single-axis Skill call; up to 500 candidate records, up to 18 organized items; selected, sentence-audited knowledge packet | 1 forced builder call plus 1 final generation call |

All final answers used `deepseek-flash`, temperature `0`, explicitly disabled
thinking, a 2,000-token completion limit, and the same seven requirements with a
500-word limit including references. Each question and condition started with a
new conversation. There was no external search, PubMed reading, or source-link
opening by the evaluated workflows. Reference answers and scoring guidance were
not supplied to the generation model. See [generation-settings.json](generation-settings.json).
The model identifier is the recorded provider alias, not a date-pinned weights
release. Temperature zero does not guarantee identical future responses.

The 15 questions comprise five gene, five phenotype/process, and five hypothesis
tasks selected to match the resource's alteration-centered scope and coverage,
with substantial attention to mitochondrial biology. They are a resource-focused
task set, not a representative sample of all AD questions. Query axes and labels
were fixed in advance for these runs; this evaluation did not test unrestricted
autonomous routing or multi-axis planning. Different evidence and call budgets
are properties of the compared workflows; differences cannot be attributed to
MCP transport or Skill instructions alone.

## Response and input provenance

The original three-condition answers were generated on 14 October 2026. After
review of that evaluation, evidence filtering, annotation checks, and evidence
integration were revised in Skills. All 15 Skills answers were regenerated on
15 October using the same common prompt, model settings, questions, and original
frozen query responses. The current review interfaces contain those Skills v2
answers together with the existing MCP and no-knowledge-base answers. This is a
post-development comparison; the questions are not a held-out validation set.

The database inputs were frozen query-response captures in two batches: the five
gene tasks and the ten phenotype/hypothesis tasks. Repeated captures were checked
for equality before replay; within each task both database workflows used the
same captured REST responses. These captures are not a complete, simultaneous
database snapshot. Capture times and manifest hashes appear in
[input-provenance.json](input-provenance.json). Full frozen responses and private
execution logs are not included in this release; running against today's API
reproduces the workflow, not the historical inputs or outputs byte for byte.

The first successful final English API output was retained verbatim, without
quality-based reruns, editing, or selection. One retry for specified transport or
server errors was allowed; no such retries occurred in the completed runs.
Chinese translations and source-card enrichment were prepared afterward for
review and were not generation inputs. Displayed citations remain part of the
model response and require assessment; their presence does not establish support.

## Exact prompts and request assembly

- [Common question and seven requirements](prompts/common.txt)
- Condition instructions: [no knowledge base](prompts/no_kb.txt),
  [MCP](prompts/mcp.txt), [Skills](prompts/skills.txt)
- [All 15 bilingual questions and prespecified queries](questions.json)
- [Portable prompt renderer](prompt_templates.py)

The common block is placed in the user message and the condition instruction in
the system message. For MCP, the user message additionally contains
`Retrieved evidence records:` followed by the selected records as JSON. Native
retrieval is orchestrated by the application before this single generation call;
the final LLM does not autonomously invoke MCP tools. The webpage's JSON summary
prompt is **not** used for these evaluation answers.

For Skills v2, append `Provided Skill instructions:` and the exact pinned
`skills/adalterome-knowledge-synthesis/SKILL.md` to the system instruction. The
first call is forced to the one permitted builder function with the prespecified
query enum. Run that builder with `--candidate-limit 500 --organized-limit 18`,
the question text, and the frozen replay endpoint; disable caching. The second
call receives the original assistant tool call and a tool message whose only
field is `knowledge_packet`. The raw candidate pool, evidence map, and coverage
files are archived but not inserted into the v2 model context. The first call's
tool schema and final message assembly are reproduced in `prompt_templates.py`.
The Skill implementation and its instructions are referenced externally below.

Examples (run from the repository root; these only prepare requests):

```bash
python3 qa_evaluation/prompt_templates.py no_kb G4 > no-kb-request.json
python3 qa_evaluation/prompt_templates.py mcp G4 --evidence evidence.json > mcp-request.json
python3 qa_evaluation/prompt_templates.py skills G4 \
  --skill-file ../adalterome-skills/skills/adalterome-knowledge-synthesis/SKILL.md \
  > skills-initial-request.json
```

The JSON uses the OpenAI-compatible Python SDK request shape, including
`extra_body.thinking`. Supplying the prompt alone does not freeze retrieval or
enforce network permissions: a replication must separately restrict tools and
replay only permitted query responses. Do not use reference answers as model
context or selectively repair one condition's outputs.

## Related implementations and manuscript scope

- [MCP adapter and native QA retrieval source](../mcp/).
- [Skills source pinned to the evaluated v2 commit](https://github.com/YaoXinZhi/adalterome-skills/tree/79359ca5ee83fbac45e00199903c44b97c587d9c),
  including the knowledge-synthesis instructions and builder.
- [Separately maintained API documentation](https://github.com/YaoXinZhi/adalterome-skills/blob/79359ca5ee83fbac45e00199903c44b97c587d9c/skills/adalterome-api/references/api_docs.md).
  The REST implementation and database are not copied into this repository.

The manuscript's earlier MCP webpage examples and extended MCP–Agent
mitochondrial case are distinct from this later 15-question evaluation. Those
examples use the webpage's structured-summary prompt; the extended Agent case
also permits supplementary literature retrieval. Their models, tool permissions,
and outputs must not be described as those of this no-external-search evaluation.
This directory records the executed evaluation rather than replacing historical
case-study settings with a single configuration.

The public review systems use three 1–4 dimensions: factual and source accuracy,
evidence support and traceability, and relevance and coverage. They contain no
collected reviewer scores or completed independent-human evaluation results.
