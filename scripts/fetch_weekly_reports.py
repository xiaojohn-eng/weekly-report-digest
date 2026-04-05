#!/usr/bin/env python3
"""
从企业邮箱 IMAP 拉取指定周期的周报邮件，输出结构化 JSON。
用法:
  python3 fetch_weekly_reports.py                    # 本周（周一~现在）
  python3 fetch_weekly_reports.py --week last        # 上周
  python3 fetch_weekly_reports.py --since 2026-03-30 --until 2026-04-05
"""
import argparse
import imaplib
import email
import json
import os
import re
import sys
from datetime import datetime, timedelta
from email.header import decode_header
from email.utils import parsedate_to_datetime

try:
    from bs4 import BeautifulSoup
except ImportError:
    print("正在安装 beautifulsoup4 ...", file=sys.stderr)
    os.system(f"{sys.executable} -m pip install -q beautifulsoup4")
    from bs4 import BeautifulSoup


IMAP_HOST = os.environ.get("WEEKLY_IMAP_HOST", "imap.exmail.qq.com")
IMAP_PORT = int(os.environ.get("WEEKLY_IMAP_PORT", "993"))
IMAP_USER = os.environ.get("WEEKLY_IMAP_USER", "agent@tgkwrobot.com")
IMAP_PASS = os.environ.get("WEEKLY_IMAP_PASS", "")

# 周报关键词（主题匹配）
WEEKLY_KEYWORDS = re.compile(r"周报|weekly\s*report|week\s*\d+", re.IGNORECASE)
# 排除撤回邮件
REVOKE_PATTERN = re.compile(r"撤回邮件|已撤回")


def decode_mime(raw):
    parts = decode_header(raw or "")
    result = ""
    for part, enc in parts:
        if isinstance(part, bytes):
            result += part.decode(enc or "utf-8", errors="replace")
        else:
            result += part
    return result.strip()


def extract_body(msg):
    """提取邮件正文，优先 HTML → 纯文本。"""
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            if ct == "text/html":
                payload = part.get_payload(decode=True)
                charset = part.get_content_charset() or "utf-8"
                html = payload.decode(charset, errors="replace")
                soup = BeautifulSoup(html, "html.parser")
                body = soup.get_text(separator="\n", strip=True)
                break
            elif ct == "text/plain" and not body:
                payload = part.get_payload(decode=True)
                charset = part.get_content_charset() or "utf-8"
                body = payload.decode(charset, errors="replace")
    else:
        payload = msg.get_payload(decode=True)
        charset = msg.get_content_charset() or "utf-8"
        if msg.get_content_type() == "text/html":
            soup = BeautifulSoup(payload.decode(charset, errors="replace"), "html.parser")
            body = soup.get_text(separator="\n", strip=True)
        else:
            body = payload.decode(charset, errors="replace")
    # 清理签名块
    body = re.sub(r"(天下先智创机器人|发自我的企业微信)[\s\S]{0,200}$", "", body).strip()
    return body


def check_attachments(msg):
    """检查是否有附件（图片/文件）。"""
    attachments = []
    if msg.is_multipart():
        for part in msg.walk():
            disp = str(part.get("Content-Disposition") or "")
            if "attachment" in disp:
                fname = decode_mime(part.get_filename() or "")
                attachments.append(fname)
    return attachments


def parse_date_range(args):
    today = datetime.now()
    if args.since and args.until:
        since = datetime.strptime(args.since, "%Y-%m-%d")
        until = datetime.strptime(args.until, "%Y-%m-%d")
    elif args.week == "last":
        # 上周一到上周日
        days_since_monday = today.weekday()
        last_monday = today - timedelta(days=days_since_monday + 7)
        since = last_monday.replace(hour=0, minute=0, second=0)
        until = since + timedelta(days=6, hours=23, minutes=59, seconds=59)
    else:
        # 本周（周一到现在）
        days_since_monday = today.weekday()
        since = (today - timedelta(days=days_since_monday)).replace(hour=0, minute=0, second=0)
        until = today
    return since, until


def fetch_reports(since, until):
    imap = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
    imap.login(IMAP_USER, IMAP_PASS)
    imap.select("INBOX")

    since_str = since.strftime("%d-%b-%Y")
    until_str = (until + timedelta(days=1)).strftime("%d-%b-%Y")
    status, messages = imap.search(None, f'(SINCE "{since_str}" BEFORE "{until_str}")')

    if status != "OK" or not messages[0]:
        imap.logout()
        return []

    mail_ids = messages[0].split()
    reports = []

    for mid in mail_ids:
        status, msg_data = imap.fetch(mid, "(RFC822)")
        if status != "OK":
            continue
        msg = email.message_from_bytes(msg_data[0][1])

        subject = decode_mime(msg["Subject"])

        # 过滤：只保留周报 + 排除撤回
        if not WEEKLY_KEYWORDS.search(subject):
            continue
        if REVOKE_PATTERN.search(subject):
            continue

        from_raw = decode_mime(msg["From"])
        # 提取姓名和邮���
        name_match = re.match(r'"?([^"<]+)"?\s*<(.+?)>', from_raw)
        if name_match:
            sender_name = name_match.group(1).strip()
            sender_email = name_match.group(2).strip()
        else:
            sender_name = from_raw
            sender_email = from_raw

        try:
            date_obj = parsedate_to_datetime(msg["Date"])
            date_str = date_obj.strftime("%Y-%m-%d %H:%M")
        except Exception:
            date_str = msg.get("Date", "")

        body = extract_body(msg)
        attachments = check_attachments(msg)

        # 提取抄送
        cc = decode_mime(msg.get("Cc", ""))

        reports.append({
            "id": mid.decode(),
            "sender_name": sender_name,
            "sender_email": sender_email,
            "subject": subject,
            "date": date_str,
            "body": body,
            "attachments": attachments,
            "cc": cc,
        })

    imap.logout()
    return reports


def main():
    parser = argparse.ArgumentParser(description="拉取周报邮件")
    parser.add_argument("--week", choices=["this", "last"], default="this")
    parser.add_argument("--since", help="起始日期 YYYY-MM-DD")
    parser.add_argument("--until", help="截止日期 YYYY-MM-DD")
    parser.add_argument("--output", "-o", help="输出文件路径（默认 stdout）")
    args = parser.parse_args()

    since, until = parse_date_range(args)
    print(f"拉取周报范围: {since.strftime('%Y-%m-%d')} ~ {until.strftime('%Y-%m-%d')}", file=sys.stderr)

    reports = fetch_reports(since, until)
    print(f"共找到 {len(reports)} 封周报", file=sys.stderr)

    result = {
        "period": f"{since.strftime('%Y-%m-%d')} ~ {until.strftime('%Y-%m-%d')}",
        "fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "count": len(reports),
        "reports": reports,
    }

    output = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"已保存到 {args.output}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
