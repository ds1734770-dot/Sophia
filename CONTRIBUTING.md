# Contributing to Sophia

Thanks for helping! Bug reports, ideas, documentation and code are all welcome.

## Ways to help

- **Report a bug** or **suggest a feature** with the issue templates.
- **Pick an issue** labelled [`good first issue`](https://github.com/ds1734770-dot/Sophia/labels/good%20first%20issue).
- **Ask a question** in [Discussions](https://github.com/ds1734770-dot/Sophia/discussions).
- **Security problems:** never in a public issue. See [SECURITY.md](SECURITY.md).

## Set up

```bash
git clone https://github.com/ds1734770-dot/Sophia.git
cd Sophia
scripts/setup_mac.sh --no-setup        # macOS: Python 3.12 environment in ~/.venvs/sophia
source ~/.venvs/sophia/bin/activate
```

On Windows: `py -3.12 -m venv .venv`, `.venv\Scripts\activate`, `pip install -r requirements-dev.txt`.

You need a free [Gemini API key](https://aistudio.google.com/apikey) to run the app (`sophia --setup` or `GEMINI_API_KEY` in `.env`). **The tests need no key and make no network calls.**

## Before you open a pull request

```bash
QT_QPA_PLATFORM=offscreen pytest -q          # about 900 tests, headless
ruff check app main.py tests scripts
mypy                                         # the safety-critical modules
python scripts/licenses.py --check           # only if you changed dependencies
```

CI runs the same on Windows and macOS. If you can only test one system, say so in the pull request.

## Guidelines

- **Keep the safety tiers.** Any new action that changes something must go through the tool registry with the right `Risk` (see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)). Never let text from a web page, file or screen trigger an action by itself.
- **Both systems.** Platform code goes behind the adapters (`app/computer/macos.py`, the Windows modules beside it). If a feature only works on one system, it must fail with a clear message on the other.
- **Tests for behaviour.** New tools and fixes come with a test; use fakes rather than the real screen, microphone or network.
- **Small pull requests** with one purpose are reviewed fastest.
- **Plain language** in messages the user sees: short sentences, no jargon.
- **Dependencies:** pin new ones in `requirements.txt`, declare them in `pyproject.toml`, and run `scripts/licenses.py --check`. No new GPL/AGPL dependencies without discussion.

## Licensing of contributions

Sophia is MIT licensed. By opening a pull request you agree that your contribution is licensed under the same MIT license (inbound = outbound), and that you have the right to submit it. No CLA is needed.

## Where things are

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for a map of the code and step-by-step guides: adding a tool, a local command, a skill, a character, a plugin, or support for another operating system.
