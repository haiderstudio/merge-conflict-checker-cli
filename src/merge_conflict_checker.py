#!/usr/bin/env python3
"""Check files for leftover merge-conflict markers, fail CI on a marker.

Run: python3 src/merge_conflict_checker.py examples/conflicted.py
     python3 src/merge_conflict_checker.py src/ docs/
     cat file.py | python3 src/merge_conflict_checker.py --stdin

The tool scans each file for the four lines git leaves behind when a
merge is not finished:

    <<<<<<< HEAD
    ||||||| merged common ancestors      (only with diff3 style)
    =======
    >>>>>>> branch-name

Every marker is reported with its file and line number. It prints
FAIL per marker and a one-line summary, and exits 1 when any marker
is found — so it can fail a CI run.

A marker only counts when it sits at the start of a line, uses
exactly seven of the same character, and is followed by a space or
the end of the line — the same rule the pre-commit hook uses. That
keeps ordinary code out of the report: a line of eight equals signs
in a comment banner is not a marker, and neither is a line that only
starts with six angle brackets.

It never rewrites a file and never resolves a conflict. It is
report-only and runs fully offline: it sends nothing anywhere and
needs no API key.

Exit codes: 0 when no marker is found, 1 when any marker is found,
2 for a usage or input problem (a missing file, a bad flag, no file
to check).

Python standard library only.
"""

import argparse
import contextlib
import fnmatch
import json
import sys
from pathlib import Path

VERSION = "1.0.0"

# The four marker kinds, in the order git writes them in a conflict.
MARKERS = (
    ("<<<<<<<", "conflict start"),
    ("|||||||", "diff3 base"),
    ("=======", "conflict separator"),
    (">>>>>>>", "conflict end"),
)

_MARKER_CHARS = {"<", "|", "=", ">"}


def marker_kind(line):
    """Return the kind of merge-conflict marker a line is, or None.

    A marker is exactly seven of one marker character at the start of
    the line, followed by a space or the end of the line. The line is
    matched as written — a marker indented by even one space is not a
    real conflict marker, because git always writes them at column 0.
    """
    stripped = line.rstrip("\r\n")
    if len(stripped) < 7:
        return None
    first = stripped[0]
    if first not in _MARKER_CHARS:
        return None
    head = stripped[:7]
    if head != first * 7:
        return None
    rest = stripped[7:]
    if rest != "" and not rest.startswith(" "):
        return None
    for marker, kind in MARKERS:
        if head == marker:
            return kind
    return None


def check_text(text, label):
    """Find every marker in one file's text.

    Returns a list of (line_number, kind, marker_text) tuples.
    """
    problems = []
    for number, line in enumerate(text.splitlines(), start=1):
        kind = marker_kind(line)
        if kind is not None:
            problems.append((number, kind, line.rstrip("\r\n")))
    return problems


def is_text_file(path):
    """True when a file can be read as UTF-8 text.

    Files that are not valid UTF-8 are binary for this tool's purpose
    and are skipped, not reported as failures.
    """
    try:
        path.read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    return True


def collect_files(paths, recursive=True, excludes=()):
    """Turn file and folder arguments into a sorted list of files.

    Folders are walked (recursively unless --no-recursive), `.git`
    folders are never walked, and directory links are never followed,
    so a link cycle cannot loop the check. Files matching an
    --exclude glob (checked against the name and the path) are left
    out.
    """
    found = []
    for raw in paths:
        path = Path(raw)
        if path.is_file():
            if not _excluded(path, excludes):
                found.append(path)
        elif path.is_dir():
            if recursive:
                for root, dirs, files in path.walk():
                    dirs[:] = sorted(d for d in dirs if d != ".git")
                    for name in sorted(files):
                        candidate = root / name
                        if not _excluded(candidate, excludes):
                            found.append(candidate)
            else:
                for child in sorted(path.iterdir()):
                    if child.is_file() and not _excluded(child, excludes):
                        found.append(child)
        else:
            raise FileNotFoundError(raw)
    return found


def _excluded(path, excludes):
    name = path.name
    text = str(path)
    return any(
        fnmatch.fnmatch(name, pattern) or fnmatch.fnmatch(text, pattern)
        for pattern in excludes
    )


