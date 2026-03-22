import os
import json
import requests
from datetime import datetime, timezone, timedelta

X_BEARER_TOKEN       = os.environ["X_BEARER_TOKEN"]
THREADS_ACCESS_TOKEN = os.environ["THREADS_ACCESS_TOKEN"]
GH_PAT               = os.environ["GH_PAT"]
GH_REPO              = "younoki01/x-benchmark"

JST = timezone(timedelta(hours=9))

# X スコア基準
X_HIGH    = 0.01   # 1%以上
X_MEDIUM  = 0.003  # 0.3%以上

# Threads スコア基準
TH_HIGH   = 0.03   # 3%以上
TH_MEDIUM = 0.01   # 1%以上

def load_from_github(filepath: str) -> dict:
    url = f"https://api.github.com/repos/{GH_REPO}/contents/{filepath}"
    headers = {"Authorization": f"Bearer {GH_PAT}"}
    r = requests.get(url, headers=headers)
    if r.status_code != 200:
        return {}
    import base64
    content = base64.b64decode(r.json()["content"]).decode()
    return json.loads(content)

def save_to_github(filepath: str, content: dict, message: str):
    url = f"https://api.github.com/repos/{GH_REPO}/contents/{filepath}"
    headers = {
        "Authorization": f"Bearer {GH_PAT}",
        "Content-Type": "application/json",
    }
    r = requests.get(url, headers=headers)
    sha = r.json().get("sha") if r.status_code == 200 else None

    import base64
    encoded = base64.b64encode(json.dumps(content, ensure_ascii=False, indent=2).encode()).decode()

    payload = {"message": message, "content": encoded}
    if sha:
        payload["sha"] = sha

    r = requests.put(url, headers=headers, json=payload)
    print(f"GitHub save: {r.status_code} {filepath}")

def get_x_metrics(tweet_id: str) -> dict:
    url = f"https://api.twitter.com/2/tweets/{tweet_id}"
    headers = {"Authorization": f"Bearer {X_BEARER_TOKEN}"}
    params = {"tweet.fields": "public_metrics"}
    r = requests.get(url, headers=headers, params=params)
    if r.status_code != 200:
        print(f"X metrics error: {r.status_code}")
        return {}
    metrics = r.json().get("data", {}).get("public_metrics", {})
    return metrics

def get_threads_metrics(post_id: str) -> dict:
    url = f"https://graph.threads.net/v1.0/{post_id}/insights"
    params = {
        "metric": "views,likes,replies,reposts,quotes",
        "access_token": THREADS_ACCESS_TOKEN,
    }
    r = requests.get(url, params=params)
    if r.status_code != 200:
        print(f"Threads metrics error: {r.status_code}")
        return {}
    metrics = {}
    for item in r.json().get("data", []):
        name = item.get("name")
        value = item.get("values", [{}])[0].get("value", 0)
        metrics[name] = value
    return metrics

def calc_score(platform: str, metrics: dict) -> str:
    if platform == "x":
        impressions = metrics.get("impression_count", 0)
        likes = metrics.get("like_count", 0)
        if impressions == 0:
            return "unknown"
        rate = likes / impressions
        if rate >= X_HIGH:
            return "high"
        elif rate >= X_MEDIUM:
            return "medium"
        else:
            return "low"
    elif platform == "threads":
        views = metrics.get("views", 0)
        likes = metrics.get("likes", 0)
        if views == 0:
            return "unknown"
        rate = likes / views
        if rate >= TH_HIGH:
            return "high"
        elif rate >= TH_MEDIUM:
            return "medium"
        else:
            return "low"
    return "unknown"

def main():
    print("▶ エンゲージメント収集 起動")

    posted_log = load_from_github("data/posted_log.json")
    posts = posted_log.get("posts", [])
    print(f"  投稿ログ: {len(posts)}件")

    feedback = load_from_github("data/feedback.json")
    if "posted" not in feedback:
        feedback["posted"] = []

    existing_ids = {f["post_id"] for f in feedback.get("posted", [])}
    added = 0

    for post in posts:
        post_id   = post.get("post_id")
        platform  = post.get("platform")
        posted_at = post.get("posted_at", "")

        if post_id in existing_ids:
            continue

        print(f"  収集中: {platform} {post_id}")

        if platform == "x":
            metrics = get_x_metrics(post_id)
        elif platform == "threads":
            metrics = get_threads_metrics(post_id)
        else:
            continue

        score = calc_score(platform, metrics)
        print(f"    metrics: {metrics} → score: {score}")

        feedback["posted"].append({
            "text":       post.get("text", ""),
            "platform":   platform,
            "post_id":    post_id,
            "posted_at":  posted_at,
            "metrics":    metrics,
            "score":      score,
            "collected_at": datetime.now(JST).isoformat(),
        })
        added += 1

    if added > 0:
        save_to_github("data/feedback.json", feedback, f"feedback: collect {added} engagements")
        print(f"✅ {added}件のエンゲージメントを収集しました")
    else:
        print("新規収集なし")

if __name__ == "__main__":
    main()
