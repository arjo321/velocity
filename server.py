""" Velocity backend - yt-dlp powered download server. """
import http.cookiejar
import json
import logging
import os
import platform
import queue
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from uuid import uuid4

import yt_dlp
from flask import Flask, Response, jsonify, request, send_from_directory
from flask_cors import CORS

logging.getLogger("werkzeug").setLevel(logging.ERROR)
app = Flask(__name__)
app.logger.disabled = True
CORS(app)

def resource_path(relative: str) -> Path:
    base = Path(sys._MEIPASS) if hasattr(sys, "_MEIPASS") else Path(__file__).parent
    return base / relative

HTML_FILE = "youtube-downloader.html"
CONFIG_DIR = Path.home() / ".velocity"
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
SETTINGS_FILE = CONFIG_DIR / "settings.json"
HISTORY_FILE = CONFIG_DIR / "history.json"
COOKIES_FILE = CONFIG_DIR / "cookies.txt"

# --- Hardcoded Cookies ---
RAW_COOKIES = "VISITOR_INFO1_LIVE=5tu8QQG8-BA; SID=EAjiV3znEQszubjsRHOY0kaQghYXdMkpwIEglA_Zr0IdqcrfDfEOdB9GldJ96NH-bR9O9A.; __Secure-1PSID=EAjiV3znEQszubjsRHOY0kaQghYXdMkpwIEglA_Zr0IdqcrfU2JnUEJKyI-4RVhaxbe4Yg.; __Secure-3PSID=EAjiV3znEQszubjsRHOY0kaQghYXdMkpwIEglA_Zr0Idqcrf0YrvllRYcHqngNs-jT0Vmw.; HSID=Ajxm0H5wNF1IkkyZ_; SSID=AjZiOtolvFvhTQUX5; APISID=eldjCushWvww7udN/AM7sNr0PuR-L5x3hD; SAPISID=CM9PFYgoOCUklKJz/ARQctM0VN6GdkSbGL; __Secure-1PAPISID=CM9PFYgoOCUklKJz/ARQctM0VN6GdkSbGL; __Secure-3PAPISID=CM9PFYgoOCUklKJz/ARQctM0VN6GdkSbGL; YSC=5n0ANQ117EA; LOGIN_INFO=AFmmF2swRQIhAOvnag4nukpr2M-BwhTc-FFHAVf3OIz4z7unRCdBIbJFAiANTrZ8vw5eHxk2GhgcV3z2kubMTA0kL7P5sczDkdrawQ:QUQ3MjNmd2x0dW9jb0FRbGpVNUNNZFpXeGNSZWp4VngtWTdGazVYR2diY0Q1WkhNX1UycHd0T2NIUFg1S0psN3E3WnM1c25zZGRsME0zYlJ2UTBzdlV2b1praGpsYU9PNm5wWmNIem5uNXN3X3JjaWNQbkIzR0JwUkVwQUZ6MDlYLTBnME9lZ2M3MWFZeWFlNjJnOHlYcnZzZ1g0b2dfSUFR; PREF=tz=Asia.Calcutta&f6=40000000; CONSISTENCY=AGDxDeNTO0pHnOA-RuF2jtttgxtEADlsJA6X3Bv0j93yPzzwvXYc4fYstsRzXoKw3lec3IEhI39iBCOvuBSTCP5SuNwujxzLgkT_irJkLkCU0bez3zfdgU4zKZAiV6K40xiR6IoolcVfl-y6F1nXd9Zp; SIDCC=AJi4QfERQqPMSFpCxE0LBSO1-9sFsNqgQvwZTp3iH7pkiR3toomFa8KKV9WHivENXW6GdDgW; __Secure-3PSIDCC=AJi4QfFRbB-UGnrZ71Ex-OlxoAF9MA9mBPEfCx2iq6z4owWIBnEqudUtV2qQq5ZsIQIASUekwQ"

def write_hardcoded_cookies():
    jar = http.cookiejar.MozillaCookieJar(str(COOKIES_FILE))
    for pair in RAW_COOKIES.split(';'):
        if not pair.strip() or '=' not in pair: continue
        name, value = pair.strip().split('=', 1)
        cookie = http.cookiejar.Cookie(
            version=0, name=name, value=value, port=None, port_specified=False,
            domain='.youtube.com', domain_specified=True, domain_initial_dot=True,
            path='/', path_specified=True, secure=True, expires=int(time.time()) + 31536000,
            discard=False, comment=None, comment_url=None, rest={}
        )
        jar.set_cookie(cookie)
    jar.save(ignore_discard=True, ignore_expires=True)

