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
# An inline comment must be preceded by whitespace, so a literal ';' or '#'
# inside a value (a URL fragment, a password) isn't mistaken for one.
INLINE_COMMENT_RE = re.compile(r"[ \t][;#]")


def _strip_inline_comment(text):
    match = INLINE_COMMENT_RE.search(text)
    return text[:match.start()] if match else text


@dataclass
class Problem:
    line: int
    col: int
    message: str


def lint_text(text, filename="<stdin>", strict=False):
    """Return a list of Problem objects found in the given INI text.

    A value may continue onto following lines: any line that is indented
    (starts with a space or tab) is treated as part of the previous key's
    value, as long as the previous non-blank line was itself a key or a
    continuation of one. Blank lines and comments break the continuation,
    so an indented line right after either of those is an error rather
    than silently absorbed.

    Section and key names are compared case-insensitively by default,
    matching the common INI convention (Windows .ini files work this way),
    since that's the more common source of accidental duplicates. Pass
    strict=True to compare them exactly as written instead.
    """
    problems = []
    sections_seen = {}
    keys_seen = {}
    current_section = None
    current_section_key = None
    continuation_active = False

    def fold(name):
        return name if strict else name.lower()

    for lineno, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line
        stripped = line.strip()

        if not stripped:
            continuation_active = False
            continue
        if stripped.startswith(";") or stripped.startswith("#"):
            continuation_active = False
            continue

        if line[0] in (" ", "\t"):
            if continuation_active:
                continue
            leading = len(line) - len(line.lstrip())
            problems.append(Problem(
                lineno, leading + 1,
                "continuation line with no preceding 'key = value' line",
            ))
            continue

        if stripped.startswith("["):
            continuation_active = False
            header = _strip_inline_comment(stripped)
            bracket_col = line.index("[") + 1
            match = SECTION_RE.match(header)
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
            section_key = fold(name)
            if section_key in sections_seen:
                problems.append(Problem(
                    lineno, bracket_col,
                    f"duplicate section '{name}' "
                    f"(first defined at line {sections_seen[section_key]})",
                ))
                continue
            sections_seen[section_key] = lineno
            current_section = name
            current_section_key = section_key
            keys_seen.setdefault(section_key, {})
            continue

        match = KEYVAL_RE.match(line)
        if not match:
            leading = len(line) - len(line.lstrip())
            problems.append(Problem(
                lineno, leading + 1,
                "expected 'key = value', a section header, or a comment",
            ))
            continuation_active = False
            continue

        key_part, sep, _value_part = match.groups()
        key = key_part.strip()
        sep_col = len(key_part) + 1

        if not key:
            problems.append(Problem(
                lineno, sep_col, f"missing key before '{sep}'",
            ))
            continuation_active = False
            continue

        continuation_active = True
        key_col = len(key_part) - len(key_part.lstrip()) + 1

        if current_section is None:
            problems.append(Problem(
                lineno, key_col, f"key '{key}' is outside of any section",
            ))
            continue

        key_key = fold(key)
        first_line = keys_seen[current_section_key].get(key_key)
        if first_line is not None:
            problems.append(Problem(
                lineno, key_col,
                f"duplicate key '{key}' in section [{current_section}] "
                f"(first set at line {first_line})",
            ))
            continue

        keys_seen[current_section_key][key_key] = lineno

    return problems


def lint_file(path, strict=False):
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    return lint_text(text, filename=path, strict=strict)


def fix_text(text, strict=False):
    """Remove duplicate key definitions, keeping the first occurrence.

    Returns (fixed_text, removed_count). A removed key's continuation
    lines go with it. Everything else - comments, blank lines, duplicate
    sections, malformed lines - is left as-is, since guessing what the
    user meant there is more likely to make the file worse.

    Duplicate detection follows the same section/key folding rules as
    lint_text, including its quirk where a repeated section header does
    not reset the "current section" - so keys after it are still checked
    against the original section's keys. Fixing that file structure is
    out of scope for a key-only fix.
    """
    def fold(name):
        return name if strict else name.lower()

    output = []
    sections_seen = set()
    keys_seen = {}
    current_section_key = None
    continuation_active = False
    skip_continuation = False
    removed = 0

    for raw_line in text.splitlines(keepends=True):
        line = raw_line.rstrip("\r\n")
        stripped = line.strip()

        if not stripped:
            continuation_active = False
            skip_continuation = False
            output.append(raw_line)
            continue

        if stripped.startswith(";") or stripped.startswith("#"):
            continuation_active = False
            skip_continuation = False
            output.append(raw_line)
            continue

        if line[0] in (" ", "\t"):
            if continuation_active:
                if not skip_continuation:
                    output.append(raw_line)
                continue
            output.append(raw_line)
            continue

        if stripped.startswith("["):
            continuation_active = False
            skip_continuation = False
            output.append(raw_line)
            header = _strip_inline_comment(stripped)
            match = SECTION_RE.match(header)
            if not match:
                continue
            name = match.group(1).strip()
            if not name:
                continue
            section_key = fold(name)
            if section_key in sections_seen:
                continue
            sections_seen.add(section_key)
            current_section_key = section_key
            keys_seen.setdefault(section_key, set())
            continue

        match = KEYVAL_RE.match(line)
        if not match:
            continuation_active = False
            skip_continuation = False
            output.append(raw_line)
            continue

        key_part, _sep, _value_part = match.groups()
        key = key_part.strip()

        if not key:
            continuation_active = False
            skip_continuation = False
            output.append(raw_line)
            continue

        continuation_active = True

        if current_section_key is None:
            skip_continuation = False
            output.append(raw_line)
            continue

        key_key = fold(key)
        if key_key in keys_seen[current_section_key]:
            skip_continuation = True
            removed += 1
            continue

        skip_continuation = False
        keys_seen[current_section_key].add(key_key)
        output.append(raw_line)

    return "".join(output), removed


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="inilint",
        description="Check INI files for structural problems.",
    )
    parser.add_argument("files", nargs="+", help="INI files to check")
    parser.add_argument(
        "--strict", action="store_true",
        help="treat section and key names as case-sensitive "
             "(default: case-insensitive, e.g. [Server] and [server] collide)",
    )
    parser.add_argument(
        "--fix", action="store_true",
        help="remove duplicate key definitions in place, keeping the "
             "first occurrence of each key",
    )
    args = parser.parse_args(argv)

    total_problems = 0
    for path in args.files:
        try:
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
        except OSError as exc:
            print(f"inilint: cannot read {path}: {exc.strerror}", file=sys.stderr)
            total_problems += 1
            continue

        if args.fix:
            text, removed = fix_text(text, strict=args.strict)
            if removed:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(text)
                plural = "" if removed == 1 else "s"
                print(f"{path}: removed {removed} duplicate key{plural}")

        problems = lint_text(text, filename=path, strict=args.strict)
        for problem in problems:
            print(f"{path}:{problem.line}:{problem.col}: error: {problem.message}")
        total_problems += len(problems)

        if not problems:
            print(f"{path}: no problems found")

    return 1 if total_problems else 0


if __name__ == "__main__":
    sys.exit(main())
