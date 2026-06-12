# LLM Hypothesis Annotation Materials

This directory contains raw data and prompt templates for the AD-Alterome
LLM-assisted hypothesis annotation experiment.

The active annotation task is sentence-level AD hypothesis estimation, not
direct event extraction. Given a literature-derived candidate sentence, the LLM
evaluates AD relevance, molecular mechanism content, and alignment with
predefined Alzheimer disease hypothesis classes.

## Directory Layout

- `raw_data/`: raw sentence datasets sampled from AD-Alterome candidate
  sentences.
- `prompts/hypothesis-annotation-prompt.v2.txt`: active prompt used to ask LLMs
  for structured AD hypothesis annotation.
- `prompts/base-prompt.v4.*.txt`: legacy direct event-extraction prompt drafts
  retained for provenance; these are not the active hypothesis annotation
  prompt.
- `manual_review/`: manually reviewed annotation check files.

## Model Settings

The primary model used for hypothesis-aware annotation was DeepSeek-V3,
reported as `DeepSeek-V3-0324` / `deepseek-chat`. DeepSeek API documentation
records the `deepseek-chat` upgrade to DeepSeek-V3-0324 on 2025-03-24, with a
release note dated 2025-03-25.

Low-randomness decoding parameters were used to improve annotation consistency:

- `temperature = 0.2`
- `top_p = 0.1`
- `max_tokens = 2048`

Comparison LLMs included GPT-4o, Kimi K2, Qwen 3.0, and Gemini 2.5.

| Model/service | Access date |
| --- | --- |
| DeepSeek-V3-0324 / `deepseek-chat` | 2026-06-10 |
| GPT-4o | 2026-06-10 |
| Kimi K2 | 2026-06-10 |
| Qwen 3.0 / Qwen3 | 2026-06-10 |
| Gemini 2.5 | 2026-06-10 |

## Prompt Location

The active hypothesis annotation prompt is:

- `prompts/hypothesis-annotation-prompt.v2.txt`

It instructs the model to return, for each sentence:

- AD relevance and explicitly mentioned non-AD disease names when present;
- a definition/explanation of the sentence;
- whether the sentence provides a molecular mechanism, with reasoning;
- linked AD hypotheses selected primarily from the provided hypothesis list;
- an extended explanation supporting the hypothesis assignment;
- whether the judgment is based on the sentence, external resources, or both;
- whether the judgment basis is gene-level, phenotype-level, or both.

The prompt uses 11 predefined AD hypothesis classes plus `Not applicable to any
AD hypothesis`: Cholinergic, Amyloid, Tau protein, Neuroinflammation, Oxidative
stress, Metal ion, Glutamatergic excitotoxicity, Microbiota-Gut-Brain Axis,
Abnormal autophagy, Mitochondrial autophagy, and Vascular hypotheses.

## Raw Data Location

Raw data files are stored in `raw_data/`.

## Sampling and Manual Review

The 100-sentence prompt refinement set and the 200-sentence model comparison
set were randomly sampled from AD-Alterome candidate sentences. Domain experts
manually checked the sampled sentences and model annotations for AD relevance,
molecular/mechanistic interpretation, and hypothesis alignment.

Manual review files are stored in `manual_review/`:

- `ad_alterome_manual_review_fm.docx`
- `ad_alterome_manual_review_yh.docx`

## Generative AI Use Statement

Generative AI models were used only for structured hypothesis-aware annotation
of literature-derived sentences and for assisting the organization of evidence
summaries. All LLM-generated annotations used in evaluation were manually
reviewed by domain experts. The final biological interpretations,
methodological descriptions, and manuscript claims were checked and edited by
the authors.
