import os
import json
import requests
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ── 環境変数 ──────────────────────────────────────────────
X_BEARER_TOKEN = os.environ["X_BEARER_TOKEN"]
JST = timezone(timedelta(hours=9))

# ── ベンチマーク対象アカウント ────────────────────────────
BENCHMARK_ACCOUNTS = [
    {"username": "sayu5632j"},
    {"username": "iiGIANT"},
]

DATA_FILE = Path("data/tweets.json")

# ── X API: ユーザーIDを取得 ───────────────────────────────
def get_user_id(username: str) -> str:
    url = f"https://api.twitter.com/2/users/by/username/{username}"
    headers = {"Authorization": f"Bearer {X_BEARER_TOKEN}"}
    r = requests.get(url, headers=headers)
    r.raise_for_status()
    return r.json()["data"]["id"]

# ── X API: 前日のツイートを取得 ───────────────────────────
def get_yesterday_tweets(user_id: str) -> list:
    now = datetime.now(JST)
    yesterday_start = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday_end   = yesterday_start.replace(hour=23, minute=59, second=59)

    url = f"https://api.twitter.com/2/users/{user_id}/tweets"
    headers = {"Authorization": f"Bearer {X_BEARER_TOKEN}"}
    params = {
        "start_time": yesterday_start.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "end_time":   yesterday_end.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "tweet.fields": "public_metrics,created_at,text",
        "max_results": 100,
    }
    r = requests.get(url, headers=headers, params=params)
    r.raise_for_status()
    return r.json().get("data", [])

# ── 既存データの読み込み ──────────────────────────────────
def load_existing_data() -> dict:
    if DATA_FILE.exists():
        with open(DATA_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {"tweets": []}

# ── 差分のみ保存 ──────────────────────────────────────────
def save_diff(existing: dict, new_tweets: list, username: str) -> int:
    existing_ids = {t["id"] for t in existing["tweets"]}
    added = 0

    for tweet in new_tweets:
        if tweet["id"] not in existing_ids:
            existing["tweets"].append({
                "id": tweet["id"],
                "username": username,
                "text": tweet["text"],
                "created_at": tweet["created_at"],
                "metrics": tweet["public_metrics"],
                "collected_at": datetime.now(JST).isoformat(),
            })
            added += 1

    # 直近90日分のみ保持
    cutoff = (datetime.now(JST) - timedelta(days=90)).isoformat()
    existing["tweets"] = [t for t in existing["tweets"] if t["collected_at"] > cutoff]

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)

    return added

# ── メイン ────────────────────────────────────────────────
def main():
    print("▶ ベンチマーク収集 起動")
    existing = load_existing_data()
    total_added = 0

    for account in BENCHMARK_ACCOUNTS:
        username = account["username"]
        print(f"  @{username} 処理中...")
        user_id = get_user_id(username)
        tweets = get_yesterday_tweets(user_id)
        added = save_diff(existing, tweets, username)
        print(f"  @{username} 新規追加: {added}件 / 取得: {len(tweets)}件")
        total_added += added

    print(f"✅ 収集完了 合計新規追加: {total_added}件")
    print(f"   総蓄積件数: {len(existing['tweets'])}件")

if __name__ == "__main__":
    main()
