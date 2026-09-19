# Agent Instructions

This file defines agent behavior only. It does not describe the protocol and does not replace the README.

## Communication style

1. State the conclusion first, then the evidence that supports it. Do not restate the request or explain the same thing twice.
2. Give one plan and proceed. List alternatives only when the user asks for a comparison.
3. Keep replies short, formal and free of translationese. Use the common wording for a term.
4. Close with what changed, how it was verified, and what could not be verified.

## Single source of truth and compatibility

1. `protocol/contract.json` and `extensions/functions_spark.yaml` are the canonical protocol sources. Read `README.md` and the contract before changing protocol files.
2. The contract is the single declaration of payload fields, enums, function identities and options. Never hand-write a parallel field table, in a consumer or in a test.
3. Do not hand-edit files under `generated/` or `capabilities/capabilities.json`. Run `python3 tools/generate.py generate`.
4. One wire schema, described by the contract. Do not add a second typed schema, and reject unknown fields and undeclared option values explicitly.
5. Preserve protobuf field numbers and enum values. Reserve removed numbers and names.
6. Keep the unreleased contract on one version. Plan identity comes from the canonical digest the contract derives from its own content, not from a version number.
7. Update the contract, the generator, the generated output, the tests and the README in the same round as a rename or concept change.
8. Keep this repository implementation-neutral. Engine names, source paths, version pins, mappings, benchmarks and implementation capability profiles are prohibited.

## Design constraints

1. Keep the contract declarative. Do not add arbitrary executable expressions, scripts, templates or evaluation hooks to it.
2. Keep one wire schema and one declaration per concept; never introduce a second representation of a field, an enum or an option.
3. Keep the generator and build tooling on the Python 3 standard library so the artifact builds anywhere.
4. Keep the generator readable: one responsibility per function and no hidden rewriting of the contract.
5. Keep the distribution artifact content list derived from the contract rather than written by hand.
6. Fail loudly on an unknown field, an undeclared option value or a stale generated file instead of guessing.

## Documentation and comments

1. Write repository documentation, code comments, commit messages and pull request titles in English. Use English identifiers and generated text.
2. Document current decisions only. A historical implementation belongs in an explicitly archived document.
3. Update the README, examples and generated documentation that a change affects in the same round.
4. This file holds agent behavior only, not protocol design.

## Code and directory constraints

1. Add no new schema, tool or test framework without user confirmation.
2. Keep a file under 1000 lines. Use four-space indentation and the repository formatter.
3. Maintain versions in one place. No dynamic versions and no unpinned CI tool versions.
4. Never commit generated archives from `dist/`, caches, temporary files, build output, secrets or credentials.

## Git and commit rules

1. Follow Conventional Commits for commit messages and pull request titles: `type(scope)!: concise description`, with an imperative English subject and no trailing period.
2. The repository allows squash merges only, so the pull request title becomes the commit subject and must follow the format above.
3. Sign every commit with the SSH signing key configured for the repository. Do not commit when the signature cannot be confirmed.
4. Do not commit or push unless the user explicitly requests it. Do not amend an existing commit or rewrite shared history.
5. Before committing, run `./build.sh` for a protocol change: contract validation, generator check, unit tests and artifact build. A documentation-only change needs at least `git diff --check`.
6. GitHub Actions is the engineering gate. Reuse the repository scripts so local and CI rules cannot drift, run version-independent checks once, and pin CI tools and container images.
