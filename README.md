# Sophia

A personal AI assistant that lives on your Windows PC. Talk or type to it; it answers with Google Gemini and works on your computer: it opens apps, searches the web and reads pages, finds and manages files anywhere on the PC, runs PowerShell, controls the screen, sets reminders and routines, and talks back.

> Status: v0.2, Windows only for now.

## What it can do

| Area | Examples |
| --- | --- |
| Chat and learning | "Explain binary search", "Help me debug this error" |
| Web | "Who won the match last night?" (searches the web), "Summarize this article: <link>", "Weather in Vizag" |
| Apps and windows | "Open VS Code", "Open YouTube", "Close Spotify", "Minimize Chrome" |
| Files, whole PC | "Find my resume", "Summarize that PDF", "Move it to Documents", "Undo that" |
| Shell | "How much free space do I have?", "What is using port 3000?" (shows the exact PowerShell command first) |
| Screen control | "Click the Send button", "Type my email in the search box" (looks at the screen, then clicks and types) |
| Screen questions | "What error is on my screen?" |
| Reminders and routines | "Remind me at 6pm", "Timer for 10 minutes", "Every weekday at 8 give me a morning briefing" |
| Notes and to-dos | "Add a to-do: finish report", "Note that the exam is on Monday" |
| System | "Volume to 30", "Battery and memory?", "Take a screenshot", "Play lofi on YouTube", "Pause the music" |
| Clipboard | "Fix the grammar of what I copied" |
| Memory | "Remember I prefer Python", "What do you know about me?", "Forget my city" |
| Voice | Click the mic, or say "Hey Jarvis" in hands-free mode; natural spoken replies |
| Integrations | Plugins and MCP servers add email, calendar, GitHub, Spotify and more (see below) |

## The interface

Sophia is a yellow sports car that lives on your screen (an original design, no manufacturer badge). Start it from the command line:

```powershell
python main.py            # the car
python main.py --chat     # classic chat window instead
```

- **It drives in** from the nearest screen edge when Sophia starts, and drives off again when you hide it or quit.
- **Drag it** anywhere, like any window. The wheels turn and the car faces the way you move it; it parks facing the middle of the screen.
- **Hover over it** and the headlights come on, the engine revs, and three buttons appear below: **Voice** (listen, then answer aloud), **Chat** (open the full chat beside the car) and **Hide** (drive off).
- **Alt+S** hides the car or brings it back (change it with `HIDE_HOTKEY`, for example `ctrl+alt+o`). The tray icon does the same.
- **Answers** appear as a small text card above the car and are spoken. Questions get Yes / No / Always allow buttons on the card.
- The car shows what Sophia is doing: bright cool headlights that follow your voice while listening, blinking hazard lights while thinking, brake lights glowing while speaking, a headlight flash and sparkles when a task is done, a shudder on an error.
- **It is small on purpose** (130 px wide) with three tiny buttons that show their name as a tooltip. Right-click > Size picks Tiny, Small, Medium or Large, or set `CAR_WIDTH` (70 to 300).
- **Windscreen wiper:** it sweeps when you hover, when the car parks, and the whole time Sophia is thinking.
- **Sound effects** (generated in code, no files): engine arriving, a rev when you hover, a honk when it parks, a wiper swish, button clicks, a chime when listening starts and another when a task succeeds, a rev-and-launch when it leaves. Right-click > Sound effects mutes them; `SOUND_VOLUME` (0 to 1) sets the level. Preview them all with `python -m app.ui.sounds` (add a folder name to also save them as .wav files).
- **Right-click** the car for a menu (open chat, talk, hide, spoken replies, hands-free, reset position, quit). The car never takes keyboard focus, so it will not interrupt what you are typing elsewhere.

The welcome screen in the chat window shows the car too, with tap-to-send ideas; it folds into the header after your first message and replies are typed out word by word.

Sophia can launch any program on your PC (she shows the path, whether it is signed and whether it was downloaded; one "Always allow" covers the session), open any folder, and look at and operate anything visible on your screen.

## How it decides what to do

Gemini decides. Sophia gives it a set of tools (open app, search the web, read a file, run PowerShell, click on the screen, and so on) and it chooses which to call, chaining several when a task needs it. A few exact commands ("open notepad", "what time is it", "12*(5+8)") are answered locally and instantly without using any AI quota; anything vague goes to Gemini.

## Safety

Every action goes through one registry with three tiers:

- **Runs immediately:** reading and low-risk actions (open an app, search the web, find or read files, check status).
- **Asks first:** closing apps, writing, renaming, moving or copying files, clicking and typing on the screen, looking at your screen, running PowerShell. Answer **Yes**, **No**, or **Always allow** to stop asking for that kind of action until Sophia restarts. PowerShell can never be "always allowed".
- **Asks with a warning:** deleting files (they go to the Recycle Bin), shutdown or restart (30 second countdown), PowerShell commands that change things, adding integrations.

Rules that apply on top:

- Files can be read anywhere except secrets (SSH keys, saved passwords, browser cookies). They can be changed anywhere in your own files, but never in Windows, Program Files, AppData or Sophia's own folder. Programs and scripts are never opened or created.
- PowerShell commands that download and run code, hide commands, or weaken protection are refused outright.
- Web pages, files, clipboard text and tool output are treated as data, never as instructions.
- Every action is written to `data/logs/actions.jsonl`. File changes made this session can be undone.
- Your API key lives in Windows Credential Manager, not in a file.

