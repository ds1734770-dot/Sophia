"""
Plugins: drop a Python file into data/plugins (or plugins/ next to the
code) and its tools appear in Sophia on the next start.

A plugin file defines either

    TOOLS = [Tool(...), ...]

or

    def register(registry, services): ...

Files whose name starts with an underscore are ignored. A plugin runs
with full access to the computer, so only install plugins you trust.
"""

import importlib.util
import logging
from pathlib import Path

log = logging.getLogger("sophia.plugins")


def load_plugins(registry, folders, services=None):
    """
    Load every plugin from the given folders. Returns the list of
    plugin file names that loaded; a broken plugin is skipped.
    """

    loaded = []

    for folder in folders:

        folder = Path(folder)

        if not folder.is_dir():
            continue

        for path in sorted(folder.glob("*.py")):

            if path.name.startswith("_"):
                continue

            try:

                spec = importlib.util.spec_from_file_location(
                    f"sophia_plugin_{path.stem}", path
                )

                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)

                if hasattr(module, "register"):

                    module.register(registry, services or {})

                else:

                    for tool in getattr(module, "TOOLS", []):
                        registry.register(tool)

                loaded.append(path.name)

            except Exception:

                log.exception("Plugin %s failed to load", path.name)

    return loaded
