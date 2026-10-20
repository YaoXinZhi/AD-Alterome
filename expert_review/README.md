# AD-Alterome Expert Review Systems

Two standalone interfaces support evidence-linked assessment of biomedical
question-answering responses. The English and Chinese versions contain the same
**15 questions and 45 anonymous response pages**: five questions each about
genes, phenotypes, and hypotheses, with three responses per question.

| Version | Interface and materials | Start here |
| --- | --- | --- |
| English | English questions, responses, article metadata, excerpts, reference points, and scoring guide | [`en/README.md`](en/README.md) |
| Chinese | Bilingual questions and materials, with Chinese interface labels and reading assistance | [`zh/README.md`](zh/README.md) |

## Run a review session

Download and extract the repository, then open the selected language directory.
Python 3 is the only runtime requirement. No third-party packages, model API
keys, or database service are needed to run the review interface.

- macOS: double-click `start.command`, or run `sh start.sh`.
- Windows: double-click `start.bat`.
- Linux: run `sh start.sh`.

The launcher opens a loopback address printed in the terminal. Keep the terminal
open during review. Enter an assigned neutral reviewer ID, such as `E01`, to
start or resume a session. Each ID has a separate local file. IDs are file labels,
not authenticated accounts.

## Assessment protocol

Each response receives three independent integer scores from **1 to 4** and an
optional note. All scores start unrated. The floating scoring guide contains the
full definitions and anchors; the reference-points window follows the question.

| Dimension | Scope |
| --- | --- |
| Factual and source accuracy | Whether the evidence and its identifiers, entities, interventions, and model context are accurate |
| Evidence support and traceability | Whether identifiable evidence supports the response's key claims in the stated direction and context |
| Relevance and coverage | Whether the response addresses the question and covers necessary, correct core content |

Read the original response beside its cited article titles, PMIDs, and available
excerpts. Click an in-text citation to locate the corresponding evidence card.
Source inclusion does not establish that it supports a claim. Credit valid
equivalent content beyond the reference points, and assess the three dimensions
separately. The package does not generate expert scores automatically.

Each question's three responses appear on adjacent pages in a fixed randomized
order. Anonymous page IDs support later analysis without displaying method
labels. Original response wording and citations are preserved, so reviewers may
infer a method from the content. The private response-to-method mapping is not
included.

## Storage and language versions

The bundled Python server automatically writes changes to
`ratings/<reviewer-id>.json` inside the selected language folder. Confirm the
saved status before closing the server. JSON and CSV export provide portable
copies. Browser drafts help recover interrupted sessions; revision checks report
conflicting changes rather than silently overwriting them.

The English interface also supports static hosting, including GitHub Pages, in
browser-only mode. Static pages cannot write to repository files: use browser
drafts and export, or start the local Python server for disk autosave. The Chinese
interface is intended to be run using its bundled local launcher; directly
opening its HTML file provides a browser-only preview.

The English version has a separate dataset identifier and local storage namespace.
The Chinese version retains its existing identifier. Both use the same three-score
rubric and underlying response/page IDs. Keep a reviewer on one language version
during a session; do not pool the two versions as independent observations or
rename identifiers to force an old rating file to load.

This public release contains no completed reviewer records, private method mapping,
personal reviewer information, credentials, or machine-specific paths. Local
rating files, environment files, and caches are excluded by `.gitignore`.

## Appendix screenshots

The English version includes unscored screenshots of the
[workspace](en/docs/workspace.jpg), [scoring guide](en/docs/scoring-guide.jpg),
and [reference-points window](en/docs/reference-points.jpg), plus a
[supplementary figure caption](en/docs/figure-caption.md). These show the
interface and workflow, not collected expert results.

## Validation

From the English interface directory, run:

```sh
python3 -B -m unittest discover -s tests -v
```

The tests cover data integrity, blank public release state, disk persistence,
reviewer isolation, concurrent saves, conflicts, and local-server restrictions.
The optional source-file integrity check is skipped unless a developer supplies
`ADALTEROME_CHINESE_SOURCE`; ordinary users do not need this variable.
