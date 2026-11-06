# Security Policy

This tool runs locally, collects no data, sends nothing anywhere, and needs no API key or secret. It only reads the files and folders you name, and it never rewrites a file, never resolves a conflict, and never changes anything. It writes nothing except the report on standard output (and usage errors on standard error).

If you find a case where the tool changes a file, or reports a pass for a file that holds a conflict marker, please open an issue describing the exact commands and input. Do not include any real secret in the report.
