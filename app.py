from flask import Flask, request, send_file
import yt_dlp

app = Flask(__name__)

@app.route('/ping', methods=['GET'])
def ping():
    return "Awake!"

@app.route('/download', methods=['POST'])
def download_video():
    url = request.json.get('url')
    
    # Settings to get a good quality mp4
    ydl_opts = {
        'format': 'best[ext=mp4]/best', 
        'outtmpl': 'video.mp4'
    }
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])
        
    return send_file('video.mp4', as_attachment=True)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