# Generate the cookies file immediately
write_hardcoded_cookies()

DEFAULT_SETTINGS = {
    "download_dir": str(Path.home() / "Downloads" / "Velocity"),
    "default_format": "mp4-1080",
    "video_codec": "h264",
    "audio_bitrate": "320",
    "concurrent_fragments": 16,
    "use_aria2c": True,
    "speed_limit_kbps": 0,
    "embed_thumbnail": True,
    "download_subtitles": False,
    "subtitle_lang": "en",
    "notify_on_complete": True,
}

def load_settings():
    if SETTINGS_FILE.exists():
        try:
            data = json.loads(SETTINGS_FILE.read_text())
            return {**DEFAULT_SETTINGS, **data}
        except Exception: pass
    return dict(DEFAULT_SETTINGS)

def save_settings(settings):
    SETTINGS_FILE.write_text(json.dumps(settings, indent=2))

SETTINGS = load_settings()

def get_download_dir() -> Path:
    d = Path(SETTINGS["download_dir"])
    d.mkdir(parents=True, exist_ok=True)
    return d

def load_history():
    if HISTORY_FILE.exists():
        try:
            return json.loads(HISTORY_FILE.read_text())
        except Exception: pass
    return []

def save_history():
    HISTORY_FILE.write_text(json.dumps(HISTORY, indent=2))

HISTORY = load_history()

def add_history_entry(entry):
    HISTORY.insert(0, entry)
    del HISTORY[200:]
    save_history()

JOBS: dict[str, dict] = {}

@app.get("/")
def index():
    return send_from_directory(resource_path("."), HTML_FILE)

def find_ffmpeg_dir():
    exe_name = "ffmpeg.exe" if platform.system() == "Windows" else "ffmpeg"
    bundled = resource_path("ffmpeg_bin")
    if (bundled / exe_name).exists():
        return str(bundled)
    return None

FFMPEG_DIR = find_ffmpeg_dir()
FFMPEG_EXE = str(Path(FFMPEG_DIR) / ("ffmpeg.exe" if platform.system() == "Windows" else "ffmpeg")) if FFMPEG_DIR else "ffmpeg"
FFPROBE_EXE = str(Path(FFMPEG_DIR) / ("ffprobe.exe" if platform.system() == "Windows" else "ffprobe")) if FFMPEG_DIR else "ffprobe"
HAS_FFMPEG = bool(FFMPEG_DIR) or bool(shutil.which("ffmpeg"))

def base_opts():
    opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "concurrent_fragment_downloads": int(SETTINGS.get("concurrent_fragments", 16)),
        "retries": 5,
        "fragment_retries": 5,
        "cookiefile": str(COOKIES_FILE) # Hardcoded injection happens here
    }
    
    if FFMPEG_DIR:
        opts["ffmpeg_location"] = FFMPEG_DIR
        
    if SETTINGS.get("use_aria2c", True) and shutil.which("aria2c"):
        n = str(int(SETTINGS.get("concurrent_fragments", 16)))
        opts["external_downloader"] = "aria2c"
        opts["external_downloader_args"] = ["-x", n, "-s", n, "-k", "1M"]
        
    limit = int(SETTINGS.get("speed_limit_kbps", 0) or 0)
    if limit > 0:
        opts["ratelimit"] = limit * 1024
    return opts

CODEC_FILTERS = {
    "h264": "vcodec^=avc1",
    "h265": "vcodec~='^(hev1|hvc1)'",
    "vp9":  "vcodec~='^vp0?9'",
    "av1":  "vcodec^=av01",
    "any":  None,
}

def format_string(choice: str, codec: str = "h264") -> str:
    if choice == "mp3":
        return "bestaudio/best"
    height = "[height<=1080]" if choice == "mp4-1080" else ""
    vfilter = CODEC_FILTERS.get(codec)
    if vfilter:
        primary = f"bestvideo[{vfilter}]{height}+bestaudio[ext=m4a]/bestvideo[{vfilter}]{height}+bestaudio/best[{vfilter}]{height}"
    else:
        primary = f"bestvideo{height}+bestaudio/best{height}"
    return f"{primary}/best{height}"

