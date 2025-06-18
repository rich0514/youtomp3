import os
import uuid
import re
import yt_dlp
from flask import Flask, request, render_template, send_file, flash, redirect, url_for, after_this_request
import logging
from threading import Timer

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", str(uuid.uuid4()))

# 临时下载目录
DOWNLOAD_DIR = os.path.join(os.getcwd(), "downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

def download_video(url: str, resolution: str) -> str:
    """下載 MP4 (720p 或 1080p)，返回文件路径"""
    # resolution: '1080' 或 '720'
    max_h = int(resolution)
    outtmpl = os.path.join(DOWNLOAD_DIR, "%(id)s.%(ext)s")
    opts = {
        "format": f"bestvideo[height<={max_h}]+bestaudio/best",
        "outtmpl": outtmpl,
        "merge_output_format": "mp4",
    }
    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        # yt-dlp by default may name .mkv, ensure .mp4
        if not filename.endswith(".mp4"):
            filename = os.path.splitext(filename)[0] + ".mp4"
    return filename

def download_audio(url: str, bitrate: str) -> str:
    """下載 MP3 (192,256,320 kbps)，返回文件路径"""
    uid = str(uuid.uuid4())
    outtmpl = os.path.join(DOWNLOAD_DIR, f"{uid}.%(ext)s")
    opts = {
        "format": "bestaudio/best",
        "outtmpl": outtmpl,
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": bitrate,
        }],
    }
    with YoutubeDL(opts) as ydl:
        ydl.extract_info(url, download=True)
    return os.path.join(DOWNLOAD_DIR, f"{uid}.mp3")

def sanitize_filename(title):
    # 移除不合法字元
    return re.sub(r'[\\/:*?"<>|]', '', title)

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        url = request.form.get("url", "").strip()
        mode = request.form.get("mode")
        quality = request.form.get("quality")
        if not url:
            flash("請輸入 YouTube 連結或影片 ID", "danger")
            return redirect(url_for("index"))
        if not mode:
            flash("請選擇下載格式", "danger")
            return redirect(url_for("index"))
        if not quality:
            flash("請選擇畫質或音質", "danger")
            return redirect(url_for("index"))

        try:
            if mode == "mp4":
                filepath = download_video(url, quality)
            elif mode == "mp3":
                filepath = download_audio(url, quality)
            else:
                flash("未知的下載格式", "danger")
                return redirect(url_for("index"))

            @after_this_request
            def remove_file(response):
                try:
                    os.remove(filepath)
                except Exception:
                    pass
                return response

            return send_file(filepath, as_attachment=True)
        except Exception as e:
            flash(f"下載失敗：{e}", "danger")
            return redirect(url_for("index"))

    return render_template("index.html")

@app.route('/download', methods=['POST'])
def download():
    print("收到 /download 請求")
    url = request.form['url']
    format_type = request.form['format']
    try:
        if format_type == 'mp3':
            quality = request.form.get('quality_mp3', '192')
            output_ext = 'mp3'
            ydl_format = 'bestaudio/best'
            ydl_opts = {
                'format': ydl_format,
                'outtmpl': 'downloads/%(title)s.%(ext)s',
                'noplaylist': True,
                'quiet': True,
                'no_warnings': True,
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': quality,
                }],
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                title = info.get('title', 'download')
                safe_title = sanitize_filename(title)
                filename = f"downloads/{safe_title}.{output_ext}"
                orig_filename = ydl.prepare_filename(info)
                if output_ext == 'mp3':
                    orig_filename = os.path.splitext(orig_filename)[0] + '.mp3'
                if orig_filename != filename and os.path.exists(orig_filename):
                    os.rename(orig_filename, filename)
                logging.info(f"檔案產生於: {filename}")
                if not os.path.exists(filename):
                    logging.error(f"檔案未產生: {filename}")
                    flash("檔案下載失敗，請檢查網址或格式。")
                    return redirect(url_for('index'))
        else:
            quality = request.form.get('quality_mp4', '720')
            output_ext = 'mp4'
            # 強制選擇 mp4 格式的影片和音訊，避免 Windows 內建播放器不支援的編碼
            ydl_format = f"bestvideo[ext=mp4][height<={quality}]+bestaudio[ext=m4a]/best[ext=mp4][height<={quality}]"
            ydl_opts = {
                'format': ydl_format,
                'outtmpl': 'downloads/%(title)s.%(ext)s',
                'noplaylist': True,
                'quiet': False,
                'no_warnings': False,
                'merge_output_format': 'mp4',
            }
            print(f"yt-dlp 參數: {ydl_opts}")
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                print(f"實際下載格式: {info.get('requested_formats', info.get('format'))}")
                title = info.get('title', 'download')
                safe_title = sanitize_filename(title)
                filename = f"downloads/{safe_title}.{output_ext}"
                orig_filename = ydl.prepare_filename(info)
                orig_filename = os.path.splitext(orig_filename)[0] + '.mp4'
                if orig_filename != filename and os.path.exists(orig_filename):
                    os.rename(orig_filename, filename)
                logging.info(f"檔案產生於: {filename}")
                if not os.path.exists(filename):
                    logging.error(f"檔案未產生: {filename}")
                    flash("檔案下載失敗，請檢查網址或格式。")
                    return redirect(url_for('index'))

        def delayed_remove(path):
            import time
            time.sleep(3)
            try:
                os.remove(path)
                logging.info(f"已刪除暫存檔案: {path}")
            except Exception as e:
                logging.error(f"Error removing file: {e}")

        response = send_file(filename, as_attachment=True, download_name=f"{safe_title}.{output_ext}")
        Timer(3, delayed_remove, args=(filename,)).start()
        return response
    except Exception as e:
        logging.error(f"下載失敗：{e}")
        flash(f"下載失敗：{e}")
        return redirect(url_for('index'))

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=True, host="0.0.0.0", port=port)
