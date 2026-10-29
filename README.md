# Curriculum Auditor

Turns university catalog prerequisite text, e.g.

> CSC 210 and (MATH 243 or MATH 223) with a grade of C or better; consent of instructor

into structured AND/OR logic, then audits the whole catalog for defects: prerequisites that
point to courses that no longer exist, prerequisite loops, and degree paths too long to
finish on time. Every finding cites the catalog text it came from.

Built solo by Tanya George for the **Meta Global AI Developer Hackathon** (Oct 27 – Nov 4, 2026).
All code in this repository was written during the hackathon.

## Status

Updated as the build progresses. Only what is listed under "Done" exists.

**Done**
- Prerequisite schema in conjunctive normal form (`src/auditor/schema.py`)
- A short text notation for hand-labeling parses (`src/auditor/notation.py`)
- Data loaders for the Mendeley corpus and the UIUC catalog (`src/auditor/data.py`)
- Frozen dev/test split and a 150-course gold-label sheet (`scripts/make_splits.py`)
- Muse Spark API client and smoke test (`src/auditor/llm.py`, `scripts/smoke_test_api.py`)
- Parser agent on Muse Spark with strict JSON-schema output (`src/auditor/parser.py`)
- Guardrails in code: every course in the output must appear in the input text; on failure the
  model gets the specific problem back for one retry, then the course is flagged for review
  (`src/auditor/guardrails.py`)
- Result caching, a regex baseline parser, and an eval runner with per-tier metrics, cost and
  latency (`src/auditor/baseline.py`, `src/auditor/metrics.py`, `scripts/run_eval.py`)
- 150-course gold test set, hand-labeled with a terminal labeling tool (`scripts/label_gold.py`)

**Planned**
- Independent second parser on Muse Spark Open (Baseten); disagreement → human review
- Prerequisite graph and audit checks (missing courses, cycles, renumbered courses, path length)
- Report agent, web app, and evaluation results

## Evaluation design

- **Split:** one row per course identity (latest edition), hashed 80/20 into dev and test, so
  the same course never appears in both.
- **Gold labels:** 150 test courses hand-labeled (oversampling hard cases; 20 from Caltech,
  labeled from scratch). These are the headline accuracy numbers. Of the 130 gold courses that
  have a Mendeley parse, that parse was fully correct for 110 (85%); 5 texts were judged
  genuinely ambiguous.
- **Silver reference:** the Mendeley corpus's own parses for ~11,000 courses. Most were produced
  with LLM assistance by the dataset authors, so agreement with them is reported as agreement,
  not accuracy.

## Results so far (dev split, 300 courses, silver reference)

Agreement with the Mendeley parses, which contain known errors, so these numbers are a lower
bound; gold-set accuracy will be reported once the test set is hand-labeled.

| Parser | Agreement | Moderate tier, unflagged | $/course | Median latency |
|---|---|---|---|---|
| Regex baseline | 84.7% | 82.0% | 0 | – |
| Muse Spark 1.3, prompt v2, `minimal` reasoning | 87.3% | 98.6% | 0.0022 | 1.0 s |

Most remaining disagreements were traced to the reference: it omits corequisites, flattens
explicit AND/OR structure for one institution, and in some catalogs counts the next course's
heading (extracted onto the end of the prerequisite text) as a prerequisite.
Summaries of every run are in `results/`.

## Data

Data files are not included in this repository. Download them into `data/`:

| Folder | Source | License |
|---|---|---|
| `data/mendeley/` | Turaev et al., *A Confound-Annotated Multi-Institution Curriculum Dataset with Parsed Prerequisite Logic*, Mendeley Data — [dataset page](https://data.mendeley.com/datasets/fs2hvkps7z) (unzip all files here) | CC BY 4.0 |
| `data/uiuc/` | UIUC Course Catalog, Spring 2026 (Kaggle; from Wade Fagen-Ulmschneider's University of Illinois data repository) — save `course-catalog.csv` here | CC BY-SA 4.0 |

Changes made to the Mendeley data: filtered to English-language prerequisite text, reduced to
the latest edition of each course, and split into dev/test; course ids in `evals/` refer to it.
The dataset authors' own analysis code (`data/mendeley/code/`) is not used by or part of this project.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # then add your Meta Model API key
pytest -q                   # unit tests
python scripts/smoke_test_api.py
```

`scripts/make_splits.py` has already been run; its outputs are committed in `evals/`.
