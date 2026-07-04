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
        
        # 1. Clean up any old files
        for file in glob.glob("video.*"):
            os.remove(file)
            
        # 2. Add the disguise!
        ydl_opts = {
            'format': 'b[ext=mp4]/b', 
            'outtmpl': 'video.%(ext)s',
            # This line tricks YouTube by pretending we are an embedded blog player
            'extractor_args': {'youtube': ['player_client=web_embedded']} 
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
            
        # 3. Find the file and send it back
        downloaded_file = glob.glob("video.*")[0]
        return send_file(downloaded_file, as_attachment=True)
        
    except Exception as e:
        return str(e), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
