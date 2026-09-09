# 🍅 Pomodoro Spotify

A cool-looking study/work dashboard: a Pomodoro-style timer, real Spotify
integration with lyrics, a task manager with subtasks and time tracking,
and a notes tool — all on one page — plus a dashboard/calendar to see what
you got done.

> **Status:** V1 built and working locally (Flask + SQLite, all 20 tests
> passing). You still need to fill in your own Spotify Client ID/Secret in
> `.env` to connect a real account — see section 6. A few small spec items
> in section 7 are still open/default.

---

## 1. Concept

A single page split into a **2x2 grid**:

```
┌───────────────────────┬───────────────────────┐
│   SPOTIFY / LYRICS     │    POMODORO TIMER      │
│  album art, track,     │  presets, countdown,   │
│  lyrics (or music      │  work/break cycle      │
│  icon if no lyrics)    │                         │
├───────────────────────┼───────────────────────┤
│      DASHBOARD          │    TASK MANAGER         │
│  completed tasks,       │  add task + time,       │
│  time spent, date,      │  Start button per        │
│  calendar view          │  task, subtasks,         │
│                          │  status                  │
└───────────────────────┴───────────────────────┘
```

- **Top-left — Spotify panel:** Spotify logo, currently playing track's
  album art, title/artist, playback controls, and lyrics for the current
  track. If no lyrics are found, show the track's music/album icon instead.
- **Top-right — Pomodoro timer:** preset table (5 / 25 / 50 min) plus a
  custom time input, countdown display, start/pause/reset, auto-cycling
  work/break sessions.
- **Bottom-right — Task manager:** add tasks (with an estimated time),
  each task has a **Start** button that begins tracking time on it and
  moves it to "In Progress"; tasks can have **subtasks**; status is
  Not Started / In Progress / Done.
- **Bottom-left — Dashboard:** overview of completed tasks, time spent,
  and a **calendar** — pick a date to see the tasks logged/due that day.
- **Floating "Take Notes" button** (not tied to a grid cell — floats over
  the page, accessible from anywhere): opens a full-screen notes overlay
  with a text editor and a Save button on the right, and a sidebar on the
  **left** listing your previously saved note files — click one to open it.

Goal: make it feel like a polished, modern study-with-me / focus app —
dark, glassy, minimal, satisfying to look at — not a bare HTML form.

---

## 2. Core Features

### Pomodoro timer (top-right)

- [ ] Preset table: **5 min / 25 min / 50 min** buttons (pick one to start)
- [ ] Custom duration input (user types/sets any minutes)
- [ ] Countdown display (large, central, animated progress ring or bar)
- [ ] Start / Pause / Reset controls
- [ ] **Auto-cycle** between Work and Break (classic Pomodoro flow): after a
      work session ends, automatically start a break; long break every 4
      cycles
- [ ] Sound/notification when a session ends
- [ ] Optionally link a running timer session to whichever task is
      currently "In Progress" in the task manager

### Spotify integration (top-left)

- [x] "Connect Spotify" button → real OAuth login with your Spotify account
- [x] Spotify logo/icon displayed
- [x] Shows currently playing track: album art, title, artist
- [x] **In-browser playback control** via Spotify Web Playback SDK (play /
      pause / skip directly on the site) — uses your **Premium** account
- [x] **Karaoke-style synced lyrics** via lrclib.net: the current line is
      highlighted and auto-scrolled in sync with real playback position
      (falls back to plain, unsynced lyrics text if a track only has those)
- [x] **Fallback:** if a track has no lyrics at all, show its album art
      large instead of an empty panel
- [x] Auto-refreshes as tracks change
- [x] **Playlist browser:** browse your own Spotify playlists, pick one to
      see its songs, click a song to play it, Back button returns to the
      playlist list — all within the same panel (no page navigation).
      Falls back to Spotify's own embedded player widget if Spotify's API
      blocks track listing for a specific playlist (common for algorithmic
      ones like Discover Weekly, regardless of permissions granted)
