# Gold-label annotation guide

`test_gold_to_annotate.csv` holds 150 courses from the **test split**. These labels are the
ground truth for the parser's headline accuracy. Label them by hand; never tune prompts on
these rows.

## For each row

Read `prerequisites_raw` and `corequisites_raw`, then look at `proposed`
(the Mendeley dataset's parse, written in the notation below; blank for Caltech).

| verdict | when | what to fill in |
|---|---|---|
| `ok` | `proposed` is exactly right | nothing else |
| `fix` | `proposed` is wrong or blank | the correct parse in `corrected` |
| `ambiguous` | the text itself can't be read one way (e.g. no operator stated, a footnote symbol) | your best reading in `corrected` (or leave blank to keep `proposed`); say why in `notes` |

**Label what the text says, not what you think the catalog meant.** If a parse depends on a
convention that isn't in the text (like `*` meaning co-requisite), that is `ambiguous`.

## Notation

```
NONE                                          no requirement at all
CSC 210                                       one course
CSC 210 AND (MATH 243 OR MATH 223)            AND between groups, OR inside a group
MATH 210 [min C]                              minimum grade
PHYS 141 [concurrent]                         must be taken at the same time
PHYS 141 [prior or concurrent]                before or at the same time
CSC 210 COND: consent of instructor           non-course requirement(s), separated by ;
COND: senior standing                         only a non-course requirement
```

- Copy course codes as written; spacing and case don't matter when scoring.
- "X or equivalent" → `X`, with `COND: or equivalent`.
- "X, or instructor's permission" → `X COND: or instructor's permission`
  (the parser should flag these; an OR between a course and a condition can't be
  expressed as a group).
- Corequisite field courses get `[concurrent]` unless the text says "prior or concurrent".
- Only one level of nesting fits: rewrite "(A and B) or C" as `(A OR C) AND (B OR C)`.

## Check your work

```
python -c "import sys; sys.path.insert(0,'src'); from auditor.data import load_gold; from pathlib import Path; print(len(load_gold(Path('evals/gold/test_gold_to_annotate.csv'), allow_partial=True)), 'rows labeled')"
```
It raises an error naming the row if any label can't be read.
