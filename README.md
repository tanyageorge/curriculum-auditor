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
- Audit engine in plain code (`src/auditor/audit.py`): prerequisite graph (networkx) and checks for
  courses that require themselves, prerequisite loops, prerequisites missing from the catalog,
  prerequisites renumbered or removed in a later edition, and very long chains; each finding has a
  severity and cites the catalog text. Per-catalog reports in `results/audit/` (`scripts/run_audit.py`)
- Planted-defect evaluation of the audit checks (`scripts/eval_audit.py`)
- Static website (`site/`): pick a catalog, browse findings by type and severity, open any course to
  see its catalog text, parsed AND/OR logic, review flags and an upstream prerequisite graph; plus the
  evaluation results. Precomputed by `scripts/export_site.py`, so it needs no server or API key
- Second, independent parser on **Muse Spark Open** (open weights, served by Baseten); when the two
  parsers' structures differ, the course is flagged for human review (`src/auditor/ensemble.py`)

- Full UIUC Spring 2026 file (4,502 courses, 2,732 prerequisite texts) parsed by Muse Spark as an
  out-of-sample demo: 0 API errors, 98 courses flagged for review, ~$7 (`scripts/parse_uiuc.py`; no
  labels, not scored). The file lists one term's offerings rather than the full catalog, so only the
  structural checks run on it (self-reference, loops, chains); missing-course checks would be false alarms

**Planned**
- Deployment and demo video

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

## Headline results (gold test set, 150 hand-labeled courses, run once)

Exact match of the AND/OR course structure against the hand labels.

| Tier | Regex baseline | Muse Spark 1.3 (`minimal` reasoning) |
|---|---|---|
| Simple (25) | 100% | 100% |
| Moderate (50) | 92.0% | 92.0% |
| Hard (75) | 66.7% | **94.7%** |
| **All (150)** | **80.7%** | **94.7%** |

- On courses Muse Spark did **not** flag for review: 97.0% correct. It flagged 11% of courses,
  including 4 of the 5 texts labeled genuinely ambiguous and 4 of its 8 errors.
- On the 130 gold courses that also have a Mendeley parse: Muse Spark 96.9%, the dataset's own
  published parses 90.8%.
- Caltech (20 courses, no published parse, labeled from scratch): 16/20.
- Cost $0.0025 per course, median latency 1.3 s. Run summaries: `results/*_gold_summary.json`.

## Development results (dev split, 300 courses, silver reference)

Agreement with the Mendeley parses, which contain known errors, so these numbers are a lower
bound; gold-set accuracy will be reported once the test set is hand-labeled.

| Parser | Agreement | Moderate tier, unflagged | $/course | Median latency |
|---|---|---|---|---|
| Regex baseline | 84.7% | 82.0% | 0 | – |
| Muse Spark 1.3, prompt v2, `minimal` reasoning | 87.3% | 98.6% | 0.0022 | 1.0 s |

Most remaining disagreements were traced to the reference: it omits corequisites, flattens
explicit AND/OR structure for one institution, and in some catalogs counts the next course's
heading (extracted onto the end of the prerequisite text) as a prerequisite.
**Second parser (Muse Spark Open), 150 dev courses:** on its own it scores 88.0%, the same as
Muse Spark. The two disagreed on only 3 courses (2%), all garbled catalog rows Muse Spark already
flagged, so the second opinion caught no new errors here, at about 4x the tokens and +4 s per course.
Muse Spark Open is the open-weights release of the same model family, and the two largely fail on the
same inputs; an independent check needs a verifier that fails differently. The deterministic
guardrails remain the main safety net.

**Audit checks, planted-defect evaluation** (5 real catalogs x 5 random seeds, 400 planted defects):
courses requiring a non-existent course 100% found, a required course removed from the catalog 99%,
prerequisite loops 100%, courses requiring themselves 100%; 0 false alarms. (Loops through a
corequisite are correctly not reported: both courses can be taken together.)

**Audit of 13 real catalogs** (Mendeley reference parses, 17,237 courses): see `results/audit/`.
Examples: a UAEU course that lists itself as its own prerequisite (CURR710); an AUS lecture and lab
that each require the other (CHM 101 / CHM 101L); UAEU courses still requiring codes renumbered
after 2023-24 (NUTR377, now NUTR376). Findings on reference parses inherit that reference's errors.

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

Website locally: `python scripts/export_site.py && python -m http.server -d site 8000`, then open
http://localhost:8000. Data files in `site/data/` are derived from the datasets above under their
licenses (Mendeley CC BY 4.0; UIUC CC BY-SA 4.0).
