#!/usr/bin/env python3
"""Tests for merge_conflict_checker. Standard library unittest only."""

import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from merge_conflict_checker import (  # noqa: E402
    check_files,
    check_text,
    collect_files,
    format_problems,
    marker_kind,
    run,
    summarize,
)

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
EXAMPLES = ROOT / "examples"


def run_cli(argv, stdin_text=None):
    """Run the CLI in-process and capture stdout/stderr. Returns (code, out, err)."""
    out = io.StringIO()
    err = io.StringIO()
    code = run(argv, stdin_text=stdin_text, stdout=out, stderr=err)
    return code, out.getvalue(), err.getvalue()


class MarkerKindTests(unittest.TestCase):
    def test_start_marker_with_label(self):
        self.assertEqual(marker_kind("<<<<<<< HEAD"), "conflict start")

    def test_start_marker_bare(self):
        self.assertEqual(marker_kind("<<<<<<<"), "conflict start")

    def test_separator_marker(self):
        self.assertEqual(marker_kind("======="), "conflict separator")

    def test_end_marker_with_label(self):
        self.assertEqual(
            marker_kind(">>>>>>> feature-branch"), "conflict end"
        )

    def test_base_marker(self):
        self.assertEqual(
            marker_kind("||||||| merged common ancestors"), "diff3 base"
        )

    def test_six_chars_is_not_a_marker(self):
        self.assertIsNone(marker_kind("<<<<<< HEAD"))
        self.assertIsNone(marker_kind("======"))
        self.assertIsNone(marker_kind(">>>>>> branch"))

    def test_eight_equals_is_not_a_marker(self):
        # A comment banner of equals signs is not a conflict separator.
        self.assertIsNone(marker_kind("========"))
        self.assertIsNone(marker_kind("===================="))

    def test_marker_glued_to_text_is_not_a_marker(self):
        self.assertIsNone(marker_kind("<<<<<<<HEAD"))
        self.assertIsNone(marker_kind(">>>>>>>branch"))

    def test_indented_marker_is_not_a_marker(self):
        # Git always writes markers at column 0.
        self.assertIsNone(marker_kind("  <<<<<<< HEAD"))
        self.assertIsNone(marker_kind("\t>>>>>>> branch"))

    def test_plain_code_is_not_a_marker(self):
        self.assertIsNone(marker_kind("x = a < b"))
        self.assertIsNone(marker_kind("print('hello')"))
        self.assertIsNone(marker_kind(""))
        self.assertIsNone(marker_kind(">>>>>"))  # only five

    def test_mixed_characters_are_not_a_marker(self):
        self.assertIsNone(marker_kind("<<<====="))
        self.assertIsNone(marker_kind(">>>>>>>><"))


class CheckTextTests(unittest.TestCase):
    def test_clean_text(self):
        self.assertEqual(check_text("a = 1\nb = 2\n", "f.py"), [])

    def test_one_full_conflict(self):
        text = (
            "def f():\n"
            "<<<<<<< HEAD\n"
            "    return 1\n"
            "=======\n"
            "    return 2\n"
            ">>>>>>> branch\n"
        )
        problems = check_text(text, "f.py")
        self.assertEqual(len(problems), 3)
        self.assertEqual(problems[0], (2, "conflict start", "<<<<<<< HEAD"))
        self.assertEqual(problems[1], (4, "conflict separator", "======="))
        self.assertEqual(problems[2], (6, "conflict end", ">>>>>>> branch"))

    def test_diff3_base_is_reported(self):
        text = "<<<<<<< HEAD\n||||||| base\n=======\n>>>>>>> b\n"
        kinds = [kind for _, kind, _ in check_text(text, "f.txt")]
        self.assertEqual(
            kinds,
            ["conflict start", "diff3 base", "conflict separator", "conflict end"],
        )

    def test_line_numbers_are_exact(self):
        text = "one\ntwo\n<<<<<<< HEAD\nfour\n"
        self.assertEqual(
            check_text(text, "f.txt"),
            [(3, "conflict start", "<<<<<<< HEAD")],
        )

    def test_empty_text(self):
        self.assertEqual(check_text("", "f.txt"), [])

    def test_crlf_lines(self):
        text = "a\r\n<<<<<<< HEAD\r\nb\r\n"
        self.assertEqual(len(check_text(text, "f.txt")), 1)


