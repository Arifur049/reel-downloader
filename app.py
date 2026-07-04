from flask import Flask, request, send_file
import yt_dlp
import os
import glob
import shutil
import subprocess
import sys

app = Flask(__name__)

_updated_this_boot = False
WRITABLE_COOKIE_PATH = "/tmp/cookies.txt"
APP_DIR = os.path.dirname(os.path.abspath(__file__))
DENO_PATH = os.path.join(APP_DIR, ".deno", "bin", "deno")

FORMAT_SELECTOR = (
    "bestvideo[height<=1080][vcodec^=avc1][filesize<49M]+bestaudio[acodec^=mp4a]/"
    "bestvideo[height<=1080][filesize<49M]+bestaudio/"
    "bestvideo[height<=1080][vcodec^=avc1][filesize_approx<49M]+bestaudio[acodec^=mp4a]/"
    "bestvideo[height<=1080][filesize_approx<49M]+bestaudio/"
    "bestvideo[height<=720][vcodec^=avc1]+bestaudio[acodec^=mp4a]/"
    "bestvideo[height<=720]+bestaudio/"
    "bestvideo[height<=480][vcodec^=avc1]+bestaudio[acodec^=mp4a]/"
    "bestvideo[height<=480]+bestaudio/"
    "bestvideo[height<=360][vcodec^=avc1]+bestaudio[acodec^=mp4a]/"
    "bestvideo[height<=360]+bestaudio/"
    "best[height<=1080][filesize<49M]/"
    "best[height<=720]/"
    "best[height<=480]/"
    "best[height<=360]"
)

def js_runtime_opts():
    """Tells yt-dlp where Deno lives and allows it to fetch its JS
    challenge-solving script from GitHub (disabled by default)."""
    opts = {'remote_components': ['ejs:github']}
    if os.path.exists(DENO_PATH):
        opts['js_runtimes'] = {'deno': {'path': DENO_PATH}}
    else:
        opts['js_runtimes'] = {'deno': {}}  # fall back to PATH lookup
    return opts

def update_yt_dlp():
    global _updated_this_boot
    if _updated_this_boot:
        return
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--upgrade", "yt-dlp"],
            check=True, timeout=30
        )
        print("yt-dlp update check completed.")
    except Exception as e:
        print(f"yt-dlp update check failed: {e}")
    finally:
        _updated_this_boot = True

def get_writable_cookie_file():
    source_candidates = [
        "/etc/secrets/cookies.txt",
        os.path.join(APP_DIR, "cookies.txt"),
    ]
    source_path = next((p for p in source_candidates if os.path.exists(p)), None)
    if not source_path:
        return None
    try:
        shutil.copyfile(source_path, WRITABLE_COOKIE_PATH)
        return WRITABLE_COOKIE_PATH
    except Exception as e:
        print(f"Failed to copy cookies to writable path: {e}")
        return None

@app.route('/ping', methods=['GET'])
def ping():
    return "Awake!"

@app.route('/update', methods=['GET'])
def force_update():
    global _updated_this_boot
    _updated_this_boot = False
    update_yt_dlp()
    return f"yt-dlp version: {yt_dlp.version.__version__}"

@app.route('/debug-jsruntime', methods=['GET'])
def debug_jsruntime():
    info = {'expected_deno_path': DENO_PATH, 'deno_exists_at_path': os.path.exists(DENO_PATH)}
    try:
        result = subprocess.run([DENO_PATH, "--version"], capture_output=True, text=True, timeout=10)
        info['deno_version_output'] = result.stdout.strip()
    except Exception as e:
        info['deno_check_error'] = str(e)
    return info

@app.route('/debug-ffmpeg', methods=['GET'])
def debug_ffmpeg():
    try:
        result = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, timeout=10)
        return {"ffmpeg_found": True, "version_line": result.stdout.splitlines()[0] if result.stdout else None}
    except FileNotFoundError:
        return {"ffmpeg_found": False}, 500
    except Exception as e:
        return {"error": str(e)}, 500

@app.route('/debug-cookies', methods=['GET'])
def debug_cookies():
    info = {'yt_dlp_version': yt_dlp.version.__version__}
    cookie_path = get_writable_cookie_file()
    info['cookie_path_used'] = cookie_path
    if cookie_path:
        try:
            info['cookie_file_size_bytes'] = os.path.getsize(cookie_path)
        except Exception as e:
            info['error_reading_file'] = str(e)
    return info

@app.route('/debug-formats', methods=['POST'])
def debug_formats():
    try:
        url = request.json.get('url')
        if not url:
            return "No URL provided", 400

        ydl_opts = {
            'extractor_args': {'youtube': {'player_client': ['android', 'web', 'mweb']}},
            'quiet': True,
            'no_warnings': True,
        }
        ydl_opts.update(js_runtime_opts())

        cookie_path = get_writable_cookie_file()
        if cookie_path:
            ydl_opts['cookiefile'] = cookie_path

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        formats = [{
            'format_id': f.get('format_id'), 'ext': f.get('ext'), 'height': f.get('height'),
            'vcodec': f.get('vcodec'), 'acodec': f.get('acodec'),
            'filesize': f.get('filesize'), 'filesize_approx': f.get('filesize_approx'),
        } for f in info.get('formats', [])]

        return {'title': info.get('title'), 'formats': formats}
    except Exception as e:
        return f"Error: {str(e)}", 500

@app.route('/download', methods=['POST'])
def download_video():
    try:
        update_yt_dlp()

        url = request.json.get('url')
        if not url:
            return "No URL provided", 400

        for file in glob.glob("video.*"):
            os.remove(file)

        ydl_opts = {
            'format': FORMAT_SELECTOR,
            'merge_output_format': 'mp4',
            'outtmpl': 'video.%(ext)s',
            'extractor_args': {'youtube': {'player_client': ['android', 'web', 'mweb']}},
            'noplaylist': True,
            'quiet': False,
            'no_warnings': False,
        }
        ydl_opts.update(js_runtime_opts())

        cookie_path = get_writable_cookie_file()
        if cookie_path:
            ydl_opts['cookiefile'] = cookie_path

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        downloaded_file = "video.mp4" if os.path.exists("video.mp4") else None
        if not downloaded_file:
            remaining = glob.glob("video.*")
            if not remaining:
                return "Download completed but no file was found", 500
            downloaded_file = remaining[0]

        return send_file(downloaded_file, as_attachment=True)

    except yt_dlp.utils.DownloadError as e:
        return f"yt-dlp download error: {str(e)}", 500
    except Exception as e:
        return f"Server error: {str(e)}", 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
