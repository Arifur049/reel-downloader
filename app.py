from flask import Flask, request, send_file
import yt_dlp
import os
import glob
import shutil
import socket
import subprocess
import sys
import time

app = Flask(__name__)

_updated_this_boot = False
WRITABLE_COOKIE_PATH = "/tmp/cookies.txt"
APP_DIR = os.path.dirname(os.path.abspath(__file__))
DENO_PATH = os.path.join(APP_DIR, ".deno", "bin", "deno")
BGUTIL_BIN = os.path.join(APP_DIR, ".bgutil", "bgutil-pot")
BGUTIL_PORT = 4416

_bgutil_process = None

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

def is_port_open(port, host="127.0.0.1"):
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False

def ensure_bgutil_running():
    """Starts the PO Token provider server once per boot, if not already up."""
    global _bgutil_process
    if is_port_open(BGUTIL_PORT):
        return True

    if not os.path.exists(BGUTIL_BIN):
        print(f"bgutil-pot binary not found at {BGUTIL_BIN}")
        return False

    try:
        _bgutil_process = subprocess.Popen(
            [BGUTIL_BIN, "server", "--host", "127.0.0.1", "--port", str(BGUTIL_PORT)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        # Give it a moment to bind the port
        for _ in range(10):
            if is_port_open(BGUTIL_PORT):
                print("bgutil-pot server started.")
                return True
            time.sleep(0.5)
        print("bgutil-pot server did not come up in time.")
        return False
    except Exception as e:
        print(f"Failed to start bgutil-pot: {e}")
        return False

# Start it once when the module loads (i.e. on boot / cold start)
ensure_bgutil_running()

def js_runtime_opts():
    opts = {'remote_components': ['ejs:github']}
    if os.path.exists(DENO_PATH):
        opts['js_runtimes'] = {'deno': {'path': DENO_PATH}}
    else:
        opts['js_runtimes'] = {'deno': {}}
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

@app.route('/debug-pot', methods=['GET'])
def debug_pot():
    running = is_port_open(BGUTIL_PORT)
    if not running:
        running = ensure_bgutil_running()
    return {
        "bgutil_binary_exists": os.path.exists(BGUTIL_BIN),
        "bgutil_server_running": running,
        "port": BGUTIL_PORT,
    }

@app.route('/debug-jsruntime', methods=['GET'])
def debug_jsruntime():
    info = {'expected_deno_path': DENO_PATH, 'deno_exists_at_path': os.path.exists(DENO_PATH)}
    try:
        result = subprocess.run([DENO_PATH, "--version"], capture_output=True, text=True, timeout=10)
        info['deno_version_output'] = result.stdout.strip()
    except Exception as e:
        info['deno_check_error'] = str(e)
    return info

@app.route('/debug-cookies', methods=['GET'])
def debug_cookies():
    info = {'yt_dlp_version': yt_dlp.version.__version__}
    cookie_path = get_writable_cookie_file()
    info['cookie_path_used'] = cookie_path
    return info

@app.route('/debug-formats', methods=['POST'])
def debug_formats():
    try:
        url = request.json.get('url')
        if not url:
            return "No URL provided", 400

        ensure_bgutil_running()

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
        ensure_bgutil_running()

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