def ensure_h264(filepath: str, codec: str):
    if codec != "h264" or not HAS_FFMPEG:
        return filepath
    probe = subprocess.run(
        [FFPROBE_EXE, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=codec_name", "-of", "csv=p=0", filepath],
        capture_output=True, text=True,
    )
    codec_found = probe.stdout.strip()
    if codec_found in ("h264", ""):
        return filepath
    fixed = str(Path(filepath).with_suffix("")) + ".h264.mp4"
    subprocess.run(
        [FFMPEG_EXE, "-y", "-i", filepath, "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-c:a", "copy", fixed],
        capture_output=True,
    )
    os.remove(filepath)
    return fixed

def open_in_file_manager(path: Path):
    system = platform.system()
    try:
        if system == "Windows": os.startfile(path)
        elif system == "Darwin": subprocess.run(["open", str(path)])
        else: subprocess.run(["xdg-open", str(path)])
        return True
    except Exception:
        return False

@app.get("/api/health")
def health():
    return jsonify({"ok": True, "ffmpeg": HAS_FFMPEG})

@app.post("/api/info")
def info():
    url = (request.json or {}).get("url", "").strip()
    if not url: return jsonify({"error": "Missing url"}), 400
    try:
        with yt_dlp.YoutubeDL({**base_opts(), "skip_download": True}) as ydl:
            data = ydl.extract_info(url, download=False)
        mins, secs = divmod(int(data.get("duration") or 0), 60)
        return jsonify({
            "title": data.get("title", "Untitled"),
            "thumbnail": data.get("thumbnail"),
            "duration": f"{mins}:{secs:02d}",
            "uploader": data.get("uploader", ""),
            "view_count": data.get("view_count"),
            "extractor": data.get("extractor_key"),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.post("/api/preview")
def preview():
    url = (request.json or {}).get("url", "").strip()
    if not url: return jsonify({"error": "Missing url"}), 400
    try:
        opts = {**base_opts(), "skip_download": True, "format": "worst[ext=mp4][vcodec^=avc1]/worst[ext=mp4]/worst"}
        with yt_dlp.YoutubeDL(opts) as ydl:
            data = ydl.extract_info(url, download=False)
        preview_url = data.get("url")
        if not preview_url and data.get("requested_formats"):
            preview_url = data["requested_formats"][0].get("url")
        if not preview_url: return jsonify({"error": "No previewable stream found"}), 400
        return jsonify({"preview_url": preview_url, "note": f"{data.get('format_note') or ''} {data.get('height') or ''}p".strip()})
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.post("/api/download")
def download():
    body = request.json or {}
    url = body.get("url", "").strip()
    fmt_choice = body.get("format", SETTINGS.get("default_format", "mp4-1080"))
    codec = body.get("codec", SETTINGS.get("video_codec", "h264"))
    
    if not url: return jsonify({"error": "Missing url"}), 400
    if not HAS_FFMPEG: return jsonify({"error": "ffmpeg not found"}), 400
    
    job_id = uuid4().hex
    JOBS[job_id] = {"q": queue.Queue(), "filepath": None, "done": False}
    threading.Thread(target=_run_download, args=(job_id, url, fmt_choice, codec), daemon=True).start()
    return jsonify({"job_id": job_id})

def _run_download(job_id, url, fmt_choice, codec):
    q = JOBS[job_id]["q"]
    def hook(d):
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            done = d.get("downloaded_bytes", 0)
            pct = (done / total * 100) if total else 0
            q.put({"status": "downloading", "pct": round(pct, 1), "speed": d.get("speed") or 0, "eta": d.get("eta") or 0})
        elif d["status"] == "finished":
            q.put({"status": "merging"})
            
    opts = {
        **base_opts(),
        "format": format_string(fmt_choice, codec),
        "outtmpl": str(get_download_dir() / "%(title).150s.%(ext)s"),
        "progress_hooks": [hook],
    }
    
    postprocessors = []
    if fmt_choice == "mp3":
        postprocessors.append({"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": str(SETTINGS.get("audio_bitrate", "320"))})
    else:
        opts["merge_output_format"] = "mp4"
        
    if SETTINGS.get("embed_thumbnail"):
        opts["writethumbnail"] = True
        postprocessors.append({"key": "EmbedThumbnail"})
        
    if SETTINGS.get("download_subtitles") and fmt_choice != "mp3":
        opts["writesubtitles"] = True
        opts["subtitleslangs"] = [SETTINGS.get("subtitle_lang", "en")]
        postprocessors.append({"key": "FFmpegEmbedSubtitle"})
        
    if postprocessors:
        opts["postprocessors"] = postprocessors
        
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info_dict = ydl.extract_info(url, download=True)
            filepath = ydl.prepare_filename(info_dict)
            if fmt_choice == "mp3":
                filepath = str(Path(filepath).with_suffix(".mp3"))
            else:
                filepath = str(Path(filepath).with_suffix(".mp4"))
                filepath = ensure_h264(filepath, codec)
                
        JOBS[job_id]["filepath"] = filepath
        JOBS[job_id]["done"] = True
        size = Path(filepath).stat().st_size if Path(filepath).exists() else 0
        add_history_entry({
            "id": job_id, "title": info_dict.get("title", Path(filepath).stem), "format": fmt_choice,
            "codec": codec, "filepath": filepath, "filename": Path(filepath).name,
            "thumbnail": info_dict.get("thumbnail"), "size": size, "timestamp": time.time(),
            "source": info_dict.get("extractor_key")
        })
        q.put({"status": "finished", "filename": Path(filepath).name, "title": info_dict.get("title", "")})
    except Exception as e:
        JOBS[job_id]["done"] = True
        q.put({"status": "error", "message": str(e)})

@app.get("/api/progress/<job_id>")
def progress(job_id):
    if job_id not in JOBS: return jsonify({"error": "unknown job"}), 404
    def stream():
        q = JOBS[job_id]["q"]
        while True:
            item = q.get()
            yield f"data: {json.dumps(item)}\n\n"
            if item["status"] in ("finished", "error"): break
    return Response(stream(), mimetype="text/event-stream")

@app.get("/api/file/<job_id>")
def get_file(job_id):
    job = JOBS.get(job_id)
    if not job or not job["filepath"]: return jsonify({"error": "not ready"}), 404
    path = Path(job["filepath"])
    return send_from_directory(path.parent, path.name, as_attachment=True)

@app.get("/api/history")
def get_history():
    return jsonify({"items": HISTORY})

@app.post("/api/history/clear")
def clear_history():
    HISTORY.clear()
    save_history()
    return jsonify({"ok": True})

@app.post("/api/history/open/<entry_id>")
def open_history_item(entry_id):
    entry = next((h for h in HISTORY if h["id"] == entry_id), None)
    if not entry: return jsonify({"error": "not found"}), 404
    path = Path(entry["filepath"])
    return jsonify({"ok": open_in_file_manager(path if path.exists() else path.parent)})

@app.get("/api/settings")
def get_settings():
    return jsonify({
        "settings": SETTINGS,
        "ffmpeg": HAS_FFMPEG,
        "aria2c": bool(shutil.which("aria2c")),
    })

@app.post("/api/settings")
def update_settings():
    body = request.json or {}
    for key in set(DEFAULT_SETTINGS.keys()):
        if key in body: SETTINGS[key] = body[key]
    if "download_dir" in body:
        try: Path(SETTINGS["download_dir"]).mkdir(parents=True, exist_ok=True)
        except Exception as e: return jsonify({"error": f"Can't use that folder: {e}"}), 400
    try:
        SETTINGS["concurrent_fragments"] = max(1, min(32, int(SETTINGS.get("concurrent_fragments", 16))))
        SETTINGS["speed_limit_kbps"] = max(0, int(SETTINGS.get("speed_limit_kbps", 0) or 0))
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid number"}), 400
    save_settings(SETTINGS)
    return jsonify({"ok": True, "settings": SETTINGS})

@app.post("/api/open-downloads")
def open_downloads():
    return jsonify({"ok": open_in_file_manager(get_download_dir())})

if __name__ == "__main__":
    print(f"Cookie source: Hardcoded injection")
    print(f"Saving files to: {get_download_dir()}")
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True, use_reloader=False)
