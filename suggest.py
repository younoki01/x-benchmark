import os
import json
import requests
from datetime import datetime, timedelta, timezone
from pathlib import Path

ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
SLACK_BOT_TOKEN   = os.environ["SLACK_BOT_TOKEN"]
SLACK_CHANNEL     = os.environ["SLACK_CHANNEL"]

JST = timezone(timedelta(hours=9))
DATA_FILE     = Path("data/tweets.json")
FEEDBACK_FILE = Path("data/feedback.json")

# ── キーワード設定 ────────────────────────────────────────
KEYWORDS        = ["転職", "キャリア相談", "面接対策", "エンジニア転職"]
EXPERT_KEYWORDS = ["キャリア設計", "自己分析", "就活テクニック"]
POST_COUNT = 3

def load_data() -> list:
    if not DATA_FILE.exists():
        return []
    with open(DATA_FILE, encoding="utf-8") as f:
        return json.load(f).get("tweets", [])

def load_feedback() -> dict:
    if not FEEDBACK_FILE.exists():
        return {}
    with open(FEEDBACK_FILE, encoding="utf-8") as f:
        return json.load(f)

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

def build_feedback_prompt(feedback: dict) -> str:
    sections = []
    posted = feedback.get("posted", [])
    high_posts = [p for p in posted if p.get("score") == "high"]
    if high_posts:
        examples = "\n".join([
            f"- {p['text'][:80]}（{p['platform']} いいね:{p['metrics'].get('like_count') or p['metrics'].get('likes',0)}）"
            for p in high_posts[-5:]
        ])
        sections.append(f"【過去の高パフォーマンス投稿（積極的に参考にしてください）】\n{examples}")

    skipped = [s for s in feedback.get("skipped", []) if s.get("score") == "low"]
    if skipped:
        from collections import Counter
        reasons = Counter(s["reason"] for s in skipped)
        reason_text = "\n".join([f"- {r}：{c}件" for r, c in reasons.most_common()])
        sections.append(f"【避けるべきパターン（スキップ理由より）】\n{reason_text}")

    return "\n\n".join(sections)

def generate_general_posts(tweets: list, feedback: dict) -> list:
    sorted_tweets = sorted(tweets, key=lambda x: x["metrics"].get("impression_count", 0), reverse=True)
    top_tweets = sorted_tweets[:10]

    examples = "\n".join([
        f"- [@{t['username']}] {t['text'][:100]}\n"
        f"  いいね:{t['metrics'].get('like_count',0)} IMP:{t['metrics'].get('impression_count',0):,}"
        for t in top_tweets
    ])

    feedback_prompt = build_feedback_prompt(feedback)
    keywords_str = "・".join(KEYWORDS)

    prompt = f"""以下はベンチマークアカウントの高パフォーマンス投稿データです。

{examples}

【投稿者プロフィール（参考程度に。毎回含める必要はない）】
- 1989年福岡県生まれ、東京から福岡に移住中
- アプリケーションエンジニア → データベースシステムコンサルタント → Windowsサポートエンジニア（現職）
- 副業：キャリアアドバイザー、プログラミングスクールメンター、人材紹介業
- 国家資格キャリアコンサルタント取得済み

【重要】投稿案は以下の口調・スタイルで書いてください：
- 一人称は「私」を使う
- ですます調で丁寧に書く
- エンジニアとキャリアコンサルタントの両方の視点を活かす
- プロフィールは頻繁に入れない
- 専門的だが親しみやすいトーン
- 適度に改行を入れて読みやすくする
- 短文版は140文字以内、長文版は480文字以内

{feedback_prompt}

キーワードごとに投稿案を作成してください。
キーワード：{keywords_str}

各キーワードについて：
- 【短文版】140文字以内 × {POST_COUNT}案
- 【長文版】480文字以内 × {POST_COUNT}案

以下の形式で返答してください：

===転職 短文1===
投稿内容

===転職 短文2===
投稿内容

===転職 長文1===
投稿内容

（以下同様）"""

    return _parse_posts(call_claude(prompt, max_tokens=4000))

