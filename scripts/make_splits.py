"""Create the frozen dev/test split and the gold-label annotation sheet.

Run once. Outputs (committed to the repo):
  evals/splits/dev.csv, evals/splits/test.csv   course ids per split
  evals/gold/test_gold_to_annotate.csv          150 test courses to hand-label

Design
- One row per course identity (institution + canonical_code), latest edition only,
  so the same course can never appear in both dev and test.
- Split by a hash of the course identity (20% test): deterministic, no random seed to lose.
- Gold sample oversamples hard cases and flattens institution sizes, so one large
  university cannot dominate the score. Caltech has no reference parse and is
  labeled from scratch.
"""
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from auditor.data import ROOT, difficulty, is_english, load_courses, load_reference_parses  # noqa: E402
from auditor.notation import to_text  # noqa: E402

GOLD_SIZES = {"simple": 25, "moderate": 45, "hard": 60}
CALTECH_GOLD = 20
SEED = 20261027


def is_test(institution: str, canonical_code: str) -> bool:
    h = hashlib.sha1(f"{institution}|{canonical_code}".encode()).hexdigest()
    return int(h, 16) % 5 == 0


def main() -> None:
    courses = load_courses()
    refs = load_reference_parses(courses)

    pop = courses[courses.has_prereq_text & ~courses.ambiguous_id].copy()
    pop = pop[pop.prerequisites_raw.map(is_english) & pop.corequisites_raw.map(is_english)]
    pop["canonical_code"] = pop["canonical_code"].where(pop["canonical_code"] != "", pop["code"])
    pop = pop.sort_values("edition").drop_duplicates(["institution", "canonical_code"], keep="last")
    pop["tier"] = [
        difficulty(p, c, o)
        for p, c, o in zip(pop.prerequisites_raw, pop.corequisites_raw, pop.prereq_operator_stated)
    ]
    pop["has_reference"] = pop.course_id.isin(refs)
    pop["split"] = ["test" if is_test(i, c) else "dev" for i, c in zip(pop.institution, pop.canonical_code)]

    cols = ["course_id", "institution", "edition", "code", "tier", "has_reference"]
    out = ROOT / "evals" / "splits"
    out.mkdir(parents=True, exist_ok=True)
    for split in ("dev", "test"):
        pop[pop.split == split][cols].sort_values("course_id").to_csv(out / f"{split}.csv", index=False)

    # ---- gold sample (test split only)
    test = pop[pop.split == "test"]
    picks = []
    for tier, n in GOLD_SIZES.items():
        pool = test[(test.tier == tier) & test.has_reference]
        weights = 1.0 / pool.groupby("institution")["course_id"].transform("count")
        picks.append(pool.sample(n=n, weights=weights, random_state=SEED))
    caltech = test[test.institution == "California Institute of Technology"]
    picks.append(caltech.sample(n=CALTECH_GOLD, random_state=SEED))
    gold = __import__("pandas").concat(picks).sample(frac=1, random_state=SEED)

    gold_out = gold.assign(
        id=gold.course_id,
        proposed=[to_text(refs[c]) if c in refs else "" for c in gold.course_id],
        verdict="",
        corrected="",
        notes="",
    )[["id", "institution", "code", "tier", "prerequisites_raw", "corequisites_raw",
       "proposed", "verdict", "corrected", "notes"]]
    gdir = ROOT / "evals" / "gold"
    gdir.mkdir(parents=True, exist_ok=True)
    gold_path = gdir / "test_gold_to_annotate.csv"
    if gold_path.exists():
        print(f"NOT overwriting {gold_path} (it may contain your labels). Delete it to regenerate.")
    else:
        gold_out.to_csv(gold_path, index=False)

    # ---- summary
    print(f"population: {len(pop)} courses ({pop.has_reference.sum()} with a reference parse)")
    print(pop.groupby(["split", "tier"]).size().unstack().to_string())
    print("\ngold sample by tier:", gold.tier.value_counts().to_dict())
    print("gold sample by institution:", gold.institution.value_counts().to_dict())


if __name__ == "__main__":
    main()