## Install (development)

Requires Windows 10/11 and Python 3.12.

```powershell
git clone https://github.com/ds1734770-dot/Sophia.git
cd Sophia
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

On first start Sophia asks for a Gemini API key (free at https://aistudio.google.com/apikey). For development you can put `GEMINI_API_KEY` in a `.env` file instead (see `.env.example`).

```powershell
python main.py              # the floating car (hover for Voice / Chat / Hide, Alt+S to hide)
python main.py --chat       # classic chat window
python main.py --cli        # text-only console
python main.py --no-voice   # without microphone and speech
```

Press **Ctrl+Alt+Space** (or **Ctrl+Alt+S** / **Ctrl+Alt+J** if another program owns it) to start a voice request. Closing the chat keeps the car on screen.

## Voice

- **Speech recognition** runs on your PC with [faster-whisper](https://github.com/SYSTRAN/faster-whisper): audio never leaves the computer and uses no quota. The model (about 140 MB for `base.en`) downloads the first time you use the microphone.
- **Spoken replies** use Microsoft Edge's neural voices (natural, needs internet) and fall back to the offline Windows voice. Pick a voice with `TTS_VOICE`.
- **Hands-free:** menu > "Hands-free (wake word)" listens for "Hey Jarvis" with a small local model ([openwakeword](https://github.com/dscripka/openWakeWord)); a spoken request gets a spoken reply. Say it clearly near the microphone; lower `WAKE_THRESHOLD` if it misses you. A custom "Hey Sophia" word needs a trained model.

## Gemini quota

The free tier limits each model separately. Sophia spreads requests across a chain of models (`MODEL_NAME`, then `FALLBACK_MODELS`), remembers which are cooling down, uses a cheaper model for background work (`LIGHT_MODEL`), and only extracts memories from messages that look like personal facts. Type `usage` to see today's requests per model. Web search, page reading, weather and speech recognition do not use Gemini at all.

## Integrations

**MCP servers** give Sophia new tools without code. Create `data/mcp.json`:

```json
{
  "servers": {
    "files": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "C:/Users/me/Documents"],
      "env": { "TOKEN": "${MY_TOKEN}" }
    }
  }
}
```

Their tools appear as `mcp_<server>_<tool>` and ask for confirmation unless the server marks them read-only. Ask Sophia "which integrations are connected?" to check.

**Plugins:** put a Python file in `data/plugins/` that defines `TOOLS = [Tool(...)]` or `register(registry, services)`. Files starting with `_` are ignored; see `plugins/_example_plugin.py`. A plugin runs with full access to your PC, so only install ones you trust.

## Configuration

Environment variables or `.env`:

| Variable | Default | Meaning |
| --- | --- | --- |
| `GEMINI_API_KEY` | (Credential Manager) | API key |
| `MODEL_NAME` | `gemini-3.5-flash` | Main model |
| `FALLBACK_MODELS` | `gemini-3.8-flash,gemini-3.6-flash,gemini-3-flash-preview,gemini-3.1-flash-lite` | Used when the main model is out of quota |
| `LIGHT_MODEL` | `gemini-3.1-flash-lite` | Memory extraction and summaries |
| `REQUEST_TIMEOUT` | `30` | Seconds before a request is given up |
| `WHISPER_MODEL` | `base.en` | Local speech model (`tiny.en` is smaller and faster) |
| `TTS_VOICE` | `en-IN-NeerjaNeural` | Neural voice for replies |
| `NEURAL_VOICE` | `true` | Set to `false` to always use the offline Windows voice |
| `WAKE_WORD` | `hey_jarvis` | Wake word model |
| `WAKE_THRESHOLD` | `0.5` | Lower is more sensitive |
| `HIDE_HOTKEY` | `alt+s` | Global shortcut that hides or shows the car |
| `CAR_WIDTH` | `130` | Width of the car in pixels (70 to 300) |
| `SOUND_EFFECTS` | `true` | Turn the car's sound effects on or off |
| `SOUND_VOLUME` | `0.6` | Sound effect volume (0 to 1) |
| `SOPHIA_HOME` | `./data` | Where history, profile, notes and logs are kept |

Your data (chat history, profile, notes, schedule, routines, logs) lives in `data/` and is git-ignored.

## Project layout

```
app/
  brain/      routing, Gemini client, model pool, local fast path
  tools/      tool registry (safety tiers) and every tool: files, web, shell, screen,
              reminders, notes, system, MCP bridge, plugins, undo, action log
  computer/   app discovery and launching, windows, system controls, screen control, shell
  file/       path policy, whole-PC search, file manager
  planner/    schedule, timers, routines and the background reminder service
  memory/     history, profile, summaries
  voice/      speech-to-text, spoken replies, neural voice, wake word
  ui/         PySide6 desktop window
tests/        pytest suite (runs headless)
```

## Develop

```powershell
pip install -r requirements-dev.txt
pytest
```

## Build a standalone app

```powershell
pip install pyinstaller
.\scripts\build.ps1
```

This produces `dist\Sophia\Sophia.exe`. The packaged app keeps its data in `%APPDATA%\Sophia`. An installer (for example Inno Setup) can wrap the folder.

## Roadmap

- Installer and auto-update
- Server layer (accounts, per-user limits, hosted model access) for a public release
- Several saved conversations with search
- A custom "Hey Sophia" wake word
- Email and calendar through a Google or Microsoft sign-in
- macOS and Linux behind a platform adapter
