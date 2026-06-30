"""通过 X GraphQL API 直接抓取媒体数据（在浏览器内执行）"""
import json
import urllib.request
import urllib.parse
import sys
import time
import hashlib
import websocket
from pathlib import Path
from datetime import datetime, timezone, timedelta
from data_store import load_posts, save_posts, get_existing_filenames, merge_posts

sys.stdout.reconfigure(encoding="utf-8")

CDP = "http://127.0.0.1:9223"
SCREEN_NAME = "Hina_Youmiya"
JST = timezone(timedelta(hours=9))
IMGDIR = Path(__file__).parent / "data" / "images"
DATAFILE = Path(__file__).parent / "data" / "posts.json"
CONFIG = json.loads((Path(__file__).parent / "config.json").read_text(encoding="utf-8"))
BEARER = CONFIG.get("x_bearer_token", "")

# 浏览器内执行的 JS：调用 X API 获取媒体数据
FETCH_MEDIA_JS = """
(async function(){
  const vars = JSON.stringify({USER_ID_PLACEHOLDER});
  const feats = JSON.stringify({FEATURES_PLACEHOLDER});
  const url = '/i/api/graphql/QUERY_ID_PLACEHOLDER/UserMedia?variables=' + encodeURIComponent(vars) + '&features=' + encodeURIComponent(feats);
  const ct0 = document.cookie.match(/ct0=([^;]+)/)?.[1] || '';
  const r = await fetch(url, {
    credentials: 'include',
    headers: {
      'x-csrf-token': ct0,
      'x-twitter-auth-type': 'OAuth2Session',
      'x-twitter-active-user': 'yes',
      'authorization': 'Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs=1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA'
    }
  });
  return await r.text();
})()
"""


def get_browser_ws():
    """获取浏览器 WebSocket URL"""
    pages = json.loads(urllib.request.urlopen(f"{CDP}/json").read())
    x_pages = [p for p in pages if "x.com" in p.get("url", "") and p["type"] == "page"]
    if not x_pages:
        return None
    return x_pages[-1]["webSocketDebuggerUrl"]


def cdp_eval(ws, expr, timeout=30):
    """在浏览器中执行 JS 并返回结果"""
    msg_id = int(time.time() * 1000) % 1000000
    ws.send(json.dumps({
        "id": msg_id,
        "method": "Runtime.evaluate",
        "params": {"expression": expr, "awaitPromise": True, "returnByValue": True}
    }))
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            ws.settimeout(max(1, deadline - time.time()))
            m = json.loads(ws.recv())
            if m.get("id") == msg_id:
                return m.get("result", {}).get("result", {}).get("value", "")
        except Exception:
            break
    return None


def find_endpoint_id(ws):
    """从 JS bundle 中找到 UserMedia 的 queryId"""
    expr = """
    (async function(){
      const scripts = Array.from(document.querySelectorAll('script[src]')).map(s => s.src);
      for (const url of scripts) {
        try {
          const r = await fetch(url);
          const text = await r.text();
          const idx = text.indexOf('UserMedia');
          if (idx !== -1) {
            const ctx = text.substring(Math.max(0, idx-120), idx+20);
            const m = ctx.match(/queryId[\"\\']?\\s*[:=]\\s*[\"\\']([^\"\\']+)[\"\\']/);
            if (m) return m[1];
          }
        } catch(e) {}
      }
      return '';
    })()
    """
    result = cdp_eval(ws, expr, timeout=60)
    return result or ""


def find_user_id(ws, screen_name):
    """获取用户 ID"""
    expr = f"""
    (async function(){{
      const vars = JSON.stringify({{screen_name: "{screen_name}", withSafetyModeUserFields: true}});
      const feats = JSON.stringify({{hidden_profile_subscriptions_enabled:true,rweb_tipjar_consumption_enabled:true,responsive_web_graphql_exclude_directive_enabled:true,verified_phone_label_enabled:false,responsive_web_graphql_skip_user_profile_image_extensions_enabled:false,responsive_web_graphql_timeline_navigation_enabled:true}});
      const url = '/i/api/graphql/xmU6X_CKVnQ5lSrCbAmJsg/UserByScreenName?variables=' + encodeURIComponent(vars) + '&features=' + encodeURIComponent(feats);
      const ct0 = document.cookie.match(/ct0=([^;]+)/)?.[1] || '';
      const r = await fetch(url, {{
        credentials: 'include',
        headers: {{
          'x-csrf-token': ct0,
          'x-twitter-auth-type': 'OAuth2Session',
          'authorization': 'Bearer {BEARER}'
        }}
      }});
      const data = await r.json();
      return data?.data?.user?.result?.rest_id || '';
    }})()
    """
    return cdp_eval(ws, expr)


