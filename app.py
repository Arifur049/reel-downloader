from flask import Flask, request, send_file
import yt_dlp
import os
import glob
import subprocess
import sys

app = Flask(__name__)

# Track whether we've already tried updating yt-dlp since this instance woke up
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

@app.route('/ping', methods=['GET'])
def ping():
    return "Awake!"

@app.route('/update', methods=['GET'])
def force_update():
    """Manually trigger a yt-dlp update check without restarting the server."""
    global _updated_this_boot
    _updated_this_boot = False
    update_yt_dlp()
    return f"yt-dlp version: {yt_dlp.version.__version__}"

@app.route('/download', methods=['POST'])
def download_video():
    try:
        update_yt_dlp()

        url = request.json.get('url')
        if not url:
            return "No URL provided", 400

        # 1. Clean up any old files
        for file in glob.glob("video.*"):
            os.remove(file)

        # 2. Build download options
        ydl_opts = {
            'format': 'b[ext=mp4]/b',
            'outtmpl': 'video.%(ext)s',
            'extractor_args': {
                'youtube': {
                    'player_client': ['android', 'web_embedded', 'ios']
                }
            },
            'noplaylist': True,
            'quiet': True,
            'no_warnings': True,
        }

        # 3. Use cookies if present (export via "Get cookies.txt LOCALLY" extension)
        cookie_path = os.path.join(os.path.dirname(__file__), 'cookies.txt')
        if os.path.exists(cookie_path):
            ydl_opts['cookiefile'] = cookie_path

        # 4. Download
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        # 5. Find the file and send it back
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
