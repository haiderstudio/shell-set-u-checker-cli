#!/usr/bin/env python3
"""Check shell scripts opt into failing on unset variables with set -u.

Run: python3 src/shell_set_u_checker.py deploy.sh
     python3 src/shell_set_u_checker.py scripts/
     python3 src/shell_set_u_checker.py --stdin < deploy.sh

A typo'd variable name silently becomes empty
under plain `sh` — the script deletes the wrong
path or deploys to nowhere, and the cause reads
like a logic bug, not a missing flag. This tool
reads each shell script, looks for a `set -u`
(or a combined form like `set -euo pipefail`,
or `set -o nounset`) near the top of the script,
after the shebang, and reports each script
missing it, with the file and the line where the
script starts doing work. It exits 1 when any
script is missing the guard, so it can fail a CI
run. A script with the guard exits 0.

"Near the top" means the first 10 lines of code
after the shebang — blank lines and comment lines
do not count toward the 10, so a long comment header
does not push the guard out of reach. A shebang that
passes -u to the shell itself (for example
`#!/bin/bash -u`) counts too: the script does fail
on unset variables, and there is nothing to add.

A file given directly on the command line is always
checked, whatever its name. A folder is walked for
files ending in .sh, .bash, or .zsh only,
recursively by default (--no-recursive stops at the
top level). .git folders are never walked, and
directory links are never followed. An extensionless
script is checked by pointing at the file directly.

It never rewrites a file, never touches the network,
and reads only the files and folders you point it at.
"""

import argparse
import fnmatch
import json
import os
import sys

VERSION = "1.0.0"
EXTENSIONS = (".sh", ".bash", ".zsh")
HEADER_LINES = 10

FLAG_LETTERS = set("abefhkmnoptuvxC")


def _flag_token_enables_nounset(token):
    """True when one set-flag token turns nounset on.

    Covers -u and combined flags such as -euo. A token
    that is not a plain flag cluster (an operand such
    as "pipefail", or a lone "--") does not enable.
    """
    if not token.startswith("-") or token == "-":
        return False
    if token == "--":
        return False
    flags = token[1:]
    return "u" in flags and all(c in FLAG_LETTERS for c in flags)


def _set_line_enables_nounset(line):
    """True when one line is a set command enabling nounset.

    Handles `set -u`, combined flags like
    `set -euo pipefail`, and `set -o nounset`. A
    `set +u` (nounset off) never counts, and anything
    after `--` is a positional argument, not a flag.
    """
    code = line.split(" #", 1)[0]
    code = code.replace(";", " ").replace("&&", " ")
    tokens = code.split()
    if not tokens or tokens[0] != "set":
        return False
    index = 1
    while index < len(tokens):
        token = tokens[index]
        if token == "--":
            return False
        if token == "-o":
            if index + 1 < len(tokens):
                if tokens[index + 1] == "nounset":
                    return True
                index += 2
                continue
            return False
        if token == "+o":
            if index + 1 < len(tokens):
                if tokens[index + 1] == "nounset":
                    return False
                index += 2
                continue
            return False
        if token.startswith("+"):
            if "u" in token[1:]:
                return False
            index += 1
            continue
        if _flag_token_enables_nounset(token):
            return True
        index += 1
    return False


def _shebang_enables_nounset(line):
    """True when the shebang itself passes -u to the shell.

    Covers `#!/bin/bash -u` and `#!/usr/bin/env bash -u`.
    """
    tokens = line[2:].split()
    return any(_flag_token_enables_nounset(t) for t in tokens)


def _code_lines(text):
    """Yield (line_number, line) for lines that are code.

    Blank lines and comment-only lines are skipped.
    The shebang line is yielded as code too — the
    caller decides what to do with it.
    """
    for number, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        yield number, line


def check_text(text):
    """Check one shell script given as text.

    Returns a list of finding dicts: empty when the
    script opts into failing on unset variables, one
    entry when it does not. The finding names the line
    where the script starts doing work without the guard.
    """
    lines = text.splitlines()
    start = 0
    if lines and lines[0].startswith("#!"):
        if _shebang_enables_nounset(lines[0]):
            return []
        start = 1
    code = [(n, line) for n, line in _code_lines(text)
            if n > start]
    if not code:
        return []
    for number, line in code[:HEADER_LINES]:
        if _set_line_enables_nounset(line):
            return []
    first_number = code[0][0]
    return [{
        "line": first_number,
        "reason": (
            "has no set -u in the first %d lines after "
            "the shebang" % HEADER_LINES
        ),
    }]


