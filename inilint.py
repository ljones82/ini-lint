#!/usr/bin/env python3
"""Lint INI files and report problems with exact line and column numbers."""

import argparse
import re
import sys
from dataclasses import dataclass

SECTION_RE = re.compile(r"^\[(.*)\]\s*$")
# Matches "key = value" or "key : value". The key group is greedy up to the
# first separator so a value containing "=" or ":" doesn't confuse the split.
KEYVAL_RE = re.compile(r"^([^=:]*)([=:])(.*)$")


@dataclass
class Problem:
    line: int
    col: int
    message: str


def lint_text(text, filename="<stdin>"):
    """Return a list of Problem objects found in the given INI text."""
    problems = []
    sections_seen = {}
    keys_seen = {}
    current_section = None

    for lineno, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line
        stripped = line.strip()

        if not stripped:
            continue
        if stripped.startswith(";") or stripped.startswith("#"):
            continue

        if stripped.startswith("["):
            bracket_col = line.index("[") + 1
            match = SECTION_RE.match(stripped)
            if not match:
                problems.append(Problem(
                    lineno, len(line) + 1,
                    "unterminated section header, expected closing ']'",
                ))
                continue
            name = match.group(1).strip()
            if not name:
                problems.append(Problem(
                    lineno, bracket_col + 1, "section name cannot be empty",
                ))
                continue
            if name in sections_seen:
                problems.append(Problem(
                    lineno, bracket_col,
                    f"duplicate section '{name}' "
                    f"(first defined at line {sections_seen[name]})",
                ))
                continue
            sections_seen[name] = lineno
            current_section = name
            keys_seen.setdefault(name, {})
            continue

        match = KEYVAL_RE.match(line)
        if not match:
            leading = len(line) - len(line.lstrip())
            problems.append(Problem(
                lineno, leading + 1,
                "expected 'key = value', a section header, or a comment",
            ))
            continue

        key_part, sep, _value_part = match.groups()
        key = key_part.strip()
        sep_col = len(key_part) + 1

        if not key:
            problems.append(Problem(
                lineno, sep_col, f"missing key before '{sep}'",
            ))
            continue

        key_col = len(key_part) - len(key_part.lstrip()) + 1

        if current_section is None:
            problems.append(Problem(
                lineno, key_col, f"key '{key}' is outside of any section",
            ))
            continue

        first_line = keys_seen[current_section].get(key)
        if first_line is not None:
            problems.append(Problem(
                lineno, key_col,
                f"duplicate key '{key}' in section [{current_section}] "
                f"(first set at line {first_line})",
            ))
            continue

        keys_seen[current_section][key] = lineno

    return problems


def lint_file(path):
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    return lint_text(text, filename=path)


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="inilint",
        description="Check INI files for structural problems.",
    )
    parser.add_argument("files", nargs="+", help="INI files to check")
    args = parser.parse_args(argv)

    total_problems = 0
    for path in args.files:
        try:
            problems = lint_file(path)
        except OSError as exc:
            print(f"inilint: cannot read {path}: {exc.strerror}", file=sys.stderr)
            total_problems += 1
            continue

        for problem in problems:
            print(f"{path}:{problem.line}:{problem.col}: error: {problem.message}")
        total_problems += len(problems)

        if not problems:
            print(f"{path}: no problems found")

    return 1 if total_problems else 0


if __name__ == "__main__":
    sys.exit(main())
