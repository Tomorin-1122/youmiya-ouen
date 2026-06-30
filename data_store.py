"""
共享数据层 — 所有脚本通过此模块读写 posts.json
提供原子写入、一致的错误处理、公共数据操作
"""
import json
import hashlib
import os
from pathlib import Path


def load_posts(data_file):
    """读取 posts.json，文件不存在或解析失败返回空列表"""
    data_file = Path(data_file)
    if not data_file.exists():
        return []
    try:
        return json.loads(data_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        print(f"[WARN] 读取 {data_file.name} 失败: {e}")
        return []


def save_posts(data_file, posts):
    """原子写入 posts.json（先写临时文件，再 os.replace）"""
    data_file = Path(data_file)
    tmp = data_file.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(posts, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(str(tmp), str(data_file))


def get_existing_filenames(posts):
    """从帖子列表中提取所有已引用的图片文件名"""
    filenames = set()
    for p in posts:
        for img in p.get("images", []):
            fn = img.get("filename", "")
            if fn:
                filenames.add(fn)
    return filenames


def generate_post_id(filename):
    """根据文件名生成稳定的帖子 ID"""
    return hashlib.md5(filename.encode()).hexdigest()[:12]


def merge_posts(new_posts, existing_posts):
    """合并新旧帖子并按时间降序排序"""
    all_posts = new_posts + existing_posts
    all_posts.sort(key=lambda p: p.get("time", ""), reverse=True)
    return all_posts
