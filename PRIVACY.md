# Privacy

Sophia runs on your computer. There is **no Sophia server, no account and no telemetry**: the project does not collect anything about you or your use of it. What leaves your computer is listed below.

## What is sent where

| Destination | When | What |
| --- | --- | --- |
| **Google Gemini** (your API key) | every request that is not answered locally | your message, the recent conversation and its summary, facts you asked Sophia to remember, a short description of this computer (computer name, OS version, user name, everyday folder paths, names of installed apps and open windows), and the results of tools Sophia used for the request: text of files or web pages it read, clipboard text when you ask about it, **screenshots and window contents when you ask about or work on the screen** |
| DuckDuckGo and the search engines behind `ddgs` | "search the web" | the search query |
| Web pages | "summarize this page", or when Sophia reads a search result | a normal page request |
| open-meteo.com | weather | the city name |
| frankfurter.app | currency conversion | the currencies |
| Wikipedia, Wiktionary, Google News RSS | "tell me about", "define", "latest news" | the topic |
| Hugging Face | first use of voice | model downloads (no personal data) |
| Microsoft Edge TTS | only with `TTS_ENGINE=edge` | the text to speak |
| MCP servers and plugins | only ones you add | whatever they are built to send |

Google's handling of Gemini API data is set by [Google's terms](https://ai.google.dev/gemini-api/terms); on the free tier Google may use requests to improve its products. Use a paid key if that matters to you.

**Never sent:** your API key (other than to Google), audio (speech recognition and the voice run offline), files Sophia did not open for a request, anything while Sophia is idle.

Local answers (time, timers, volume, calculator, opening apps by exact name, instant screen commands, the WhatsApp skills) make no AI request at all.

## What is stored on your computer

In your data folder (`~/Library/Application Support/Sophia` on macOS, `%APPDATA%\Sophia` on Windows, or `SOPHIA_HOME`):

| File | Contents |
| --- | --- |
| `memory.json`, `summary.json` | recent conversation and its running summary |
| `memories.json`, `profile.json` | facts you told Sophia to remember |
| `notes.json`, `schedules.json`, `routines.json`, `timers.json` | your notes, reminders and routines |
| `applications.json`, `fingerprints.json`, `launch_history.json` | installed apps and how often you open them |
| `usage.json` | Gemini requests per model per day (for the quota) |
| `logs/sophia.log` | the app's log |
| `logs/actions.jsonl` | every action Sophia took, with its arguments |
| `logs/voice/` | the last 12 voice requests as audio, to investigate recognition problems |
| `models/` | downloaded speech and voice models |
| `agent_hub.json` | the random token of the local agent hub |

The Gemini API key is stored in the macOS Keychain or Windows Credential Manager (or in `.env` if you put it there).

To delete everything, quit Sophia and delete the data folder; remove the key with Keychain Access or Credential Manager (entry "Sophia").
