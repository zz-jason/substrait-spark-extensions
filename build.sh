#!/usr/bin/env sh
set -eu
export PYTHONDONTWRITEBYTECODE=1
cd "$(dirname "$0")"
python3 tools/generate.py validate
python3 tools/generate.py check
python3 -m unittest discover -s tests -v
python3 tools/build_artifact.py --output dist
