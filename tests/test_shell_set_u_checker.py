#!/usr/bin/env python3
"""Tests for shell_set_u_checker — stdlib unittest only.

Every shell script in this file is made up for testing.
No real secret appears anywhere in this file.
"""

import ast
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import shell_set_u_checker as checker

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src/shell_set_u_checker.py"


def run_cli(argv):
    """Run main(argv), capture stdout/stderr, return (code, out, err)."""
    out = io.StringIO()
    err = io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        try:
            code = checker.main(argv)
        except SystemExit as exc:
            code = exc.code
    return code, out.getvalue(), err.getvalue()


def write(tmp, name, text, encoding="utf-8"):
    path = Path(tmp) / name
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(text, bytes):
        path.write_bytes(text)
    else:
        path.write_text(text, encoding=encoding)
    return str(path)


def findings_of(text):
    return checker.check_text(text)


class TestGuardDetection(unittest.TestCase):
    def test_set_u_passes(self):
        self.assertEqual(
            findings_of("#!/bin/bash\nset -u\necho hi\n"), [])

    def test_set_euo_pipefail_passes(self):
        self.assertEqual(
            findings_of("#!/bin/bash\nset -euo pipefail\necho hi\n"),
            [])

    def test_set_eu_passes(self):
        self.assertEqual(
            findings_of("#!/bin/bash\nset -eu\necho hi\n"), [])

    def test_set_o_nounset_passes(self):
        self.assertEqual(
            findings_of("#!/bin/sh\nset -o nounset\necho hi\n"), [])

    def test_set_o_nounset_with_pipefail_passes(self):
        self.assertEqual(
            findings_of("#!/bin/sh\nset -o nounset -o pipefail\n"
                        "echo hi\n"), [])

    def test_set_e_only_fails(self):
        bad = findings_of("#!/bin/bash\nset -e\necho hi\n")
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0]["line"], 2)

    def test_set_o_pipefail_only_fails(self):
        bad = findings_of("#!/bin/bash\nset -o pipefail\necho hi\n")
        self.assertEqual(len(bad), 1)

    def test_set_plus_u_fails(self):
        bad = findings_of("#!/bin/bash\nset +u\necho hi\n")
        self.assertEqual(len(bad), 1)

    def test_set_u_in_comment_does_not_count(self):
        bad = findings_of("#!/bin/bash\n# set -u\necho hi\n")
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0]["line"], 3)

    def test_set_u_after_first_command_still_passes(self):
        # The rule is presence in the first 10 code lines,
        # not "before the first command".
        self.assertEqual(
            findings_of("#!/bin/bash\necho starting\nset -u\n"
                        "echo hi\n"), [])

    def test_set_u_on_tenth_code_line_passes(self):
        text = "#!/bin/bash\n" + "echo x\n" * 9 + "set -u\n"
        self.assertEqual(findings_of(text), [])

    def test_set_u_on_eleventh_code_line_fails(self):
        text = "#!/bin/bash\n" + "echo x\n" * 10 + "set -u\n"
        bad = findings_of(text)
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0]["line"], 2)

    def test_set_u_with_trailing_comment_passes(self):
        self.assertEqual(
            findings_of("#!/bin/bash\nset -u  # fail on unset\n"
                        "echo hi\n"), [])

    def test_set_u_with_semicolon_passes(self):
        self.assertEqual(
            findings_of("#!/bin/bash\nset -u; echo hi\n"), [])

    def test_set_u_with_and_and_passes(self):
        self.assertEqual(
            findings_of("#!/bin/bash\nset -u && echo hi\n"), [])

    def test_set_dash_dash_u_fails(self):
        bad = findings_of("#!/bin/bash\nset -- -u\necho hi\n")
        self.assertEqual(len(bad), 1)

    def test_set_plus_o_nounset_fails(self):
        bad = findings_of("#!/bin/bash\nset +o nounset\necho hi\n")
        self.assertEqual(len(bad), 1)

    def test_shebang_with_u_passes(self):
        self.assertEqual(
            findings_of("#!/bin/bash -u\necho hi\n"), [])

    def test_shebang_with_env_bash_u_passes(self):
        self.assertEqual(
            findings_of("#!/usr/bin/env bash -u\necho hi\n"), [])

    def test_no_shebang_with_set_u_passes(self):
        self.assertEqual(
            findings_of("set -u\necho hi\n"), [])

    def test_no_shebang_without_set_u_fails(self):
        bad = findings_of("echo hi\n")
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0]["line"], 1)

    def test_empty_script_passes(self):
        self.assertEqual(findings_of(""), [])

    def test_comments_only_passes(self):
        self.assertEqual(
            findings_of("#!/bin/bash\n# nothing here\n"), [])

    def test_long_comment_header_does_not_push_guard_out(self):
        text = ("#!/bin/bash\n" + "# note\n" * 20
                + "set -u\necho hi\n")
        self.assertEqual(findings_of(text), [])

    def test_failing_line_is_first_code_line(self):
        bad = findings_of("#!/bin/bash\n# note\n\necho hi\n")
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0]["line"], 4)

    def test_crlf_script(self):
        bad = findings_of("#!/bin/bash\r\nset -u\r\necho hi\r\n")
        self.assertEqual(bad, [])
        bad = findings_of("#!/bin/bash\r\necho hi\r\n")
        self.assertEqual(len(bad), 1)

    def test_reason_names_the_window(self):
        bad = findings_of("#!/bin/bash\necho hi\n")
        self.assertIn("first 10 lines", bad[0]["reason"])
        self.assertIn("set -u", bad[0]["reason"])


