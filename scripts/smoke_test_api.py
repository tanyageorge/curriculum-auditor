"""First Muse Spark call: parse one prerequisite sentence into the PrereqParse schema.

Usage:  python scripts/smoke_test_api.py
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from auditor.llm import default_model, get_client, response_format  # noqa: E402
from auditor.notation import to_text  # noqa: E402
from auditor.schema import PrereqParse  # noqa: E402

TEXT = "CSC 210 and (MATH 243 or MATH 223) with a grade of C or better; consent of instructor."

client, model = get_client(), default_model()
t0 = time.time()
resp = client.chat.completions.create(
    model=model,
    messages=[
        {"role": "system", "content": "Convert the course prerequisite text into the JSON schema. "
                                      "Groups are ANDed; options within a group are ORed."},
        {"role": "user", "content": TEXT},
    ],
    response_format=response_format(PrereqParse, "prereq_parse"),
    reasoning_effort="low",
)
elapsed = time.time() - t0

raw = resp.choices[0].message.content
parse = PrereqParse.model_validate_json(raw)
print("model:   ", resp.model)
print("input:   ", TEXT)
print("parsed:  ", to_text(parse))
print("json:    ", json.dumps(json.loads(raw)))
print(f"latency:  {elapsed:.1f}s")
print("usage:   ", resp.usage)
