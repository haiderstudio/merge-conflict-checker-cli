# merge-conflict-checker-cli

Check files for leftover merge-conflict markers, fail CI on a marker.

[![CI](https://github.com/haiderstudio/merge-conflict-checker-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/haiderstudio/merge-conflict-checker-cli/actions/workflows/ci.yml) [![Licence: MIT](https://img.shields.io/badge/Licence-MIT-yellow.svg)](LICENSE)

## What it does

`merge_conflict_checker` reads the files or folders you name and
looks for the lines git leaves behind when a merge is not finished:

- `<<<<<<< HEAD` — the start of a conflict
- `|||||||` — the base version, only when git is set to diff3 style
- `=======` — the separator between the two sides
- `>>>>>>> branch-name` — the end of a conflict

Every marker is reported with its file and line number, and the tool
exits 1 when any marker is found — so it can fail a CI run. A clean
tree exits 0.

- A marker only counts when it sits at the start of a line, uses
  exactly seven of the same character, and is followed by a space or
  the end of the line — the same rule the pre-commit hook uses. A
  line of eight equals signs in a comment banner is not a marker,
  and neither is a line that only starts with six angle brackets.
- Folders are walked recursively by default (`--no-recursive` stops
  at the top level). `.git` folders are never walked, and directory
  links are never followed, so a link cycle cannot loop the check.
- `--exclude PATTERN` skips files by glob, for example
  `--exclude '*.min.js'`. It can be repeated.
- Files that are not valid UTF-8 text are skipped, not reported as
  failures — a binary file cannot hold a conflict marker. Skipped
  files are counted in the summary.
- `--stdin` checks one file piped in, `--json` prints the result as
  machine-readable JSON (the summary goes to standard error, so
  standard output stays clean JSON).
- It is report-only and runs fully offline: it never rewrites a
  file, never resolves a conflict, sends nothing anywhere, and needs
  no API key.

## What it does NOT do

- It does not resolve conflicts. A marker is reported; fixing the
  file is your job.
- It does not predict conflicts. It only finds markers that are
  already in the files — two branches that will clash later are a
  different tool's job.
- It does not check whether a merge is in progress, and it does not
  talk to git at all except for never walking `.git` folders.
- It does not check anything else about a file — no syntax, no
  style, no secrets. Markers only.

## Who it is for

Anyone who has ever pushed a file with `<<<<<<< HEAD` still in it:
a developer adding a CI step that fails the build on a leftover
marker, a team lead who keeps finding half-finished merges in
reviews, or anyone who wants one small check instead of a marker
rule buried inside a big CI setup. If every file is clean, you get
a plain OK line; if one is not, the report says exactly which file
and line to open.

## How this differs from similar tools

The exact name `merge-conflict-checker-cli` matches 0 repositories
on GitHub. The unquoted search for `merge conflict checker` returns
14 results, and none of them is a local file scanner:

- The top result, outsideris/potential-conflicts-checker-action
  (10 stars), is a GitHub Action that predicts whether a pull
  request CAN conflict after other pull requests merge — it looks
  at branches, not at files, and it answers a different question.
- The other same-named repos are all 0 stars: a branch-conflict
  detector Action (Saumya0206/Conflict-Detector, 2 stars) that
  compares branches, and three small repos that check branches or
  plug into an editor.
- The closest existing check is `check-merge-conflict`, one hook
  inside the pre-commit-hooks collection. It does the same scan,
  but only as a pre-commit hook — you need pre-commit installed
  and configured. This tool is a standalone command: no hook
  framework, no install beyond Python, usable in any CI.
- The AI resolver n0conflict scans and then rewrites conflicts
  using an API key. This tool only reports; it never touches a
  file and needs no key.

This tool does a narrower job: a Python standard-library-only CLI
that scans files and folders for leftover markers, reports each
one with file and line, and exits 1 for CI — no install beyond
Python, no hook, no API key, no network.

## Install

Python standard library only — no packages to download. You need
Python 3.11 or newer. Clone the repo and run it in place:

```
git clone https://github.com/haiderstudio/merge-conflict-checker-cli.git
cd merge-conflict-checker-cli
python3 src/merge_conflict_checker.py examples/clean.py
```

```
OK — 1 file(s) checked, no merge-conflict markers.
```

## Usage

Check one file:

```
python3 src/merge_conflict_checker.py examples/conflicted.py
```

```
FAIL examples/conflicted.py:2: conflict start marker '<<<<<<< HEAD'
FAIL examples/conflicted.py:4: conflict separator marker '======='
FAIL examples/conflicted.py:6: conflict end marker '>>>>>>> feature-greeting'
Checked 1 file(s), 3 marker(s) in 1 file(s).
```

Check a whole folder (walked recursively):

```
python3 src/merge_conflict_checker.py src/
```

Check one file from standard input (no file named reads stdin):

```
cat examples/conflicted.py | python3 src/merge_conflict_checker.py --stdin
```

```
FAIL <stdin>:2: conflict start marker '<<<<<<< HEAD'
FAIL <stdin>:4: conflict separator marker '======='
FAIL <stdin>:6: conflict end marker '>>>>>>> feature-greeting'
Checked 1 file(s), 3 marker(s) in 1 file(s).
```

Machine-readable output with `--json` (the summary goes to
standard error, so standard output stays clean JSON):

```
python3 src/merge_conflict_checker.py examples/conflicted.py --json
```

```
{
  "files": [
    {
      "file": "examples/conflicted.py",
      "markers": [
        {
          "line": 2,
          "kind": "conflict start",
          "text": "<<<<<<< HEAD"
        },
        {
          "line": 4,
          "kind": "conflict separator",
          "text": "======="
        },
        {
          "line": 6,
          "kind": "conflict end",
          "text": ">>>>>>> feature-greeting"
        }
      ]
    }
  ],
  "summary": {
    "checked": 1,
    "files_with_markers": 1,
    "markers": 3,
    "skipped": 0
  }
}
```

Exit codes: 0 when no marker is found, 1 when any marker is found,
2 for a usage or input problem (a missing file, a bad flag, no file
to check).

## Examples

### 1. A file with a full conflict

`examples/conflicted.py` has all three markers of a normal
conflict:

```
python3 src/merge_conflict_checker.py examples/conflicted.py
```

```
FAIL examples/conflicted.py:2: conflict start marker '<<<<<<< HEAD'
FAIL examples/conflicted.py:4: conflict separator marker '======='
FAIL examples/conflicted.py:6: conflict end marker '>>>>>>> feature-greeting'
Checked 1 file(s), 3 marker(s) in 1 file(s).
```

### 2. A diff3 conflict, with the base marker

`examples/conflicted-diff3.txt` was merged with diff3 style, so it
also carries the `|||||||` base marker:

```
python3 src/merge_conflict_checker.py examples/conflicted-diff3.txt
```

```
FAIL examples/conflicted-diff3.txt:2: conflict start marker '<<<<<<< HEAD'
FAIL examples/conflicted-diff3.txt:4: diff3 base marker '||||||| merged common ancestors'
FAIL examples/conflicted-diff3.txt:6: conflict separator marker '======='
FAIL examples/conflicted-diff3.txt:8: conflict end marker '>>>>>>> feature-port'
Checked 1 file(s), 4 marker(s) in 1 file(s).
```

### 3. The bundled examples, all at once

```
sh examples/run-example.sh
```

The script checks the clean file (passes), then the two conflicted
files (both fail, on purpose). Its full output is in
`examples/sample-output.txt`, ending with
`Checked 2 file(s), 7 marker(s) in 2 file(s).` The conflicted run
exits 1, which is the expected result — the script ends with exit 0
so it can be run as a demo.

## How it is tested

51 tests, standard library `unittest` only, no packages to install:

```
python3 tests/test_merge_conflict_checker.py
```

The tests cover: each marker kind, the exact-seven rule (six
characters is not a marker, eight equals signs is a comment banner,
a marker glued to text is not a marker, an indented marker is not
a marker), full conflicts and diff3 conflicts with exact line
numbers, folder walking (recursive, `--no-recursive`, `.git`
skipped, `--exclude`), binary files skipped, stdin, `--json`
output, `--version`, bad flags, missing files, input files left
unchanged, the bundled examples (sample output compared
byte-for-byte against a fresh run, and the README-quoted outputs
checked against it), and hygiene checks (no placeholder text, no
absolute paths, stdlib imports only, `.env` first in `.gitignore`).

## Contributing

Small, focused improvements are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md).

## Licence

MIT — see [LICENSE](LICENSE).

## Original work

This tool was written from scratch for this repo. The idea of
checking for leftover conflict markers is not new — the similar
tools named above (the pre-commit `check-merge-conflict` hook, the
potential-conflicts checker Action) are listed in "How this
differs" — but every line of code here is original, and the tool
builds on nothing but Python's standard library.
