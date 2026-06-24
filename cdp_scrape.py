"""CDP scraper - 增量抓取版本"""
import json
import websocket
import urllib.request
import time
import hashlib
import logging
from pathlib import Path
from datetime import datetime, timezone, timedelta

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

JST = timezone(timedelta(hours=9))
CDP = "http://127.0.0.1:9223"
CONFIG_FILE = Path(__file__).parent / "config.json"


def load_config():
    """加载配置文件"""
    if not CONFIG_FILE.exists():
        logger.error(f"配置文件不存在: {CONFIG_FILE}")
        return None
    try:
        config = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        logger.info(f"已加载配置: {len(config.get('accounts', []))} 个账号")
        return config
    except json.JSONDecodeError as e:
        logger.error(f"配置文件格式错误: {e}")
        return None


def load_existing_posts(data_file):
    """加载现有帖子数据"""
    if not data_file.exists():
        return []
    try:
        posts = json.loads(data_file.read_text(encoding="utf-8"))
        logger.info(f"已加载 {len(posts)} 条现有帖子")
        return posts
    except json.JSONDecodeError as e:
        logger.error(f"帖子数据文件格式错误: {e}")
        return []


def get_existing_ids(posts):
    """获取现有帖子ID集合"""
    return {p.get("id") for p in posts if p.get("id")}


def get_existing_filenames(posts):
    """获取现有图片文件名集合"""
    filenames = set()
    for p in posts:
        for img in p.get("images", []):
            filenames.add(img.get("filename", ""))
    return filenames


def connect_cdp():
    """连接到 Chrome CDP"""
    try:
        pages = json.loads(urllib.request.urlopen(f"{CDP}/json").read())
    except Exception as e:
        logger.error(f"无法连接到 Chrome CDP ({CDP}): {e}")
        return None, None

    ws_url = None
    for p in pages:
        if "x.com" in p.get("url", ""):
            ws_url = p["webSocketDebuggerUrl"]
            logger.info(f"找到 X 页面: {p.get('title', '?')}")
            break

    if not ws_url:
        logger.error("未找到 X 页面 - 请先在 Chrome 中打开 X")
        return None, None

    try:
        ws = websocket.create_connection(ws_url, timeout=10)
        ws.settimeout(10)
        return ws, ws_url
    except Exception as e:
        logger.error(f"WebSocket 连接失败: {e}")
        return None, None


def cdp_send(ws, method, params=None):
    """发送 CDP 命令"""
    msg_id = int(time.time() * 1000) % 1000000
    ws.send(json.dumps({"id": msg_id, "method": method, "params": params or {}}))
    for _ in range(50):
        try:
            m = json.loads(ws.recv())
            if m.get("id") == msg_id:
                if m.get("error"):
                    logger.warning(f"CDP 错误: {m['error'].get('message', '')}")
                return m.get("result", {})
        except Exception as e:
            logger.error(f"接收 CDP 响应失败: {e}")
            return {}
    return {}


def scrape_account(ws, account_id, account_name, scroll_times=3):
    """抓取单个账号的媒体图片"""
    url = f"https://x.com/{account_id}/media"
    logger.info(f"开始抓取: {account_name} (@{account_id})")

    cdp_send(ws, "Runtime.enable")
    cdp_send(ws, "Page.navigate", {"url": url})
    time.sleep(5)

    # 滚动加载更多内容
    for i in range(scroll_times):
        cdp_send(ws, "Input.dispatchKeyEvent", {
            "type": "rawKeyDown",
            "windowsVirtualKeyCode": 34,
            "key": "PageDown"
        })
        cdp_send(ws, "Input.dispatchKeyEvent", {
            "type": "keyUp",
            "windowsVirtualKeyCode": 34,
            "key": "PageDown"
        })
        time.sleep(0.5)

    # 提取媒体图片
    js_imgs = (
        "JSON.stringify(Array.from(document.querySelectorAll('img'))"
        ".map(i=>i.src)"
        ".filter(s=>s&&s.includes('pbs.twimg.com/media'))"
        ".map(s=>s.replace(/&name=\\w+/,'&name=orig')))"
    )
    r = cdp_send(ws, "Runtime.evaluate", {"expression": js_imgs, "returnByValue": True})
    img_urls = json.loads(r.get("result", {}).get("value", "[]"))
    img_urls = list(set(img_urls))
    logger.info(f"发现 {len(img_urls)} 张唯一媒体图片")

    # 提取推文信息（包含每条推文的图片URL）
    js_tweets = (
        "JSON.stringify(Array.from(document.querySelectorAll('article'))"
        ".map(a=>{"
        "  const l=a.querySelector('a[href*=\"/status/\"]');"
        "  if(!l)return null;"
        "  const m=l.href.match(/\\/status\\/(\\d+)/);"
        "  if(!m)return null;"
        "  const t=a.querySelector('time');"
        "  const x=a.querySelector('[data-testid=\"tweetText\"]');"
        "  const imgs=Array.from(a.querySelectorAll('img'))"
        "    .map(i=>i.src)"
        "    .filter(s=>s&&s.includes('pbs.twimg.com/media'))"
        "    .map(s=>s.replace(/&name=\\w+/,'&name=orig'));"
        "  return{id:m[1],time:t?t.getAttribute('datetime'):'',text:x?x.innerText:'',images:imgs}"
        "}).filter(Boolean))"
    )
    r2 = cdp_send(ws, "Runtime.evaluate", {"expression": js_tweets, "returnByValue": True})
    tweets = json.loads(r2.get("result", {}).get("value", "[]"))
    logger.info(f"识别到 {len(tweets)} 条推文")

    return img_urls, tweets


