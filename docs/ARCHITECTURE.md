# Architecture

How a request flows through Sophia, where each part lives, and how to add to it.

## A request, end to end

```
 voice ──► wake phrase ──► recorder ──► speech recognizer ─┐
 (app/voice: wakeword.py, listener.py, moonshine.py)        │
                                                            ▼
 chat window / floating car / --cli ─────────────────► Sophia.respond()   (app/sophia.py)
                                                            │
                                                            ▼
                                                     Brain (app/brain/brain.py)
                                         ┌──────────────────┴──────────────────┐
                                         ▼                                     ▼
                              QuickEngine: exact commands           Gemini with tools
                              ("volume 30", "timer 5 min",          (app/brain/gemini_client.py,
                              "open notepad") answered locally      model_pool.py: fallbacks, quota)
                                         │                                     │
                                         └──────────────┬──────────────────────┘
                                                        ▼
                                          ToolRegistry (app/tools/registry.py)
                                 every action: SAFE runs, CONFIRM asks, DANGEROUS warns
                                                        │
       ┌───────────────┬───────────────┬───────────────┼───────────────┬───────────────┐
       ▼               ▼               ▼               ▼               ▼               ▼
  apps & windows   files          web & lookups    screen          shell          plugins & MCP
  app/computer     app/file       app/tools/       app/computer/   computer/      tools/plugins.py
                   path_guard.py  web_tools.py     screen_control  shell_runner   tools/mcp_bridge.py
                                                   ui_automation
                                                   app/agent (screen agent, skills, guard)
                                                        │
                                                        ▼
                                  reply ──► chat / car card ──► speaker (Piper / system voice)
```

## Packages

| Package | What it does |
| --- | --- |
| `app/brain` | routing, the Gemini client and model pool, the local fast path (`engines/quick_engine.py`) |
| `app/tools` | the tool registry and every tool; `builtin_tools.py` builds the registry |
| `app/computer` | apps (discovery, launching), windows, system controls, screen control, shell, accessibility. Platform adapters live here |
| `app/agent` | the screen agent (multi-step screen tasks), skills (WhatsApp), the screen guard and stop control |
| `app/agents` | the local hub that shows what other AI agents (Claude Code...) are doing |
| `app/file` | path policy (`path_guard.py`), whole-computer search, file operations |
| `app/memory`, `app/planner` | conversation memory and profile; reminders, timers, routines |
| `app/voice` | wake phrase, recording, speech recognition, spoken replies |
| `app/ui` | PySide6: floating character, chat window, overlay, hotkeys |
| `app/context` | what Sophia knows about the computer up front |
| `app/setup_wizard.py` | `sophia --setup` |

## Safety model in one paragraph

Gemini never acts directly. It asks for tools; the **registry** decides from each tool's `risk` (or `risk_fn`, which can look at the arguments) whether to run it, ask the user (`CONFIRM`) or ask with a warning (`DANGEROUS`). A `risk_fn` can also raise `ToolBlocked` to refuse outright. Underneath, `path_guard.py` limits which paths can be read or changed, `shell_runner.py` refuses harmful commands, and `agent/guard.py` keeps the screen agent away from banking pages, password fields and system settings. See [THREAT_MODEL.md](THREAT_MODEL.md).

## Guides

### Add a tool

1. Write a handler `def my_tool(context, **args) -> (ok: bool, message: str)`.
2. Register it in the right `register_*` function (or a new one called from `build_default_registry` in `app/tools/builtin_tools.py`):

   ```python
   registry.register(Tool(
       name="count_words",
       description="Count the words in a text file.",   # Gemini reads this
       parameters={"path": {"type": "string"}},
       required=["path"],
       risk=Risk.SAFE,              # SAFE, CONFIRM or DANGEROUS
       preview=lambda a: f"I'm about to count the words in {a['path']}.",
       handler=count_words,
   ))
   ```

   Anything that changes the computer is at least `CONFIRM`. File paths go through `guard.for_read()` / `guard.for_write()`.
3. Give it a friendly label in `app/ui/activity.py` (shown in the live steps card).
4. Add a test with fakes (see `tests/test_tools.py`).

### Add a local command (no AI request)

Add a rule to `QuickEngine.rules` in `app/brain/engines/quick_engine.py`: a regular expression for the **whole** sentence and the tool call it maps to. The tool still goes through the registry. Add cases to `tests/test_quick_engine.py`.

### Add a skill (a multi-step screen task with no AI)

See `WhatsAppSkill` in `app/agent/skills.py`: it reads the window through `ScreenElements` (accessibility), checks `self._check()` before every action (stop switch, limits, forbidden windows) and raises `Stopped` with a plain message when the app looks different. Register it like `register_skill_tools` in `app/agent/screen_agent.py`.

### Add a character (appearance)

A character is a model class with the same states as `CarModel` (`app/ui/car.py`) and `ArmorModel` (`app/ui/armor.py`). Add it to `CHARACTERS` in `app/ui/characters.py` with its label and sizes; it then appears in the Appearance menu.

### Write a plugin (no change to Sophia's code)

Copy `plugins/_example_plugin.py` into the `plugins` folder of your data folder, define `TOOLS = [Tool(...)]` or `register(registry, services)`, then run `sophia --trust-plugin your_plugin.py`.

### Support another operating system

Platform code is selected by `sys.platform` behind small adapters:

| Job | Windows | macOS |
| --- | --- | --- |
| system helpers | `windows_*.py`, `system_controls.py` | `macos.py` |
| app discovery | `application_discovery/*_scanner.py` | `application_discovery/mac_app_scanner.py` |
| reading a window's controls | `ui_automation.py` (`UiaBackend`) | `mac_accessibility.py` (`MacAxBackend`) |
| global hotkeys | `ui/hotkey.py` | `ui/mac_hotkey.py` |
| shell | PowerShell | zsh (`shell_runner.py`) |

For Linux, add the same pieces (for example AT-SPI for accessibility, `xdg-open` for opening files, `.desktop` files for apps) and a CI job.
