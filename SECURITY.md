# Security policy

Sophia can click, type, run shell commands, move files and read your screen, so security reports matter a lot to us.

## Reporting a vulnerability

**Please do not open a public issue.** Report it privately through GitHub:
[Security > Report a vulnerability](https://github.com/ds1734770-dot/Sophia/security/advisories/new).

Include what you did, what happened, the version (`git rev-parse --short HEAD` or the release tag) and your operating system. A proof of concept helps.

What to expect:

| | |
| --- | --- |
| Acknowledgement | within 7 days |
| First assessment | within 14 days |
| Fix or mitigation for confirmed issues | aimed at within 90 days, sooner for severe ones |

You will be credited in the release notes unless you prefer not to be.

## Supported versions

Only the latest release receives security fixes.

## What counts

Especially welcome:

- ways for text on a web page, in a file, in the clipboard or on the screen to make Sophia act without the user asking (prompt injection);
- getting around a safety tier: a destructive action that runs without confirmation, a refused shell command that runs, writing to a protected folder, reading a secrets file;
- the screen agent acting on a password field, a banking page or a system settings window;
- the local agent hub (`127.0.0.1`) accepting requests without its token, or from a web page;
- a plugin loading without being trusted;
- secrets (the API key) ending up in logs or files.

Out of scope: problems that need an attacker who already controls your user account, plugins or MCP servers you chose to trust, and Gemini model quality issues that cause no unsafe action.

See [docs/THREAT_MODEL.md](docs/THREAT_MODEL.md) for how Sophia is meant to defend itself.
