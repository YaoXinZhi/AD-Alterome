# LLM Hypothesis Annotation Materials

This directory contains raw data and prompt templates for the AD-Alterome
LLM-assisted hypothesis annotation experiment.

## Directory Layout

- `raw_data/`: raw sentence datasets sampled from AD-Alterome candidate
  sentences.
- `prompts/`: prompt templates used to ask LLMs for structured GARE/hypothesis
  annotation.

The generated ChatGPT/LLM result files are not included.

## Model Settings

The primary model used for hypothesis-aware annotation was DeepSeek-V3,
reported as `DeepSeek-V3-0324` / `deepseek-chat`. DeepSeek API documentation
records the `deepseek-chat` upgrade to DeepSeek-V3-0324 on 2025-03-24, with a
release note dated 2025-03-25.

Low-randomness decoding parameters were used to improve annotation consistency:

- `temperature = 0.2`
- `top_p = 0.1`
- `max_tokens = 2048`

Comparison LLMs included GPT-4o, Kimi K2, Qwen 3.0, and Gemini 2.5. If a
manuscript version needs provider-specific snapshots, add the exact platform
access dates before submission.

## Prompt Location

Prompt templates are stored in `prompts/`. They were copied from the local
working directory:

`/Users/yao/Nutstore Files/Mac2PC/AD-PNRLE/AD-Alterome调整-2024/ChatGPT-experiment/prompt-dir`

## Raw Data Location

Raw data files are stored in `raw_data/`. They were copied from the local
working directory:

`/Users/yao/Nutstore Files/Mac2PC/AD-PNRLE/AD-Alterome调整-2024/ChatGPT-experiment/real-data`

## Sampling and Manual Review

The 100-sentence prompt refinement set and the 200-sentence model comparison
set were randomly sampled from AD-Alterome candidate sentences. Domain experts
manually checked the sampled sentences and model annotations for AD relevance,
molecular/mechanistic interpretation, and hypothesis alignment.

Manual checking files are maintained separately in the project working
directory:

`/Users/yao/Nutstore Files/Mac2PC/AD-PNRLE/AD-Alterome调整-2024/result/manual_check_result`

## Generative AI Use Statement

Generative AI models were used only for structured hypothesis-aware annotation
of literature-derived sentences and for assisting the organization of evidence
summaries. All LLM-generated annotations used in evaluation were manually
reviewed by domain experts. The final biological interpretations,
methodological descriptions, and manuscript claims were checked and edited by
the authors.

## Excluded Files

The original local experiment directory also contains generated LLM output
files under `chatgpt-result/`. These files are intentionally not included here
to keep this repository focused on raw data, prompts, and reproducibility
documentation.
