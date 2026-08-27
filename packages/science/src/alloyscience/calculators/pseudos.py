"""Fetch PAW pseudopotentials for an element pair from PSlibrary (QE's
pseudopotential site) so the espresso engine can run any two elements.

Tries the common PSlibrary 1.0.0 PBE PAW name variants for each element.
"""

from __future__ import annotations

import urllib.request
from pathlib import Path

BASE_URL = "https://pseudopotentials.quantum-espresso.org/upf_files/"
VARIANTS = (
    "pbe-n-kjpaw_psl.1.0.0", "pbe-dn-kjpaw_psl.1.0.0", "pbe-spn-kjpaw_psl.1.0.0",
    "pbe-dnl-kjpaw_psl.1.0.0", "pbe-spdn-kjpaw_psl.1.0.0", "pbe-nl-kjpaw_psl.1.0.0",
    "pbe-n-kjpaw_psl.0.3.1", "pbe-dn-kjpaw_psl.0.3.1", "pbe-spn-kjpaw_psl.0.3.1",
    "pbe-n-kjpaw_psl.0.1", "pbe-dn-kjpaw_psl.0.1",
)


def fetch_pseudopotentials(elements: list[str], pseudo_dir: str | Path) -> dict[str, str]:
    """Download one PBE PAW UPF per element (skipping ones already present).
    Returns {element: filename}; raises if an element cannot be found."""
    from .espresso import resolve_pseudopotentials

    pseudo_dir = Path(pseudo_dir)
    pseudo_dir.mkdir(parents=True, exist_ok=True)
    found, missing = resolve_pseudopotentials(pseudo_dir, elements)
    for el in missing:
        for variant in VARIANTS:
            name = f"{el}.{variant}.UPF"
            try:
                with urllib.request.urlopen(BASE_URL + name, timeout=30) as resp:
                    data = resp.read()
            except Exception:  # noqa: BLE001 — try the next naming variant
                continue
            if b"<UPF" not in data[:2000] and b"<PP_INFO" not in data[:5000]:
                continue
            (pseudo_dir / name).write_bytes(data)
            found[el] = name
            break
        else:
            raise RuntimeError(
                f"no PSlibrary PAW pseudopotential found for {el!r}; download a UPF manually into {pseudo_dir}"
            )
    return found
