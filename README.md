# inilint

A command-line linter for INI files. It checks structure — section headers,
key/value lines, duplicates — and reports every problem with an exact line
and column number, the way a compiler does.

## Why

INI has no real specification, so every parser is a little different, and
most of them are bad at telling you what's wrong. Python's own
`configparser`, for example, will happily raise `MissingSectionHeaderError`
or `DuplicateOptionError` without a column, and it stops at the first error
instead of showing you everything wrong with the file. `inilint` is meant
for the case where you just want a quick, blunt answer to "is this file
well-formed, and if not, exactly where."

## Usage

```
$ python3 inilint.py config.ini
```

Given a broken file like this:

```ini
[server]
host = localhost
port = 8080

[server]
timeout = 30

port
```

`inilint` reports:

```
config.ini:5:1: error: duplicate section 'server' (first defined at line 1)
config.ini:8:1: error: expected 'key = value', a section header, or a comment
```

A clean file produces:

```
$ python3 inilint.py config.ini
config.ini: no problems found
```

You can check several files in one call; the exit code is `1` if any file
had a problem, `0` otherwise.

## What it checks (so far)

- Section headers missing a closing `]`
- Empty section names (`[]`)
- Duplicate section names, with a pointer back to the first definition
- Key/value lines with no key (e.g. a bare `= value`)
- Keys defined before any `[section]`
- Duplicate keys within the same section, with a pointer back to the first
  definition

Blank lines and comments (`;` or `#`) are ignored, as usual.

## Not yet handled

Multi-line values (continuation lines), inline comments after a value, and
configurable dialects (case sensitivity, alternate comment characters) are
left for later — see the roadmap in commit history.

## Requirements

Python 3.9+, standard library only.

## License

MIT, see LICENSE.
