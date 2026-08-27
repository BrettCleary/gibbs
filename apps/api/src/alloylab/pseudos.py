"""Fetch PSlibrary PAW pseudopotentials for elements into the configured pseudo_dir.

    uv run --package alloylab python -m alloylab.pseudos Cu Au
"""

from __future__ import annotations

import sys

from alloyscience.calculators import fetch_pseudopotentials

from .config import get_settings


def main(argv: list[str]) -> int:
    if not argv:
        print("usage: python -m alloylab.pseudos <El> [<El> ...]", file=sys.stderr)
        return 2
    pseudo_dir = get_settings().pseudo_dir
    found = fetch_pseudopotentials([a.capitalize() for a in argv], pseudo_dir)
    for el, name in found.items():
        print(f"{el}: {name}")
    print(f"pseudo_dir: {pseudo_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
