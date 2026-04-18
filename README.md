# JARVIS

JARVIS is a single-user, local-first Windows desktop assistant daemon. It combines Claude for reasoning, faster-whisper for speech-to-text, ElevenLabs with Piper fallback for speech synthesis, ChromaDB for semantic memory, SQLite for structured profile data, Playwright for browser automation, APScheduler for proactive jobs, and pystray plus pynput for desktop integration.

## Requirements

- Windows 10/11 (the project targets a Windows workstation; several tools use Windows-specific launch helpers).
- Python 3.11 or newer.
- [Playwright](https://playwright.dev/python/docs/intro) browsers after install: `playwright install chromium`.
- Optional: [Piper](https://github.com/rhasspy/piper) binary and ONNX voice for offline TTS when ElevenLabs keys are absent.
- Optional: Google Cloud OAuth client JSON for Calendar and Gmail tools (combined scopes).

## Setup

1. Create a virtual environment and install dependencies:

```powershell
cd D:\Projects\JARVIS-AI
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
playwright install chromium
```

2. Copy `.env.example` to `.env`:

```powershell
copy .env.example .env
```

If `.env.example` in your local workspace is already populated, this step is enough.

3. Run the daemon:

```powershell
python -m jarvis.main
```

The system tray icon appears with **Status** and **Exit**. A default global hotkey (`Ctrl+Alt+J`) triggers a short agent acknowledgement (voice capture is wired separately in `jarvis.voice`).

## Dashboard + API (development)

From the repo root (with the venv activated, `pip install -r requirements.txt` done, and `npm install` inside `dashboard/` once):

1. **Set up the control-plane SQLite DB** (`data/jarvis.db`):

```powershell
python -m database.db_setup
```

(Equivalent: `python database/db_setup.py` — prints `DB ready`.)

2. **Start the API and the Vite dashboard together** (API on **8765**, UI on **5173**):

```powershell
python scripts/dev.py
```

3. **In another terminal**, smoke-test the API:

```powershell
python scripts/test_api.py
```

4. **Open the dashboard:** [http://localhost:5173](http://localhost:5173)
   (If 5173 is already in use, Vite will auto-pick the next free port and print it in the terminal.)

Use `Ctrl+C` in the `dev.py` terminal to stop both processes.

## Environment variables

| Variable | Purpose |
| --- | --- |
| `ANTHROPIC_API_KEY` | Required. Claude API access. |
| `CLAUDE_MODEL_FAST` / `CLAUDE_MODEL_SMART` | Optional model overrides. |
| `ELEVENLABS_API_KEY` / `ELEVENLABS_VOICE_ID` | Primary cloud TTS. |
| `PIPER_EXECUTABLE` / `PIPER_MODEL_PATH` | Offline Piper fallback. |
| `WHISPER_MODEL_SIZE` | faster-whisper model size. |
| `DATA_DIR` | Base directory for Chroma, SQLite, and Google token storage. |
| `GOOGLE_CREDENTIALS_PATH` | OAuth client secret JSON for Calendar and Gmail. |
| `GOOGLE_TOKEN_PATH` | Optional override for the stored OAuth token file. |
| `BRIEFING_NEWS_RSS_URLS` | Comma-separated RSS feeds for the morning briefing. |
| `LOG_LEVEL` | Python logging level. |

## Architecture notes

- Async-first services avoid blocking the voice path; blocking SDKs run in executors or threads.
- Tool arguments are validated with Pydantic before execution, and the registry enforces at most eight active tools.
- Long-term memory queries filter on cosine similarity above `0.76` (stricter than the `0.75` guideline in `.cursor/rules`).
- Subprocess usage never sets `shell=True`.

## Project layout

```text
jarvis/
  config.py
  main.py
  agent.py
  voice/
  memory/
  tools/
  scheduler/
  ui/
database/       # SQLite schema + bootstrap (data/jarvis.db)
scripts/        # dev.py, test_api.py
dashboard/      # Vite + React HUD
main_api.py     # FastAPI on :8765
```

## License

Add your preferred license.
