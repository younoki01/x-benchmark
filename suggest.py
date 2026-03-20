import os
import json
import requests
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ── 環境変数 ──────────────────────────────────────────────
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
SLACK_WEBHOOK_URL = os.environ["SLACK_WEBHOOK_URL"]

JST = timezone(timedelta(hours=9))
DATA_FILE = Path("data/tweets.json")

# ── 投稿案生成キーワード ──────────────────────────────────
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
def generate_posts(tweets: list) -> str:
    # インプレッション上位10件を参考に
    sorted_tweets = sorted(tweets, key=lambda x: x["metrics"].get("impression_count", 0), reverse=True)
    top_tweets = sorted_tweets[:10]

    examples = "\n".join([
        f"- [@{t['username']}] {t['text'][:100]}\n"
        f"  いいね:{t['metrics'].get('like_count',0)} RT:{t['metrics'].get('retweet_count',0)} "
        f"IMP:{t['metrics'].get('impression_count',0):,}"
        for t in top_tweets
    ])

    keywords_str = "・".join(KEYWORDS)
    now_str = datetime.now(JST).strftime("%Y/%m/%d %H:%M")

    prompt = f"""以下はベンチマークアカウントの高パフォーマンス投稿データです（蓄積データより上位10件）。

{examples}

上記の投稿スタイル・構成を参考に、以下のキーワードそれぞれについて投稿案を日本語で作成してください。
キーワード：{keywords_str}

条件：
- キャリアコンサルタント・エンジニアとしての専門知識を活かした内容
- 共感・驚き・具体的なアドバイスのいずれかを含む
- 各キーワードについて以下の2パターンを{POST_COUNT}案ずつ作成：
  【短文版】140文字以内（日常的なつぶやき・共感系）
  【長文版】300〜400文字（知識・体験談・具体的アドバイス系）

形式：
【転職】
＜短文版＞
1. ...
2. ...
3. ...

＜長文版＞
1. ...
2. ...
3. ...

【キャリア相談】
...（以下同様）"""

    return call_claude(prompt)

# ── Slack通知 ─────────────────────────────────────────────
def send_to_slack(text: str):
    payload = {"text": text}
    r = requests.post(SLACK_WEBHOOK_URL, json=payload)
    r.raise_for_status()

# ── メイン ────────────────────────────────────────────────
def main():
    print("▶ 投稿案生成 起動")
    tweets = load_data()

    if not tweets:
        print("データがありません")
        send_to_slack("⚠️ 投稿案生成: データが蓄積されていません。収集ワークフローを確認してください。")
        return

    print(f"  蓄積データ: {len(tweets)}件")
    suggestions = generate_posts(tweets)

    now_str = datetime.now(JST).strftime("%Y/%m/%d %H:%M")
    message = f"*✍️ 投稿案（{now_str}）*\n蓄積データ {len(tweets)}件より生成\n\n{suggestions}"

    send_to_slack(message)
    print("✅ Slack通知送信完了")

if __name__ == "__main__":
    main()
