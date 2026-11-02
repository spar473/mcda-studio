"""Write the API's OpenAPI document to docs/api/openapi.json (the machine-readable contract).

The frontend generates its TypeScript types from this file, so the Python domain models remain
the single source of truth. ``python scripts/export_openapi.py --check`` exits 1 if the committed
file is out of date (a test runs the same comparison).
"""

import json
import sys
import tempfile
from pathlib import Path

from mcda_studio.api import create_app

TARGET = Path(__file__).resolve().parents[1] / "docs" / "api" / "openapi.json"


def render() -> str:
    with tempfile.TemporaryDirectory() as tmp:
        spec = create_app(tmp, examples_dir=None, frontend_dir=False).openapi()
    return json.dumps(spec, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main() -> int:
    text = render()
    if "--check" in sys.argv:
        if not TARGET.is_file() or TARGET.read_text(encoding="utf-8") != text:
            print(f"{TARGET} is out of date; run: python scripts/export_openapi.py")
            return 1
        print("openapi.json is up to date")
        return 0
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(text, encoding="utf-8")
    print(f"wrote {TARGET} ({len(text)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
