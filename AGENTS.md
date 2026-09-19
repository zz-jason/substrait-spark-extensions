# Agent Instructions

This file defines agent behavior only. It does not describe the protocol and does not replace the README.

## Communication

1. State the conclusion first, then the evidence that supports it. Do not restate the request.
2. Give one plan and proceed. List alternatives only when the user asks for a comparison.
3. Close with what changed, how it was verified, and what could not be verified.

## Canonical sources

1. `protocol/contract.json` and `extensions/functions_spark.yaml` are the canonical protocol sources. Read `README.md` and the contract before changing protocol files.
2. The contract is the single declaration of payload fields, enums, function identities and options. Never hand-write a parallel field table, in a consumer or in a test.
3. Do not hand-edit files under `generated/` or `capabilities/capabilities.json`; run `python3 tools/generate.py generate`.
4. One wire schema, described by the contract. Do not add a second typed schema, and reject unknown fields and undeclared option values explicitly.
5. Preserve protobuf field numbers and enum values. Reserve removed numbers and names.
6. Keep this repository implementation-neutral. Engine names, source paths, version pins, mappings, benchmarks and implementation capability profiles are prohibited.
7. Do not add arbitrary executable expressions, scripts, templates or evaluation hooks to the contract.
8. Keep the unreleased contract on one version. Plan identity comes from the canonical digest the contract derives from its own content, not from a version number.
9. Keep the generator and build tooling on the Python 3 standard library.

## Code and layout

1. Use English for documentation, comments, identifiers, generated text, commit messages and release notes.
2. Add no new service, schema or test framework without user confirmation, and no abstraction layer for future needs.
3. Fix a rename or concept change in one round: contract, generator, generated output, tests and README together.
4. Keep a file under 1000 lines. Use four-space indentation and the repository formatter.

## Validation

1. Run `./build.sh` after every protocol change: contract validation, generator check, unit tests and artifact build.
2. Add or update a test in the same round as the change; a documentation-only change needs at least `git diff --check`.
3. State in the final reply what could not run and why.

## Git

1. Use English Conventional Commits with an imperative subject and no trailing period.
2. Sign every commit with the configured SSH signing key. Do not commit when the signature cannot be confirmed.
3. The repository allows squash merges only, so the pull request title becomes the commit subject and must follow the same format.
4. Do not commit generated archives from `dist/`, caches or temporary files.
5. Do not commit or push unless the user explicitly requests it. Do not amend existing commits or rewrite shared history.