- [x] **Playback timeline:** a progress bar under the track info showing
      elapsed/total time — click or drag anywhere on it to seek forward or
      backward in the song. Clicking a lyric line seeks there too

### Task manager (bottom-right)

- [ ] Add a task: title + an associated/estimated time
- [ ] **Start** button per task → begins timing that task, status becomes
      "In Progress"
- [ ] Status per task/subtask: **Not Started / In Progress / Done**
      (updates automatically — Not Started until you hit Start, In Progress
      while timing, Done when you mark it complete)
- [ ] **Subtasks:** a task can have any number of subtasks, each with its
      own Start button and independent timer
- [ ] Parent task's total time = sum of its subtasks' logged time (plus any
      time logged directly on the parent)
- [ ] Assign a date to a task (so it shows up on the dashboard calendar)
- [ ] Mark task/subtask as Done

### Dashboard (bottom-left)

- [ ] Summary of completed tasks (count, total time spent)
- [ ] **Calendar view** — click/pick a date → see tasks logged or due that
      day
- [ ] Per-day and per-task time breakdown

### Notes (floating button)

- [ ] Floating **"Take Notes"** button, always accessible on the page
- [ ] Clicking it opens a full-screen overlay: left sidebar = list of
      previously saved notes (filenames/titles), right side = text editor
      block
- [ ] Write freely, then **Save** → stored as a **Markdown (.md)** file
- [ ] Click a note in the left sidebar to open/edit it; new notes get their
      own file
- [ ] Close overlay to return to the main dashboard

### Look & feel

- [ ] Dark, modern, "cool" aesthetic (Spotify-green accent + dark background)
- [ ] Smooth animations/transitions (timer ring, panel fades, hover states)
- [ ] Fully responsive (works on desktop + mobile) — 2x2 grid collapses to
      a stacked single column on small screens

---

## 3. Tech Stack

| Layer | Choice |
|---|---|
| Backend | **Python + Flask** (handles Spotify OAuth + API calls, serves the app, task/time REST endpoints) |
| Frontend | Plain HTML/CSS/JS, served directly by Flask (Jinja templates) |
| Database | **SQLite** (free, zero setup, single local file — via Flask-SQLAlchemy) |
| Spotify access | Spotify Web API via OAuth 2.0 (Authorization Code Flow) + **Web Playback SDK** (Premium, in-browser playback) |
| Lyrics | [lrclib.net](https://lrclib.net) (free, no API key) |
| Hosting/repo | GitHub — public repo `pomodoro-spotify` |

### Why Flask + SQLite

Flask is lightweight and simple to wire up for Spotify's OAuth redirect
flow and API proxying. SQLite needs no server or account, ships with
Python, and is stored as a single file (`pomodoro.db`) — ideal for a
single-user local app like this. If we ever deploy this beyond local use,
swapping SQLite for Postgres later is a small change since we're going
through SQLAlchemy.

---

## 4. Data Model (proposed)

```
Task
├── id
├── title
├── status         (not_started | in_progress | done)
├── estimated_minutes
├── logged_seconds        # accumulates as timer runs
├── date                   # assigned date, shown on dashboard calendar
├── parent_task_id         # null if top-level task, set if this is a subtask
├── created_at
└── completed_at

TimerSession               # one row per Start→Stop/Pause run, for history
├── id
├── task_id                # nullable — Pomodoro sessions may be unlinked to a task
├── started_at
├── ended_at
├── duration_seconds
└── kind                    # pomodoro_work | pomodoro_break | task_tracking

Note
├── id
├── title                  # derived from filename or first line
├── filename                # e.g. notes/2026-09-10-meeting.md
├── created_at
└── updated_at
```

---

## 5. Project Structure (proposed)

```
pomodoro-spotify/
├── README.md
├── .gitignore
├── .env.example              # Spotify client id/secret placeholders (never commit real .env)
├── requirements.txt
├── app.py                    # Flask entry point
├── config.py                 # App config, env loading
├── models.py                  # SQLAlchemy models: Task, TimerSession
├── pomodoro.db                # SQLite database file (gitignored, created on first run)
├── spotify/
│   ├── __init__.py
│   ├── auth.py                # OAuth login/callback/token refresh
│   └── client.py               # Wrapper around Spotify Web API calls
├── lyrics/
│   ├── __init__.py
│   └── lrclib_client.py        # Wrapper around lrclib.net lookups
├── tasks/
│   ├── __init__.py
│   └── routes.py                # REST endpoints: create/start/stop/complete task, subtasks
├── notes/
│   ├── __init__.py
│   ├── routes.py                 # REST endpoints: list/create/read/save notes
│   └── files/                     # saved note .md files live here (gitignored)
├── static/
│   ├── css/
│   │   └── style.css
│   ├── js/
│   │   ├── timer.js             # Pomodoro logic (presets, custom, auto-cycle work/break)
│   │   ├── spotify-panel.js     # Top-left panel: now playing, lyrics, controls
│   │   ├── spotify-player.js    # Web Playback SDK setup (in-browser playback)
│   │   ├── tasks.js              # Bottom-right: add/start/complete tasks + subtasks
│   │   ├── dashboard.js          # Bottom-left: stats + calendar view
│   │   └── notes.js               # Floating button + notes overlay (list, edit, save)
│   └── img/
│       └── spotify-logo.svg
├── templates/
│   └── index.html               # Main single page (2x2 grid layout)
└── tests/
    └── ...
```

---

## 6. Spotify API Setup (you'll need to do this)

1. Go to the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard).
2. Create an app → get a **Client ID** and **Client Secret**.
3. Add a Redirect URI (e.g. `http://127.0.0.1:5000/callback` for local dev).
4. Note: your Spotify account needs an active device (the Spotify app open
   somewhere) for playback control to work — the Web API controls existing
   playback, it doesn't play audio itself in the browser unless we add the
   Web Playback SDK (Premium-only feature — see open questions).