def generate_expert_posts(feedback: dict) -> list:
    feedback_prompt = build_feedback_prompt(feedback)
    keywords_str = "・".join(EXPERT_KEYWORDS)

    prompt = f"""あなたは国家資格キャリアコンサルタントとして、専門的な知識に基づいた投稿案を作成してください。

【投稿者プロフィール】
- 国家資格キャリアコンサルタント取得済み
- アプリケーションエンジニア → データベースシステムコンサルタント → Windowsサポートエンジニア（現職）
- キャリアアドバイザー・人材紹介業の副業経験あり
- 1989年福岡県生まれ、東京から福岡に移住中

【重要】以下の専門家らしい口調・スタイルで書いてください：
- 一人称は「私」を使う
- ですます調で丁寧に、かつ専門家として自信を持った表現
- キャリアコンサルタントの理論・フレームワーク（自己概念、キャリアアンカー、SWOT等）を自然に盛り込む
- 具体的な数字・事例・体験談を入れてリアリティを出す
- 読者が「なるほど」と思えるインサイトを提供する
- 適度に改行を入れて読みやすくする
- 短文版は140文字以内、長文版は480文字以内

{feedback_prompt}

キーワードごとに投稿案を作成してください。
キーワード：{keywords_str}

各キーワードについて：
- 【短文版】140文字以内 × {POST_COUNT}案（専門知識をコンパクトに凝縮）
- 【長文版】480文字以内 × {POST_COUNT}案（理論・事例・アドバイスを盛り込んだ専門的な内容）

以下の形式で返答してください：

===キャリア設計 短文1===
投稿内容

===キャリア設計 短文2===
投稿内容

===キャリア設計 長文1===
投稿内容

（以下同様）"""

    return _parse_posts(call_claude(prompt, max_tokens=4000))

def _parse_posts(result: str) -> list:
    posts = []
    sections = result.split("===")
    for i in range(1, len(sections), 2):
        if i + 1 < len(sections):
            header  = sections[i].strip()
            content = sections[i + 1].strip()
            if not content:
                continue
            parts = header.rsplit(" ", 1)
            if len(parts) == 2:
                keyword = parts[0]
                ptype   = "短文" if "短文" in parts[1] else "長文"
            else:
                keyword = header
                ptype   = "投稿"
            posts.append({"keyword": keyword, "type": ptype, "text": content})

    if not posts:
        posts = [{"keyword": "全体", "type": "投稿案", "text": result}]

    return posts

def send_section_header(title: str, count: int):
    headers = {"Authorization": f"Bearer {SLACK_BOT_TOKEN}", "Content-Type": "application/json"}
    now_str = datetime.now(JST).strftime("%Y/%m/%d %H:%M")
    requests.post("https://slack.com/api/chat.postMessage", headers=headers, json={
        "channel": SLACK_CHANNEL,
        "text": f"*{title}（{now_str}）* {count}件 ↓"
    })

def send_post_to_slack(post: dict):
    headers = {"Authorization": f"Bearer {SLACK_BOT_TOKEN}", "Content-Type": "application/json"}
    keyword = post["keyword"]
    ptype   = post["type"]
    text    = post["text"]

    blocks = [
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*【{keyword}】{ptype}*\n{text}"}
        },
        {
            "type": "actions",
            "elements": [
                {"type": "button", "text": {"type": "plain_text", "text": "X + Threads"},
                 "style": "primary", "action_id": "post_to_both", "value": text},
                {"type": "button", "text": {"type": "plain_text", "text": "X のみ"},
                 "action_id": "post_to_x", "value": text},
                {"type": "button", "text": {"type": "plain_text", "text": "Threads のみ"},
                 "action_id": "post_to_threads", "value": text},
                {"type": "button", "text": {"type": "plain_text", "text": "編集して投稿"},
                 "action_id": "edit_and_post", "value": text},
            ]
        },
        {
            "type": "actions",
            "elements": [
                {"type": "button", "text": {"type": "plain_text", "text": "テーマが違う"},
                 "action_id": "skip_theme", "value": text},
                {"type": "button", "text": {"type": "plain_text", "text": "文体が合わない"},
                 "action_id": "skip_style", "value": text},
                {"type": "button", "text": {"type": "plain_text", "text": "内容が薄い"},
                 "action_id": "skip_thin", "value": text},
                {"type": "button", "text": {"type": "plain_text", "text": "事実が違う"},
                 "action_id": "skip_fact", "value": text},
                {"type": "button", "text": {"type": "plain_text", "text": "タイミングが違う"},
                 "action_id": "skip_timing", "value": text},
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

def main():
    print("▶ 投稿案生成 起動")
    tweets   = load_data()
    feedback = load_feedback()

    if not tweets:
        print("データがありません")
        return

    print(f"  蓄積データ: {len(tweets)}件")
    print(f"  フィードバック: 投稿済み{len(feedback.get('posted',[]))}件 スキップ{len(feedback.get('skipped',[]))}件")

    # 一般投稿案
    general_posts = generate_general_posts(tweets, feedback)
    print(f"  一般投稿案: {len(general_posts)}件")

    # 専門家投稿案
    expert_posts = generate_expert_posts(feedback)
    print(f"  専門家投稿案: {len(expert_posts)}件")

    # Slack送信：一般セクション
    send_section_header("✍️ 一般投稿案", len(general_posts))
    for post in general_posts:
        send_post_to_slack(post)

    # Slack送信：専門家セクション
    send_section_header("🎓 専門家投稿案", len(expert_posts))
    for post in expert_posts:
        send_post_to_slack(post)

    print("✅ Slack送信完了")

if __name__ == "__main__":
    main()
