# Agent Instructions

- Use English for documentation, comments, identifiers, generated text, commit messages, and release notes.
- Read `README.md` and `protocol/contract.json` before changing protocol files.
- Treat `protocol/contract.json` and `extensions/functions_spark.yaml` as canonical protocol sources.
- Keep this repository implementation-neutral. Engine names, source paths, version pins, mappings, benchmarks, and implementation capability profiles are prohibited.
- Do not hand-edit files under `generated/` or `capabilities/capabilities.json`; run `python3 tools/generate.py generate`.
- Keep the generator and build tooling compatible with the Python 3 standard library.
- Do not add arbitrary executable expressions, scripts, templates, or evaluation hooks to the contract.
- Preserve protobuf field numbers and enum values. Reserve removed numbers and names.
- Run `./build.sh` after every protocol change.
- Do not commit generated archives from `dist/`.
- Do not commit or push unless the user explicitly requests it.
