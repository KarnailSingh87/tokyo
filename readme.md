# ⚙️ TOKYO
### The Ultimate Cross-Platform Personal AI Assistant

A real-time voice AI that can hear, see, understand, and control your computer — on any OS. Supports Windows, macOS, and Linux. Built on the Gemini Live API for native audio streaming, delivering zero subscriptions and total digital autonomy.

---

## ✨ Overview

TOKYO is an assistant you extend without ever touching its engine. Drop a single plugin file into the `plugins/` folder and TOKYO learns a new skill on the next launch — no code changes, no configuration, no risk. On top of that, the voice itself got smarter: TOKYO now hears the emotion in your voice, knows when you're talking to someone else in the room and stays silent, and can hold one conversation for hours without losing the thread.

It's not just an assistant — it's an extension of your digital life.

---

## 🚀 Capabilities

### Core Features
| Feature | Description |
|---|---|
| 🧩 Plugin System | Drop a single `.py` file into `plugins/` — TOKYO learns a new skill on next launch |
| 🎙️ Real-time Voice | Ultra-low latency conversation in any language via Gemini Live API |
| 💓 Affective Dialog | Hears the emotion in your voice and adapts its tone in response |
| 🤫 Proactive Audio | Knows when you're not talking to it — background chatter never triggers a reply |
| ♾️ Unlimited Sessions | Sliding-window context compression — one conversation can last for hours |
| 🖥️ System Control | Launch apps, adjust volume/brightness, WiFi, shortcuts, power — all by voice |
| 🧩 Autonomous Tasks | High-level planning for complex multi-step goals via agent mode |
| 👁️ Visual Awareness | Real-time screen capture and webcam vision piped into your main Gemini session |
| 🧠 Persistent Memory | Deeply remembers projects, preferences, and personal context across sessions |
| ⌨️ Hybrid Input | Seamlessly switch between keyboard typing and voice commands |
| 🌅 Morning Briefing | On first boot: greets you, reads the time, recaps yesterday, and fetches live news |
| 🔔 Proactive 2.0 | Time-aware, context-aware check-ins — knows the time of day, your projects, and what you've been discussing |
| 🗓️ Session Memory | Summarises each conversation and mentions it naturally next morning — consumed after use, never repeats |
| 👁️‍🗨️ Background Monitoring | User-configured topic watching — checks for new headlines once a day and alerts naturally |
| 📊 Hardware Monitoring | Continuous CPU, RAM, GPU and temperature telemetry with localized voice alerts |
| 🌤️ Weather Report | Live weather data for your city, personalized from memory |
| 🗺️ Dynamic Content Panel | Scrollable display layer beneath the HUD that renders web results, news, and search data |
| 🔍 Multi-Mode Web Search | `news` / `research` / `price` / `compare` / `search` — Gemini Grounded first, DDG fallback |
| ⏰ Smart Reminders | OS-native scheduled notifications (Windows Task Scheduler / macOS LaunchAgent / Linux systemd) |
| ✈️ Flight Finder | Live flight price and availability lookup |
| 🎮 Game Updater | Checks and triggers game updates on Steam and Epic Games on demand |
| 📂 File Processor | Read, summarize, and answer questions about local files |
| 💻 Code Helper | Inline code review, debugging, and generation |
| 🌐 Browser Control | Open URLs, navigate tabs, and interact with the browser by voice |
| 📨 Send Message | Compose and send messages through WhatsApp, Telegram, and more |
| 💼 LinkedIn Updater | Upload your resume — AI rewrites it and updates your LinkedIn profile automatically |
| 🎬 YouTube Control | Search, play, and control YouTube playback by voice |
| 🖱️ Desktop Control | Taskbar, window management, and desktop-level operations |
| 🧑‍💻 Silent Language Memory | Detects spoken language on first use — all future sessions adapt automatically |
| 📱 Remote Dashboard | Control the assistant from your phone via QR code pairing |
| ⚡ Auto-Start on Boot | Registers with the OS startup system (registry / LaunchAgent / .desktop) |
| 📋 Clipboard Intelligence | Copy any text → floating panel with Translate / Summarise / Explain / Fix |
| 🎨 Assistant Customization | Change the assistant name and your name from the UI — takes effect immediately |

---

## 🆕 What's New

### 💼 LinkedIn Auto-Updater — Upload Your Resume, Get an Updated Profile
Tell TOKYO *"update my LinkedIn profile with my resume"* and it handles everything:
1. Finds your newest resume/CV automatically (Downloads, Desktop, Documents, TOKYO Uploads) or accepts a path
2. Extracts text from PDF/DOCX/TXT
3. Gemini rewrites it into polished LinkedIn content — headline, about, experience, education, skills
4. Applies it to your real profile via a persistent browser session — log in once by hand, then it's fully automatic
5. `preview_only` mode shows the generated content on screen before touching anything
Parsed profiles are cached in `memory/linkedin_latest.json`, so re-runs skip re-parsing.

### 🐛 Build LIII — Stability Pass
- Fixed approval flow crashing the Live session; denied/timed-out tools no longer execute; approved tools no longer run twice
- Fixed permission engine denying every terminal command via broken arg-regex matching
- `save_memory` now actually persists (was silently returning "Unknown tool")
- TOKYO-X: memory/voice/notify tools execute correctly, web search works, agent planner import fixed, audit trail actually writes, goal runner fixed
- Activated dormant plugins: calorie counter, pushup counter, video upload
- Added `pypdf` / `python-docx` / `pdfplumber` for document parsing