def check_file(path):
    """Check one file. Return (findings, error).

    error is a string when the file cannot be read or
    is not valid UTF-8, else None.
    """
    try:
        with open(path, "r", encoding="utf-8") as handle:
            text = handle.read()
    except OSError as exc:
        return [], "cannot read file: %s" % exc.strerror
    except UnicodeDecodeError:
        return [], "not valid UTF-8"
    return check_text(text), None


def collect_files(paths, recursive, exclude):
    """Expand command-line paths into a sorted file list.

    Files are checked in the order given, each path
    once. Folders contribute their .sh, .bash, and
    .zsh files only. Returns (files, error): error
    names the first problem (a missing path, or no
    shell files found).
    """
    files = []
    seen = set()
    for path in paths:
        if os.path.isfile(path):
            real = os.path.realpath(path)
            if real not in seen:
                seen.add(real)
                files.append(path)
        elif os.path.isdir(path):
            for root, dirs, names in os.walk(path,
                                            followlinks=False):
                dirs[:] = sorted(
                    d for d in dirs if d != ".git")
                if not recursive:
                    dirs[:] = []
                for name in sorted(names):
                    if not name.lower().endswith(EXTENSIONS):
                        continue
                    if any(fnmatch.fnmatch(name, pattern)
                           for pattern in exclude):
                        continue
                    full = os.path.join(root, name)
                    real = os.path.realpath(full)
                    if real not in seen:
                        seen.add(real)
                        files.append(full)
        else:
            return [], "no such file or folder: %s" % path
    if not files:
        return [], "no shell files found"
    return files, None


def report_text(results, checked, findings):
    """Build the plain-text report for a run."""
    lines = []
    for result in results:
        path = result["path"]
        if result["error"]:
            lines.append("ERROR %s: %s" % (path, result["error"]))
        for finding in result["findings"]:
            lines.append("FAIL %s: line %d %s"
                         % (path, finding["line"],
                            finding["reason"]))
    bad = sum(1 for r in results
              if r["findings"] or r["error"])
    if bad:
        lines.append(
            "Checked %d file(s), %d file(s) failed."
            % (checked, bad))
    else:
        lines.append(
            "OK \u2014 %d file(s) checked, every script opts "
            "into failing on unset variables." % checked)
    return "\n".join(lines) + "\n"


def report_json(results, checked, findings):
    """Build the JSON report for a run."""
    return json.dumps({
        "files": results,
        "checked": checked,
        "findings": findings,
    }, indent=2) + "\n"


def main(argv=None):
    """Entry point. Returns an exit code (0, 1, or 2)."""
    parser = argparse.ArgumentParser(
        prog="shell_set_u_checker",
        description="Check shell scripts opt into failing "
                    "on unset variables with set -u.")
    parser.add_argument("paths", nargs="*", metavar="PATH",
                        help="shell script or folder to check")
    parser.add_argument("--no-recursive", action="store_true",
                        help="do not walk into subfolders")
    parser.add_argument("--exclude", action="append",
                        default=[],
                        metavar="PATTERN",
                        help="skip files matching this glob pattern "
                             "(repeatable)")
    parser.add_argument("--json", action="store_true",
                        help="print the result as JSON")
    parser.add_argument("--stdin", action="store_true",
                        help="check one shell script from stdin")
    parser.add_argument("--version", action="version",
                        version="shell_set_u_checker " + VERSION)
    args = parser.parse_args(argv)

    if args.stdin:
        if args.paths:
            print("error: --stdin takes no paths",
                  file=sys.stderr)
            return 2
        text = sys.stdin.read()
        findings_list = check_text(text)
        results = [{"path": "<stdin>",
                    "findings": findings_list,
                    "error": None}]
        checked = 1
        findings = len(findings_list)
        bad = findings
    else:
        if not args.paths:
            print("error: give a shell script or folder to check",
                  file=sys.stderr)
            return 2
        files, error = collect_files(
            args.paths, not args.no_recursive, args.exclude)
        if error:
            print("error: %s" % error, file=sys.stderr)
            return 2
        results = []
        findings = 0
        bad = 0
        for path in files:
            found, err = check_file(path)
            if found or err:
                bad += 1
            findings += len(found)
            results.append({"path": path, "findings": found,
                            "error": err})
        checked = len(files)

    if args.json:
        sys.stdout.write(report_json(results, checked, findings))
    else:
        sys.stdout.write(report_text(results, checked, findings))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
