# AD-Alterome Expert Review

An English interface for reviewing biomedical question-answering responses against their cited evidence. The package contains **15 questions and 45 responses**: five gene questions, five phenotype questions, and five hypothesis questions. Each question has three responses on adjacent pages, with their order fixed after randomization. Method labels are hidden; original response wording and citations remain visible, so this is not a guarantee that reviewers cannot infer a method.

All ratings start blank. No previous reviewer scores are included. Each response receives three independent **1–4 integer scores** and an optional comment. The page is complete when all three scores have been selected.

![English expert review workspace with response, cited evidence, and three assessment dimensions](docs/workspace.jpg)

## Run locally

Download and extract the entire package to a writable folder. Python 3 is required; there are **no third-party dependencies**.

| Platform | Start |
| --- | --- |
| macOS | Double-click `start.command`, or run `sh start.sh` in this folder. |
| Windows | Double-click `start.bat`. |
| Linux | Run `sh start.sh` in this folder. |

The launcher selects an available local port and opens your browser. If the browser does not open, visit the `http://127.0.0.1:.../` address printed in the terminal. Keep the terminal open while reviewing. Confirm that the page shows **Saved** before stopping the server with `Ctrl+C`.

Start with reviewer ID **E01**, or enter your assigned ID using letters, digits, underscores, or hyphens. Each reviewer has an independent file, for example `ratings/E01.json`. Reopen the package and use the same ID to resume. Reviewer IDs are file labels, not authenticated accounts; use this server only on your own computer.

## Review and score

Read the question, response, and source cards. Click a citation in the response to locate the corresponding source. A source card is verification material; its presence does not establish that it supports the claim. Floating **Scoring guide** and **Reference points** panels can be opened while reviewing.

| Dimension | Scope | What to assess |
| --- | --- | --- |
| Factual and source accuracy | Evidence itself | Whether sources, identifiers, quotations, biological entities, interventions, and model context are accurate. |
| Evidence support and traceability | Evidence–response relation | Whether key claims have identifiable support with the correct direction, conditions, and model context. |
| Relevance and coverage | Response itself | Whether the answer directly addresses the question and covers the necessary, correct core content. |

Use the anchored 1–4 definitions in the scoring guide. Judge dimensions independently: a single issue does not automatically lower every score. A missing citation affects support but does not by itself prove a factual error. Reference points are nonexclusive; scientifically valid equivalent content can receive credit. Leave an item unscored if it cannot yet be assessed, and add a comment if helpful.

## Save and export

With `server.py` running, changes are automatically saved to `ratings/<reviewer-id>.json`. **Saved** means the local server confirmed a disk write. If saving fails, keep the page open and use JSON export to protect your draft. Browser drafts provide recovery assistance; the saved JSON file is the durable server record.

JSON and CSV export buttons provide a portable copy of the current reviewer's records. If two tabs change the same response, the interface reports a revision conflict rather than silently overwriting it. Compare the records before loading the saved version or explicitly retrying your draft. Changes to different response pages are merged.

Opening `index.html` directly or hosting the package on **GitHub Pages** provides a static review interface with browser drafts and JSON/CSV export only. It **cannot write into this package's `ratings/` folder**. Use the bundled Python server for disk autosave. Static hosting publishes every uploaded asset; keep collected ratings and any private method mapping out of the public repository.

## Optional server arguments

```sh
python3 server.py --port 8765
python3 server.py --no-open
python3 server.py --no-open --ratings-dir ./private-ratings
```

The default `--port 0` selects an available port. `--ratings-dir` separates practice or test records from the package. The server binds only to `127.0.0.1`, serves an allowlist of interface assets, and does not serve rating files as static resources. It uses file locks, revision checks, and atomic replacement for saves. Corrupt or incompatible existing records are preserved and reported as errors; they are not replaced with blank records.

The supplied `.gitignore` excludes local `ratings/`, environment files, Python caches, and operating-system artifacts. If using a custom ratings directory inside a repository, exclude that directory too. Do not rename dataset/rubric identifiers to force old scores into revised material; coordinate any migration separately.

## Public demonstration and appendix screenshots

Use a fresh reviewer ID and the blank supplied package for interface screenshots. A screenshot illustrates the review workflow and scoring controls; it is not a presentation of collected expert results. Any scores entered for a demonstration must be identified as illustrative. Keep reviewer files out of the public package.

The `docs/` folder includes unscored screenshots of the [main workspace](docs/workspace.jpg), [scoring guide](docs/scoring-guide.jpg), and [question-specific reference points](docs/reference-points.jpg), with a ready-to-adapt [supplementary figure caption](docs/figure-caption.md).

The English package is separate from the original Chinese package. This interface does not automatically generate expert scores or modify model answers.

## Checks

From this folder, run:

```sh
python3 -m unittest discover -s tests -v
```

Tests use temporary folders and do not write reviewer files into this package. They cover disk persistence, reviewer isolation, revision conflicts, concurrent saves, invalid inputs, missing data, and loopback/static-asset restrictions.
