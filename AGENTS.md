# Agent Instructions

This file defines agent behavior only. It does not describe the protocol and does not replace the README.

## Communication

1. State the conclusion first, then the evidence that supports it. Do not restate the request or explain the same thing twice.
2. Give one plan and proceed. List alternatives only when the user asks for a comparison.
3. Keep replies short, formal and free of translationese. Use the common wording for a term.
4. Close with what changed, how it was verified, and what could not be verified.

## Before changing files

1. Read the user's latest request, the working tree and the nearest `AGENTS.md` first.
2. Confirm the directory and uncommitted changes with `pwd`, `git status --short` and `rg --files`. Never overwrite the user's or another agent's work.
3. Touch production code only when the task requires it.
4. Work on the files the task names. Untracked directories that already exist are not part of the task.

## Single source of truth and compatibility

1. `protocol/contract.json` and `extensions/functions_spark.yaml` are the canonical protocol sources. Read `README.md` and the contract before changing protocol files.
2. The contract is the single declaration of payload fields, enums, function identities and options. Never hand-write a parallel field table, in a consumer or in a test.
3. Do not hand-edit files under `generated/` or `capabilities/capabilities.json`. Run `python3 tools/generate.py generate`.
4. One wire schema, described by the contract. Do not add a second typed schema, and reject unknown fields and undeclared option values explicitly.
5. Preserve protobuf field numbers and enum values. Reserve removed numbers and names.
6. Keep the unreleased contract on one version. Plan identity comes from the canonical digest the contract derives from its own content, not from a version number.
7. Keep this repository implementation-neutral. Engine names, source paths, version pins, mappings, benchmarks and implementation capability profiles are prohibited.
8. Do not add arbitrary executable expressions, scripts, templates or evaluation hooks to the contract.
9. Update the contract, the generator, the generated output, the tests and the README in the same round as a rename or concept change.

## Code and layout

1. Use English for documentation, comments, identifiers, generated text, commit messages and release notes.
2. Add no new schema, tool or test framework without user confirmation, and no abstraction layer for future needs.
3. Keep a file under 1000 lines. Use four-space indentation and the repository formatter.
4. Keep the generator and build tooling on the Python 3 standard library.
5. Keep the generator readable: one responsibility per function and no hidden rewriting of the contract.

## Artifacts and dependencies

1. Build the distribution artifact from the contract with `tools/build_artifact.py` and keep its content list in sync with the contract.
2. Do not commit generated archives from `dist/`, caches or temporary files.
3. Add a dependency only when the Python 3 standard library cannot satisfy the need, and record its purpose in the change.
4. Maintain versions in one place. No dynamic versions and no unpinned CI tool versions.
5. Never commit tokens, credentials or temporary files.

## Documentation

1. Write repository documentation, code comments, commit messages and pull request titles in English.
2. Document current decisions only. A historical implementation belongs in an explicitly archived document.
3. Update the README, examples and generated documentation that a change affects in the same round.
4. This file holds agent behavior only, not protocol design.

## Validation

1. Run `./build.sh` after every protocol change: contract validation, generator check, unit tests and artifact build.
2. Add or update a test in the same round as the change.
3. A documentation-only change needs at least `git diff --check`.
4. State in the final reply what could not run and why.

## Git and CI

1. Follow Conventional Commits for commit messages and pull request titles: `type(scope)!: concise description`, with an imperative English subject and no trailing period.
2. The repository allows squash merges only, so the pull request title becomes the commit subject and must follow the format above.
3. Sign every commit with the SSH signing key configured for the repository. Do not commit when the signature cannot be confirmed.
4. Do not commit or push unless the user explicitly requests it. Do not amend an existing commit or rewrite shared history.
5. Never commit build output, caches or temporary files.
6. Run version-independent checks once. Use version-keyed caches when a check needs a toolchain, and pin CI tools and container images.