class TestCli(unittest.TestCase):
    def test_clean_file_exits_zero(self):
        code, out, _err = run_cli([str(REPO / "examples/clean.sh")])
        self.assertEqual(code, 0)
        self.assertIn("OK", out)

    def test_flagged_file_exits_one(self):
        code, out, _err = run_cli(
            [str(REPO / "examples/flagged.sh")])
        self.assertEqual(code, 1)
        self.assertIn("line 2", out)
        self.assertIn("Checked 1 file(s), 1 file(s) failed.", out)

    def test_folder_walk(self):
        code, out, _err = run_cli([str(REPO / "examples")])
        self.assertEqual(code, 1)
        self.assertIn("Checked 4 file(s), 1 file(s) failed.", out)

    def test_no_recursive(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "a.sh", "#!/bin/bash\nset -u\necho hi\n")
            write(tmp, "sub/b.sh", "#!/bin/bash\necho hi\n")
            code, out, _err = run_cli(["--no-recursive", tmp])
            self.assertEqual(code, 0)
            self.assertIn("1 file(s) checked", out)

    def test_nested_folders_found(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "a.sh", "#!/bin/bash\nset -u\necho hi\n")
            write(tmp, "sub/b.sh", "#!/bin/bash\nset -u\necho hi\n")
            write(tmp, "sub/deep/c.bash",
                  "#!/bin/bash\nset -u\necho hi\n")
            code, out, _err = run_cli([tmp])
            self.assertEqual(code, 0)
            self.assertIn("3 file(s) checked", out)

    def test_shell_extensions(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "a.sh", "#!/bin/bash\nset -u\necho hi\n")
            write(tmp, "b.bash", "#!/bin/bash\nset -u\necho hi\n")
            write(tmp, "c.zsh", "#!/bin/zsh\nset -u\necho hi\n")
            write(tmp, "d.SH", "#!/bin/bash\nset -u\necho hi\n")
            write(tmp, "e.txt", "#!/bin/bash\nset -u\necho hi\n")
            code, out, _err = run_cli([tmp])
            self.assertEqual(code, 0)
            self.assertIn("4 file(s) checked", out)

    def test_exclude_pattern(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "a.sh", "#!/bin/bash\nset -u\necho hi\n")
            write(tmp, "vendor.sh", "#!/bin/bash\necho hi\n")
            code, out, _err = run_cli(
                ["--exclude", "vendor.sh", tmp])
            self.assertEqual(code, 0)
            self.assertIn("1 file(s) checked", out)

    def test_git_folder_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "a.sh", "#!/bin/bash\nset -u\necho hi\n")
            write(tmp, ".git/b.sh", "#!/bin/bash\necho hi\n")
            code, out, _err = run_cli([tmp])
            self.assertEqual(code, 0)
            self.assertIn("1 file(s) checked", out)

    def test_direct_file_checked_whatever_its_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "notes.txt",
                         "#!/bin/bash\necho hi\n")
            code, out, _err = run_cli([path])
            self.assertEqual(code, 1)
            self.assertIn("line 2", out)

    def test_duplicate_paths_checked_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "a.sh", "#!/bin/bash\nset -u\necho hi\n")
            code, out, _err = run_cli([path, path])
            self.assertEqual(code, 0)
            self.assertIn("1 file(s) checked", out)

    def test_json_output(self):
        result = subprocess.run(
            [sys.executable, "src/shell_set_u_checker.py",
             "--json", "examples/flagged.sh"],
            cwd=REPO, capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        data = json.loads(result.stdout)
        self.assertEqual(data["checked"], 1)
        self.assertEqual(data["findings"], 1)
        self.assertIn("set -u", data["files"][0]["findings"][0]["reason"])

    def test_stdin(self):
        result = subprocess.run(
            [sys.executable, "src/shell_set_u_checker.py",
             "--stdin"],
            cwd=REPO, input="#!/bin/bash\necho hi\n",
            capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn("FAIL <stdin>: line 2", result.stdout)

    def test_stdin_with_paths_is_usage_error(self):
        code, _out, err = run_cli(["--stdin", "deploy.sh"])
        self.assertEqual(code, 2)
        self.assertIn("--stdin takes no paths", err)

    def test_no_paths_is_usage_error(self):
        code, _out, err = run_cli([])
        self.assertEqual(code, 2)
        self.assertIn("give a shell script", err)

    def test_bad_flag(self):
        code, _out, _err = run_cli(["--nope"])
        self.assertEqual(code, 2)

    def test_missing_path(self):
        code, _out, err = run_cli(["no-such-folder"])
        self.assertEqual(code, 2)
        self.assertIn("no such file or folder", err)

    def test_empty_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, _out, err = run_cli([tmp])
            self.assertEqual(code, 2)
            self.assertIn("no shell files found", err)

    def test_version(self):
        code, out, _err = run_cli(["--version"])
        self.assertEqual(code, 0)
        self.assertIn("shell_set_u_checker", out)

    def test_non_utf8_file_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "a.sh", b"#!/bin/bash\n\xff\xfe\n")
            code, out, _err = run_cli([path])
            self.assertEqual(code, 1)
            self.assertIn("ERROR", out)
            self.assertIn("not valid UTF-8", out)

    def test_input_files_left_unchanged(self):
        import hashlib
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "a.sh", "#!/bin/bash\necho hi\n")
            before = hashlib.sha256(
                Path(path).read_bytes()).hexdigest()
            code, _out, _err = run_cli([path])
            self.assertEqual(code, 1)
            after = hashlib.sha256(
                Path(path).read_bytes()).hexdigest()
            self.assertEqual(before, after)

    def test_run_from_another_folder_and_fake_home(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = dict(os.environ, HOME=tmp)
            result = subprocess.run(
                [sys.executable, str(SRC), "deploy.sh"],
                cwd=tmp, capture_output=True, text=True, env=env)
            self.assertEqual(result.returncode, 2)
            self.assertIn("no such file or folder", result.stderr)


class TestExamplesAndReadme(unittest.TestCase):
    def test_sample_output_matches_fresh_run(self):
        result = subprocess.run(
            ["sh", "examples/run-example.sh"],
            cwd=REPO, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)
        saved = (REPO / "examples/sample-output.md").read_text()
        self.assertEqual(result.stdout, saved)

    def test_readme_quotes_real_outputs(self):
        readme = (REPO / "README.md").read_text()
        clean = subprocess.run(
            [sys.executable, "src/shell_set_u_checker.py",
             "examples/clean.sh"],
            cwd=REPO, capture_output=True, text=True)
        self.assertEqual(clean.returncode, 0)
        self.assertIn(clean.stdout.strip(), readme)
        flagged = subprocess.run(
            [sys.executable, "src/shell_set_u_checker.py",
             "examples/flagged.sh"],
            cwd=REPO, capture_output=True, text=True)
        self.assertEqual(flagged.returncode, 1)
        self.assertIn(flagged.stdout.strip(), readme)
        folder = subprocess.run(
            [sys.executable, "src/shell_set_u_checker.py",
             "examples/"],
            cwd=REPO, capture_output=True, text=True)
        self.assertEqual(folder.returncode, 1)
        self.assertIn("Checked 4 file(s), 1 file(s) failed.",
                      folder.stdout)
        self.assertIn("Checked 4 file(s), 1 file(s) failed.",
                      readme)
        edge = subprocess.run(
            [sys.executable, "src/shell_set_u_checker.py",
             "examples/edge.sh"],
            cwd=REPO, capture_output=True, text=True)
        self.assertEqual(edge.returncode, 0)
        self.assertIn(edge.stdout.strip(), readme)
        js = subprocess.run(
            [sys.executable, "src/shell_set_u_checker.py",
             "--json", "examples/flagged.sh"],
            cwd=REPO, capture_output=True, text=True)
        self.assertEqual(js.returncode, 1)
        self.assertIn(js.stdout.strip(), readme)
        stdin_run = subprocess.run(
            [sys.executable, "src/shell_set_u_checker.py",
             "--stdin"],
            cwd=REPO, input="#!/bin/bash\necho hi\n",
            capture_output=True, text=True)
        self.assertEqual(stdin_run.returncode, 1)
        self.assertIn(stdin_run.stdout.strip(), readme)


class TestHygiene(unittest.TestCase):
    def _repo_files(self, skip_tests=True, skip_examples=True):
        for root, dirs, files in os.walk(REPO):
            dirs[:] = [d for d in dirs
                       if d not in (".git", "__pycache__")
                       and not (skip_tests and d == "tests")
                       and not (skip_examples and d == "examples")]
            for name in files:
                if name.endswith(".pyc"):
                    continue
                yield Path(root) / name

    def test_no_placeholder_text(self):
        banned = ["TODO", "coming soon", "lorem", "FIXME", "XXX"]
        hits = []
        for path in self._repo_files(skip_tests=True,
                                     skip_examples=False):
            text = path.read_text(errors="ignore")
            for word in banned:
                if word in text:
                    hits.append("%s: %s" % (path.name, word))
        self.assertEqual(hits, [])

    def test_no_absolute_paths(self):
        # The markers are built without a literal temp-dir
        # path in this file, so the test itself stays clean.
        markers = ("/home/", "/Users/", "C:\\\\",
                   "/" + "tmp" + "/")
        hits = []
        for path in self._repo_files(skip_tests=True,
                                     skip_examples=False):
            text = path.read_text(errors="ignore")
            for marker in markers:
                if marker in text:
                    hits.append("%s: %s" % (path.name, marker))
        self.assertEqual(hits, [])

    def test_no_real_secrets_outside_tests_and_examples(self):
        # The source holds no key values at all; the tests
        # and examples hold fake values only, so they are
        # excluded from this scan.
        patterns = [
            re.compile(r"AKIA[0-9A-Z]{16}"),
            re.compile(r"gh[pousr]_[A-Za-z0-9_]{20,}"),
            re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
            re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),
            re.compile(r"AIza[0-9A-Za-z_-]{35}"),
            re.compile(r"[rs]k_(?:live|test)_[A-Za-z0-9]{16,}"),
            re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}"),
            re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.eyJ"),
        ]
        hits = []
        for path in self._repo_files():
            text = path.read_text(errors="ignore")
            for pattern in patterns:
                if pattern.search(text):
                    hits.append("%s: %s" % (path.name, pattern.pattern))
        self.assertEqual(hits, [])

    def test_stdlib_imports_only(self):
        stdlib = set(sys.stdlib_module_names)
        for target in (REPO / "src/shell_set_u_checker.py",
                       REPO / "tests/test_shell_set_u_checker.py"):
            tree = ast.parse(target.read_text())
            imported = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update(a.name.split(".")[0]
                                    for a in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported.add(node.module.split(".")[0])
            self.assertFalse(
                imported - stdlib - {"shell_set_u_checker"},
                (target.name, imported))
            self.assertNotIn("yaml", imported)

    def test_no_network_use_in_src(self):
        src = (REPO / "src/shell_set_u_checker.py").read_text()
        for marker in ("urllib.request", "requests", "socket",
                       "http.client", "urlopen", "urlretrieve"):
            self.assertNotIn(marker, src, marker)

    def test_gitignore_lists_env_first(self):
        lines = (REPO / ".gitignore").read_text().splitlines()
        self.assertEqual(lines[0], ".env")

    def test_ci_runs_this_test_file(self):
        ci = (REPO / ".github/workflows/ci.yml").read_text()
        self.assertIn("tests/test_shell_set_u_checker.py", ci)
        self.assertIn("ubuntu-latest", ci)
        self.assertIn("3.12", ci)
        self.assertIn("actions/checkout", ci)
        self.assertIn("setup-python", ci)
        self.assertIn("push", ci)
        self.assertIn("pull_request", ci)

    def test_readme_names_the_neighbouring_repos(self):
        readme = (REPO / "README.md").read_text()
        self.assertIn("shell-shebang-checker-cli", readme)
        self.assertIn("shell-quote-checker-cli", readme)
        self.assertIn("shell-set-e-checker-cli", readme)
        self.assertIn("shellcheck", readme.lower())


if __name__ == "__main__":
    unittest.main()
