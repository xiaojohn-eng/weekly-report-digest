#!/usr/bin/env python3
"""
情报雷达桥接器 — 从天工情报雷达获取本周行业动态，注入 CEO 简报

功能：
1. 查询情报雷达的 SQLite 数据库或 REST API
2. 提取本周高分情报（≥60分）
3. 生成"行业动态"段落供 CEO 简报使用
4. AI 交叉分析：行业情报 × 公司周报 → 战略建议

用法：
  python3 radar_bridge.py                    # 获取本周情报摘要
  python3 radar_bridge.py --cross-analyze    # 与周报交叉分析
"""
import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

try:
    import httpx
except ImportError:
    os.system(f"{sys.executable} -m pip install -q httpx")
    import httpx

RADAR_DIR = Path("/root/tgqb")
RADAR_DB = RADAR_DIR / "data" / "index" / "articles.db"
RADAR_API = "http://localhost:3030"
API_TOKEN = os.environ.get("API_TOKEN", "")

MEMORY_DIR = Path("/root/.openclaw/memory-weekly")
API_BASE = os.environ.get("MINIMAX_API_BASE", "https://api.minimaxi.com/v1")
API_KEY = os.environ.get("MINIMAX_API_KEY", "")


def query_db(days=7, min_score=60, limit=20):
    """直接查询 SQLite 数据库获取高分情报。"""
    if not RADAR_DB.exists():
        return []

    since = (datetime.now() - timedelta(days=days)).isoformat()
    conn = sqlite3.connect(str(RADAR_DB))
    conn.row_factory = sqlite3.Row

    try:
        rows = conn.execute("""
            SELECT title, source, score, priority, summary, tags, published_at
            FROM articles
            WHERE published_at >= ? AND score >= ?
            ORDER BY score DESC
            LIMIT ?
        """, (since, min_score, limit)).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        print(f"⚠️ DB 查询失败: {e}", file=sys.stderr)
        return []
    finally:
        conn.close()


def query_api(days=7, min_score=60, limit=20):
    """通过 REST API 查询情报。"""
    try:
        headers = {"Authorization": f"Bearer {API_TOKEN}"} if API_TOKEN else {}
        resp = httpx.get(
            f"{RADAR_API}/api/articles/search",
            params={"limit": limit, "min_score": min_score},
            headers=headers,
            timeout=10,
        )
        if resp.status_code == 200:
            return resp.json().get("articles", [])
    except Exception:
        pass
    return []


def get_weekly_intel(days=7):
    """获取本周情报，优先DB直查，fallback到API。"""
    articles = query_db(days=days)
    if not articles:
        articles = query_api(days=days)
    return articles


def format_intel_summary(articles):
    """格式化情报摘要（Markdown）。"""
    if not articles:
        return "本周无高分行业情报（情报雷达可能未运行）。"

    red = [a for a in articles if a.get("priority") == "red"]
    yellow = [a for a in articles if a.get("priority") == "yellow"]

    lines = []
    if red:
        lines.append("### 🔴 紧急情报")
        for a in red[:5]:
            lines.append(f"- **{a['title']}**（{a.get('source', '')}，{a.get('score', '')}分）")
            if a.get("summary"):
                lines.append(f"  > {a['summary'][:150]}")
    if yellow:
        lines.append("\n### 🟡 跟进情报")
        for a in yellow[:10]:
            lines.append(f"- **{a['title']}**（{a.get('source', '')}，{a.get('score', '')}分）")

    return "\n".join(lines)


