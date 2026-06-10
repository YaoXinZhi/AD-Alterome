# LLM Hypothesis Annotation Materials

This directory contains raw data and prompt templates for the AD-Alterome
LLM-assisted hypothesis annotation experiment.

## Directory Layout

- `raw_data/`: raw sentence datasets sampled from AD-Alterome candidate
  sentences.
- `prompts/`: prompt templates used to ask LLMs for structured GARE/hypothesis
  annotation.
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

Prompt templates are stored in `prompts/`.

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
