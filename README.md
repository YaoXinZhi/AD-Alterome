# AD-Alterome

This repository provides source materials for the AD-Alterome manuscript and the
LLM-assisted AD hypothesis annotation experiment.

The current LLM workflow is not direct event extraction. It starts from
literature-derived AD-Alterome candidate sentences and asks an LLM to evaluate
AD relevance, molecular-mechanism content, and links to predefined Alzheimer
disease hypotheses.

## Contents

- `llm_hypothesis_annotation/raw_data/`: raw sentence datasets used for prompt
  refinement and model comparison.
- `llm_hypothesis_annotation/prompts/hypothesis-annotation-prompt.v2.txt`:
  active prompt for sentence-level AD hypothesis annotation.
- `llm_hypothesis_annotation/prompts/base-prompt.v4.*.txt`: legacy prompt
  drafts for direct genetic alteration regulatory event extraction, retained as
  historical materials but not the active hypothesis annotation prompt.
- `llm_hypothesis_annotation/manual_review/`: manually reviewed annotation
  check files with English filenames.
- `llm_hypothesis_annotation/README.md`: methodological notes, model settings,
  sampling rules, manual review notes, model access dates, and generative AI
  use statement.

## Active Annotation Task

The active prompt asks the model to annotate each source sentence with:

- whether the sentence is relevant to AD, or which other disease is explicitly
  mentioned;
- a sentence definition/explanation;
- whether a molecular mechanism is provided, with reasoning;
- linked AD hypotheses from the predefined hypothesis list;
- an extended explanation of how the hypothesis accounts for the described
  phenomenon;
- whether the hypothesis judgment is based completely on the sentence, partly
  on external resources, or completely on external resources;
- whether the judgment basis is gene-level, phenotype-level, or both.

The predefined hypothesis list contains 11 AD hypothesis classes plus
`Not applicable to any AD hypothesis`:

1. Cholinergic hypothesis
2. Amyloid hypothesis
3. Tau protein hypothesis
4. Neuroinflammation hypothesis
5. Oxidative stress hypothesis
6. Metal ion hypothesis
7. Glutamatergic excitotoxicity hypothesis
8. Microbiota-Gut-Brain Axis hypothesis
9. Abnormal autophagy hypothesis
10. Mitochondrial autophagy hypothesis
11. Vascular hypothesis
0. Not applicable to any AD hypothesis

## Citation

If you use these materials, please cite the AD-Alterome manuscript and this
repository.
