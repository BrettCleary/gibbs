"""Export the OpenAPI schema so the TypeScript client can be generated from it.

Usage: python -m alloylab.export_openapi [output_path]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from .main import create_app


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("openapi.json")
    schema = create_app().openapi()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(schema, indent=2))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
