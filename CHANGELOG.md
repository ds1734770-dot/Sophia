# Changelog

All notable changes. Versions follow [Semantic Versioning](https://semver.org/); the installers install a tagged release.

## [0.3.0] - 2026-11-15

First public release.

### Added
- **"Hey Sophia" wake phrase** (the new default). It is recognised by the local Whisper model with a strict match on the name, with no keyword model and no non-commercial license. `scripts/wake_benchmark.py` measures it; `python -m app.voice.diagnose` shows what it hears. Other wake words are still available with `WAKE_WORD` (for example `hey_jarvis`).
- **macOS support**:
  - every app in /Applications;
  - quitting apps, window control, volume, media keys, brightness, power, dark mode, clipboard;
  - Spotlight search;
  - the Accessibility API for screen controls and the WhatsApp skills;
  - Carbon global hotkeys and zsh, with its own safety rules;
  - the `say` voice, and Open at login.
- One-line installers for macOS and Windows, pinned to this release, plus a manual install path.
- `sophia` command and `sophia --setup` wizard: API key, app scan, permissions, voice models, start at login.
- Plugin trust: plugins in the data folder load only after `sophia --trust-plugin FILE`, pinned to the file's SHA-256.
- `SITE_BROWSERS` setting to open chosen websites in a chosen browser.
- Project documents:
  - SECURITY.md, PRIVACY.md, docs/THREAT_MODEL.md and docs/ARCHITECTURE.md;
  - CONTRIBUTING.md and CODE_OF_CONDUCT.md;
  - issue and pull request templates, CODEOWNERS;
  - THIRD_PARTY_LICENSES.md.
- CI on Windows and macOS:
  - wider lint rules and mypy on the safety-critical modules;
  - test coverage;
  - license check and a weekly `pip-audit`;
  - Dependabot.
- `pyproject.toml` can now be installed with pip (`pip install .`), which creates the `sophia` command.

### Changed
- Windows data moved from `data\` in the code folder to `%APPDATA%\Sophia` (copied once on first start).
- The armor appearance is called "Armored suit".
- The default voice is credited as "Jenny (Dioco)", as its license requires.

### Fixed
- System status on macOS, opening websites when a preferred browser is missing, the agent commands in the README.

### Security
- Upgraded certifi, cryptography, filelock, opentelemetry-api, Pillow, pyasn1 and pypdf to versions without known vulnerabilities.

## [0.2.0]

Windows-only development version (not released).

[0.3.0]: https://github.com/ds1734770-dot/Sophia/releases/tag/v0.3.0