class CollectFilesTests(unittest.TestCase):
    def test_single_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "a.py"
            target.write_text("x = 1\n")
            self.assertEqual(collect_files([str(target)]), [target])

    def test_folder_is_walked_recursively(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a.py").write_text("x = 1\n")
            sub = root / "sub"
            sub.mkdir()
            (sub / "b.py").write_text("y = 2\n")
            found = collect_files([str(root)])
            self.assertEqual(found, [root / "a.py", root / "sub" / "b.py"])

    def test_no_recursive_stops_at_top_level(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a.py").write_text("x = 1\n")
            sub = root / "sub"
            sub.mkdir()
            (sub / "b.py").write_text("y = 2\n")
            self.assertEqual(
                collect_files([str(root)], recursive=False), [root / "a.py"]
            )

    def test_git_folder_is_never_walked(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a.py").write_text("x = 1\n")
            git = root / ".git"
            git.mkdir()
            (git / "config").write_text("<<<<<<< HEAD\n")
            self.assertEqual(collect_files([str(root)]), [root / "a.py"])

    def test_exclude_by_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a.py").write_text("x = 1\n")
            (root / "a.min.py").write_text("y = 2\n")
            found = collect_files([str(root)], excludes=["*.min.py"])
            self.assertEqual(found, [root / "a.py"])

    def test_missing_path_raises(self):
        with self.assertRaises(FileNotFoundError):
            collect_files(["/definitely/not/a/real/path.txt"])

    def test_files_and_folders_mix(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a.py").write_text("x = 1\n")
            sub = root / "sub"
            sub.mkdir()
            (sub / "b.py").write_text("y = 2\n")
            found = collect_files([str(root / "a.py"), str(sub)])
            self.assertEqual(found, [root / "a.py", sub / "b.py"])


class CheckFilesTests(unittest.TestCase):
    def test_binary_file_is_skipped_not_failed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            binary = root / "image.bin"
            binary.write_bytes(b"\x89PNG\r\n\x1a\n\x00\xff\xfe")
            results, skipped = check_files([binary])
            self.assertEqual(results, {})
            self.assertEqual(skipped, 1)

    def test_clean_and_conflicted_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            clean = root / "clean.py"
            clean.write_text("x = 1\n")
            bad = root / "bad.py"
            bad.write_text("<<<<<<< HEAD\nx = 1\n=======\nx = 2\n>>>>>>> b\n")
            results, skipped = check_files([clean, bad])
            self.assertEqual(results[clean], [])
            self.assertEqual(len(results[bad]), 3)
            self.assertEqual(skipped, 0)

    def test_summarize(self):
        results = {
            Path("a.py"): [],
            Path("b.py"): [(1, "conflict start", "<<<<<<< HEAD")],
        }
        summary = summarize(results, skipped=1)
        self.assertEqual(
            summary,
            {
                "checked": 2,
                "files_with_markers": 1,
                "markers": 1,
                "skipped": 1,
            },
        )

    def test_format_problems_sorted_by_file(self):
        results = {
            Path("z.py"): [(1, "conflict start", "<<<<<<< HEAD")],
            Path("a.py"): [(2, "conflict end", ">>>>>>> b")],
        }
        lines = format_problems(results)
        self.assertEqual(
            lines,
            [
                "FAIL a.py:2: conflict end marker '>>>>>>> b'",
                "FAIL z.py:1: conflict start marker '<<<<<<< HEAD'",
            ],
        )


class CliTests(unittest.TestCase):
    def test_clean_file_passes(self):
        code, out, _ = run_cli([str(EXAMPLES / "clean.py")])
        self.assertEqual(code, 0)
        self.assertIn("OK — 1 file(s) checked, no merge-conflict markers.", out)

    def test_conflicted_file_fails(self):
        code, out, _ = run_cli([str(EXAMPLES / "conflicted.py")])
        self.assertEqual(code, 1)
        self.assertIn("conflict start marker '<<<<<<< HEAD'", out)
        self.assertIn("conflict separator marker '======='", out)
        self.assertIn("conflict end marker '>>>>>>> feature-greeting'", out)
        self.assertIn("Checked 1 file(s), 3 marker(s) in 1 file(s).", out)

    def test_diff3_file_reports_base_marker(self):
        code, out, _ = run_cli([str(EXAMPLES / "conflicted-diff3.txt")])
        self.assertEqual(code, 1)
        self.assertIn("diff3 base marker '||||||| merged common ancestors'", out)
        self.assertIn("Checked 1 file(s), 4 marker(s) in 1 file(s).", out)

    def test_folder_argument(self):
        code, out, _ = run_cli([str(EXAMPLES)])
        self.assertEqual(code, 1)
        self.assertIn("Checked 5 file(s), 7 marker(s) in 2 file(s).", out)

    def test_stdin(self):
        code, out, _ = run_cli(
            ["--stdin"], stdin_text="a\n<<<<<<< HEAD\nb\n"
        )
        self.assertEqual(code, 1)
        self.assertIn("<stdin>:2: conflict start marker '<<<<<<< HEAD'", out)

    def test_stdin_clean(self):
        code, out, _ = run_cli(["--stdin"], stdin_text="a\nb\n")
        self.assertEqual(code, 0)
        self.assertIn("no merge-conflict markers", out)

    def test_stdin_with_paths_is_usage_error(self):
        code, _, err = run_cli(["--stdin", "some.py"], stdin_text="x\n")
        self.assertEqual(code, 2)
        self.assertIn("--stdin cannot be combined", err)

    def test_missing_file_is_usage_error(self):
        code, _, err = run_cli(["/definitely/not/a/real/path.txt"])
        self.assertEqual(code, 2)
        self.assertIn("no such file or folder", err)

    def test_empty_folder_is_usage_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, _, err = run_cli([tmp])
            self.assertEqual(code, 2)
            self.assertIn("no files to check", err)

    def test_bad_flag_is_usage_error(self):
        code, _, err = run_cli(["--nope"])
        self.assertEqual(code, 2)
        self.assertIn("unrecognized arguments", err)

    def test_json_output(self):
        code, out, err = run_cli(
            ["--json", str(EXAMPLES / "conflicted.py")]
        )
        self.assertEqual(code, 1)
        payload = json.loads(out)
        self.assertEqual(payload["summary"]["markers"], 3)
        self.assertEqual(payload["summary"]["files_with_markers"], 1)
        self.assertEqual(len(payload["files"]), 1)
        self.assertEqual(payload["files"][0]["markers"][0]["line"], 2)
        self.assertEqual(
            payload["files"][0]["markers"][0]["kind"], "conflict start"
        )
        self.assertIn("Checked 1 file(s)", err)

    def test_json_clean(self):
        code, out, err = run_cli(["--json", str(EXAMPLES / "clean.py")])
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(payload["summary"]["markers"], 0)
        self.assertEqual(payload["files"], [])
        self.assertIn("no merge-conflict markers", err)

    def test_exclude_flag(self):
        code, out, _ = run_cli(
            ["--exclude", "*.py", str(EXAMPLES)]
        )
        self.assertEqual(code, 1)
        # Only the .txt and .sh files are checked now: 4 markers, 1 file.
        self.assertIn("Checked 3 file(s), 4 marker(s) in 1 file(s).", out)

    def test_no_recursive_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a.py").write_text("<<<<<<< HEAD\n")
            sub = root / "sub"
            sub.mkdir()
            (sub / "b.py").write_text(">>>>>>> branch\n")
            code, out, _ = run_cli(["--no-recursive", str(root)])
            self.assertEqual(code, 1)
            self.assertIn("Checked 1 file(s), 1 marker(s) in 1 file(s).", out)

    def test_input_files_are_not_changed(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "a.py"
            target.write_text("<<<<<<< HEAD\nx = 1\n=======\nx = 2\n>>>>>>> b\n")
            before = target.read_text()
            run_cli([str(target)])
            self.assertEqual(target.read_text(), before)

    def test_version_flag(self):
        code, out, _ = run_cli(["--version"])
        self.assertEqual(code, 0)
        self.assertIn("1.0.0", out)


class ExampleTests(unittest.TestCase):
    def test_sample_output_matches_a_fresh_run(self):
        # Run the same two commands the example script runs, from the
        # repo root, and compare against the committed sample output.
        import subprocess

        result = subprocess.run(
            ["sh", "examples/run-example.sh"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0)
        committed = (EXAMPLES / "sample-output.txt").read_text()
        self.assertEqual(result.stdout, committed)

    def test_run_example_script_exits_zero(self):
        import subprocess

        result = subprocess.run(
            ["sh", "examples/run-example.sh"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(
            result.stdout, (EXAMPLES / "sample-output.txt").read_text()
        )


class HygieneTests(unittest.TestCase):
    """The template gate: no placeholder text, no secrets, no local
    paths, stdlib imports only. The scan skips .git and __pycache__
    (Day 21 rule) and skips tests/ itself (Day 22 pattern), because
    this file's own banned-word list would otherwise trip it."""

    BANNED = ("TODO", "FIXME", "coming soon", "lorem", "API_KEY")

    def _repo_files(self):
        for path in ROOT.rglob("*"):
            if not path.is_file():
                continue
            if ".git" in path.parts or "__pycache__" in path.parts:
                continue
            if "tests" in path.parts:
                continue
            yield path

    def test_no_placeholder_text(self):
        hits = []
        for path in self._repo_files():
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            for word in self.BANNED:
                if word in text:
                    hits.append(f"{path.relative_to(ROOT)}: {word}")
        self.assertEqual(hits, [])

    def test_no_absolute_local_paths(self):
        hits = []
        for path in self._repo_files():
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            if "/home/" in text or "/Users/" in text or "C:\\" in text:
                hits.append(str(path.relative_to(ROOT)))
        self.assertEqual(hits, [])

    def test_stdlib_only_imports(self):
        import ast

        allowed = {
            "argparse",
            "contextlib",
            "fnmatch",
            "json",
            "sys",
            "pathlib",
            # Test file only: unittest, io, os, tempfile.
            "io",
            "os",
            "tempfile",
            "unittest",
        }
        src = ROOT / "src" / "merge_conflict_checker.py"
        tree = ast.parse(src.read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imported.add(node.module.split(".")[0])
        self.assertEqual(imported - allowed, set())

    def test_gitignore_lists_env_first(self):
        lines = (ROOT / ".gitignore").read_text().splitlines()
        self.assertEqual(lines[0], ".env")

    def test_readme_quoted_outputs_are_real(self):
        readme = (ROOT / "README.md").read_text()
        self.assertIn(
            "FAIL examples/conflicted.py:2: conflict start marker '<<<<<<< HEAD'",
            readme,
        )
        self.assertIn("Checked 2 file(s), 7 marker(s) in 2 file(s).", readme)
        self.assertIn(
            "OK — 1 file(s) checked, no merge-conflict markers.", readme
        )


if __name__ == "__main__":
    unittest.main()