### 🧩 Plugin System — Extend TOKYO Without Touching a Single Core File
The headline feature of TOKYO, and the reason for its final architecture version. Every new capability from now on ships as a single `.py` file:

1. Download a plugin file (e.g. `calorie_counter.py`)
2. Drop it into the `plugins/` folder
3. Restart TOKYO — done. The skill is live, by voice, in any language.

Each plugin declares its own Gemini tool schema and logic in one file. The engine auto-discovers it at startup, registers it with the Live session, and lists it in the **🧩 Plugin Manager** panel where every plugin gets its own persistent ON/OFF toggle.

Safety is built in at three layers: a broken or badly written plugin can **never** crash TOKYO — it simply shows up as "BROKEN" in the manager with the error explained, while every other tool and plugin keeps working. Name collisions with core tools are detected and rejected automatically. Want to write your own? Copy `plugins/_template.py` and fill in two things: the `PLUGIN` dict and the `run()` function.

### 💓 Affective Dialog — TOKYO Hears How You Feel
Powered by Gemini Live's native audio understanding, TOKYO now picks up the emotion in your voice — excitement, frustration, fatigue — and adapts its own tone in response. Late-night tired questions get calm answers; excited announcements get energy back.

### 🤫 Proactive Audio — Knows When You're Not Talking to It
The biggest quality-of-life upgrade for an always-listening assistant: TOKYO can now tell when speech isn't addressed to it. Talking to someone in the room, taking a phone call, TV in the background — it stays silent instead of interjecting. No wake word needed, no accidental replies.

### ♾️ Unlimited Session Length — The Conversation Never Dies
Sliding-window context compression means the Live session no longer terminates when the context window fills up. Combined with session resumption, TOKYO holds one continuous conversation for hours without losing the thread.

All three Live API upgrades degrade gracefully: if the preview API ever rejects them, TOKYO automatically reconnects with the standard configuration — users never see a crash.

---

## 🗺️ Roadmap

| Build | Focus |
|---|---|
| **XLVIII** | Instant interrupt · parallel news · two-phase briefing · exponential backoff · vision cooldown |
| **XLIX** | Auto-start · clipboard intelligence · assistant customization |
| **L** | Session memory · background monitoring · proactive 2.0 · instant vision · parallel news search |
| **LI** | Plugin system · affective dialog · proactive audio · unlimited sessions |
| **LII+** | Plugin files: email · quiz mode · calorie counter · calendar · and more |

---

## ⚡ Quick Start

```bash
git clone https://github.com/KarnailSingh87/tokyo.git
cd tokyo
pip install -r requirements.txt
python main.py
```

> ⚠️ **Installation Note:** Some OS-specific dependencies are not bundled in `requirements.txt` to keep the repo lightweight. If you hit a `ModuleNotFoundError`, install the missing package with `pip install <module_name>`.

---

## 📋 Requirements

| Requirement | Details |
| --- | --- |
| **OS** | Windows 10/11, macOS, or Linux |
| **Python** | 3.11 or 3.12 |
| **Microphone** | Required for voice interaction |
| **API Key** | Free Gemini API key (`config/api_keys.json`) |

---

## 🗂️ Project Structure

```
tokyo/
├── main.py                   # Core loop — Gemini Live session, audio I/O, tool dispatch
├── ui.py                     # PyQt6 HUD — waveform, log panel, plugin manager, camera feed
├── setup.py                  # First-run configuration wizard
├── plugins/
│   └── _template.py          # Copy this to write a new plugin — one file, drop in, done
├── actions/
│   ├── web_search.py         # Gemini + DDG parallel search (news, research, price, compare)
│   ├── screen_processor.py   # Screen capture & webcam vision via Gemini Live
│   ├── background_monitor.py # User-configured topic watching — daily DDG check, no crypto
│   ├── proactive.py          # Proactive 2.0 — time/context/rotation-aware check-ins
│   ├── reminder.py           # OS-native scheduled notifications
│   ├── system_monitor.py     # CPU / RAM / GPU / temperature telemetry
│   ├── computer_settings.py  # Volume, brightness, WiFi, power
│   ├── computer_control.py   # Keyboard shortcuts, mouse, window management
│   ├── open_app.py           # Application launcher
│   ├── browser_control.py    # Web browser control
│   ├── file_controller.py    # File system operations
│   ├── file_processor.py     # Document reading and summarization
│   ├── send_message.py       # Messaging integration
│   ├── weather_report.py     # Live weather data
│   ├── flight_finder.py      # Flight search
│   ├── youtube_video.py      # YouTube playback control
│   ├── game_updater.py       # Game update management (Steam / Epic)
│   ├── code_helper.py        # Code review and generation
│   ├── dev_agent.py          # Developer task agent
│   └── desktop.py            # Desktop and taskbar control
├── memory/
│   ├── memory_manager.py     # Load/save long_term.json — sessions, monitors, identity
│   └── long_term.json        # Persistent store: identity, preferences, projects, sessions, monitors
├── core/
│   ├── prompt.txt            # Assistant personality and tool-routing rules
│   └── plugin_loader.py      # Plugin engine — discovery, validation, crash isolation
└── config/
    └── api_keys.json         # API key, OS setting, assistant name, user name
```

---

## ⚠️ License

Personal and non-commercial use only.
Licensed under **[Creative Commons BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/)**.
