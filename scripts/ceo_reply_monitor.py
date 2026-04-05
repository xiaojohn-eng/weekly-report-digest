#!/usr/bin/env python3
"""
CEO 邮件回复闭环 — 监听 CEO 对简报的回复，AI 回答后自动邮件回复

流程：
1. IMAP 扫描来自 shaw@tgkwrobot.com 的邮件
2. 识别是否是对周报简报的追问
3. 从周报原文 + 知识库中查找答案
4. 调用 AI 生成回答
5. 自动回复邮件

用法：
  python3 ceo_reply_monitor.py          # 扫描并处理
  python3 ceo_reply_monitor.py --once   # 只处理最新一封
"""
import argparse
import email
import imaplib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta
from email.header import decode_header
from pathlib import Path

try:
    from bs4 import BeautifulSoup
except ImportError:
    os.system(f"{sys.executable} -m pip install -q beautifulsoup4")
    from bs4 import BeautifulSoup

try:
    import httpx
except ImportError:
    os.system(f"{sys.executable} -m pip install -q httpx")
    import httpx

IMAP_HOST = "imap.exmail.qq.com"
IMAP_PORT = 993
IMAP_USER = "agent@tgkwrobot.com"
IMAP_PASS = os.environ.get("WEEKLY_IMAP_PASS", "")
CEO_EMAIL = "shaw@tgkwrobot.com"
SEND_SCRIPT = "/root/.claude/send_email.py"
MEMORY_DIR = Path("/root/.openclaw/memory-weekly")
PROCESSED_FILE = MEMORY_DIR / "org" / "processed_replies.json"

API_BASE = os.environ.get("MINIMAX_API_BASE", "https://api.minimaxi.com/v1")
API_KEY = os.environ.get("MINIMAX_API_KEY", "")


def decode_mime(raw):
    parts = decode_header(raw or "")
    result = ""
    for part, enc in parts:
        if isinstance(part, bytes):
            result += part.decode(enc or "utf-8", errors="replace")
        else:
            result += part
    return result.strip()


def get_body(msg):
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            if ct == "text/plain":
                payload = part.get_payload(decode=True)
                charset = part.get_content_charset() or "utf-8"
                body = payload.decode(charset, errors="replace")
                break
            elif ct == "text/html" and not body:
                payload = part.get_payload(decode=True)
                charset = part.get_content_charset() or "utf-8"
                soup = BeautifulSoup(payload.decode(charset, errors="replace"), "html.parser")
                body = soup.get_text(separator="\n", strip=True)
    else:
        payload = msg.get_payload(decode=True)
        charset = msg.get_content_charset() or "utf-8"
        body = payload.decode(charset, errors="replace")
    return body


def load_processed():
    if PROCESSED_FILE.exists():
        try:
            return set(json.loads(PROCESSED_FILE.read_text(encoding="utf-8")))
        except Exception:
            pass
    return set()


def save_processed(ids):
    PROCESSED_FILE.parent.mkdir(parents=True, exist_ok=True)
    PROCESSED_FILE.write_text(json.dumps(list(ids), ensure_ascii=False), encoding="utf-8")


def load_company_context():
    """加载公司知识上下文。"""
    context_parts = []

    # 公司快照
    snapshot = MEMORY_DIR / "company_snapshot.md"
    if snapshot.exists():
        context_parts.append(snapshot.read_text(encoding="utf-8")[:3000])

    # 最新 AI 分析
    digests = MEMORY_DIR / "digests"
    if digests.exists():
        ai_files = sorted(digests.glob("*_ai.json"), reverse=True)
        if ai_files:
            try:
                ai_data = json.loads(ai_files[0].read_text(encoding="utf-8"))
                context_parts.append(f"最新AI分析：{json.dumps(ai_data.get('insights', {}), ensure_ascii=False)[:2000]}")
            except Exception:
                pass

    # 最新周报原文
    if Path("/tmp/weekly_reports.json").exists():
        try:
            with open("/tmp/weekly_reports.json") as f:
                data = json.load(f)
            for r in data.get("reports", [])[:20]:
                context_parts.append(f"【{r['sender_name']}】{r['body'][:500]}")
        except Exception:
            pass

    return "\n\n---\n\n".join(context_parts)


