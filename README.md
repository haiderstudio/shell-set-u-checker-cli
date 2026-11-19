# shell-set-u-checker-cli

Check shell scripts opt into failing on unset variables with `set -u` — fail CI when one does not.

[![CI](https://github.com/haiderstudio/shell-set-u-checker-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/haiderstudio/shell-set-u-checker-cli/actions/workflows/ci.yml) [![Licence: MIT](https://img.shields.io/badge/Licence-MIT-yellow.svg)](LICENSE)

## What it does

`shell_set_u_checker` reads each shell script,
looks for a `set -u` (or a combined form like
`set -euo pipefail`, or `set -o nounset`) near the
top of the script, after the shebang, and reports
each script missing it, with the file and the line
where the script starts doing work. It exits 1 when
any script is missing the guard, so it can fail a CI
run. A script with the guard exits 0.

- A typo'd variable name silently becomes empty
  under plain `sh` — the script deletes the wrong
  path or deploys to nowhere, and the cause reads
  like a logic bug, not a missing flag. This names
  the exact line, and the fix is one flag per
  script.
- "Near the top" means the first 10 lines of code
  after the shebang — blank lines and comment lines
  do not count toward the 10, so a long comment
  header does not push the guard out of reach. A
  shebang that passes `-u` to the shell itself (for
  example `#!/bin/bash -u`) counts too: the script
  does fail on unset variables, and there is
  nothing to add.
- `set -e` alone does not count, and `set +u`
  (nounset switched off) never counts. A `set -u`
  written inside a comment does not count either.
- A file given directly on the command line is always
  checked, whatever its name. A folder is walked for
  files ending in `.sh`, `.bash`, or `.zsh` only,
  recursively by default (`--no-recursive` stops at
  the top level). `.git` folders are never walked,
  and directory links are never followed. An
  extensionless script is checked by pointing at the
  file directly.
- `--json` prints the result as JSON, and `--stdin`
  checks one shell script read from standard input.

## Who it is for

Every shell script that runs in CI — a deploy
script, a backup script, a setup script. One
typo'd variable name and the script carries on
with an empty value as if nothing happened, and
the real cause is nowhere near the line that
breaks. This is the gate that stops it at the
pull request.

## What it does NOT do

- It does not lint the whole script. That is
  ShellCheck's job — koalaman/shellcheck, 40,346
  stars, is a whole static-analysis tool for shell
  scripts, with hundreds of checks, and it needs
  installing. This repo is one check only, as a
  zero-install standard-library CLI with per-line
  reporting and a CI exit code. If you want whole-
  script linting, install ShellCheck; if you want
  this one guard enforced in CI with no install,
  use this.
- It does not check the shebang line itself. That is
  repo #64, shell-shebang-checker-cli — the shebang
  is a different check on the same files.
- It does not check quoting inside the script. That
  is repo #100, shell-quote-checker-cli — quoting is
  a different check on the same files.
- It does not check the fail-fast guard. That is
  repo #112, shell-set-e-checker-cli — `set -e` is
  the sibling flag, a different failure mode
  (error exit vs unset variable).
- It does not check whether the script is correct,
  safe, or idempotent. It only checks that the
  unset-variable guard is there.
- It never rewrites a file, never runs a script, and
  never touches the network.

## How this differs

- A fresh search of GitHub on Nov 17, 2026 found 0
  results for `"shell-set-u-checker-cli"` and 0
  results for `shell set u checker` — a completely
  empty field for this one check.
- ShellCheck (koalaman/shellcheck, 40,346 stars,
  re-verified Nov 17, 2026) owns the BROAD job:
  whole-script static analysis. This repo is the
  narrow slice — one check, zero install, per-line
  reporting, CI exit code — the same broad-vs-narrow
  pattern that lets repo #100 (shell-quote-checker-cli)
  and repo #112 (shell-set-e-checker-cli) stand
  against ShellCheck itself.

## Install

```sh
git clone https://github.com/haiderstudio/shell-set-u-checker-cli.git
cd shell-set-u-checker-cli
```

There is nothing else to install: Python 3.10 or newer,
standard library only, no dependencies.

## Usage

Check one shell script:

```sh
python3 src/shell_set_u_checker.py deploy.sh
```

A script with the guard passes:

```sh
$ python3 src/shell_set_u_checker.py examples/clean.sh
OK — 1 file(s) checked, every script opts into failing on unset variables.
```

A script without it fails, with the file and the
line where the script starts doing work:

```sh
$ python3 src/shell_set_u_checker.py examples/flagged.sh
FAIL examples/flagged.sh: line 2 has no set -u in the first 10 lines after the shebang
Checked 1 file(s), 1 file(s) failed.
```

Check a whole folder (`.sh` / `.bash` / `.zsh`
files only):

```sh
$ python3 src/shell_set_u_checker.py examples/
FAIL examples/flagged.sh: line 2 has no set -u in the first 10 lines after the shebang
Checked 4 file(s), 1 file(s) failed.
```

Check one script from standard input:

```sh
$ printf '#!/bin/bash\necho hi\n' | python3 src/shell_set_u_checker.py --stdin
FAIL <stdin>: line 2 has no set -u in the first 10 lines after the shebang
Checked 1 file(s), 1 file(s) failed.
```

Machine-readable output:

```sh
$ python3 src/shell_set_u_checker.py --json examples/flagged.sh
{
  "files": [
    {
      "path": "examples/flagged.sh",
      "findings": [
        {
          "line": 2,
          "reason": "has no set -u in the first 10 lines after the shebang"
        }
      ],
      "error": null
    }
  ],
  "checked": 1,
  "findings": 1
}
```

Exit codes: 0 when every script opts into failing
on unset variables, 1 when any script is missing
the guard or a file cannot be read, 2 for a usage
error (a missing path, a bad flag, or no shell
files found).

## Examples

A deploy script with the full guard passes —
`examples/clean.sh` carries `set -euo pipefail`:

```sh
$ python3 src/shell_set_u_checker.py examples/clean.sh
OK — 1 file(s) checked, every script opts into failing on unset variables.
```

The long form counts too — `examples/edge.sh` uses
`set -o nounset` after a three-line comment header,
and it passes:

```sh
$ python3 src/shell_set_u_checker.py examples/edge.sh
OK — 1 file(s) checked, every script opts into failing on unset variables.
```

A script with only `set -e` still fails — the
fail-fast flag is not the unset-variable guard.
`examples/flagged.sh` carries `set -e` and nothing
else:

```sh
$ python3 src/shell_set_u_checker.py examples/flagged.sh
FAIL examples/flagged.sh: line 2 has no set -u in the first 10 lines after the shebang
Checked 1 file(s), 1 file(s) failed.
```

Run every bundled example at once with `sh
examples/run-example.sh` — the output is saved in
[examples/sample-output.md](examples/sample-output.md).
The runner script itself carries `set -eu`, so it
passes its own check.

## How it is tested

```sh
python3 tests/test_shell_set_u_checker.py
```

The tests cover guard detection (a `set -u` passes,
`set -euo pipefail` passes, `set -eu` passes,
`set -o nounset` passes, `set -o nounset -o
pipefail` passes, `set -e` alone fails, `set -o
pipefail` alone fails, `set +u` fails, a `set -u`
in a comment fails, a `set -u` after the first
command still passes inside the window, a `set -u`
on the 10th code line passes, on the 11th fails, a
`set -u` with a trailing comment passes, with a
semicolon passes, a `set -- -u` fails, a shebang
with `-u` passes, a shebang with `env bash -u`
passes, no shebang with `set -u` passes, no shebang
without it fails, an empty script passes, a
comments-only script passes, a long comment header
does not push the guard out, the failing line is the
first code line, CRLF scripts, the reason names the
window), the CLI (exit 0/1/2, folder walking for
several shell files including `.bash`, `.zsh`, and
`.SH`, nested folders, `--no-recursive`,
`--exclude`, `.git` skipped, a direct file checked
whatever its name, duplicate paths checked once,
`--json` output, `--stdin`, bad flags, missing
paths, empty folders, `--version`, a non-UTF-8 file
reported, a missing file reported, input files left
unchanged, the tool run from another folder and
under a changed HOME), the bundled examples (sample
output compared byte-for-byte against a fresh run,
and the README-quoted outputs checked against it),
and hygiene checks (no placeholder text, no absolute
paths, no real secrets outside the tests and
examples, stdlib imports only, no network use in the
source, `.env` first in `.gitignore`, CI file runs
the test file, README names the neighbouring repos).

## Contributing

Small, focused improvements are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md).

## Licence

MIT — see [LICENSE](LICENSE).

## Original work

This tool was written from scratch for this repo. The
idea of failing on unset variables in shell scripts
is not new, and ShellCheck (koalaman/shellcheck) is
the honest reference for whole-script linting — but
no existing tool does this one job, checking that
shell scripts in local folders carry a `set -u`
guard near the top, as a tested zero-install
command-line gate with a CI exit code, as the search
above shows — and every line of code here is
original, built on nothing but Python's standard
library.