def format_intel_html(articles):
    """格式化情报摘要（HTML，用于 CEO 简报注入）。"""
    if not articles:
        return ""

    BRAND = "#e05a2b"
    red = [a for a in articles if a.get("priority") == "red"]
    yellow = [a for a in articles if a.get("priority") == "yellow"]

    html = f'<h2 style="color:{BRAND};border-bottom:2px solid {BRAND};padding-bottom:8px;margin-top:25px;">🛰️ 行业情报动态</h2>'
    html += f'<p style="font-size:13px;color:#666;">来源：天工情报雷达 · 本周 {len(articles)} 条高分情报</p>'

    if red:
        html += '<h3 style="color:#dc3545;margin:12px 0 6px;">🔴 紧急情报</h3>'
        html += '<table style="width:100%;border-collapse:collapse;font-size:13px;">'
        html += '<tr style="background:#dc3545;color:#fff;"><th style="padding:6px;text-align:left;color:#fff !important;">标题</th><th style="padding:6px;text-align:left;color:#fff !important;">来源</th><th style="padding:6px;text-align:center;color:#fff !important;">评分</th></tr>'
        for a in red[:5]:
            html += f'<tr style="border-bottom:1px solid #eee;"><td style="padding:6px;">{a["title"][:60]}</td><td style="padding:6px;">{a.get("source","")}</td><td style="padding:6px;text-align:center;font-weight:bold;">{a.get("score","")}</td></tr>'
        html += '</table>'

    if yellow:
        html += '<h3 style="color:#ff8c00;margin:12px 0 6px;">🟡 跟进情报</h3><ul style="font-size:13px;">'
        for a in yellow[:8]:
            html += f'<li>{a["title"][:50]}（{a.get("source","")}，{a.get("score","")}分）</li>'
        html += '</ul>'

    return html


def cross_analyze(articles, weekly_reports_path=None):
    """AI 交叉分析：行业情报 × 公司周报。"""
    if not articles or not API_KEY:
        return None

    # 加载周报摘要
    report_context = ""
    if weekly_reports_path and Path(weekly_reports_path).exists():
        with open(weekly_reports_path, encoding="utf-8") as f:
            data = json.load(f)
        for r in data.get("reports", [])[:15]:
            report_context += f"【{r['sender_name']}】{r['body'][:300]}\n---\n"

    # 加载公司快照
    snapshot = ""
    snap_path = MEMORY_DIR / "company_snapshot.md"
    if snap_path.exists():
        snapshot = snap_path.read_text(encoding="utf-8")[:2000]

    intel_text = "\n".join(
        f"[{a.get('score','')}分/{a.get('priority','')}] {a['title']} - {a.get('summary','')[:200]}"
        for a in articles[:15]
    )

    system = """你是天工机器人CEO的战略顾问。结合行业情报和公司内部周报，做交叉分析。

输出 JSON：
{
  "strategic_alerts": [{"alert":"描述", "source":"情报/周报", "action":"建议"}],
  "opportunities": [{"opportunity":"机会", "evidence":"证据", "next_step":"下一步"}],
  "competitive_risks": [{"risk":"风险", "competitor":"竞品", "our_position":"我方现状"}],
  "summary": "一段话总结本周内外部形势"
}

要求：只输出有实质关联的分析，不要强行关联。"""

    user = f"""行业情报（本周）：
{intel_text}

---
公司内部周报摘要：
{report_context[:5000]}

---
公司背景：
{snapshot[:2000]}"""

    url = f"{API_BASE.rstrip('/').replace('/v1','')}/anthropic/v1/messages"
    headers = {"Content-Type": "application/json", "x-api-key": API_KEY, "anthropic-version": "2023-06-01"}
    payload = {"model": "MiniMax-M2.5", "max_tokens": 2000, "system": system, "messages": [{"role": "user", "content": user}]}

    try:
        resp = httpx.post(url, json=payload, headers=headers, timeout=90)
        resp.raise_for_status()
        for block in resp.json().get("content", []):
            if block.get("type") == "text":
                import re
                match = re.search(r'\{[\s\S]*\}', block["text"])
                if match:
                    return json.loads(match.group())
    except Exception as e:
        print(f"⚠️ 交叉分析失败: {e}", file=sys.stderr)

    return None


def main():
    parser = argparse.ArgumentParser(description="情报雷达桥接器")
    parser.add_argument("--cross-analyze", action="store_true", help="与周报交叉分析")
    parser.add_argument("--html", action="store_true", help="输出HTML格式")
    parser.add_argument("--json", action="store_true", help="输出JSON格式")
    args = parser.parse_args()

    print("🛰️ 获取本周行业情报...", file=sys.stderr)
    articles = get_weekly_intel()
    print(f"   找到 {len(articles)} 条高分情报", file=sys.stderr)

    if args.html:
        print(format_intel_html(articles))
    elif args.json:
        print(json.dumps(articles, ensure_ascii=False, indent=2))
    else:
        print(format_intel_summary(articles))

    if args.cross_analyze:
        print("\n🔀 内外交叉分析...", file=sys.stderr)
        result = cross_analyze(articles, "/tmp/weekly_reports.json")
        if result:
            print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
