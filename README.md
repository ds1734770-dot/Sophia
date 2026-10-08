# Sophia

A personal AI assistant for Windows. Talk or type to it; it answers questions with Google Gemini and carries out tasks on your computer: open and close apps, search the web, find and manage files, set reminders, control volume, and look at your screen.

> Status: early (v0.1). Windows only for now.

## What it can do

| Area | Examples |
| --- | --- |
| Chat and learning | "Explain binary search", "Help me debug this error" |
| Apps and windows | "Open VS Code", "Close Spotify", "Minimize Chrome" |
| Web | "Search YouTube for lofi", "Open github.com" |
| Files | "Find my resume", "Rename it to CV.pdf", "Delete old-notes.txt" |
| Schedule | "Remind me to call mom tomorrow at 6pm", "What is on tomorrow?" |
| System | "Volume to 30", "Take a screenshot", "Restart in 30 seconds" |
| Screen | "What error is on my screen?" (sends a screenshot to Gemini, only after you confirm) |
| Memory | "Remember I prefer Python", "What do you know about me?", "Forget my city" |
| Voice | Click the mic and speak; turn on the speaker to hear replies |

## Safety

Everything Sophia does on your computer goes through one registry with three tiers:

- **Runs immediately:** reading and low-risk actions (open an app, search, find files).
- **Asks first:** closing apps, renaming or opening files, looking at your screen, clearing a day's schedule.
- **Asks with a warning:** deleting files (they go to the Recycle Bin) and shutdown or restart (30 second countdown you can cancel).

File actions are limited to Desktop, Documents and Downloads, and Sophia will not open programs or scripts. Text found in files or web pages is treated as data, never as instructions.

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

On first start Sophia asks for a Gemini API key (free at https://aistudio.google.com/apikey) and stores it in Windows Credential Manager. For development you can instead put `GEMINI_API_KEY` in a `.env` file (see `.env.example`).

```powershell
python main.py              # desktop window
python main.py --cli        # text-only console
python main.py --no-voice   # without microphone and speech
```

Press **Ctrl+Alt+Space** (or **Ctrl+Alt+S** if another program owns it) to show or hide the window. Closing the window keeps Sophia in the system tray; use the menu to quit.

## Voice

Speech recognition runs on your PC with [faster-whisper](https://github.com/SYSTRAN/faster-whisper), so audio never leaves your computer and uses no AI quota. The model (about 140 MB for `base.en`) downloads the first time you use the microphone. Spoken replies use the built-in Windows voices.

## Gemini quota

The free tier limits each model separately. Sophia spreads requests across a chain of models (`MODEL_NAME`, then `FALLBACK_MODELS`), remembers which are cooling down, uses a cheaper model for background work (`LIGHT_MODEL`), and only extracts memories from messages that look like personal facts. Type `usage` to see today's requests per model. Simple commands ("open notepad", "what time is it", "12*(5+8)") are handled locally without any request.

## Configuration

Environment variables or `.env`:

| Variable | Default | Meaning |
| --- | --- | --- |
| `GEMINI_API_KEY` | (Credential Manager) | API key |
| `MODEL_NAME` | `gemini-3.5-flash` | Main model |
| `FALLBACK_MODELS` | `gemini-3-flash-preview,gemini-3.1-flash-lite` | Used when the main model is out of quota |
| `LIGHT_MODEL` | `gemini-3.1-flash-lite` | Memory extraction and summaries |
| `REQUEST_TIMEOUT` | `30` | Seconds before a request is given up |
| `WHISPER_MODEL` | `base.en` | Local speech model (`tiny.en` is smaller and faster) |
| `SOPHIA_HOME` | `./data` | Where history, profile and logs are kept |

Your data (chat history, profile, schedule, file index, logs) lives in `data/` and is git-ignored.

## Project layout

```
app/
  brain/      routing, Gemini client, model pool, local command shortcuts
  tools/      tool registry (safety tiers) and the built-in tools
  computer/   app discovery and launching, windows, system controls, autostart
  file/       file index, file manager, path guard
  memory/     history, profile, summaries
  voice/      speech-to-text and text-to-speech
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
.\scriptsuild.ps1
```

This produces `dist\Sophia\Sophia.exe` (about 400 MB, mostly the Qt and speech libraries). The packaged app keeps its data in `%APPDATA%\Sophia`. An installer (for example Inno Setup) can wrap the folder.

## Roadmap

- Installer and auto-update
- Server layer (accounts, per-user limits, hosted model access) for a public release
- Multiple saved conversations and search
- Wake word
- macOS and Linux support behind a platform adapter