def check_files(files):
    """Check each file. Returns (results, skipped).

    results maps each checked file to its list of problems.
    skipped counts the files left out because they are not UTF-8 text.
    """
    results = {}
    skipped = 0
    for path in files:
        if not is_text_file(path):
            skipped += 1
            continue
        text = path.read_text(encoding="utf-8")
        results[path] = check_text(text, str(path))
    return results, skipped


def summarize(results, skipped):
    """Build the summary numbers from per-file results."""
    checked = len(results)
    bad_files = sum(1 for problems in results.values() if problems)
    markers = sum(len(problems) for problems in results.values())
    return {
        "checked": checked,
        "files_with_markers": bad_files,
        "markers": markers,
        "skipped": skipped,
    }


def format_problems(results):
    """Format the per-marker FAIL lines, in file order."""
    lines = []
    for path in sorted(results, key=str):
        for number, kind, marker in results[path]:
            lines.append(
                f"FAIL {path}:{number}: {kind} marker '{marker}'"
            )
    return lines


def run(argv=None, stdin_text=None, stdout=None, stderr=None):
    """Run the CLI. Returns the exit code."""
    stdout = stdout if stdout is not None else sys.stdout
    stderr = stderr if stderr is not None else sys.stderr

    parser = argparse.ArgumentParser(
        prog="merge_conflict_checker",
        description=(
            "Check files for leftover merge-conflict markers, "
            "fail CI on a marker."
        ),
    )
    parser.add_argument(
        "paths", nargs="*", help="files or folders to check (default: .)"
    )
    parser.add_argument(
        "--stdin",
        action="store_true",
        help="read one file from standard input instead of paths",
    )
    parser.add_argument(
        "--no-recursive",
        action="store_true",
        help="do not walk into subfolders of a named folder",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        metavar="PATTERN",
        help="skip files matching this glob (repeatable)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="print the result as JSON on stdout",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {VERSION}"
    )
    # argparse exits (SystemExit) on --version and on bad flags. Catch
    # it so the message lands in the caller's streams and run() returns
    # the code instead of raising.
    try:
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(
            stderr
        ):
            args = parser.parse_args(argv)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 2

    if args.stdin and args.paths:
        print(
            "error: --stdin cannot be combined with file paths", file=stderr
        )
        return 2
    if args.stdin:
        if stdin_text is None:
            stdin_text = sys.stdin.read()
        results = {"<stdin>": check_text(stdin_text, "<stdin>")}
        skipped = 0
    else:
        paths = args.paths if args.paths else ["."]
        try:
            files = collect_files(
                paths,
                recursive=not args.no_recursive,
                excludes=args.exclude,
            )
        except FileNotFoundError as exc:
            print(f"error: no such file or folder: {exc}", file=stderr)
            return 2
        if not files:
            print("error: no files to check", file=stderr)
            return 2
        results, skipped = check_files(files)

    summary = summarize(results, skipped)

    if args.json:
        payload = {
            "files": [
                {
                    "file": str(path),
                    "markers": [
                        {
                            "line": number,
                            "kind": kind,
                            "text": marker,
                        }
                        for number, kind, marker in results[path]
                    ],
                }
                for path in sorted(results, key=str)
                if results[path]
            ],
            "summary": summary,
        }
        print(json.dumps(payload, indent=2), file=stdout)
    else:
        for line in format_problems(results):
            print(line, file=stdout)

    if summary["markers"] == 0:
        checked = summary["checked"]
        line = f"OK — {checked} file(s) checked, no merge-conflict markers."
        if skipped:
            line += f" ({skipped} non-text file(s) skipped.)"
        print(line, file=stderr if args.json else stdout)
        return 0

    line = (
        f"Checked {summary['checked']} file(s), "
        f"{summary['markers']} marker(s) in "
        f"{summary['files_with_markers']} file(s)."
    )
    if skipped:
        line += f" ({skipped} non-text file(s) skipped.)"
    print(line, file=stderr if args.json else stdout)
    return 1


def main():
    sys.exit(run())


if __name__ == "__main__":
    main()
