"""Hand-label the gold test set, one course at a time, in the terminal.

    python scripts/label_gold.py

Keys:  o = proposed is correct    f = fix it (type the correct parse)
       a = ambiguous text          s = skip for now
       While editing a parse, '=' alone keeps the proposed parse.
       b = back to previous row    q = save and quit      ? = notation help

Saves after every row, so you can quit and resume any time.
Rules are in evals/gold/ANNOTATION_GUIDE.md.
"""
import os
import sys
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd  # noqa: E402

from auditor import baseline  # noqa: E402
from auditor.data import ROOT  # noqa: E402
from auditor.notation import from_text, to_text  # noqa: E402

PATH = ROOT / "evals" / "gold" / "test_gold_to_annotate.csv"

HELP = """
  NONE                                      no requirement at all
  CSC 210 AND (MATH 243 OR MATH 223)        AND between groups, OR inside a group
  MATH 210 [min C]                          minimum grade
  PHYS 141 [concurrent]                     taken at the same time (corequisite field)
  PHYS 141 [prior or concurrent]            before or at the same time
  CSC 210 COND: consent of instructor       non-course requirements, separated by ;
  "X or instructor's permission"  ->  X COND: or instructor's permission
  "(A and B) or C"                ->  (A OR C) AND (B OR C)
  Label what the TEXT says. A convention not in the text (e.g. * = corequisite) -> ambiguous.
"""

try:  # pre-fill the input line with the proposed parse so a fix is a small edit
    import readline

    def ask(prompt: str, prefill: str = "") -> str:
        readline.set_startup_hook(lambda: readline.insert_text(prefill))
        try:
            return input(prompt)
        finally:
            readline.set_startup_hook()
except ImportError:  # pragma: no cover
    def ask(prompt: str, prefill: str = "") -> str:
        if prefill:
            print(f"  (start from: {prefill})")
        return input(prompt)


def save(df: pd.DataFrame) -> None:
    tmp = PATH.with_suffix(".tmp")
    df.to_csv(tmp, index=False)
    os.replace(tmp, PATH)


def read_parse(prompt: str, prefill: str) -> str:
    """Ask until the text is valid notation; return it normalized."""
    while True:
        text = ask(prompt, prefill).strip()
        if text == "=":                      # shortcut: keep the proposed parse as is
            text = prefill
        if not text:
            print("  ! Empty. Type the parse, '=' to keep the proposed one, or NONE for no requirement.")
            continue
        try:
            return to_text(from_text(text))
        except ValueError as exc:
            print(f"  ! {exc}. Try again (? for help).")
            prefill = text


def wrap(label: str, text: str) -> str:
    return textwrap.fill(text, width=100, initial_indent=f"  {label:<10}", subsequent_indent=" " * 12)


def main() -> None:
    df = pd.read_csv(PATH, dtype=str, keep_default_na=False)
    order = list(df.index)
    history = []
    i = 0
    while i < len(order):
        idx = order[i]
        r = df.loc[idx]
        if r.verdict:                        # already labeled
            i += 1
            continue
        done = int((df.verdict != "").sum())
        proposed = r.proposed
        suggestion_note = ""
        if not proposed:
            proposed = to_text(baseline.parse(r.prerequisites_raw, r.corequisites_raw))
            suggestion_note = "  (no reference: suggestion from the regex baseline, check carefully)"
        print("\n" + "-" * 100)
        print(f"  {done}/{len(df)} labeled   |   {r.institution}   {r.code}   [{r.tier}]")
        print(wrap("PREREQ:", r.prerequisites_raw))
        if r.corequisites_raw:
            print(wrap("COREQ:", r.corequisites_raw))
        print(wrap("PROPOSED:", proposed) + suggestion_note)
        if r.verdict:
            print(f"  (currently: {r.verdict} {r.corrected} {r.notes})")

        key = ask("  [o]k  [f]ix  [a]mbiguous  [s]kip  [b]ack  [q]uit  [?]  > ").strip().lower()[:1]
        if key == "?":
            print(HELP)
            continue
        if key == "q":
            save(df)
            print(f"Saved. {done}/{len(df)} labeled.")
            return
        if key == "s":
            i += 1
            continue
        if key == "b":
            if history:
                prev = history.pop()
                df.loc[prev, ["verdict", "corrected", "notes"]] = ""
                save(df)
                i = order.index(prev)
            else:
                print("  nothing to go back to")
            continue
        if key == "o":
            if not r.proposed:   # no reference: accepting means confirming the baseline suggestion
                df.loc[idx, ["verdict", "corrected", "notes"]] = ["fix", proposed, "confirmed baseline suggestion"]
            else:
                df.loc[idx, ["verdict", "corrected", "notes"]] = ["ok", "", ""]
        elif key == "f":
            corrected = read_parse("  correct parse > ", proposed)
            note = ask("  note (optional) > ").strip()
            df.loc[idx, ["verdict", "corrected", "notes"]] = ["fix", corrected, note]
        elif key == "a":
            best = read_parse("  best reading (edit or keep) > ", proposed)
            note = ""
            while not note:
                note = ask("  why is it ambiguous? > ").strip()
            corrected = "" if best == r.proposed else best
            df.loc[idx, ["verdict", "corrected", "notes"]] = ["ambiguous", corrected, note]
        else:
            print("  ? unknown key")
            continue
        save(df)
        history.append(idx)
        i += 1

    left = int((df.verdict == "").sum())
    print(f"\nEnd of list. {len(df) - left}/{len(df)} labeled" + (f", {left} skipped: run again to finish them." if left else ". All done!"))


if __name__ == "__main__":
    main()
