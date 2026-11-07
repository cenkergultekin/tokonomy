# Security

tokonomy is a local-first tool. By design it has no server, no account and no
outbound telemetry. The dashboard listens on `127.0.0.1` only.

## What is stored

- Session identifiers, timestamps, model names and token counters.
- Source file paths (which may include local project names).
- Provider quota observations.
- Explicit work-group names you assign.

tokonomy never stores prompts, model responses, tool arguments, tool results or
file contents. Source files are opened read-only.

## Reporting

If you find a vulnerability — for example, a parser that writes content fields,
a dashboard endpoint reachable from another interface, or a path traversal in the
HTML exporter — please open a private security advisory on GitHub or email the
maintainer listed in `pyproject.toml`.

Please do not include real session data in a public issue. A minimal synthetic
record is enough to reproduce a parser bug.

## Data you can delete

```text
tokonomy delete --source codex     # one source's imported rows
tokonomy delete --all             # every imported row
```

Deleting tokonomy's database does not touch the clients' own session files.
