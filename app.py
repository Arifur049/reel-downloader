from flask import Flask, request, send_file
import yt_dlp
import os
import glob

app = Flask(__name__)

@app.route('/ping', methods=['GET'])
def ping():
    return "Awake!"

@app.route('/download', methods=['POST'])
def download_video():
    try:
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
                # Try android and ios clients first (less likely to trigger
                # bot-check), fall back to web_embedded
                'youtube': {
                    'player_client': ['android', 'web_embedded', 'ios']
                }
            },
            'noplaylist': True,
            'quiet': True,
            'no_warnings': True,
        }

        # 3. Use cookies if a cookies.txt file exists in the project root
        #    (export this from your browser using "Get cookies.txt LOCALLY"
        #    while logged into a throwaway/secondary Google account)
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
        # Common case: bot-check / cookies expired
        return f"yt-dlp download error: {str(e)}", 500

    except Exception as e:
        return f"Server error: {str(e)}", 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
