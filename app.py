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

def update_yt_dlp():
    global _updated_this_boot
    if _updated_this_boot:
        return
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--upgrade", "yt-dlp"],
            check=True,
            timeout=30
        )
        print("yt-dlp update check completed.")
    except Exception as e:
        print(f"yt-dlp update check failed: {e}")
    finally:
        _updated_this_boot = True

def get_writable_cookie_file():
    """Copies the read-only Secret File cookies.txt to /tmp so yt-dlp
    can freely rewrite it during a session. Refreshes the copy from the
    source each call so we always start from the latest secret."""
    source_candidates = [
        "/etc/secrets/cookies.txt",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "cookies.txt"),
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

@app.route('/debug-cookies', methods=['GET'])
def debug_cookies():
    info = {}
    info['yt_dlp_version'] = yt_dlp.version.__version__
    cookie_path = get_writable_cookie_file()
    info['cookie_path_used'] = cookie_path

    if cookie_path:
        try:
            info['cookie_file_size_bytes'] = os.path.getsize(cookie_path)
            with open(cookie_path, 'r', errors='ignore') as f:
                info['first_lines_preview'] = [next(f) for _ in range(3)]
        except Exception as e:
            info['error_reading_file'] = str(e)

    return info

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
            'format': 'b[ext=mp4]/b',
            'outtmpl': 'video.%(ext)s',
            'extractor_args': {
                'youtube': {
                    'player_client': ['android', 'web', 'mweb']
                }
            },
            'noplaylist': True,
            'quiet': False,
            'no_warnings': False,
        }

        cookie_path = get_writable_cookie_file()
        if cookie_path:
            ydl_opts['cookiefile'] = cookie_path
        else:
            print("No cookies.txt found — expect bot-check failures on this IP.")

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        downloaded_files = glob.glob("video.*")
        if not downloaded_files:
            return "Download completed but no file was found", 500

        downloaded_file = downloaded_files[0]
        return send_file(downloaded_file, as_attachment=True)

    except yt_dlp.utils.DownloadError as e:
        return f"yt-dlp download error: {str(e)}", 500

    except Exception as e:
        return f"Server error: {str(e)}", 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