---

## 7. ❓ Open Questions (please answer / edit this section directly)

Decided already: 2x2 layout (Spotify+lyrics / Timer / Dashboard+calendar /
Task manager), auto-cycling Pomodoro work/break flow, Spotify Premium
in-browser playback via the Web Playback SDK, lyrics via lrclib.net (with
music-icon fallback if no lyrics found), plain HTML/CSS/JS frontend served
by Flask, SQLite database, tasks with subtasks and independent timers
(parent sums children's time), Not Started/In Progress/Done statuses, and a
floating "Take Notes" button opening a Markdown note editor with a
saved-notes sidebar on the left.

Remaining small items — defaults noted, edit this file or tell me to change
them:

1. **Notifications:** Sound + browser notification when a Pomodoro session
   ends. *(Default: yes to both — say if you want only one, or neither.)*
2. **Accounts/persistence:** Single-user personal use, no login system
   besides Spotify OAuth itself. *(Default: yes, single user — say if you
   want multi-user support.)*
3. **Theme:** Dark mode only (Spotify-green accent on near-black
   background). *(Default: dark only — say if you want a light toggle
   too.)*
4. **Deployment:** Local use only for now (`python app.py` on
   `localhost`). *(Default: local only — say if you want it deployed
   somewhere like Render/Railway later.)*
5. **License:** MIT. *(Default — say if you want a different license or
   none at all.)*
6. **Timer ↔ Task link:** Should starting a Pomodoro work session require
   picking a task to attach it to, or are Pomodoro sessions and task timers
   fully separate (you can run a Pomodoro without any task selected)?
   *(Default: separate/optional link — a Pomodoro can run standalone, or
   you can optionally attach it to whatever task is "In Progress.")*

---

## 8. Getting Started

```bash
git clone https://github.com/<your-username>/pomodoro-spotify.git
cd pomodoro-spotify
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env   # then fill in your real Spotify Client ID/Secret
python app.py
```

Then open <http://127.0.0.1:5000>. The SQLite database and notes folder are
created automatically on first run.

Run the test suite with:

```bash
pytest
```

---

## License

MIT (default — see open questions above if you'd prefer something else).
