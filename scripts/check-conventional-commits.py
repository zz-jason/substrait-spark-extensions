#!/usr/bin/env python3
"""Validate commit subjects and pull/merge request titles as Conventional Commits."""

import argparse
import re
import subprocess
import sys

ALLOWED_TYPES = (
    "build|chore|ci|docs|feat|fix|perf|refactor|revert|style|test"
)
HEADER = re.compile(
    rf"^(?:{ALLOWED_TYPES})(?:\([a-z0-9][a-z0-9._/-]*\))?!?: [a-z0-9].*$"
)
MAX_HEADER_LENGTH = 100


def validate(value: str, label: str) -> list[str]:
    errors: list[str] = []
    if not HEADER.fullmatch(value):
        errors.append(
            f"{label} must match 'type(scope)!: concise description'; got: {value!r}"
        )
    if len(value) > MAX_HEADER_LENGTH:
        errors.append(
            f"{label} must be at most {MAX_HEADER_LENGTH} characters; got {len(value)}"
        )
    if value.endswith("."):
        errors.append(f"{label} must not end with a period")
    return errors


def git_subjects(revision_range: str | None) -> list[tuple[str, str]]:
    revision = revision_range or "HEAD"
    result = subprocess.run(
        ["git", "log", "--format=%H%x00%s", revision],
        check=True,
        capture_output=True,
        text=True,
    )
    subjects = []
    for line in result.stdout.splitlines():
        commit, subject = line.split("\0", 1)
        subjects.append((commit, subject))
    return subjects


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--range", dest="revision_range")
    parser.add_argument("--title")
    parser.add_argument("--title-only", action="store_true")
    args = parser.parse_args()

    errors: list[str] = []
    if args.title is not None:
        errors.extend(validate(args.title.strip(), "PR title"))
    if not args.title_only:
        for commit, subject in git_subjects(args.revision_range):
            errors.extend(validate(subject, f"commit {commit[:12]}"))

    if errors:
        print("Conventional Commits validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("Conventional Commits validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
