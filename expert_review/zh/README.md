# AD-Alterome Expert Review — Chinese Interface

This folder contains the Chinese review interface with bilingual questions,
original English responses, Chinese reading assistance, cited article titles
and excerpts, and question-specific reference points. It includes **15 questions
and 45 anonymous response pages**, with three independent 1–4 scores and optional
reviewer notes. All ratings start blank.

For detailed Chinese instructions, see [`README.zh-CN.md`](README.zh-CN.md).
For the English interface, use [`../en/`](../en/). The two versions present the
same underlying responses and are not independent evaluation datasets.

## Start and save

Download and extract the whole repository. Open this folder and run `sh start.sh`
on macOS or Linux; macOS users may also double-click `start.command`. On Windows,
double-click `start.bat`. Python 3 is required, with no third-party dependencies.

Keep the terminal open while reviewing, and use the local address it prints.
Assigned reviewer IDs such as `E01` identify separate local files. Changes are
automatically saved to `ratings/<reviewer-id>.json` once confirmed by the local
server. JSON and CSV exports provide portable copies. Directly opening
`index.html` is a browser-only preview and does not write into the ratings folder.
Use the bundled launcher for this Chinese version.

## Review dimensions

1. **Factual and source accuracy** — the evidence itself.
2. **Evidence support and traceability** — the evidence–response link.
3. **Relevance and coverage** — the response itself.

Use the full anchors in the floating scoring-guide window. The reference-points
window provides nonexclusive guidance for the current question. Chinese text
supports reading; assess the original English response if a translation is
ambiguous. Source cards are verification material, not an endorsement of a
response's claim.

Anonymous page IDs and response order are retained. No completed reviewer
records or private method mapping are included. Do not upload locally collected
rating files or environment files; these are excluded by `.gitignore`.
