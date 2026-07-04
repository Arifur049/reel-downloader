from flask import Flask, request, send_file
import yt_dlp
import os
import glob
import subprocess
import sys

app = Flask(__name__)

_updated_this_boot = False

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

def find_cookie_file():
    candidates = [
        "/etc/secrets/cookies.txt",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "cookies.txt"),
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
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
    """Diagnostic: confirms whether a cookie file exists and looks valid,
    without doing a full download."""
    info = {}
    info['yt_dlp_version'] = yt_dlp.version.__version__

    cookie_path = find_cookie_file()
    info['cookie_path_found'] = cookie_path

    if cookie_path:
        try:
            size = os.path.getsize(cookie_path)
            info['cookie_file_size_bytes'] = size
            with open(cookie_path, 'r', errors='ignore') as f:
                first_lines = [next(f) for _ in range(3)]
            info['first_lines_preview'] = first_lines
            # A real Netscape cookies.txt starts with this header
            info['looks_like_netscape_format'] = any(
                'Netscape' in line or line.startswith('.youtube.com') or line.startswith('# HTTP')
                for line in first_lines
            )
        except Exception as e:
            info['error_reading_file'] = str(e)
    else:
        info['checked_paths'] = [
            "/etc/secrets/cookies.txt",
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "cookies.txt"),
        ]

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
            'quiet': False,   # temporarily verbose for debugging
            'no_warnings': False,
        }

        cookie_path = find_cookie_file()
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