def call_llm(system, user_msg):
    url = f"{API_BASE.rstrip('/').replace('/v1','')}/anthropic/v1/messages"
    headers = {
        "Content-Type": "application/json",
        "x-api-key": API_KEY,
        "anthropic-version": "2023-06-01",
    }
    payload = {
        "model": "MiniMax-M2.5",
        "max_tokens": 2000,
        "system": system,
        "messages": [{"role": "user", "content": user_msg}],
    }
    try:
        resp = httpx.post(url, json=payload, headers=headers, timeout=60)
        resp.raise_for_status()
        for block in resp.json().get("content", []):
            if block.get("type") == "text":
                return block["text"]
    except Exception as e:
        return f"AI 回复生成失败: {e}"
    return "无法生成回复"


def generate_reply(question, context):
    system = """你是天下先智创机器人 CEO 的 AI 助理。CEO 对周报简报有追问，请基于公司知识库回答。

要求：
- 直接回答问题，不要废话
- 引用具体数据和人员
- 如果信息不足，明确说"周报中未提及"
- 中文回答
- 简洁但完整"""

    user = f"""CEO 的追问：{question}

---
公司知识上下文：
{context[:10000]}"""

    return call_llm(system, user)


def send_reply(to, subject, body):
    reply_subject = f"Re: {subject}" if not subject.startswith("Re:") else subject
    try:
        result = subprocess.run(
            [sys.executable, SEND_SCRIPT,
             "--to", to,
             "--subject", reply_subject,
             "--body", body],
            capture_output=True, text=True, timeout=15
        )
        return result.returncode == 0
    except Exception:
        return False


def scan_and_reply():
    processed = load_processed()

    imap = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
    imap.login(IMAP_USER, IMAP_PASS)
    imap.select("INBOX")

    # 搜索最近3天来自 CEO 的邮件
    since = (datetime.now() - timedelta(days=3)).strftime("%d-%b-%Y")
    status, messages = imap.search(None, f'(FROM "{CEO_EMAIL}" SINCE "{since}")')

    if status != "OK" or not messages[0]:
        print("无新邮件", file=sys.stderr)
        imap.logout()
        return

    mail_ids = messages[0].split()
    replied = 0

    for mid in mail_ids:
        mid_str = mid.decode()
        if mid_str in processed:
            continue

        status, msg_data = imap.fetch(mid, "(RFC822)")
        msg = email.message_from_bytes(msg_data[0][1])

        subject = decode_mime(msg["Subject"])
        body = get_body(msg)

        # 跳过非追问邮件（比如自己发的催报回复等）
        if not any(kw in subject.lower() for kw in ["周报", "简报", "re:", "回复"]):
            processed.add(mid_str)
            continue

        # 提取追问内容（回复邮件通常在开头）
        question = body.split("---")[0].split("发自我的")[0].strip()[:500]
        if len(question) < 5:
            processed.add(mid_str)
            continue

        print(f"\n📧 CEO 追问: {subject}", file=sys.stderr)
        print(f"   问题: {question[:100]}...", file=sys.stderr)

        # 加载知识 + AI 回答
        context = load_company_context()
        answer = generate_reply(question, context)

        reply_body = f"""军哥好，

关于你的追问，以下是基于本周周报和公司知识库的回答：

{answer}

---
如需更多细节，可以继续回复此邮件或在企微上问我。

—— AI 助理
天下先智创机器人"""

        if send_reply(CEO_EMAIL, subject, reply_body):
            print(f"   ✅ 已回复", file=sys.stderr)
            replied += 1
        else:
            print(f"   ❌ 回复失败", file=sys.stderr)

        processed.add(mid_str)

    save_processed(processed)
    imap.logout()
    print(f"\n处理完成: 回复 {replied} 封", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description="CEO 邮件回复闭环")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    scan_and_reply()


if __name__ == "__main__":
    main()
