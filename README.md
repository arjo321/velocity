# Velocity

A desktop video/audio downloader built on [yt-dlp](https://github.com/yt-dlp/yt-dlp), with a custom tactical dark UI, a Flask backend, and a native window (via `pywebview`) — no browser tab, no terminal, just an app.

Supports YouTube and anything else yt-dlp supports (TikTok, Instagram, X/Twitter, Vimeo, Reddit, SoundCloud, etc.) — the extractor is chosen automatically from the URL.

---

## Features

- **Highest-quality downloads** in your choice of codec — H.264, H.265, VP9, AV1, or "any/best available"
- **MP4 video or MP3 audio**, with a low-quality inline preview before you commit to a full download
- **Fast** — concurrent fragment downloads, optional `aria2c` acceleration, optional speed cap
- **Download history** and **settings** persisted to disk, survive restarts
- **Native desktop window** — real OS minimize/maximize/close, no browser chrome, no console window
- **Custom tactical themed UI** — every dropdown, toggle, and control is hand-built (no native `<select>` popups breaking the theme)

---

## Interface Screenshots

### 1. Main Dashboard
This is the primary interface where you paste links. It features the signature tactical dark theme, pulsating gradient effects, and instant clipboard pasting.

![Main Dashboard](image_1.png)

### 2. Active Download & Progress
When a download is active, Velocity displays a video preview, format selection chips (1080p, 4K, MP3), and a detailed progress card with a glowing linear gradient track, speed readout, and ETA.

![Active Download & Progress](image_2.png)

---

## Files

| File | Purpose |
|---|---|
| `youtube-downloader.html` | The entire frontend — UI, styles, and JS in one file |
| `server.py` | Flask backend — talks to yt-dlp, serves the API the frontend calls. Also handles the hardcoded cookie injection. |
| `desktop.py` | Launches the native window (via `pywebview`) and starts the backend in the background — **this is what you run** |
| `requirements.txt` | Python dependencies |

## Requirements

- Python 3.9+
- [ffmpeg](https://ffmpeg.org/) on your `PATH` (needed to merge video/audio and export MP3)
  - Windows: Drop a static `ffmpeg`/`ffprobe` build into a folder named `ffmpeg_bin` next to `desktop.py`
  - macOS: `brew install ffmpeg`
  - Linux: `sudo apt install ffmpeg` (or your distro's equivalent)

## Setup

```bash
pip install -r requirements.txt
```

On Linux, `pywebview` also needs a system webview backend:
```bash
sudo apt install python3-gi gir1.2-webkit2-4.1
```

## Running

```bash
python desktop.py
```

This starts the Flask backend quietly in the background and opens the app in a native window. Files are saved to `~/Downloads/Velocity` by default (changeable in Settings).

> Running `python server.py` directly instead just starts the backend on `http://127.0.0.1:5000` without the native window — useful for debugging the API, but `desktop.py` is the normal way to run the app.

## Packaging as a standalone .exe

This project uses PyInstaller and Inno Setup for packaging on Windows.

**1. Build the Executable:**
Run the provided spec file to bundle the backend, frontend, and your `ffmpeg_bin` directory into a single binary without a console window.
```bash
pyinstaller Velocity.spec
```
The finished app lands in `dist/Velocity/`.

**2. Create the Setup Wizard:**
Open `installer.iss` with [Inno Setup](https://jrsoftware.org/isinfo.php) and compile it. It will grab the files from your `dist/` folder and generate a highly compressed `Velocity_Setup.exe` in the `\Installer` folder.

## Cookies (for age-restricted / login-required videos)

Unlike standard downloaders that require manual cookie file imports or live browser database extraction, this specific build utilizes a **Hardcoded Injection Protocol**.

Inside `server.py`, a robust session string (`RAW_COOKIES`) is hardcoded. When the server starts, it automatically writes this to a secure `cookies.txt` file in your `~/.velocity/` directory and injects it into yt-dlp. This guarantees reliable access to age-restricted or login-required media without locking up your active browser databases or throwing "could not copy cookie database" errors.

*(Note: If the session expires, just update the `RAW_COOKIES` variable in `server.py` with a fresh session string).*

## Settings reference

| Section | Setting | Notes |
|---|---|---|
| General | Download folder | Where finished files are saved |
| Quality & codec | Default quality, video codec, MP3 bitrate | Codec picker also appears per-download |
| Performance | Concurrent connections, speed limit, aria2c | aria2c is used automatically if installed |
| Extras | Embed thumbnail, subtitles, notify on complete | |

Settings and history live in `~/.velocity/` as plain JSON (`settings.json`, `history.json`) — delete that folder to reset the app.

## Troubleshooting

- **"FFMPEG MISSING"** — Make sure `ffmpeg.exe` and `ffprobe.exe` are inside a folder named `ffmpeg_bin` in the root directory, or installed on your system PATH.
- **Downloads are slow** — Install [aria2c](https://aria2.github.io/) and turn it on in Settings → Performance.
- **A specific codec isn't available** — If a codec like H.264 isn't available natively at your chosen resolution, Velocity will automatically instruct FFmpeg to re-encode the file post-download.

## Credits

Built on [yt-dlp](https://github.com/yt-dlp/yt-dlp) and [ffmpeg](https://ffmpeg.org/). Desktop shell via [pywebview](https://pywebview.flowrent.com/).
