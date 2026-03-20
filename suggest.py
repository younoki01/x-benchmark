import os
import json
import requests
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ── 環境変数 ──────────────────────────────────────────────
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
SLACK_BOT_TOKEN   = os.environ["SLACK_BOT_TOKEN"]
SLACK_CHANNEL     = os.environ["SLACK_CHANNEL"]  # 例: #x-analytics

JST = timezone(timedelta(hours=9))
DATA_FILE = Path("data/tweets.json")

KEYWORDS = ["転職", "キャリア相談", "面接対策", "エンジニア転職"]
POST_COUNT = 3

# ── データ読み込み ────────────────────────────────────────
def load_data() -> list:
    if not DATA_FILE.exists():
        return []
    with open(DATA_FILE, encoding="utf-8") as f:
        return json.load(f).get("tweets", [])

# ── Claude API呼び出し ────────────────────────────────────
def call_claude(prompt: str, max_tokens: int = 4000) -> str:
    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    body = {
        "model": "claude-sonnet-4-20250514",
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }
    r = requests.post("https://api.anthropic.com/v1/messages", headers=headers, json=body)
    r.raise_for_status()
    return r.json()["content"][0]["text"]

# ── 投稿案生成 ────────────────────────────────────────────
def generate_posts(tweets: list) -> list:
    sorted_tweets = sorted(tweets, key=lambda x: x["metrics"].get("impression_count", 0), reverse=True)
    top_tweets = sorted_tweets[:10]

    examples = "\n".join([
        f"- [@{t['username']}] {t['text'][:100]}\n"
        f"  いいね:{t['metrics'].get('like_count',0)} IMP:{t['metrics'].get('impression_count',0):,}"
        for t in top_tweets
    ])

    keywords_str = "・".join(KEYWORDS)

    prompt = f"""以下はベンチマークアカウントの高パフォーマンス投稿データです。

{examples}

上記を参考に、キーワードごとに投稿案を作成してください。
キーワード：{keywords_str}

条件：
- キャリアコンサルタント・エンジニアの専門知識を活かした内容
- 各キーワードについて：
  【短文版】140文字以内 × {POST_COUNT}案
  【長文版】300〜400文字 × {POST_COUNT}案

必ずJSON形式のみで返答してください。以下の形式で：
{{
  "posts": [
    {{"keyword": "転職", "type": "短文", "text": "投稿内容"}},
    ...
  ]
}}"""

    result = call_claude(prompt)
    # JSON部分を抽出
    start = result.find("{")
    end = result.rfind("}") + 1
    return json.loads(result[start:end])["posts"]

# ── Slackにボタン付きメッセージ送信 ──────────────────────
def send_post_to_slack(post: dict):
    headers = {
        "Authorization": f"Bearer {SLACK_BOT_TOKEN}",
        "Content-Type": "application/json",
    }
    keyword = post["keyword"]
    ptype = post["type"]
    text = post["text"]

    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*【{keyword}】{ptype}*\n{text}"
            }
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "✅ 投稿する"},
                    "style": "primary",
                    "action_id": "post_to_x",
                    "value": text
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "⏭️ スキップ"},
                    "action_id": "skip_post",
                    "value": text
                }
            ]
        },
        {"type": "divider"}
    ]

    payload = {
        "channel": SLACK_CHANNEL,
        "text": f"【{keyword}】{ptype}の投稿案",
        "blocks": blocks
    }
    requests.post("https://slack.com/api/chat.postMessage", headers=headers, json=payload)

# ── メイン ────────────────────────────────────────────────
def main():
    print("▶ 投稿案生成 起動")
    tweets = load_data()

    if not tweets:
        print("データがありません")
        return

    print(f"  蓄積データ: {len(tweets)}件")
    posts = generate_posts(tweets)
    print(f"  生成投稿案: {len(posts)}件")

    now_str = datetime.now(JST).strftime("%Y/%m/%d %H:%M")
    # ヘッダーメッセージ
    headers = {
        "Authorization": f"Bearer {SLACK_BOT_TOKEN}",
        "Content-Type": "application/json",
    }
    requests.post("https://slack.com/api/chat.postMessage", headers=headers, json={
        "channel": SLACK_CHANNEL,
        "text": f"*✍️ 投稿案（{now_str}）* {len(posts)}件 ↓"
    })

    for post in posts:
        send_post_to_slack(post)

    print("✅ Slack送信完了")

if __name__ == "__main__":
    main()
