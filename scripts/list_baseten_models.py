"""List the Baseten Model API slugs this key can call (to find the Muse Spark Open slug)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from auditor.llm import get_baseten_client  # noqa: E402

ids = sorted(m.id for m in get_baseten_client().models.list().data)
print(f"{len(ids)} models:")
for i in ids:
    print(" *" if "muse" in i.lower() or "meta" in i.lower() else "  ", i)
