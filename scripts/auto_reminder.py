#!/usr/bin/env python3
"""
周五自动催报脚本 — cron 每周五 17:00 执行

流程：
1. 拉取本周已收到的周报
2. 对比花名册，找出未提交的人
3. 自动发催报邮件（不抄送 CEO）
4. 输出统计日志
"""
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent
CLAUDE_SCRIPTS = Path("/root/.claude/skills/weekly-report-digest/scripts")
MEMORY_DIR = Path("/root/.openclaw/memory-weekly")
SEND_SCRIPT = "/root/.claude/send_email.py"

def main():
    now = datetime.now()
    print(f"\n{'='*50}")
    print(f"  📢 周五自动催报 {now.strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*50}\n")

    # Step 1: 拉取本周周报
    print("📥 拉取本周周报...")
    subprocess.run([
        sys.executable, str(CLAUDE_SCRIPTS / "fetch_weekly_reports.py"),
        "--week", "this", "-o", "/tmp/weekly_reports.json"
    ], capture_output=True, timeout=120)

    if not Path("/tmp/weekly_reports.json").exists():
        print("❌ 拉取失败")
        return

    with open("/tmp/weekly_reports.json", encoding="utf-8") as f:
        data = json.load(f)

    submitters = set(r["sender_name"] for r in data["reports"])

    # Step 2: 加载花名册
    roster_path = MEMORY_DIR / "org" / "weekly_report_required.json"
    if not roster_path.exists():
        print("❌ 花名册不存在")
        return

    with open(roster_path, encoding="utf-8") as f:
        required = json.load(f)

    missing = [p for p in required if p["name"] not in submitters]

    # Load bounce log and skip previously bounced emails
    bounce_log = MEMORY_DIR / "org" / "bounce_log.json"
    bounced_names = set()
    if bounce_log.exists():
        try:
            _existing_bounces = json.loads(bounce_log.read_text(encoding="utf-8"))
            bounced_names = {b["name"] for b in _existing_bounces}
        except Exception:
            pass

    if bounced_names:
        bounced_missing = [p for p in missing if p["name"] in bounced_names]
        if bounced_missing:
            print(f"⚠️ 以下人员邮箱曾退信，跳过邮件催报（建议通过微信提醒）：")
            for p in bounced_missing:
                print(f"  - {p['name']} ({p.get('email', '')})")
        missing = [p for p in missing if p["name"] not in bounced_names]

    print(f"已提交: {len(required) - len(missing)}/{len(required)}")
    print(f"未提交: {len(missing)}/{len(required)}\n")

    if not missing:
        print("✅ 全员已提交，无需催报")
        return

    # Step 3: 发催报邮件（不抄送 CEO）
    subject = f"【周报提醒】请提交本周工作周报（{now.strftime('%m月%d日')}前）"
    body_template = """{name}，你好：

本周工作周报尚未收到，请于今天下班前提交。

发送至你的直属领导，并抄送 agent@tgkwrobot.com。

周报格式：
1. 本周问题风险、解决方案
2. 本周主要工作
3. 下周计划

如已提交但未抄送，请补发一份抄送即可。

—— AI 助理（自动提醒）"""

    sent = 0
    failed_list = []
    for p in missing:
        email = p.get("email", "")
        if not email or "@" not in email or any('\u4e00' <= c <= '\u9fff' for c in email.split("@")[0]):
            continue
        try:
            result = subprocess.run(
                [sys.executable, SEND_SCRIPT,
                 "--to", email,
                 "--subject", subject,
                 "--body", body_template.format(name=p["name"])],
                capture_output=True, text=True, timeout=15
            )
            if result.returncode == 0:
                sent += 1
            else:
                failed_list.append(p)
        except Exception:
            failed_list.append(p)
        time.sleep(0.3)

    print(f"\n📤 催报邮件已发送: {sent}/{len(missing)}")
    if failed_list:
        print(f"⚠️ 发送失败: {len(failed_list)} 人")

    # Save bounce/failure log
    import json as _json
    bounce_data = []
    if bounce_log.exists():
        try:
            bounce_data = _json.loads(bounce_log.read_text(encoding="utf-8"))
        except Exception:
            pass

    # Add new failures
    for p in failed_list:
        bounce_data.append({
            "name": p["name"],
            "email": p.get("email", ""),
            "date": datetime.now().isoformat(),
            "reason": "smtp_reject"
        })

    # Dedup by name
    seen = set()
    unique_bounces = []
    for b in bounce_data:
        if b["name"] not in seen:
            seen.add(b["name"])
            unique_bounces.append(b)

    bounce_log.parent.mkdir(parents=True, exist_ok=True)
    bounce_log.write_text(_json.dumps(unique_bounces, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"{'='*50}\n")


if __name__ == "__main__":
    main()
