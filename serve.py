#!/usr/bin/env python3
"""
应援站本地服务器
- 自动扫描 data/images/ 发现新照片并更新 posts.json
- 使用文件锁防止并发写入冲突
- 缓存扫描结果，减少文件系统操作
- 支持多线程并发请求
"""
import http.server
import socketserver
import json
import hashlib
import os
import sys
import threading
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.stdout.reconfigure(line_buffering=True)

PORT = 8800
DIRECTORY = Path(__file__).parent
IMGDIR = DIRECTORY / "data" / "images"
DATAFILE = DIRECTORY / "data" / "posts.json"
JST = timezone(timedelta(hours=9))
DEFAULT_ACCOUNT_ID = "Hina_Youmiya"
DEFAULT_ACCOUNT_NAME = "羊宮妃那"

# 扫描缓存
_scan_cache = {
    "last_scan_time": 0,
    "scan_interval": 5,  # 最小扫描间隔（秒）
    "lock": threading.Lock(),
    "file_lock": threading.Lock(),  # 文件写入锁
}


def auto_scan_photos():
    """扫描 images 文件夹，将新照片自动加入 posts.json（带缓存和锁）"""
    current_time = time.time()

    # 检查缓存：如果距离上次扫描时间不足 scan_interval 秒，跳过
    with _scan_cache["lock"]:
        if current_time - _scan_cache["last_scan_time"] < _scan_cache["scan_interval"]:
            return False

    if not IMGDIR.exists() or not DATAFILE.exists():
        return False

    # 获取文件锁
    with _scan_cache["file_lock"]:
        try:
            # 读取现有数据
            posts = json.loads(DATAFILE.read_text(encoding="utf-8"))
            existing = set()
            for p in posts:
                for img in p.get("images", []):
                    existing.add(img.get("filename", ""))

            # 扫描图片
            image_exts = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
            new_files = [f for f in sorted(IMGDIR.iterdir())
                         if f.suffix.lower() in image_exts and f.name not in existing]

            if not new_files:
                # 更新扫描时间
                with _scan_cache["lock"]:
                    _scan_cache["last_scan_time"] = current_time
                return False

            now = datetime.now(JST).isoformat()
            for f in new_files:
                post_id = hashlib.md5(f.name.encode()).hexdigest()[:12]
                posts.insert(0, {
                    "id": post_id,
                    "url": "",
                    "account_id": DEFAULT_ACCOUNT_ID,
                    "account_name": DEFAULT_ACCOUNT_NAME,
                    "text": "",
                    "time": now,
                    "images": [{"filename": f.name, "original_url": ""}],
                    "scraped_at": now
                })
                print(f"[AUTO] 新照片: {f.name}")

            posts.sort(key=lambda p: p.get("time", ""), reverse=True)
            DATAFILE.write_text(json.dumps(posts, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"[AUTO] 已添加 {len(new_files)} 张新照片")

            # 更新扫描时间
            with _scan_cache["lock"]:
                _scan_cache["last_scan_time"] = current_time

            return True

        except json.JSONDecodeError as e:
            print(f"[ERROR] posts.json 格式错误: {e}")
            return False
        except Exception as e:
            print(f"[ERROR] 扫描失败: {e}")
            return False


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(DIRECTORY), **kwargs)

    def do_GET(self):
        print(f"[DEBUG] Received GET request: {self.path}")
        # 访问页面或数据文件时触发自动扫描
        if self.path in ('/', '/gallery.html', '/index.html', '/data/posts.json'):
            print(f"[DEBUG] Triggering auto_scan_photos()")
            auto_scan_photos()
        super().do_GET()

    def end_headers(self):
        # 禁止缓存 HTML 和 JSON 数据文件
        if self.path.endswith(('.html', '.json')):
            self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
            self.send_header('Pragma', 'no-cache')
            self.send_header('Expires', '0')
        super().end_headers()

    def log_message(self, format, *args):
        print(f"[{self.log_date_time_string()}] {format % args}")


class ThreadedHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    """支持多线程的 HTTP 服务器"""
    daemon_threads = True  # 守护线程，主线程退出时自动终止


print(f"Starting server...")
print(f"Directory: {DIRECTORY}")
print(f"Port: {PORT}")

try:
    with ThreadedHTTPServer(("127.0.0.1", PORT), Handler) as httpd:
        print(f"OK - Server running at http://localhost:{PORT}")
        print(f"Auto-scan: ON (put photos in data/images/, refresh browser)")
        print(f"Multi-thread: ON (supports concurrent requests)")
        httpd.serve_forever()
except OSError as e:
    print(f"ERROR: {e}")
    sys.exit(1)
except KeyboardInterrupt:
    print("\nServer stopped.")
