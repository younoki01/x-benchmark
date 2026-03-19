import os
import requests
from datetime import datetime, timedelta, timezone

# ── 環境変数 ──────────────────────────────────────────────
X_BEARER_TOKEN    = os.environ["X_BEARER_TOKEN"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
SLACK_WEBHOOK_URL = os.environ["SLACK_WEBHOOK_URL"]

JST = timezone(timedelta(hours=9))

# ── ベンチマーク対象アカウント ────────────────────────────
BENCHMARK_ACCOUNTS = [
    {"username": "sayu5632j",  "user_id": None},
    {"username": "iiGIANT",    "user_id": None},
]

# ── 投稿案生成キーワード ──────────────────────────────────
KEYWORDS = ["転職", "キャリア相談", "面接対策", "エンジニア転職"]
POST_COUNT = 3  # キーワードごとの投稿案数

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

# ── Claude API呼び出し ────────────────────────────────────
def call_claude(prompt: str, max_tokens: int = 1500) -> str:
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

# ── 各アカウントの分析 ────────────────────────────────────
def analyze_account(username: str, tweets: list) -> str:
    if not tweets:
        return f"@{username}: 昨日の投稿はありませんでした。"

    tweet_summary = "\n".join([
        f"- [{t['created_at']}] {t['text'][:80]}{'...' if len(t['text'])>80 else ''}\n"
        f"  いいね:{t['public_metrics']['like_count']} RT:{t['public_metrics']['retweet_count']} "
        f"リプライ:{t['public_metrics']['reply_count']} インプレッション:{t['public_metrics']['impression_count']}"
        for t in tweets
    ])

    total_imp = sum(t['public_metrics']['impression_count'] for t in tweets)
    total_likes = sum(t['public_metrics']['like_count'] for t in tweets)

    prompt = f"""以下は@{username}の昨日のX投稿データです。

【集計】
- 投稿数: {len(tweets)}件
- 合計インプレッション: {total_imp:,}
- 合計いいね: {total_likes}

【投稿一覧】
{tweet_summary}

以下の形式で簡潔に分析してください：
- 最高パフォーマンス投稿（1件）とその理由
- 効果的だったコンテンツの傾向（1〜2点）"""

    return call_claude(prompt, max_tokens=800)

# ── アカウント比較分析 ────────────────────────────────────
def compare_accounts(accounts_data: list) -> str:
    summaries = "\n\n".join([
        f"【@{d['username']}】\n投稿数:{d['count']}件 / 合計インプレッション:{d['impressions']:,} / 合計いいね:{d['likes']}"
        for d in accounts_data
    ])

    prompt = f"""以下は複数のXアカウントの昨日のパフォーマンスデータです。

{summaries}

以下を簡潔に答えてください：
- 最もパフォーマンスが高いアカウントとその理由
- 共通して効果的だったテーマや傾向
- @Y0shiCareerアカウントへの示唆（1〜2点）"""

    return call_claude(prompt, max_tokens=600)

# ── 投稿案生成 ────────────────────────────────────────────
def generate_posts(top_tweets: list) -> str:
    examples = "\n".join([
        f"- {t['text'][:100]}（いいね:{t['public_metrics']['like_count']} IMP:{t['public_metrics']['impression_count']:,}）"
        for t in top_tweets[:5]
    ])

    keywords_str = "・".join(KEYWORDS)

    prompt = f"""以下はベンチマークアカウントの高パフォーマンス投稿例です。

{examples}

上記の投稿スタイル・構成を参考に、以下のキーワードそれぞれについて{POST_COUNT}件の投稿案を日本語で作成してください。
キーワード：{keywords_str}

条件：
- キャリアコンサルタント・エンジニアとしての専門知識を活かした内容
- 共感・驚き・具体的なアドバイスのいずれかを含む
- 140文字以内
- 各キーワードの投稿案は番号付きで

形式：
【転職】
1. ...
2. ...
3. ...

【キャリア相談】
...（以下同様）"""

    return call_claude(prompt, max_tokens=2000)

# ── Slack通知 ─────────────────────────────────────────────
def send_to_slack(text: str):
    payload = {"text": text}
    r = requests.post(SLACK_WEBHOOK_URL, json=payload)
    r.raise_for_status()

# ── メイン ────────────────────────────────────────────────
def main():
    print("▶ X ベンチマーク分析ツール 起動")
    today = datetime.now(JST).strftime("%Y/%m/%d")

    # ユーザーID取得
    for account in BENCHMARK_ACCOUNTS:
        account["user_id"] = get_user_id(account["username"])
        print(f"  @{account['username']} ID: {account['user_id']}")

    # 各アカウントのツイート取得・分析
    accounts_data = []
    account_reports = []
    all_tweets = []

    for account in BENCHMARK_ACCOUNTS:
        tweets = get_yesterday_tweets(account["user_id"])
        print(f"  @{account['username']} 取得ツイート数: {len(tweets)}")

        analysis = analyze_account(account["username"], tweets)
        account_reports.append(f"*【@{account['username']}】*\n{analysis}")

        if tweets:
            impressions = sum(t['public_metrics']['impression_count'] for t in tweets)
            likes = sum(t['public_metrics']['like_count'] for t in tweets)
            accounts_data.append({
                "username": account["username"],
                "count": len(tweets),
                "impressions": impressions,
                "likes": likes,
            })
            all_tweets.extend(tweets)

    # 比較分析
    comparison = compare_accounts(accounts_data) if len(accounts_data) > 1 else ""

    # 投稿案生成（インプレッション上位5件を参考に）
    top_tweets = sorted(all_tweets, key=lambda x: x['public_metrics']['impression_count'], reverse=True)[:5]
    post_suggestions = generate_posts(top_tweets) if top_tweets else "参考データが不足しています。"

    # Slackメッセージ組み立て
    message = f"""*📊 X ベンチマークレポート（{today}）*

{chr(10).join(account_reports)}

*【比較インサイト】*
{comparison}

━━━━━━━━━━━━━━━
*✍️ 今日の投稿案*
{post_suggestions}"""

    send_to_slack(message)
    print("✅ Slack通知送信完了")

if __name__ == "__main__":
    main()