def download_images(img_urls, img_dir, existing_filenames):
    """下载图片，返回新下载的文件名列表和URL到文件名的映射"""
    url_to_filename = {}
    new_filenames = []
    for url in img_urls:
        h = hashlib.md5(url.encode()).hexdigest()[:12]
        fname = f"Hina_Youmiya_{h}.jpg"
        url_to_filename[url] = fname

        if fname in existing_filenames:
            continue

        dest = img_dir / fname
        if dest.exists():
            new_filenames.append(fname)
            continue

        try:
            urllib.request.urlretrieve(url, str(dest))
            new_filenames.append(fname)
            logger.info(f"下载成功: {fname}")
        except Exception as e:
            logger.error(f"下载失败 {url}: {e}")

    return new_filenames, url_to_filename


def main():
    # 加载配置
    config = load_config()
    if not config:
        return

    img_dir = Path(__file__).parent / config.get("image_dir", "data/images")
    data_file = Path(__file__).parent / config.get("data_file", "data/posts.json")
    scroll_times = config.get("scroll_times", 3)

    img_dir.mkdir(parents=True, exist_ok=True)

    # 加载现有数据
    existing_posts = load_existing_posts(data_file)
    existing_ids = get_existing_ids(existing_posts)
    existing_filenames = get_existing_filenames(existing_posts)

    # 连接 CDP
    ws, ws_url = connect_cdp()
    if not ws:
        return

    try:
        all_new_posts = []
        all_new_filenames = []  # 跟踪所有账号下载的图片

        # 遍历所有账号
        for account in config.get("accounts", []):
            account_id = account.get("account_id")
            account_name = account.get("name", account_id)

            if not account_id:
                logger.warning("跳过无效账号配置")
                continue

            # 抓取（tweets 现在包含每条推文的图片URL）
            img_urls, tweets = scrape_account(ws, account_id, account_name, scroll_times)

            # 下载新图片，获取URL到文件名的映射
            new_filenames, url_to_filename = download_images(img_urls, img_dir, existing_filenames)
            existing_filenames.update(new_filenames)
            all_new_filenames.extend(new_filenames)

            # 为每条推文创建帖子（关联对应图片）
            for tw in tweets:
                if tw["id"] in existing_ids:
                    continue

                post = {
                    "id": tw["id"],
                    "url": f"https://x.com/{account_id}/status/{tw['id']}",
                    "account_id": account_id,
                    "account_name": account_name,
                    "text": tw.get("text", ""),
                    "time": tw.get("time") or datetime.now(JST).isoformat(),
                    "images": [
                        {"filename": url_to_filename[url], "original_url": url}
                        for url in tw.get("images", [])
                        if url in url_to_filename
                    ],
                    "scraped_at": datetime.now(JST).isoformat(),
                }
                all_new_posts.append(post)
                existing_ids.add(tw["id"])

        # 合并新旧数据
        if all_new_posts:
            all_posts = all_new_posts + existing_posts
            all_posts.sort(key=lambda p: p.get("time", ""), reverse=True)

            # 保存
            data_file.write_text(
                json.dumps(all_posts, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
            logger.info(f"已保存 {len(all_posts)} 条帖子（新增 {len(all_new_posts)} 条）")
        else:
            logger.info("没有新帖子需要保存")

        logger.info(f"完成！下载 {len(all_new_filenames)} 张新图片")

    except Exception as e:
        logger.error(f"抓取过程中出错: {e}")
    finally:
        ws.close()


if __name__ == "__main__":
    main()
