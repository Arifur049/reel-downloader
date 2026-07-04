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
        
        # 1. Clean up any old files from previous failed runs
        for file in glob.glob("video.*"):
            os.remove(file)
            
        # 2. 'b' forces yt-dlp to grab a pre-merged file (no ffmpeg needed)
        # It prefers mp4, but will accept whatever pre-merged format exists
        ydl_opts = {
            'format': 'b[ext=mp4]/b', 
            'outtmpl': 'video.%(ext)s'
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
            
        # 3. Find the downloaded file (whether it's .mp4, .webm, etc.)
        downloaded_file = glob.glob("video.*")[0]
        
        return send_file(downloaded_file, as_attachment=True)
        
    except Exception as e:
        # If it crashes, send the exact error text back to Google Apps Script
        return str(e), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
