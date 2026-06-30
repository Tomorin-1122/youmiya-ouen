#!/usr/bin/env python3
"""
快速添加照片到应援站
用法：
  1. 把照片放到 data/images/ 文件夹
  2. 运行 python add_photos.py
  3. 刷新网页即可看到新照片
"""
import json
import hashlib
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from data_store import load_posts, save_posts, get_existing_filenames, generate_post_id

JST = timezone(timedelta(hours=9))
IMGDIR = Path(__file__).parent / "data" / "images"
DATAFILE = Path(__file__).parent / "data" / "posts.json"
DEFAULT_ACCOUNT_ID = "Hina_Youmiya"
DEFAULT_ACCOUNT_NAME = "羊宮妃那"


def get_existing_filenames():
    """从 posts.json 中获取已记录的文件名"""
    if not DATAFILE.exists():
        return set()
    posts = json.loads(DATAFILE.read_text(encoding="utf-8"))
    filenames = set()
    for post in posts:
        for img in post.get("images", []):
            filenames.add(img.get("filename", ""))
    return filenames


def generate_id(filename):
    """用文件名生成短 ID"""
    h = hashlib.md5(filename.encode()).hexdigest()
    return h[:12]


def main():
    if not IMGDIR.exists():
        print("错误: data/images/ 目录不存在")
        return

    # 加载现有数据
    posts = load_posts(DATAFILE)

    existing = get_existing_filenames(posts)

    # 扫描图片文件
    image_exts = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
    new_files = []

    for f in sorted(IMGDIR.iterdir()):
        if f.suffix.lower() in image_exts and f.name not in existing:
            new_files.append(f)

    if not new_files:
        print("没有新照片需要添加")
        return

    print(f"发现 {len(new_files)} 张新照片:")

    # 添加新照片
    now = datetime.now(JST).isoformat()
    for f in new_files:
        post_id = generate_post_id(f.name)
        post = {
            "id": post_id,
            "url": "",
            "account_id": DEFAULT_ACCOUNT_ID,
            "account_name": DEFAULT_ACCOUNT_NAME,
            "text": "",
            "time": now,
            "images": [
                {
                    "filename": f.name,
                    "original_url": ""
                }
            ],
            "scraped_at": now
        }
        posts.insert(0, post)
        print(f"  + {f.name}")

    # 按时间排序并保存
    posts.sort(key=lambda p: p.get("time", ""), reverse=True)
    save_posts(DATAFILE, posts)

    total = len(posts)
    total_imgs = sum(len(p.get("images", [])) for p in posts)
    print(f"\n完成! 共 {total} 条投稿 / {total_imgs} 张照片")
    print("刷新网页即可看到新照片")


if __name__ == "__main__":
    main()