def fetch_media_page(ws, query_id, user_id, cursor=None):
    """获取一页媒体数据"""
    variables = {
        "userId": user_id,
        "count": 20,
        "includePromotedContent": False,
        "withClientEventToken": False,
        "withBirdwatchNotes": False,
        "withVoice": True,
        "withV2Timeline": True,
    }
    if cursor:
        variables["cursor"] = cursor
    
    features = {
        "rweb_tipjar_consumption_enabled": True,
        "responsive_web_graphql_exclude_directive_enabled": True,
        "verified_phone_label_enabled": False,
        "creator_subscriptions_tweet_preview_api_enabled": True,
        "responsive_web_graphql_timeline_navigation_enabled": True,
        "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
        "communities_web_enable_tweet_community_results_fetch": True,
        "c9s_tweet_anatomy_moderator_badge_enabled": True,
        "articles_preview_enabled": True,
        "responsive_web_edit_tweet_api_enabled": True,
        "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
        "view_counts_everywhere_api_enabled": True,
        "longform_notetweets_consumption_enabled": True,
        "responsive_web_twitter_article_tweet_consumption_enabled": True,
        "tweet_awards_web_tipping_enabled": True,
        "creator_subscriptions_quote_tweet_preview_enabled": False,
        "freedom_of_speech_not_reach_fetch_enabled": True,
        "standardized_nudges_misinfo": True,
        "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": True,
        "rweb_video_timestamps_enabled": True,
        "longform_notetweets_rich_text_read_enabled": True,
        "longform_notetweets_inline_media_enabled": True,
        "responsive_web_enhance_cards_enabled": False,
    }
    
    vars_str = json.dumps(variables)
    feats_str = json.dumps(features)
    
    expr = f"""
    (async function(){{
      const vars = JSON.stringify({json.dumps(variables)});
      const feats = JSON.stringify({json.dumps(features)});
      const url = '/i/api/graphql/{query_id}/UserMedia?variables=' + encodeURIComponent(vars) + '&features=' + encodeURIComponent(feats);
      const ct0 = document.cookie.match(/ct0=([^;]+)/)?.[1] || '';
      const r = await fetch(url, {{
        credentials: 'include',
        headers: {{
          'x-csrf-token': ct0,
          'x-twitter-auth-type': 'OAuth2Session',
          'x-twitter-active-user': 'yes',
          'authorization': 'Bearer {BEARER}'
        }}
      }});
      return await r.text();
    }})()
    """
    return cdp_eval(ws, expr, timeout=30)


def parse_media_response(response_text):
    """解析 API 响应，提取推文和图片"""
    data = json.loads(response_text)
    tweets = []
    cursor = None
    
    # 数据在 timeline.timeline.instructions（不是 timeline_v2）
    result = data.get("data", {}).get("user", {}).get("result", {})
    timeline = result.get("timeline_v2", result.get("timeline", {}))
    if isinstance(timeline, dict) and "timeline" in timeline:
        timeline = timeline["timeline"]
    instructions = timeline.get("instructions", []) if isinstance(timeline, dict) else []
    
    for inst in instructions:
        if inst.get("type") == "TimelineAddEntries":
            entries = inst.get("entries", [])
        elif "entries" in inst:
            entries = inst["entries"]
        else:
            continue
            
        for entry in entries:
            entry_id = entry.get("entryId", "")
            
            # 提取游标
            if "cursor-bottom" in entry_id:
                cursor = entry.get("content", {}).get("value")
                continue
            
            content = entry.get("content", {})
            entry_type = content.get("entryType", "")
            
            if entry_type == "TimelineTimelineModule":
                # VerticalGrid 模块（媒体页面的图片网格）
                items = content.get("items", [])
                for item in items:
                    item_content = item.get("item", {}).get("itemContent", {})
                    result = item_content.get("tweet_results", {}).get("result", {})
                    
                    if result.get("__typename") == "TweetWithVisibilityResults":
                        result = result.get("tweet", {})
                    
                    if result.get("__typename") == "Tweet":
                        tweet_id = result.get("rest_id", "")
                        legacy = result.get("legacy", {})
                        media_list = legacy.get("extended_entities", {}).get("media", [])
                        images = []
                        for m in media_list:
                            if m["type"] == "photo":
                                images.append(m["media_url_https"] + "?format=jpg&name=orig")
                        
                        if images:
                            tweets.append({
                                "id": tweet_id,
                                "images": images,
                                "time": legacy.get("created_at", ""),
                                "text": legacy.get("full_text", ""),
                            })
            
            elif entry_type == "TimelineTimelineItem":
                result = content.get("itemContent", {}).get("tweet_results", {}).get("result", {})
                if result.get("__typename") == "TweetWithVisibilityResults":
                    result = result.get("tweet", {})
                if result.get("__typename") == "Tweet":
                    tweet_id = result.get("rest_id", "")
                    legacy = result.get("legacy", {})
                    media_list = legacy.get("extended_entities", {}).get("media", [])
                    images = [m["media_url_https"] + "?format=jpg&name=orig" for m in media_list if m["type"] == "photo"]
                    if images:
                        tweets.append({
                            "id": tweet_id,
                            "images": images,
                            "time": legacy.get("created_at", ""),
                            "text": legacy.get("full_text", ""),
                        })
    
    # 去重
    seen = set()
    unique_tweets = []
    for t in tweets:
        if t["id"] not in seen:
            seen.add(t["id"])
            unique_tweets.append(t)
    
    return unique_tweets, cursor


