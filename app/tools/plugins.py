"""
Plugins: drop a Python file into data/plugins (or plugins/ next to the
code) and its tools appear in Sophia on the next start.

A plugin file defines either

    TOOLS = [Tool(...), ...]

or

    def register(registry, services): ...

Files whose name starts with an underscore are ignored. A plugin runs
with full access to the computer, so a plugin in your data folder only
loads after you trust that exact file:

    sophia --trust-plugin weather_plus.py

Trust is recorded as the file's SHA-256 in trusted_plugins.json. If the
file changes (an update, or something tampering with it), it stops
loading until you trust it again.
"""

import hashlib
import importlib.util
import json
import logging
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

log = logging.getLogger("sophia.plugins")

TRUST_FILE = "trusted_plugins.json"


def file_hash(path: str | Path) -> str:

    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class PluginTrust:
    """
    Which plugin files the user has approved, by content hash.
    """

    def __init__(self, path: str | Path) -> None:

        self.path = Path(path)

    def _load(self) -> dict[str, str]:

        try:
            return json.loads(self.path.read_text(encoding="utf-8"))

        except (OSError, ValueError):
            return {}

    def trusted(self, plugin_path: str | Path) -> bool:

        return self._load().get(Path(plugin_path).name) == file_hash(plugin_path)

    def trust(self, plugin_path: str | Path) -> None:

        data = self._load()
        data[Path(plugin_path).name] = file_hash(plugin_path)

        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def untrust(self, name: str) -> bool:

        data = self._load()

        if data.pop(Path(name).name, None) is None:
            return False

        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")

        return True


def trust_plugin_command(argv: Sequence[str], plugins_folder: str | Path, trust: PluginTrust) -> int:
    """
    sophia --trust-plugin FILE   /   sophia --untrust-plugin FILE
    """

    if "--untrust-plugin" in argv:

        name = argv[argv.index("--untrust-plugin") + 1] if len(argv) > argv.index("--untrust-plugin") + 1 else ""

        print("Removed." if name and trust.untrust(name) else f"'{name}' was not trusted.")

        return 0

    index = argv.index("--trust-plugin")

    if len(argv) <= index + 1:
        print(f"Usage: sophia --trust-plugin FILE   (plugins live in {plugins_folder})")
        return 1

    path = Path(argv[index + 1])

    if not path.is_absolute():
        path = Path(plugins_folder) / path.name

    if not path.is_file() or path.suffix != ".py":
        print(f"No plugin file at {path}")
        return 1

    print(f"Plugin: {path}")
    print(f"SHA-256: {file_hash(path)}")
    print("A plugin runs with full access to your computer. Only continue if you trust its author.")

    if input("Trust this exact file? [y/N] ").strip().lower() != "y":
        print("Not trusted.")
        return 1

    trust.trust(path)

    print("Trusted. Restart Sophia to load it.")

    return 0


def load_plugins(
    registry: Any,
    folders: Iterable[str | Path],
    services: dict[str, Any] | None = None,
    trust: PluginTrust | None = None,
    needs_trust: Iterable[str | Path] = (),
) -> list[str]:
    """
    Load every plugin from the given folders. Returns the list of
    plugin file names that loaded; a broken plugin is skipped. Plugins in
    a folder listed in `needs_trust` load only if `trust` approves them.
    """

    loaded = []
    guarded = {Path(f).resolve() for f in needs_trust}

    for folder in folders:

        folder = Path(folder)

        if not folder.is_dir():
            continue

        for path in sorted(folder.glob("*.py")):

            if path.name.startswith("_"):
                continue

            if folder.resolve() in guarded and (trust is None or not trust.trusted(path)):

                log.warning(
                    "Plugin %s is not trusted (new or changed), so it was not loaded. "
                    "Run: sophia --trust-plugin %s",
                    path.name, path.name,
                )

                continue

            try:

                spec = importlib.util.spec_from_file_location(
                    f"sophia_plugin_{path.stem}", path
                )

                if spec is None or spec.loader is None:
                    raise ImportError(f"cannot load {path.name}")

                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)

                if hasattr(module, "register"):

                    module.register(registry, services or {})

                else:

                    for tool in getattr(module, "TOOLS", []):
                        registry.register(tool)

                loaded.append(path.name)

                log.warning("Loaded plugin %s (runs with full access to this computer)", path.name)

            except Exception:

                log.exception("Plugin %s failed to load", path.name)

    return loaded
