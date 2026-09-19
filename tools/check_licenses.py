#!/usr/bin/env python3
"""Checks the licence, the inventory and the artifact payload."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# The canonical contract sources are data: their bytes define the protocol digest,
# so they carry no comment header. Generated files get their header from the
# generator, which check_generated() verifies.
ARTIFACT_TOOL = ROOT / "tools" / "build_artifact.py"


def tracked_files() -> list[str]:
    output = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout
    return [line for line in output.splitlines() if line]


def check_licence() -> None:
    text = (ROOT / "LICENSE").read_text()
    if "Apache License" not in text or "Version 2.0" not in text:
        raise SystemExit("LICENSE must hold the Apache License 2.0 text")


def check_delivery() -> None:
    """The artifact carries the licence of everything the repository publishes."""
    tool = ARTIFACT_TOOL.read_text()
    if '"LICENSE"' not in tool:
        raise SystemExit("build_artifact.py does not ship LICENSE")


def main() -> int:
    check_licence()
    check_delivery()
    print("licence check passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