def download_image(url, dest):
    """下载图片"""
    try:
        urllib.request.urlretrieve(url, str(dest))
        return True
    except Exception as e:
        print(f"  下载失败: {e}")
        return False


def main():
    IMGDIR.mkdir(parents=True, exist_ok=True)
    
    # 获取浏览器连接
    ws_url = get_browser_ws()
    if not ws_url:
        print("错误: 无法连接浏览器，请确保 Chrome 已打开 X")
        return
    
    ws = websocket.create_connection(ws_url, timeout=30)
    ws.settimeout(30)
    
    # 启用 Runtime
    ws.send(json.dumps({"id": 0, "method": "Runtime.enable", "params": {}}))
    for _ in range(50):
        m = json.loads(ws.recv())
        if m.get("id") == 0:
            break
    
    # 找到 UserMedia endpoint
    print("查找 API endpoint...")
    query_id = find_endpoint_id(ws)
    if not query_id:
        print("错误: 找不到 UserMedia endpoint")
        ws.close()
        return
    print(f"  queryId: {query_id}")
    
    # 获取用户 ID
    print(f"获取用户 ID ({SCREEN_NAME})...")
    user_id = find_user_id(ws, SCREEN_NAME)
    if not user_id:
        print("错误: 找不到用户 ID")
        ws.close()
        return
    print(f"  userId: {user_id}")
    
    # 加载现有数据
    existing_posts = load_posts(DATAFILE)
    existing_ids = {p.get("id") for p in existing_posts if p.get("id")}
    existing_filenames = get_existing_filenames(existing_posts)
    
    # 抓取媒体数据
    print("\n开始抓取媒体...")
    all_tweets = []
    cursor = None
    max_pages = 10
    
    for page_num in range(1, max_pages + 1):
        print(f"  第 {page_num} 页...")
        response_text = fetch_media_page(ws, query_id, user_id, cursor)
        if not response_text:
            print("  响应为空")
            break
        
        tweets, next_cursor = parse_media_response(response_text)
        if not tweets:
            print("  没有更多推文")
            break
        
        new_count = 0
        for t in tweets:
            if t["id"] not in existing_ids:
                all_tweets.append(t)
                existing_ids.add(t["id"])
                new_count += 1
        
        print(f"  找到 {len(tweets)} 条推文 (新增 {new_count})")
        
        if next_cursor == cursor or not next_cursor:
            break
        cursor = next_cursor
    
    if not all_tweets:
        print("\n没有新推文需要保存")
        ws.close()
        return
    
    # 下载图片并创建帖子
    print(f"\n下载图片并创建帖子...")
    new_posts = []
    total_downloaded = 0
    
    for tw in all_tweets:
        images = []
        for url in tw["images"]:
            h = hashlib.md5(url.encode()).hexdigest()[:12]
            fname = f"Hina_Youmiya_{h}.jpg"
            dest = IMGDIR / fname
            
            if fname not in existing_filenames:
                if not dest.exists():
                    if download_image(url, dest):
                        total_downloaded += 1
                existing_filenames.add(fname)
            
            images.append({"filename": fname, "original_url": url})
        
        # 解析时间
        time_str = tw.get("time", "")
        try:
            dt = datetime.strptime(time_str, "%a %b %d %H:%M:%S %z %Y")
            iso_time = dt.isoformat()
        except Exception:
            iso_time = datetime.now(JST).isoformat()
        
        post = {
            "id": tw["id"],
            "url": f"https://x.com/{SCREEN_NAME}/status/{tw['id']}",
            "account_id": SCREEN_NAME,
            "account_name": "羊宮妃那",
            "text": tw.get("text", ""),
            "time": iso_time,
            "images": images,
            "scraped_at": datetime.now(JST).isoformat(),
        }
        new_posts.append(post)
    
    # 合并保存
    all_posts = merge_posts(new_posts, existing_posts)
    save_posts(DATAFILE, all_posts)
    
    print(f"\n完成!")
    print(f"  新增帖子: {len(new_posts)}")
    print(f"  下载图片: {total_downloaded}")
    print(f"  总帖子数: {len(all_posts)}")
    
    ws.close()


if __name__ == "__main__":
    main()
