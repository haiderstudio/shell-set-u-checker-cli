# Security Policy

This tool runs locally, collects no data, sends nothing anywhere, and needs no API key or secret. It only reads the shell scripts you point it at, and it never rewrites a file and never changes anything. It writes nothing except the report on standard output (and usage errors on standard error). It never fetches a URL and never runs a command — it reads scripts as text, it never executes them.

It only checks that a shell script carries a `set -u` guard near the top. It never runs the script, never follows a URL inside it, and never changes the script.

If you find a case where the tool rewrites a file, runs a script, or reports a pass for a shell script with no `set -u` near the top, please open an issue describing the exact commands and input. Do not include any real secret in the report.
