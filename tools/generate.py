#!/usr/bin/env python3
"""Validate the canonical contract and generate dependency-free catalogs."""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from protocol_contract import (  # noqa: E402
    CAPABILITIES_PATH,
    CONTRACT_PATH,
    GENERATED_PATH,
    ContractError,
    load_json,
    validate_contract,
)
from protocol_render import check_rendered, rendered_files, write_rendered  # noqa: E402

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["validate", "generate", "check"])
    args = parser.parse_args()
    contract = load_json(CONTRACT_PATH)
    validate_contract(contract)
    if args.command == "validate":
        print(f"valid contract {contract['protocol']['version']} {contract['protocol']['canonicalSha256']}")
        return 0
    expected = rendered_files(contract)
    if args.command == "check":
        check_rendered(expected)
        print(f"generated output is current ({len(expected)} files)")
        return 0
    with tempfile.TemporaryDirectory(prefix="substrait-spark-generate-") as directory:
        temporary_root = Path(directory)
        write_rendered(expected, temporary_root)
        if GENERATED_PATH.exists():
            shutil.rmtree(GENERATED_PATH)
        shutil.copytree(temporary_root / "generated", GENERATED_PATH)
        CAPABILITIES_PATH.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(temporary_root / "capabilities" / "capabilities.json", CAPABILITIES_PATH)
    print(f"generated {len(expected)} files")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ContractError as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1)
